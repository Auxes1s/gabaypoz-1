"""Export and optionally seed the deterministic GabayPoz recommender v2 data.

v2 is side-by-side with the v1.2 questionnaire. It preserves the same final
six affinity outputs, but each scoring item is a construct-tagged Likert item:
two interest indicators and two self-efficacy indicators per field.

When used with live Supabase, this script can:
* execute the owner-side migration SQL (if the DB role permits it);
* upsert v2 `questions`, `answer_option`, and `answer_option_scoring_metadata`;
* upsert `program_profile_v2`;
* verify live row counts for the strict v2 contract.
"""
from __future__ import annotations

import argparse
import csv
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    import psycopg
except ImportError:  # pragma: no cover - exercised manually when missing
    psycopg = None


REPO = Path(__file__).resolve().parents[2]
ENV_LOCAL = REPO / ".env.local"
OUTPUT_DIR = REPO / "data" / "processed" / "team4_model" / "supabase_seed"
PROGRAM_PROFILE_PATH = REPO / "data" / "processed" / "team4_model" / "program_profile_v2.csv"
MIGRATION_SQL = REPO / "docs" / "reports" / "model" / "team4_recommender_v2_supabase_migration.sql"
NAMESPACE = uuid.UUID("54d5fc37-8627-4d50-b0df-4d58c64ed9aa")
MODEL_ID = "tds_recommender_v2"
NOW = datetime(2026, 5, 16, tzinfo=UTC)

DIMS = ["stem", "health", "arts", "business", "education", "agriculture"]
LIKERT_OPTIONS = [
    ("1", "Not like me", 1),
    ("2", "Slightly like me", 2),
    ("3", "Somewhat like me", 3),
    ("4", "Very like me", 4),
    ("5", "Strongly like me", 5),
]


@dataclass(frozen=True)
class V2Question:
    code: str
    text: str
    construct_family: str
    target_field: str

    @property
    def question_id(self) -> uuid.UUID:
        return uuid.uuid5(NAMESPACE, f"{MODEL_ID}:question:{self.code}")


def v2_questions() -> list[V2Question]:
    specs = {
        "stem": [
            ("domain_interest", "I would enjoy building, coding, repairing, or testing how things work."),
            ("domain_interest", "I like activities that involve numbers, experiments, tools, or technology."),
            ("domain_self_efficacy", "I can learn technical or scientific ideas if I practice them step by step."),
            ("domain_self_efficacy", "I am confident solving problems that involve math, logic, or systems."),
        ],
        "health": [
            ("domain_interest", "I would enjoy learning how to care for people's health and safety."),
            ("domain_interest", "I am interested in biology, medicine, first aid, or community health work."),
            ("domain_self_efficacy", "I can stay careful and calm when helping someone with a health concern."),
            ("domain_self_efficacy", "I am confident following detailed procedures that protect people's well-being."),
        ],
        "arts": [
            ("domain_interest", "I would enjoy creating, writing, performing, designing, or producing media."),
            ("domain_interest", "I like activities where I can express ideas in original or visual ways."),
            ("domain_self_efficacy", "I can improve creative work after feedback and revision."),
            ("domain_self_efficacy", "I am confident presenting ideas through words, images, performance, or design."),
        ],
        "business": [
            ("domain_interest", "I would enjoy planning, selling, budgeting, managing, or starting a venture."),
            ("domain_interest", "I like activities involving money decisions, customers, teams, or operations."),
            ("domain_self_efficacy", "I can organize tasks and persuade people toward a practical goal."),
            ("domain_self_efficacy", "I am confident making decisions using costs, benefits, and tradeoffs."),
        ],
        "education": [
            ("domain_interest", "I would enjoy explaining lessons, tutoring classmates, or guiding younger learners."),
            ("domain_interest", "I like helping people understand ideas and grow through patient support."),
            ("domain_self_efficacy", "I can explain a difficult topic clearly to someone who is still learning."),
            ("domain_self_efficacy", "I am confident leading discussions or learning activities for a group."),
        ],
        "agriculture": [
            ("domain_interest", "I would enjoy work connected to farming, food production, animals, or natural resources."),
            ("domain_interest", "I like practical outdoor or community work that improves land, crops, or livelihood."),
            ("domain_self_efficacy", "I can learn hands-on methods for growing, producing, or managing resources."),
            ("domain_self_efficacy", "I am confident solving practical problems in farms, food systems, or local enterprises."),
        ],
    }
    rows: list[V2Question] = []
    idx = 1
    for field in DIMS:
        for family, text in specs[field]:
            rows.append(V2Question(f"V2Q{idx:02d}", text, family, field))
            idx += 1
    rows.extend(
        [
            V2Question("V2Q25", "What is your current Senior High School (SHS) strand?", "context", "strand"),
            V2Question("V2Q26", "What is your household financial situation?", "constraint", "financial"),
            V2Question("V2Q27", "How do you plan to get to school every day?", "constraint", "mobility"),
            V2Question(
                "V2Q28",
                "How do you feel about programs that require 5+ years of study or heavy board exam preparation?",
                "constraint",
                "duration",
            ),
            V2Question(
                "V2Q29",
                "Do you plan to pursue a graduate professional degree after completing your bachelor's program?",
                "aspiration",
                "professional_track",
            ),
        ]
    )
    return rows


