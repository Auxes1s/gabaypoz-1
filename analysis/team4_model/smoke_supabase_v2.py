"""Live Supabase smoke test for the strict v2 recommender contract.

This script uses SUPABASE_DB_URL from the shell or repo-root .env.local,
verifies that the required v2 tables/columns exist, loads live data, runs one
non-persisting recommendation call, and optionally performs a rollback-only
write check against the recommendation tables.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


REPO = Path(__file__).resolve().parents[2]
ENV_LOCAL = REPO / ".env.local"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from recommender_v2 import MODEL_ID, recommend_programs
from supabase_v2 import QUESTION_ORDER, filter_program_profile_v2, normalize_v2_questions, resolve_selected_option_rows


TABLES = {
    "questions": "questions",
    "answer_options": "answer_option",
    "scoring_metadata": "answer_option_scoring_metadata",
    "barangays": "barangay_location",
    "programs": "program",
    "program_profile_v2": "program_profile_v2",
    "universities": "university",
    "university_programs": "university_program",
    "commute_matrix": "barangay_university_commute_matrix",
    "economic_burden": "barangay_university_economic_burden",
    "scholarship": "scholarship",
    "dimension_scholarship": "dimension_scholarship",
    "saturation": "municipality_field_saturation",
    "model_recommendation": "model_recommendation",
    "model_recommendation_trace": "model_recommendation_trace",
    "feedback_response": "recommender_v2_feedback_response",
    "session_completeness": "recommender_v2_session_completeness",
    "guest_tracker": "guest_tracker",
    "users_response": "users_response",
}


def load_env_local() -> None:
    if not ENV_LOCAL.exists():
        return
    for raw_line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def db_url() -> str:
    load_env_local()
    value = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not value:
        raise SystemExit("SUPABASE_DB_URL is missing. Set it in your shell or .env.local.")
    return value


def connect():
    if psycopg is None:
        raise SystemExit("Missing dependency: psycopg.")
    return psycopg.connect(db_url(), connect_timeout=15)


def read_table(conn, table_name: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(f'select * from public."{table_name}"')
        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]
    return pd.DataFrame(rows, columns=columns)


def check_table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s)", (f"public.{table_name}",))
        row = cur.fetchone()
    return bool(row and row[0])


def schema_summary(conn) -> dict[str, bool]:
    summary = {name: check_table_exists(conn, table) for name, table in TABLES.items()}
    missing = [table for table, ok in summary.items() if not ok]
    print("Schema check:")
    for table, ok in summary.items():
        print(f"  {TABLES[table]}: {'ok' if ok else 'missing'}")
    if missing:
        print(f"Missing required table(s): {', '.join(TABLES[name] for name in missing)}")
    return summary


def load_live_data(conn) -> dict[str, pd.DataFrame]:
    excluded = {
        "model_recommendation",
        "model_recommendation_trace",
        "feedback_response",
        "session_completeness",
        "guest_tracker",
        "users_response",
    }
    data = {name: read_table(conn, table) for name, table in TABLES.items() if name not in excluded}
    data["questions_scoring"] = normalize_v2_questions(
        data["questions"],
        data["answer_options"],
        data["scoring_metadata"],
    )
    data["program_profile_v2"] = filter_program_profile_v2(data["program_profile_v2"])
    return data


def default_responses() -> dict[str, str]:
    responses = {}
    for idx in range(1, 25):
        qid = f"V2Q{idx:02d}"
        if idx <= 4:
            responses[qid] = "5"
        elif idx <= 8:
            responses[qid] = "3"
        else:
            responses[qid] = "1"
    responses.update(
        {
            "V2Q25": "A",
            "V2Q26": "B",
            "V2Q27": "B",
            "V2Q28": "B",
            "V2Q29": "D",
        }
    )
    return responses


def select_barangay_id(barangays: pd.DataFrame, override: str | None) -> str:
    if override:
        return override
    if barangays.empty:
        raise RuntimeError("barangay_location is empty.")
    return str(barangays.iloc[0]["barangay_id"])


def run_recommendation(data: dict[str, pd.DataFrame], barangay_id: str, session_id: str) -> dict:
    return recommend_programs(
        session_id=session_id,
        student_barangay_id=barangay_id,
        student_responses=default_responses(),
        guest_tracker=pd.DataFrame([{"session_id": session_id, "is_completed": True}]),
        barangay_location=data["barangays"],
        questions=data["questions_scoring"],
        programs=data["programs"],
        university_programs=data["university_programs"],
        universities=data["universities"],
        commute_matrix=data["commute_matrix"],
        economic_burden=data["economic_burden"],
        scholarship=data["scholarship"],
        dimension_scholarship=data["dimension_scholarship"],
        municipality_field_saturation=data["saturation"],
        program_profile_v2=data["program_profile_v2"],
    )


def print_result_summary(result: dict) -> None:
    print(f"Model: {result.get('model_id')}")
    print(f"Status: {result.get('status')}")
    if result.get("status") != "ok":
        print(f"Error code: {result.get('error_code')}")
        print(f"Message: {result.get('message')}")
        return
    print(f"Warnings: {result.get('warnings')}")
    for rec in result["recommendations"]:
        primary = rec["primary_school"]
        print(
            f"  rank {rec['rank']}: {rec['program_name']} -> {primary.get('university_name')} "
            f"(score={rec['program_score']:.6f})"
        )


def write_check(conn, data: dict[str, pd.DataFrame], result: dict, session_id: str) -> None:
    if result.get("status") != "ok":
        raise RuntimeError("Cannot run write check on a failed recommendation result.")
    now = datetime.now(timezone.utc)
    responses = default_responses()
    selected_rows = resolve_selected_option_rows(responses, data["questions_scoring"])
    recommendation_ids = [str(uuid.uuid4()) for _ in result["model_recommendation_rows"]]
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into public.guest_tracker (session_id, is_completed, start_datetime, end_datetime)
            values (%s, true, %s, %s)
            on conflict (session_id) do update set
                is_completed = excluded.is_completed,
                end_datetime = excluded.end_datetime
            """,
            (session_id, now, now),
        )
        cur.executemany(
            """
            insert into public.users_response (response_id, session_id, question_id, option_id, created_datetime)
            values (%(response_id)s, %(session_id)s, %(question_id)s, %(option_id)s, %(created_datetime)s)
            """,
            [
                {
                    "response_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "question_id": row["question_id"],
                    "option_id": row["option_id"],
                    "created_datetime": now,
                }
                for row in selected_rows
            ],
        )
        cur.executemany(
            """
            insert into public.model_recommendation (
                recommendation_id, session_id, program_id, model_score, created_datetime, rank, model_id, university_id
            )
            values (
                %(recommendation_id)s, %(session_id)s, %(program_id)s, %(model_score)s, %(created_datetime)s, %(rank)s, %(model_id)s, %(university_id)s
            )
            """,
            [
                {**row, "recommendation_id": recommendation_ids[idx], "created_datetime": now}
                for idx, row in enumerate(result["model_recommendation_rows"])
            ],
        )
        cur.executemany(
            """
            insert into public.model_recommendation_trace (
                trace_id, recommendation_id, session_id, model_id, rank, program_id,
                construct_scores, constraints, warnings, explanation_json, created_datetime
            )
            values (
                %(trace_id)s, %(recommendation_id)s, %(session_id)s, %(model_id)s, %(rank)s, %(program_id)s,
                %(construct_scores)s::jsonb, %(constraints)s::jsonb, %(warnings)s::jsonb, %(explanation_json)s::jsonb, %(created_datetime)s
            )
            """,
            [
                {
                    "trace_id": str(uuid.uuid4()),
                    "recommendation_id": recommendation_ids[idx],
                    "session_id": row["session_id"],
                    "model_id": row["model_id"],
                    "rank": row["rank"],
                    "program_id": row["program_id"],
                    "construct_scores": json.dumps(row["construct_scores"]),
                    "constraints": json.dumps(row["constraints"]),
                    "warnings": json.dumps(row["warnings"]),
                    "explanation_json": json.dumps(row["explanation_json"]),
                    "created_datetime": now,
                }
                for idx, row in enumerate(result["model_recommendation_trace_rows"])
            ],
        )
        cur.execute(
            """
            insert into public.recommender_v2_feedback_response (
                feedback_id, session_id, model_id, relevance_score, acceptance_choice,
                would_consider_any, pre_confidence, post_confidence, stated_choice_program,
                stated_choice_field, followup_consent, created_datetime, updated_datetime
            )
            values (%s, %s, %s, 4, 'A', true, 3, 4, %s, %s, false, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                session_id,
                MODEL_ID,
                result["recommendations"][0]["program_name"],
                result["recommendations"][0]["program_profile"]["dominant_dim"],
                now,
                now,
            ),
        )
        cur.execute(
            """
            select questionnaire_response_count, trace_row_count, feedback_row_count, session_complete
            from public.recommender_v2_session_completeness
            where session_id = %s and model_id = %s
            """,
            (session_id, MODEL_ID),
        )
        completeness = cur.fetchone()
        if completeness is None:
            raise RuntimeError("Completeness view did not return the smoke session.")
        response_count, trace_count, feedback_count, session_complete = completeness
        print(
            "Completeness before rollback: "
            f"responses={response_count}, traces={trace_count}, feedback={feedback_count}, "
            f"complete={session_complete}"
        )
        if response_count < 29 or trace_count < 3 or feedback_count < 1 or not session_complete:
            raise RuntimeError("Rollback-only write check did not satisfy the v2 completeness contract.")
    conn.rollback()
    print("Rollback-only write check: ok")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live Supabase smoke test for GabayPoz recommender v2.")
    parser.add_argument("--barangay-id", help="Optional explicit live barangay_id to use.")
    parser.add_argument(
        "--write-check",
        action="store_true",
        help=(
            "Attempt rollback-only writes to guest_tracker, users_response, "
            "model_recommendation, model_recommendation_trace, and v2 feedback."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_id = str(uuid.uuid4())
    print(f"Smoke label: supabase-v2-smoke-{session_id}")
    with connect() as conn:
        summary = schema_summary(conn)
        if not all(summary.values()):
            raise SystemExit("Required v2 schema pieces are missing. Apply the owner-side migration first.")
        data = load_live_data(conn)
        barangay_id = select_barangay_id(data["barangays"], args.barangay_id)
        print(f"Selected barangay_id: {barangay_id}")
        print(f"Loaded rows: questions={len(data['questions_scoring'])}, profiles={len(data['program_profile_v2'])}")
        result = run_recommendation(data, barangay_id, session_id)
        print_result_summary(result)
        if result.get("status") != "ok":
            raise SystemExit(1)
        if args.write_check:
            write_check(conn, data, result, session_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
