"""Build the Team 4 live Supabase recommender v2 smoke-test notebook."""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks" / "team4_recommender_supabase_smoke_gui.ipynb"
CELLS = [
    (
        "markdown",
        "# Team 4 Recommender v2 Live Supabase Smoke Test GUI\n\n"
        "Run the cell below. It will show an interactive v2 questionnaire UI, load live Supabase data, "
        "call `recommender_v2.py`, and display the top recommendations.\n\n"
        "If `Persist smoke-test session to Supabase` is checked, it will insert one `guest_tracker` row, "
        "the selected `users_response` rows, three `model_recommendation` rows, three "
        "`model_recommendation_trace` rows, and one `recommender_v2_feedback_response` row "
        "for the generated session ID.\n\n"
        "Prerequisites: `SUPABASE_DB_URL` in your shell or repo-root `.env.local`, plus `pandas`, "
        "`psycopg`, and `ipywidgets` installed in the notebook kernel."
    ),
    (
        "markdown",
        "## Notes\n\n"
        "- This notebook is strict v2: it expects live `answer_option_scoring_metadata` and `program_profile_v2` tables.\n"
        "- Responses are written using `option_id` and the v2 question rows (`V2Q01`-`V2Q29`).\n"
        "- If persistence is enabled, the notebook writes real smoke-test rows to live Supabase for the displayed session ID.\n"
        "- Persisted sessions should appear in `recommender_v2_session_completeness` with 29 responses, 3 traces, 1 feedback row, and `session_complete = true`.\n"
        "- To clean a persisted smoke-test run, delete that session ID from `recommender_v2_feedback_response`, `model_recommendation_trace`, `model_recommendation`, `users_response`, and `guest_tracker`."
    ),
    (
        "code",
        """
from __future__ import annotations

import os
import sys
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

import ipywidgets as widgets
import pandas as pd
import psycopg
from IPython.display import HTML, Markdown, clear_output, display


def find_repo_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "analysis" / "team4_model" / "recommender_v2.py").exists():
            return candidate
    raise RuntimeError("Could not find GabayPoz repo root. Start Jupyter from the repo or notebooks directory.")


REPO = find_repo_root()
ENV_LOCAL = REPO / ".env.local"
sys.path.insert(0, str(REPO / "analysis" / "team4_model"))

from recommender_v2 import MODEL_ID, recommend_programs
from supabase_v2 import QUESTION_ORDER, filter_program_profile_v2, normalize_v2_questions, resolve_selected_option_rows


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
        raise RuntimeError("SUPABASE_DB_URL is missing. Add it to your shell or repo-root .env.local.")
    return value


def connect():
    return psycopg.connect(db_url(), connect_timeout=15)


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
}


def read_table(conn, table_name: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(f'select * from public."{table_name}"')
        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]
    return pd.DataFrame(rows, columns=columns)


def load_live_data() -> dict[str, pd.DataFrame]:
    with connect() as conn:
        data = {name: read_table(conn, table) for name, table in TABLES.items()}
    data["questions_scoring"] = normalize_v2_questions(
        data["questions"],
        data["answer_options"],
        data["scoring_metadata"],
    )
    data["program_profile_v2"] = filter_program_profile_v2(data["program_profile_v2"])
    return data


live = load_live_data()


def option_display(row: pd.Series) -> str:
    return f"{row['option_label']}. {row['option_text']}"


question_widgets: dict[str, widgets.Widget] = {}
question_titles: dict[str, str] = {}
for qid in QUESTION_ORDER:
    rows = live["questions_scoring"][live["questions_scoring"]["question_id"] == qid].copy()
    rows = rows.sort_values("display_order")
    if rows.empty:
        raise RuntimeError(f"No seeded answer options found for {qid}.")
    options = [(option_display(row), str(row["option_label"])) for _, row in rows.iterrows()]
    question_widgets[qid] = widgets.Dropdown(
        options=options,
        value=options[0][1],
        description=qid,
        layout=widgets.Layout(width="100%"),
        style={"description_width": "56px"},
    )
    question_titles[qid] = str(rows.iloc[0]["question_text"])


barangays = live["barangays"].sort_values(["barangay_name"]).copy()
barangay_options = [
    (f"{row['barangay_name']} ({row.get('municipality_name', 'Pozorrubio')})", str(row["barangay_id"]))
    for _, row in barangays.iterrows()
]
barangay_widget = widgets.Dropdown(
    options=barangay_options,
    description="Barangay",
    layout=widgets.Layout(width="100%"),
    style={"description_width": "84px"},
)
persist_widget = widgets.Checkbox(value=True, description="Persist smoke-test session to Supabase", indent=False)
session_widget = widgets.Text(value=str(uuid.uuid4()), description="Session", layout=widgets.Layout(width="100%"), style={"description_width": "84px"})
refresh_session_button = widgets.Button(description="New session", icon="refresh")
run_button = widgets.Button(description="Run recommender", icon="play", button_style="primary")
output = widgets.Output()

feedback_relevance_widget = widgets.IntSlider(value=4, min=1, max=5, step=1, description="Relevance", style={"description_width": "104px"})
feedback_acceptance_widget = widgets.Dropdown(
    options=[
        ("A. I would consider the rank-1 program", "A"),
        ("B. I would consider another recommendation", "B"),
        ("C. Useful, but I would not choose these", "C"),
        ("D. Not useful for me", "D"),
        ("E. I am unsure", "E"),
    ],
    value="A",
    description="Acceptance",
    layout=widgets.Layout(width="100%"),
    style={"description_width": "104px"},
)
feedback_pre_confidence_widget = widgets.IntSlider(value=3, min=1, max=5, step=1, description="Pre-conf.", style={"description_width": "104px"})
feedback_post_confidence_widget = widgets.IntSlider(value=4, min=1, max=5, step=1, description="Post-conf.", style={"description_width": "104px"})
feedback_followup_widget = widgets.Checkbox(value=False, description="Follow-up consent", indent=False)


def selected_responses() -> dict[str, str]:
    return {qid: str(widget.value) for qid, widget in question_widgets.items()}


def persist_guest_and_responses(conn, session_id: str, responses: dict[str, str]) -> None:
    now = datetime.now(timezone.utc)
    selected = resolve_selected_option_rows(responses, live["questions_scoring"])
    with conn.cursor() as cur:
        cur.execute(
            \"\"\"
            insert into public.guest_tracker (session_id, is_completed, start_datetime, end_datetime)
            values (%s, true, %s, %s)
            on conflict (session_id) do update set
                is_completed = excluded.is_completed,
                end_datetime = excluded.end_datetime
            \"\"\",
            (session_id, now, now),
        )
        cur.executemany(
            \"\"\"
            insert into public.users_response (response_id, session_id, question_id, option_id, created_datetime)
            values (%(response_id)s, %(session_id)s, %(question_id)s, %(option_id)s, %(created_datetime)s)
            \"\"\",
            [
                {
                    "response_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "question_id": row["question_id"],
                    "option_id": row["option_id"],
                    "created_datetime": now,
                }
                for row in selected
            ],
        )


def persist_recommendations_and_trace(conn, result: dict) -> None:
    now = datetime.now(timezone.utc)
    recommendations = result["model_recommendation_rows"]
    traces = result["model_recommendation_trace_rows"]
    recommendation_ids = [str(uuid.uuid4()) for _ in recommendations]
    with conn.cursor() as cur:
        cur.executemany(
            \"\"\"
            insert into public.model_recommendation (
                recommendation_id, session_id, program_id, model_score, created_datetime, rank, model_id, university_id
            )
            values (
                %(recommendation_id)s, %(session_id)s, %(program_id)s, %(model_score)s, %(created_datetime)s, %(rank)s, %(model_id)s, %(university_id)s
            )
            \"\"\",
            [
                {**row, "recommendation_id": recommendation_ids[idx], "created_datetime": now}
                for idx, row in enumerate(recommendations)
            ],
        )
        cur.executemany(
            \"\"\"
            insert into public.model_recommendation_trace (
                trace_id, recommendation_id, session_id, model_id, rank, program_id,
                construct_scores, constraints, warnings, explanation_json, created_datetime
            )
            values (
                %(trace_id)s, %(recommendation_id)s, %(session_id)s, %(model_id)s, %(rank)s, %(program_id)s,
                %(construct_scores)s::jsonb, %(constraints)s::jsonb, %(warnings)s::jsonb, %(explanation_json)s::jsonb, %(created_datetime)s
            )
            \"\"\",
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
                for idx, row in enumerate(traces)
            ],
        )


def persist_feedback(conn, session_id: str, result: dict) -> None:
    now = datetime.now(timezone.utc)
    top = result["recommendations"][0]
    acceptance_choice = str(feedback_acceptance_widget.value)
    would_consider_any = acceptance_choice in {"A", "B"}
    with conn.cursor() as cur:
        cur.execute(
            \"\"\"
            insert into public.recommender_v2_feedback_response (
                feedback_id, session_id, model_id, relevance_score, acceptance_choice,
                would_consider_any, pre_confidence, post_confidence, stated_choice_program,
                stated_choice_field, followup_consent, created_datetime, updated_datetime
            )
            values (
                %(feedback_id)s, %(session_id)s, %(model_id)s, %(relevance_score)s, %(acceptance_choice)s,
                %(would_consider_any)s, %(pre_confidence)s, %(post_confidence)s, %(stated_choice_program)s,
                %(stated_choice_field)s, %(followup_consent)s, %(created_datetime)s, %(updated_datetime)s
            )
            on conflict (session_id, model_id) do update set
                relevance_score = excluded.relevance_score,
                acceptance_choice = excluded.acceptance_choice,
                would_consider_any = excluded.would_consider_any,
                pre_confidence = excluded.pre_confidence,
                post_confidence = excluded.post_confidence,
                stated_choice_program = excluded.stated_choice_program,
                stated_choice_field = excluded.stated_choice_field,
                followup_consent = excluded.followup_consent,
                updated_datetime = excluded.updated_datetime
            \"\"\",
            {
                "feedback_id": str(uuid.uuid4()),
                "session_id": session_id,
                "model_id": MODEL_ID,
                "relevance_score": int(feedback_relevance_widget.value),
                "acceptance_choice": acceptance_choice,
                "would_consider_any": would_consider_any,
                "pre_confidence": int(feedback_pre_confidence_widget.value),
                "post_confidence": int(feedback_post_confidence_widget.value),
                "stated_choice_program": top["program_name"],
                "stated_choice_field": top["program_profile"].get("dominant_dim"),
                "followup_consent": bool(feedback_followup_widget.value),
                "created_datetime": now,
                "updated_datetime": now,
            },
        )


def read_completeness(conn, session_id: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(
            \"\"\"
            select session_id, model_id, questionnaire_response_count, trace_row_count, feedback_row_count, session_complete
            from public.recommender_v2_session_completeness
            where session_id = %s and model_id = %s
            \"\"\",
            (session_id, MODEL_ID),
        )
        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]
    return pd.DataFrame(rows, columns=columns)


def result_table(result: dict) -> pd.DataFrame:
    rows = []
    for rec in result.get("recommendations", []):
        primary = rec["primary_school"]
        rows.append(
            {
                "rank": rec["rank"],
                "program": rec["program_name"],
                "primary_school": primary.get("university_name"),
                "score": rec["program_score"],
                "dominant_dim": rec["program_profile"].get("dominant_dim"),
                "commute_mins": primary.get("commute_time_mins"),
                "annual_burden_php": primary.get("total_annual_burden_php"),
                "scholarships": primary.get("scholarship_count", 0),
            }
        )
    return pd.DataFrame(rows)


def render_result(result: dict, session_id: str, persisted: bool, completeness: pd.DataFrame | None = None) -> None:
    if result.get("status") != "ok":
        display(Markdown(f"### Failed: `{result.get('error_code')}`"))
        display(Markdown(str(result.get("message", ""))))
        return
    display(Markdown(f"### Result: `{result['status']}`"))
    display(Markdown(f"Model: `{result.get('model_id', MODEL_ID)}`  \\nSession: `{session_id}`  \\nPersisted: `{persisted}`"))
    display(result_table(result))
    if completeness is not None and not completeness.empty:
        display(Markdown("### Completeness View"))
        display(completeness)
    top = result["recommendations"][0]
    display(Markdown("### Rank 1 Explanation"))
    display(Markdown(top["explanation_text"]))
    display(Markdown("### Rank 1 Program Profile"))
    display(pd.DataFrame([top["program_profile"]]).T.rename(columns={0: "value"}))
    display(Markdown("### Constraints Applied"))
    display(pd.DataFrame([top["constraints_applied"]]).T.rename(columns={0: "value"}))
    if result.get("warnings"):
        display(Markdown("### Warnings"))
        display(pd.DataFrame({"warning": result["warnings"]}))


def refresh_session(_=None):
    session_widget.value = str(uuid.uuid4())


def run_smoke_test(_=None):
    with output:
        clear_output()
        session_id = session_widget.value.strip() or str(uuid.uuid4())
        session_widget.value = session_id
        responses = selected_responses()
        persist = bool(persist_widget.value)
        try:
            completeness = None
            with connect() as conn:
                if persist:
                    persist_guest_and_responses(conn, session_id, responses)
                result = recommend_programs(
                    session_id=session_id,
                    student_barangay_id=str(barangay_widget.value),
                    student_responses=responses,
                    guest_tracker=pd.DataFrame([{"session_id": session_id, "is_completed": True}]),
                    barangay_location=live["barangays"],
                    questions=live["questions_scoring"],
                    programs=live["programs"],
                    university_programs=live["university_programs"],
                    universities=live["universities"],
                    commute_matrix=live["commute_matrix"],
                    economic_burden=live["economic_burden"],
                    scholarship=live["scholarship"],
                    dimension_scholarship=live["dimension_scholarship"],
                    municipality_field_saturation=live["saturation"],
                    program_profile_v2=live["program_profile_v2"],
                )
                if persist and result.get("status") == "ok":
                    persist_recommendations_and_trace(conn, result)
                    persist_feedback(conn, session_id, result)
                    completeness = read_completeness(conn, session_id)
                    conn.commit()
            render_result(result, session_id, persist, completeness)
        except Exception as exc:
            display(Markdown("### Smoke test crashed"))
            display(HTML(f"<pre>{type(exc).__name__}: {exc}</pre>"))


refresh_session_button.on_click(refresh_session)
run_button.on_click(run_smoke_test)

summary = pd.DataFrame([{"frame": key, "rows": len(value), "columns": len(value.columns)} for key, value in live.items()]).sort_values("frame").reset_index(drop=True)
question_controls = []
for qid in QUESTION_ORDER:
    title = widgets.HTML(f"<b>{question_titles[qid]}</b>")
    question_controls.extend([title, question_widgets[qid]])

app = widgets.VBox([
    widgets.HTML(f"<h2>GabayPoz recommender v2 smoke test</h2><p><b>Model:</b> {MODEL_ID}<br><b>Source:</b> analysis/team4_model/recommender_v2.py</p>"),
    widgets.Accordion(children=[widgets.Output()], titles=("Loaded Supabase tables",)),
    barangay_widget,
    *question_controls,
    widgets.HTML("<h3>Smoke feedback</h3>"),
    feedback_relevance_widget,
    feedback_acceptance_widget,
    widgets.HBox([feedback_pre_confidence_widget, feedback_post_confidence_widget]),
    feedback_followup_widget,
    widgets.HBox([persist_widget, refresh_session_button]),
    session_widget,
    run_button,
    output,
])
with app.children[1].children[0]:
    display(summary)

display(app)
""",
    ),
]


nb = nbf.v4.new_notebook()
for cell_type, source in CELLS:
    if cell_type == "markdown":
        nb.cells.append(nbf.v4.new_markdown_cell(source))
    elif cell_type == "code":
        nb.cells.append(nbf.v4.new_code_cell(source))
    else:
        raise ValueError(f"Unsupported cell type: {cell_type}")

nb.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "pygments_lexer": "ipython3"},
}
nbf.write(nb, OUT)
print(f"Wrote {OUT}")