def question_rows() -> list[dict[str, object]]:
    return [
        {
            "question_id": str(q.question_id),
            "question_code": q.code,
            "question_text": f"{q.code}. {q.text}",
            "model_id": MODEL_ID,
            "construct_family": q.construct_family,
            "target_field": q.target_field,
            "created_datetime": NOW.isoformat(),
            "updated_datetime": NOW.isoformat(),
        }
        for q in v2_questions()
    ]


def option_rows() -> list[dict[str, object]]:
    rows = []
    questions = {q.code: q for q in v2_questions()}
    for q in v2_questions():
        if q.code <= "V2Q24":
            options = LIKERT_OPTIONS
        elif q.code == "V2Q25":
            options = [("A", "STEM", 0), ("B", "ABM", 0), ("C", "HUMSS", 0), ("D", "TVL", 0), ("E", "GAS", 0)]
        elif q.code == "V2Q26":
            options = [
                ("A", "Extremely limited; needs very low cost options.", 0),
                ("B", "Can afford reasonable tuition fees.", 0),
                ("C", "More flexible budget; can consider higher-cost options.", 0),
            ]
        elif q.code == "V2Q27":
            options = [
                ("A", "I need a school within 30-45 minutes of Pozorrubio.", 0),
                ("B", "I am okay with traveling 1-2 hours.", 0),
                ("C", "I am willing to stay in a dorm or boarding house.", 0),
            ]
        elif q.code == "V2Q28":
            options = [
                ("A", "I am ready for the challenge.", 0),
                ("B", "I prefer a 4-year program with no board exam.", 0),
                ("C", "I want the fastest path to a job.", 0),
            ]
        else:  # V2Q29
            options = [
                ("A", "Medicine (MD) — I plan to enter medical school.", 0),
                ("B", "Dentistry (DMD) — I plan to enter dental school.", 0),
                ("C", "Law (JD/LLB) — I plan to enter law school.", 0),
                ("D", "No / Not sure yet — I will decide based on what I enjoy.", 0),
            ]
        for display_order, (label, text, response_value) in enumerate(options, start=1):
            option_id = uuid.uuid5(NAMESPACE, f"{MODEL_ID}:option:{q.code}:{label}")
            legacy_group = (
                "internal" if q.code <= "V2Q24"
                else "aptitude" if q.construct_family == "context"
                else "aspiration" if q.construct_family == "aspiration"
                else "constraint"
            )
            rows.append(
                {
                    "option_id": str(option_id),
                    "question_id": str(questions[q.code].question_id),
                    "question_code": q.code,
                    "option_label": label,
                    "option_text": text,
                    "score_stem": 0.0,
                    "score_health": 0.0,
                    "score_arts": 0.0,
                    "score_business": 0.0,
                    "score_education": 0.0,
                    "score_agri": 0.0,
                    "question_group": legacy_group,
                    "display_order": display_order,
                    "created_datetime": NOW.isoformat(),
                    "updated_datetime": NOW.isoformat(),
                }
            )
    return rows


