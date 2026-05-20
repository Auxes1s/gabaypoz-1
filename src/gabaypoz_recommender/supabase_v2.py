"""Helpers for the v2 Supabase integration contract.

These utilities normalize live/raw Supabase tables into the exact shapes
expected by ``recommender_v2.py`` and provide option resolution for smoke-test
or API persistence flows.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd


MODEL_ID = "tds_recommender_v2"
QUESTION_ORDER = [f"V2Q{i:02d}" for i in range(1, 30)]


def parse_question_code(question_text: object) -> str:
    text = "" if pd.isna(question_text) else str(question_text).strip()
    return text.split(".", 1)[0].strip()


def normalize_v2_questions(
    questions: pd.DataFrame,
    answer_options: pd.DataFrame,
    scoring_metadata: pd.DataFrame,
    *,
    model_id: str = MODEL_ID,
) -> pd.DataFrame:
    """Return a v2 scoring frame shaped for ``recommender_v2``.

    The output is one row per selectable answer option with:
    - ``question_id`` rewritten to question_code for local model calls
    - ``question_id_uuid`` preserved for DB writes
    - ``option_value`` mapped to stable option labels
    - scoring metadata joined from ``answer_option_scoring_metadata``
    """

    q = questions.copy()
    opts = answer_options.copy()
    meta = scoring_metadata.copy()

    if "question_code" not in q.columns:
        q["question_code"] = q["question_text"].map(parse_question_code)
    if "question_code" not in opts.columns:
        opts = opts.merge(q[["question_id", "question_code"]], on="question_id", how="left")
    if "model_id" in q.columns:
        q = q[q["model_id"].astype(str) == model_id].copy()
    q = q[q["question_code"].isin(QUESTION_ORDER)].copy()
    meta = meta[meta["model_id"].astype(str) == model_id].copy()
    meta = meta[meta["question_code"].isin(QUESTION_ORDER)].copy()
    opts = opts[opts["question_code"].isin(QUESTION_ORDER)].copy()

    merged = (
        opts.merge(
            q[["question_id", "question_code", "question_text"]],
            on=["question_id", "question_code"],
            how="inner",
            suffixes=("", "_question"),
        )
        .merge(
            meta[
                [
                    "option_id",
                    "question_id",
                    "question_code",
                    "construct_family",
                    "target_field",
                    "response_value",
                    "reverse_scored",
                    "scoring_type",
                ]
            ],
            on=["option_id", "question_id", "question_code"],
            how="inner",
        )
    )

    required_questions = set(QUESTION_ORDER)
    present_questions = set(merged["question_code"].astype(str).unique())
    missing_questions = sorted(required_questions - present_questions)
    if missing_questions:
        raise RuntimeError(f"Missing v2 question rows for: {missing_questions}")

    merged["question_id_uuid"] = merged["question_id"].astype(str)
    merged["question_id"] = merged["question_code"].astype(str)
    merged["option_value"] = merged["option_label"].astype(str)
    merged["selected_option"] = merged["option_label"].astype(str)

    columns = [
        "question_id",
        "question_id_uuid",
        "question_code",
        "question_text",
        "option_id",
        "option_label",
        "option_text",
        "option_value",
        "selected_option",
        "construct_family",
        "target_field",
        "response_value",
        "reverse_scored",
        "scoring_type",
        "display_order",
    ]
    return merged[columns].sort_values(["question_code", "display_order"]).reset_index(drop=True)


def filter_program_profile_v2(program_profile_v2: pd.DataFrame) -> pd.DataFrame:
    profile = program_profile_v2.copy()
    if "profile_version" in profile.columns:
        profile = profile[profile["profile_version"].astype(str) == "program_profile_v2"].copy()
    if profile.empty:
        raise RuntimeError("No program_profile_v2 rows found.")
    return profile.reset_index(drop=True)


def resolve_selected_option_rows(
    responses: dict[str, str],
    questions_scoring: pd.DataFrame,
) -> list[dict[str, str]]:
    rows = []
    for qid in QUESTION_ORDER:
        selected = str(responses[qid])
        candidates = questions_scoring[
            (questions_scoring["question_id"].astype(str) == qid)
            & (questions_scoring["option_label"].astype(str) == selected)
        ].copy()
        if candidates.empty:
            raise RuntimeError(f"No answer_option row found for {qid}={selected}")
        row = candidates.iloc[0]
        rows.append(
            {
                "question_code": qid,
                "question_id": str(row["question_id_uuid"]),
                "option_id": str(row["option_id"]),
                "selected_option": str(row["option_label"]),
            }
        )
    return rows


def question_prompt_rows(questions_scoring: pd.DataFrame) -> Iterable[tuple[str, pd.DataFrame]]:
    for qid in QUESTION_ORDER:
        rows = questions_scoring[questions_scoring["question_id"].astype(str) == qid].copy()
        if rows.empty:
            raise RuntimeError(f"No v2 options found for {qid}")
        yield qid, rows.sort_values("display_order").reset_index(drop=True)
