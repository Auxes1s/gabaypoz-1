"""Supabase-shaped contract tests for the v2 recommender pipeline."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recommender_v2 import recommend_programs
from supabase_v2 import MODEL_ID, normalize_v2_questions, resolve_selected_option_rows


REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw" / "supabase_exports"
SEED = REPO / "data" / "processed" / "team4_model" / "supabase_seed"
PROCESSED = REPO / "data" / "processed" / "team4_model"


def _load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _live_frames() -> dict[str, pd.DataFrame]:
    questions = _load_csv(SEED / "questions_seed_v2.csv")
    answer_options = _load_csv(SEED / "answer_option_seed_v2.csv")
    scoring_metadata = _load_csv(SEED / "answer_option_scoring_metadata_seed_v2.csv")
    barangays = _load_csv(RAW / "barangay_location.csv")
    universities = _load_csv(RAW / "university.csv")
    economic_burden = pd.read_parquet(PROCESSED / "barangay_university_economic_burden.parquet")
    barangay_lookup = barangays[["barangay_id", "barangay_name"]].copy()
    barangay_lookup["_barangay_key"] = barangay_lookup["barangay_name"].astype(str).str.strip().str.lower()
    university_lookup = universities[["university_id", "university_name"]].copy()
    university_lookup["_university_key"] = university_lookup["university_name"].astype(str).str.strip().str.lower()
    economic_burden["_barangay_key"] = economic_burden["barangay_name"].astype(str).str.strip().str.lower()
    economic_burden["_university_key"] = economic_burden["university_name"].astype(str).str.strip().str.lower()
    economic_burden = economic_burden.merge(
        barangay_lookup[["barangay_id", "_barangay_key"]],
        on="_barangay_key",
        how="left",
        suffixes=("", "_live"),
    )
    economic_burden = economic_burden.merge(
        university_lookup[["university_id", "_university_key"]],
        on="_university_key",
        how="left",
        suffixes=("", "_live"),
    )
    economic_burden = economic_burden.dropna(subset=["barangay_id_live", "university_id_live"]).copy()
    economic_burden["barangay_id"] = economic_burden["barangay_id_live"]
    economic_burden["university_id"] = economic_burden["university_id_live"]
    economic_burden = economic_burden.drop(
        columns=[
            "_barangay_key",
            "_university_key",
            "barangay_id_live",
            "university_id_live",
        ],
        errors="ignore",
    )
    return {
        "guest_tracker": pd.DataFrame([{"session_id": "supabase-v2-smoke", "is_completed": True}]),
        "barangay_location": barangays,
        "questions": normalize_v2_questions(questions, answer_options, scoring_metadata),
        "programs": _load_csv(RAW / "program.csv"),
        "program_profile_v2": _load_csv(PROCESSED / "program_profile_v2.csv"),
        "universities": universities,
        "university_programs": _load_csv(RAW / "university_program.csv"),
        "commute_matrix": _load_csv(RAW / "barangay_university_commute_matrix.csv"),
        "economic_burden": economic_burden,
        "scholarship": _load_csv(RAW / "scholarship.csv"),
        "dimension_scholarship": _load_csv(RAW / "dimension_scholarship.csv"),
        "municipality_field_saturation": pd.read_parquet(PROCESSED / "municipality_field_saturation.parquet"),
    }


def _responses() -> dict[str, str]:
    result = {}
    for qnum in range(1, 25):
        code = f"V2Q{qnum:02d}"
        if qnum <= 4:
            result[code] = "5"
        elif qnum <= 8:
            result[code] = "3"
        else:
            result[code] = "1"
    result.update(
        {
            "V2Q25": "A",
            "V2Q26": "B",
            "V2Q27": "B",
            "V2Q28": "B",
            "V2Q29": "D",
        }
    )
    return result


def test_v2_supabase_contract_normalizes_questions_and_resolves_option_ids():
    questions = normalize_v2_questions(
        _load_csv(SEED / "questions_seed_v2.csv"),
        _load_csv(SEED / "answer_option_seed_v2.csv"),
        _load_csv(SEED / "answer_option_scoring_metadata_seed_v2.csv"),
    )
    selected = resolve_selected_option_rows(_responses(), questions)

    assert len(questions["question_id"].unique()) == 29
    assert len(selected) == 29
    assert {row["question_code"] for row in selected} == {f"V2Q{i:02d}" for i in range(1, 30)}
    assert all(row["option_id"] for row in selected)


def test_v2_recommender_runs_on_supabase_shaped_snapshot():
    frames = _live_frames()
    barangay_id = str(frames["barangay_location"].iloc[0]["barangay_id"])

    result = recommend_programs(
        session_id="supabase-v2-smoke",
        student_barangay_id=barangay_id,
        student_responses=_responses(),
        guest_tracker=frames["guest_tracker"],
        barangay_location=frames["barangay_location"],
        questions=frames["questions"],
        programs=frames["programs"],
        university_programs=frames["university_programs"],
        universities=frames["universities"],
        commute_matrix=frames["commute_matrix"],
        economic_burden=frames["economic_burden"],
        scholarship=frames["scholarship"],
        dimension_scholarship=frames["dimension_scholarship"],
        municipality_field_saturation=frames["municipality_field_saturation"],
        program_profile_v2=frames["program_profile_v2"],
    )

    assert result["status"] == "ok"
    assert result["model_id"] == MODEL_ID
    assert len(result["recommendations"]) == 3
    assert len(result["model_recommendation_rows"]) == 3
    assert len(result["model_recommendation_trace_rows"]) == 3
    assert result["recommendations"][0]["program_profile"]["profile_version"] == "program_profile_v2"