def scoring_metadata_rows() -> list[dict[str, object]]:
    questions = {q.code: q for q in v2_questions()}
    rows = []
    for option in option_rows():
        q = questions[option["question_code"]]
        response_value = int(option["option_label"]) if q.code <= "V2Q24" else None
        rows.append(
            {
                "option_id": option["option_id"],
                "question_id": option["question_id"],
                "question_code": option["question_code"],
                "model_id": MODEL_ID,
                "construct_family": q.construct_family,
                "target_field": q.target_field,
                "response_value": response_value,
                "reverse_scored": False,
                "scoring_type": "likert" if q.code <= "V2Q24" else q.construct_family,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]], columns: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)


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
        raise SystemExit("Missing dependency: psycopg. Install it with `python3 -m pip install psycopg[binary]`.")
    return psycopg.connect(db_url(), connect_timeout=15)


def program_profile_rows() -> list[dict[str, object]]:
    if not PROGRAM_PROFILE_PATH.exists():
        raise SystemExit(f"Missing required file: {PROGRAM_PROFILE_PATH}")
    df = pd.read_csv(PROGRAM_PROFILE_PATH)
    return df.where(pd.notna(df), None).to_dict(orient="records")


def export_seed_files() -> None:
    write_csv(
        OUTPUT_DIR / "questions_seed_v2.csv",
        question_rows(),
        [
            "question_id",
            "question_code",
            "question_text",
            "model_id",
            "construct_family",
            "target_field",
            "created_datetime",
            "updated_datetime",
        ],
    )
    write_csv(
        OUTPUT_DIR / "answer_option_seed_v2.csv",
        option_rows(),
        [
            "option_id",
            "question_id",
            "question_code",
            "option_label",
            "option_text",
            "score_stem",
            "score_health",
            "score_arts",
            "score_business",
            "score_education",
            "score_agri",
            "question_group",
            "display_order",
            "created_datetime",
            "updated_datetime",
        ],
    )
    write_csv(
        OUTPUT_DIR / "answer_option_scoring_metadata_seed_v2.csv",
        scoring_metadata_rows(),
        [
            "option_id",
            "question_id",
            "question_code",
            "model_id",
            "construct_family",
            "target_field",
            "response_value",
            "reverse_scored",
            "scoring_type",
        ],
    )


def apply_migration() -> None:
    if not MIGRATION_SQL.exists():
        raise SystemExit(f"Missing migration SQL: {MIGRATION_SQL}")
    sql = MIGRATION_SQL.read_text(encoding="utf-8")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
    print(f"Applied migration SQL: {MIGRATION_SQL}")


def apply_seed() -> None:
    q_rows = question_rows()
    o_rows = option_rows()
    meta_rows = scoring_metadata_rows()
    profile_rows = program_profile_rows()
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            insert into public.questions (
                question_id, question_code, question_text, model_id, construct_family, target_field, created_datetime, updated_datetime
            )
            values (
                %(question_id)s, %(question_code)s, %(question_text)s, %(model_id)s, %(construct_family)s, %(target_field)s, %(created_datetime)s, %(updated_datetime)s
            )
            on conflict (question_id) do update set
                question_code = excluded.question_code,
                question_text = excluded.question_text,
                model_id = excluded.model_id,
                construct_family = excluded.construct_family,
                target_field = excluded.target_field,
                updated_datetime = excluded.updated_datetime
            """,
            q_rows,
        )
        cur.executemany(
            """
            insert into public.answer_option (
                option_id, question_id, question_code, option_label, option_text,
                score_stem, score_health, score_arts, score_business, score_education, score_agri,
                question_group, display_order, created_datetime, updated_datetime
            )
            values (
                %(option_id)s, %(question_id)s, %(question_code)s, %(option_label)s, %(option_text)s,
                %(score_stem)s, %(score_health)s, %(score_arts)s, %(score_business)s, %(score_education)s, %(score_agri)s,
                %(question_group)s, %(display_order)s, %(created_datetime)s, %(updated_datetime)s
            )
            on conflict (option_id) do update set
                question_id = excluded.question_id,
                question_code = excluded.question_code,
                option_label = excluded.option_label,
                option_text = excluded.option_text,
                score_stem = excluded.score_stem,
                score_health = excluded.score_health,
                score_arts = excluded.score_arts,
                score_business = excluded.score_business,
                score_education = excluded.score_education,
                score_agri = excluded.score_agri,
                question_group = excluded.question_group,
                display_order = excluded.display_order,
                updated_datetime = excluded.updated_datetime
            """,
            o_rows,
        )
        cur.executemany(
            """
            insert into public.answer_option_scoring_metadata (
                option_id, question_id, question_code, model_id, construct_family, target_field,
                response_value, reverse_scored, scoring_type
            )
            values (
                %(option_id)s, %(question_id)s, %(question_code)s, %(model_id)s, %(construct_family)s, %(target_field)s,
                %(response_value)s, %(reverse_scored)s, %(scoring_type)s
            )
            on conflict (option_id) do update set
                question_id = excluded.question_id,
                question_code = excluded.question_code,
                model_id = excluded.model_id,
                construct_family = excluded.construct_family,
                target_field = excluded.target_field,
                response_value = excluded.response_value,
                reverse_scored = excluded.reverse_scored,
                scoring_type = excluded.scoring_type
            """,
            meta_rows,
        )
        cur.executemany(
            """
            insert into public.program_profile_v2 (
                program_id, program_name, program_code, profile_version, profile_method, profile_confidence,
                profile_family, dominant_dim, dominant_dim_label, secondary_dims, evidence_text, evidence_sources,
                review_status, occupation_bridge_confidence, occupation_bridge_p21_groups, occupation_bridge_p21_labels,
                affinity_stem_score, current_stem_score, template_stem_score,
                affinity_health_score, current_health_score, template_health_score,
                affinity_arts_score, current_arts_score, template_arts_score,
                affinity_business_score, current_business_score, template_business_score,
                affinity_education_score, current_education_score, template_education_score,
                affinity_agriculture_score, current_agriculture_score, template_agriculture_score,
                affinity_duration_score
            )
            values (
                %(program_id)s, %(program_name)s, %(program_code)s, %(profile_version)s, %(profile_method)s, %(profile_confidence)s,
                %(profile_family)s, %(dominant_dim)s, %(dominant_dim_label)s, %(secondary_dims)s, %(evidence_text)s, %(evidence_sources)s,
                %(review_status)s, %(occupation_bridge_confidence)s, %(occupation_bridge_p21_groups)s, %(occupation_bridge_p21_labels)s,
                %(affinity_stem_score)s, %(current_stem_score)s, %(template_stem_score)s,
                %(affinity_health_score)s, %(current_health_score)s, %(template_health_score)s,
                %(affinity_arts_score)s, %(current_arts_score)s, %(template_arts_score)s,
                %(affinity_business_score)s, %(current_business_score)s, %(template_business_score)s,
                %(affinity_education_score)s, %(current_education_score)s, %(template_education_score)s,
                %(affinity_agriculture_score)s, %(current_agriculture_score)s, %(template_agriculture_score)s,
                %(affinity_duration_score)s
            )
            on conflict (program_id) do update set
                program_name = excluded.program_name,
                program_code = excluded.program_code,
                profile_version = excluded.profile_version,
                profile_method = excluded.profile_method,
                profile_confidence = excluded.profile_confidence,
                profile_family = excluded.profile_family,
                dominant_dim = excluded.dominant_dim,
                dominant_dim_label = excluded.dominant_dim_label,
                secondary_dims = excluded.secondary_dims,
                evidence_text = excluded.evidence_text,
                evidence_sources = excluded.evidence_sources,
                review_status = excluded.review_status,
                occupation_bridge_confidence = excluded.occupation_bridge_confidence,
                occupation_bridge_p21_groups = excluded.occupation_bridge_p21_groups,
                occupation_bridge_p21_labels = excluded.occupation_bridge_p21_labels,
                affinity_stem_score = excluded.affinity_stem_score,
                current_stem_score = excluded.current_stem_score,
                template_stem_score = excluded.template_stem_score,
                affinity_health_score = excluded.affinity_health_score,
                current_health_score = excluded.current_health_score,
                template_health_score = excluded.template_health_score,
                affinity_arts_score = excluded.affinity_arts_score,
                current_arts_score = excluded.current_arts_score,
                template_arts_score = excluded.template_arts_score,
                affinity_business_score = excluded.affinity_business_score,
                current_business_score = excluded.current_business_score,
                template_business_score = excluded.template_business_score,
                affinity_education_score = excluded.affinity_education_score,
                current_education_score = excluded.current_education_score,
                template_education_score = excluded.template_education_score,
                affinity_agriculture_score = excluded.affinity_agriculture_score,
                current_agriculture_score = excluded.current_agriculture_score,
                template_agriculture_score = excluded.template_agriculture_score,
                affinity_duration_score = excluded.affinity_duration_score
            """,
            profile_rows,
        )
        conn.commit()
    print(
        f"Seeded {len(q_rows)} questions, {len(o_rows)} answer options, "
        f"{len(meta_rows)} scoring metadata rows, and {len(profile_rows)} program profiles."
    )


def rollback_seed() -> None:
    q_rows = question_rows()
    o_rows = option_rows()
    meta_rows = scoring_metadata_rows()
    profile_rows = program_profile_rows()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("delete from public.answer_option_scoring_metadata where option_id = any(%s)", ([row["option_id"] for row in meta_rows],))
        deleted_meta = cur.rowcount
        cur.execute("delete from public.answer_option where option_id = any(%s)", ([row["option_id"] for row in o_rows],))
        deleted_options = cur.rowcount
        cur.execute("delete from public.questions where question_id = any(%s)", ([row["question_id"] for row in q_rows],))
        deleted_questions = cur.rowcount
        cur.execute("delete from public.program_profile_v2 where program_id = any(%s)", ([row["program_id"] for row in profile_rows],))
        deleted_profiles = cur.rowcount
        conn.commit()
    print(
        f"Deleted {deleted_questions} questions, {deleted_options} answer options, "
        f"{deleted_meta} scoring metadata rows, and {deleted_profiles} program profiles."
    )


def verify_live_counts() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select count(*) from public.questions where model_id = %s", (MODEL_ID,))
        questions_count = cur.fetchone()[0]
        cur.execute("select count(*) from public.answer_option_scoring_metadata where model_id = %s", (MODEL_ID,))
        meta_count = cur.fetchone()[0]
        cur.execute(
            """
            select count(*)
            from public.answer_option ao
            join public.questions q on q.question_id = ao.question_id
            where q.model_id = %s
            """,
            (MODEL_ID,),
        )
        options_count = cur.fetchone()[0]
        cur.execute("select count(*) from public.program_profile_v2")
        profile_count = cur.fetchone()[0]
    print(f"Live v2 questions: {questions_count}")
    print(f"Live v2 answer options: {options_count}")
    print(f"Live v2 scoring metadata: {meta_count}")
    print(f"Live program_profile_v2 rows: {profile_count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export and/or seed v2 recommender data.")
    parser.add_argument("--export", action="store_true", help="Write deterministic v2 seed CSVs locally.")
    parser.add_argument("--migrate", action="store_true", help="Apply the owner-side v2 migration SQL to live Supabase.")
    parser.add_argument("--apply", action="store_true", help="Upsert v2 questions, options, scoring metadata, and program profiles to live Supabase.")
    parser.add_argument("--rollback", action="store_true", help="Delete the deterministic v2 seed rows and program profiles from live Supabase.")
    parser.add_argument("--verify", action="store_true", help="Print live counts for the v2 seed/profile tables.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not any([args.export, args.migrate, args.apply, args.rollback, args.verify]):
        raise SystemExit("Choose at least one action: --export, --migrate, --apply, --rollback, or --verify.")
    if args.export:
        export_seed_files()
        print(f"Wrote v2 seed CSVs to {OUTPUT_DIR}")
    if args.migrate:
        apply_migration()
    if args.rollback:
        rollback_seed()
    if args.apply:
        apply_seed()
    if args.verify:
        verify_live_counts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
