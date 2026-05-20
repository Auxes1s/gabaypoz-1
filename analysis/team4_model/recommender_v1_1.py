"""Official GabayPoz recommender v1.1.

This module implements the DB-aligned Team 4 recommender contract from
``docs/reports/model/team4_tds_recommender_v1.md``:

* validate session and barangay inputs,
* build a six-field student profile from questionnaire answers,
* rank programs first,
* apply municipality field saturation as a small context signal,
* apply the Q12 duration/board-exam penalty,
* choose one primary school and feasible alternates per program using Q11/Q10,
* optionally write exactly three rows shaped like ``model_recommendation``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np
import pandas as pd

DIMS = ["stem", "health", "arts", "business", "education", "agriculture"]
DIM_LABELS = ["STEM", "Health", "Arts", "Business", "Education", "Agriculture"]
FIELD_LABELS = dict(zip(DIMS, DIM_LABELS))

MODEL_ID = "tds_recommender_v1_1"
Q10_MAP = {"A": 1, "B": 3, "C": 5}
Q11_MAP = {"A": 45.0, "B": 90.0, "C": None}
Q12_MAP = {"A": 3, "B": 2, "C": 1}
Q12_PENALTY = 0.85
NEUTRAL_MARKET_SCORE = 0.50
LOW_SIGNAL_ABORT = 1.0
LOW_SIGNAL_FLAG = 1.5
TIE_ZONE_SPREAD = 0.05
INTERNAL_QUESTIONS = {f"Q{i}" for i in range(1, 7)}
APTITUDE_QUESTIONS = {"Q8", "Q9"}
SCORING_QUESTIONS = INTERNAL_QUESTIONS | APTITUDE_QUESTIONS
REQUIRED_QUESTIONS = SCORING_QUESTIONS | {"Q10", "Q11", "Q12"}

INTERNAL_WEIGHT = 0.55
APTITUDE_WEIGHT = 0.45
BASE_COSINE_WEIGHT = 0.70
BASE_DOT_WEIGHT = 0.30
PROGRAM_FIT_WEIGHT = 0.90
MARKET_WEIGHT = 0.10


class RecommenderError(Exception):
    """Typed failure used internally before conversion to a response dict."""

    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


def recommend_programs(
    *,
    session_id: str,
    student_barangay_id: int,
    student_responses: dict | pd.DataFrame,
    guest_tracker: pd.DataFrame,
    barangay_location: pd.DataFrame,
    questions: pd.DataFrame,
    programs: pd.DataFrame,
    university_programs: pd.DataFrame,
    universities: pd.DataFrame,
    commute_matrix: pd.DataFrame,
    economic_burden: pd.DataFrame,
    scholarship: Optional[pd.DataFrame] = None,
    dimension_scholarship: Optional[pd.DataFrame] = None,
    municipality_field_saturation: Optional[pd.DataFrame] = None,
    write_recommendations: Optional[Callable[[list[dict]], None]] = None,
    model_id: str = MODEL_ID,
    top_n: int = 3,
) -> dict:
    """Return v1.1 recommendations and optionally persist the top three rows.

    The function never writes on validation or candidate-selection failure. On
    success, it writes only via ``write_recommendations`` so the package stays
    independent of Team 5's final DB layer.
    """

    warnings: list[str] = []
    try:
        responses = _coerce_responses(student_responses)
        _validate_session(session_id, guest_tracker)
        barangay_row = _validate_barangay(student_barangay_id, barangay_location)
        _validate_required_answers(responses)

        burden = _normalize_burden(economic_burden, barangay_location, universities)
        _validate_burden_coverage(student_barangay_id, burden, university_programs)

        student_vector, student_norm = _build_student_vector(responses, questions)
        program_scores = _score_programs(
            programs=programs,
            student_vector=student_vector,
            student_norm=student_norm,
            q12_response=responses["Q12"],
            saturation=municipality_field_saturation,
            barangay_row=barangay_row,
            warnings=warnings,
        )

        if program_scores.empty:
            raise RecommenderError("NO_CANDIDATES", "No programs could be scored.")

        selected = _select_programs_with_schools(
            program_scores=program_scores,
            student_vector=student_vector,
            responses=responses,
            student_barangay_id=student_barangay_id,
            university_programs=university_programs,
            universities=universities,
            commute_matrix=commute_matrix,
            economic_burden=burden,
            scholarship=scholarship,
            dimension_scholarship=dimension_scholarship,
            top_n=top_n,
        )
        if len(selected) < top_n:
            raise RecommenderError(
                "NO_CANDIDATES",
                f"Only {len(selected)} feasible program recommendation(s) found.",
            )

        low_confidence, low_reason = _low_confidence(selected, student_norm)
        recommendations = [
            _build_explanation(i + 1, row, student_vector, responses, low_confidence, low_reason)
            for i, row in enumerate(selected)
        ]
        rows = _build_persisted_rows(session_id, model_id, recommendations)

        if write_recommendations is not None:
            write_recommendations(rows)

        return {
            "status": "ok",
            "error_code": None,
            "warnings": warnings,
            "model_id": model_id,
            "recommendations": recommendations,
            "model_recommendation_rows": rows,
        }
    except RecommenderError as exc:
        return {
            "status": "error",
            "error_code": exc.error_code,
            "message": str(exc),
            "warnings": warnings,
            "model_id": model_id,
            "recommendations": [],
            "model_recommendation_rows": [],
        }


def _coerce_responses(student_responses: dict | pd.DataFrame) -> dict:
    if isinstance(student_responses, dict):
        return {str(k): str(v) for k, v in student_responses.items()}
    if not {"question_id", "selected_option"} <= set(student_responses.columns):
        raise RecommenderError(
            "INCOMPLETE_RESPONSES",
            "Response rows must include question_id and selected_option.",
        )
    return {
        str(row.question_id): str(row.selected_option)
        for row in student_responses.itertuples(index=False)
    }


def _validate_session(session_id: str, guest_tracker: pd.DataFrame) -> None:
    if "session_id" not in guest_tracker.columns:
        raise RecommenderError("INVALID_SESSION", "guest_tracker is missing session_id.")
    rows = guest_tracker[guest_tracker["session_id"].astype(str) == str(session_id)]
    if rows.empty:
        raise RecommenderError("INVALID_SESSION", "Session was not found.")
    if "is_completed" in rows.columns and not bool(rows.iloc[0]["is_completed"]):
        raise RecommenderError("INVALID_SESSION", "Session is not marked completed.")


def _validate_barangay(student_barangay_id: int, barangay_location: pd.DataFrame) -> pd.Series:
    if "barangay_id" not in barangay_location.columns:
        raise RecommenderError("INVALID_BARANGAY", "barangay_location is missing barangay_id.")
    rows = barangay_location[barangay_location["barangay_id"].astype(str) == str(student_barangay_id)]
    if rows.empty:
        raise RecommenderError("INVALID_BARANGAY", "Student barangay was not found.")
    return rows.iloc[0]


def _validate_required_answers(responses: dict) -> None:
    missing = sorted(REQUIRED_QUESTIONS - set(responses))
    if missing:
        raise RecommenderError("INCOMPLETE_RESPONSES", f"Missing required answers: {missing}.")
    for qid, allowed in {"Q10": Q10_MAP, "Q11": Q11_MAP, "Q12": Q12_MAP}.items():
        if responses[qid] not in allowed:
            raise RecommenderError(
                "INCOMPLETE_RESPONSES",
                f"{qid} must use stable option values {sorted(allowed)}.",
            )


def _normalize_burden(
    economic_burden: pd.DataFrame,
    barangay_location: pd.DataFrame,
    universities: pd.DataFrame,
) -> pd.DataFrame:
    if economic_burden is None or economic_burden.empty:
        raise RecommenderError("MISSING_Q10_BURDEN_DATA", "Q10 burden data is missing.")
    burden = economic_burden.copy()

    if "barangay_id" not in burden.columns and "barangay" in burden.columns:
        name_col = _first_existing(barangay_location, ["barangay_name", "barangay"])
        if name_col is not None:
            lookup = barangay_location[["barangay_id", name_col]].copy()
            lookup["_barangay_key"] = lookup[name_col].map(_clean_key)
            burden["_barangay_key"] = burden["barangay"].map(_clean_key)
            burden = burden.merge(lookup[["barangay_id", "_barangay_key"]], on="_barangay_key", how="left")

    if "university_id" not in burden.columns and "university" in burden.columns:
        uni_name_col = _first_existing(universities, ["university_name", "university"])
        if uni_name_col is not None:
            lookup = universities[["university_id", uni_name_col]].copy()
            lookup["_university_key"] = lookup[uni_name_col].map(_clean_key)
            burden["_university_key"] = burden["university"].map(_clean_key)
            burden = burden.merge(lookup[["university_id", "_university_key"]], on="_university_key", how="left")

    tier_cols = [f"affordability_at_tier_{tier}" for tier in range(1, 6)]
    required = {"barangay_id", "university_id", "total_annual_burden_php", *tier_cols}
    missing = sorted(required - set(burden.columns))
    if missing:
        raise RecommenderError(
            "MISSING_Q10_BURDEN_DATA",
            f"Q10 burden data is missing fields: {missing}.",
        )
    if burden[["barangay_id", "university_id"]].isna().any().any():
        raise RecommenderError(
            "MISSING_Q10_BURDEN_DATA",
            "Q10 burden data has unmapped barangay or university IDs.",
        )
    return burden


def _validate_burden_coverage(
    student_barangay_id: int,
    burden: pd.DataFrame,
    university_programs: pd.DataFrame,
) -> None:
    needed_unis = set(university_programs["university_id"].dropna().astype(str))
    available = set(
        burden[burden["barangay_id"].astype(str) == str(student_barangay_id)]["university_id"]
        .dropna()
        .astype(str)
    )
    if not needed_unis or not available:
        raise RecommenderError(
            "MISSING_Q10_BURDEN_DATA",
            "Q10 burden data has no usable rows for this barangay.",
        )
    missing = needed_unis - available
    if missing:
        raise RecommenderError(
            "MISSING_Q10_BURDEN_DATA",
            f"Q10 burden data is incomplete for university_id(s): {sorted(missing)}.",
        )


def _build_student_vector(responses: dict, questions: pd.DataFrame) -> tuple[np.ndarray, float]:
    score_cols = [_score_col(questions, dim, question=True) for dim in DIMS]
    option_col = "option_value" if "option_value" in questions.columns else "selected_option"
    if option_col not in questions.columns or "question_id" not in questions.columns:
        raise RecommenderError(
            "INCOMPLETE_RESPONSES",
            "questions must include question_id and option_value/selected_option.",
        )

    rows = []
    for qid in sorted(SCORING_QUESTIONS):
        selected = responses[qid]
        match = questions[
            (questions["question_id"].astype(str) == qid)
            & (questions[option_col].astype(str) == selected)
        ]
        if match.empty:
            raise RecommenderError(
                "INCOMPLETE_RESPONSES",
                f"No scoring row for {qid}={selected}.",
            )
        rows.append(match.iloc[0][score_cols].astype(float).to_numpy())

    internal = np.sum(rows[: len(INTERNAL_QUESTIONS)], axis=0)
    aptitude = np.sum(rows[len(INTERNAL_QUESTIONS) :], axis=0)
    internal = _normalize_0_1(internal)
    aptitude = _normalize_0_1(aptitude)
    student = (INTERNAL_WEIGHT * internal) + (APTITUDE_WEIGHT * aptitude)
    norm = float(np.linalg.norm(student))
    if norm < LOW_SIGNAL_ABORT:
        raise RecommenderError("LOW_SIGNAL", "Student answers produced too little signal.")
    return student, norm


def _score_programs(
    *,
    programs: pd.DataFrame,
    student_vector: np.ndarray,
    student_norm: float,
    q12_response: str,
    saturation: Optional[pd.DataFrame],
    barangay_row: pd.Series,
    warnings: list[str],
) -> pd.DataFrame:
    prog = programs.copy()
    rows = []
    for row in prog.itertuples(index=False):
        r = row._asdict()
        program_vector = np.array([float(r.get(_program_dim_col(prog, dim), 0.0)) for dim in DIMS])
        norm_p = float(np.linalg.norm(program_vector))
        if norm_p == 0.0:
            continue
        dot = float(student_vector @ program_vector)
        cosine = dot / (student_norm * norm_p)
        dot_norm = dot / max(float(student_vector.max() * program_vector.sum()), 1.0)
        base_fit = (BASE_COSINE_WEIGHT * cosine) + (BASE_DOT_WEIGHT * min(dot_norm, 1.0))

        dominant_dim = _dominant_dim(program_vector)
        market_context = _market_context(dominant_dim, saturation, barangay_row, warnings)
        before_q12 = (PROGRAM_FIT_WEIGHT * base_fit) + (MARKET_WEIGHT * market_context["market_score"])
        penalty_applied, final_score = _apply_q12(before_q12, q12_response, r)

        rows.append({
            "program_id": r["program_id"],
            "program_name": r.get("program_name") or r.get("program") or str(r["program_id"]),
            "program_vector": program_vector,
            "dominant_dim": dominant_dim,
            "base_fit_score": float(base_fit),
            "program_score_before_q12": float(before_q12),
            "program_score": float(final_score),
            "market_context": market_context,
            "penalties_applied": ["Q12 duration/board-exam penalty x0.85"] if penalty_applied else [],
        })

    return pd.DataFrame(rows).sort_values(
        ["program_score", "base_fit_score", "program_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _select_programs_with_schools(
    *,
    program_scores: pd.DataFrame,
    student_vector: np.ndarray,
    responses: dict,
    student_barangay_id: int,
    university_programs: pd.DataFrame,
    universities: pd.DataFrame,
    commute_matrix: pd.DataFrame,
    economic_burden: pd.DataFrame,
    scholarship: Optional[pd.DataFrame],
    dimension_scholarship: Optional[pd.DataFrame],
    top_n: int,
) -> list[dict]:
    selected: list[dict] = []
    selected_fields: set[str] = set()

    for row in program_scores.itertuples(index=False):
        candidate = row._asdict()
        schools = _feasible_schools(
            candidate["program_id"],
            student_barangay_id,
            responses["Q10"],
            responses["Q11"],
            university_programs,
            universities,
            commute_matrix,
            economic_burden,
            scholarship,
            dimension_scholarship,
        )
        if schools.empty:
            continue

        enriched = dict(candidate)
        enriched["primary_school"] = _school_dict(schools.iloc[0])
        enriched["alternate_schools"] = [_school_dict(s) for _, s in schools.iloc[1:].iterrows()]
        enriched["matched_dimensions"] = _matched_dimensions(student_vector, candidate["program_vector"])
        selected.append(enriched)
        selected_fields.add(candidate["dominant_dim"])
        if len(selected) == top_n:
            break

    if len(selected) < top_n:
        return selected

    # Light diversity pass for the third slot only, preserving strong score order.
    if len({r["dominant_dim"] for r in selected}) == 1:
        for row in program_scores.iloc[top_n:].itertuples(index=False):
            alt = row._asdict()
            if alt["dominant_dim"] in selected_fields:
                continue
            if selected[0]["program_score"] - alt["program_score"] > 0.15:
                break
            schools = _feasible_schools(
                alt["program_id"],
                student_barangay_id,
                responses["Q10"],
                responses["Q11"],
                university_programs,
                universities,
                commute_matrix,
                economic_burden,
                scholarship,
                dimension_scholarship,
            )
            if not schools.empty:
                alt["primary_school"] = _school_dict(schools.iloc[0])
                alt["alternate_schools"] = [_school_dict(s) for _, s in schools.iloc[1:].iterrows()]
                alt["matched_dimensions"] = _matched_dimensions(student_vector, alt["program_vector"])
                selected[-1] = alt
                break

    return selected


def _feasible_schools(
    program_id,
    student_barangay_id: int,
    q10_response: str,
    q11_response: str,
    university_programs: pd.DataFrame,
    universities: pd.DataFrame,
    commute_matrix: pd.DataFrame,
    economic_burden: pd.DataFrame,
    scholarship: Optional[pd.DataFrame],
    dimension_scholarship: Optional[pd.DataFrame],
) -> pd.DataFrame:
    offered = university_programs[university_programs["program_id"].astype(str) == str(program_id)].copy()
    if offered.empty:
        return offered

    uni_cols = ["university_id"] + [
        col for col in ["university_name", "university_type", "type", "address"] if col in universities.columns
    ]
    offered = offered.merge(universities[uni_cols], on="university_id", how="left", suffixes=("", "_university"))
    if "university_name" not in offered.columns and "university_name_university" in offered.columns:
        offered["university_name"] = offered["university_name_university"]

    commute = commute_matrix[commute_matrix["barangay_id"].astype(str) == str(student_barangay_id)].copy()
    offered = offered.merge(
        commute[[col for col in ["university_id", "distance_km", "commute_time_mins"] if col in commute.columns]],
        on="university_id",
        how="inner",
    )
    max_commute = Q11_MAP[q11_response]
    if max_commute is not None:
        offered = offered[offered["commute_time_mins"].astype(float) <= max_commute]

    tier = Q10_MAP[q10_response]
    tier_col = f"affordability_at_tier_{tier}"
    burden = economic_burden[economic_burden["barangay_id"].astype(str) == str(student_barangay_id)].copy()
    keep_cols = [
        "university_id",
        "total_annual_burden_php",
        "annual_transport_cost_php",
        "tuition_estimate",
        "economic_constraint",
        tier_col,
    ]
    offered = offered.merge(burden[[c for c in keep_cols if c in burden.columns]], on="university_id", how="inner")
    offered = offered[offered[tier_col].astype(bool)]
    if offered.empty:
        return offered

    scholarship_context = _scholarship_details(program_id, scholarship, dimension_scholarship)
    offered["scholarship_count"] = scholarship_context["count"]
    offered["scholarship_names"] = [scholarship_context["sample_names"]] * len(offered)
    offered["university_name_sort"] = offered.get("university_name", offered["university_id"]).astype(str)
    return offered.sort_values(
        ["total_annual_burden_php", "commute_time_mins", "scholarship_count", "university_name_sort"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)


def _build_explanation(
    rank: int,
    row: dict,
    student_vector: np.ndarray,
    responses: dict,
    low_confidence: bool,
    low_reason: Optional[str],
) -> dict:
    primary = row["primary_school"]
    field = row["dominant_dim"]
    score = float(row["program_score"])
    explanation_text = (
        f"{row['program_name']} matches your strongest {', '.join(row['matched_dimensions'])} signals. "
        f"{primary['university_name']} is the primary school suggestion because it passed your travel "
        f"and affordability limits. Local {FIELD_LABELS[field]} field presence is included only as "
        "small context, not a job guarantee."
    )
    return {
        "rank": rank,
        "program_id": row["program_id"],
        "program_name": row["program_name"],
        "primary_school": primary,
        "alternate_schools": row["alternate_schools"],
        "program_score": round(score, 6),
        "base_fit_score": round(float(row["base_fit_score"]), 6),
        "market_context": row["market_context"],
        "matched_dimensions": row["matched_dimensions"],
        "constraints_applied": {
            "q10_response": responses["Q10"],
            "q10_tier": Q10_MAP[responses["Q10"]],
            "q11_response": responses["Q11"],
            "q11_max_commute_mins": Q11_MAP[responses["Q11"]],
            "primary_commute_mins": primary.get("commute_time_mins"),
            "primary_total_annual_burden_php": primary.get("total_annual_burden_php"),
            "passed_travel_filter": True,
            "passed_affordability_filter": True,
        },
        "penalties_applied": row["penalties_applied"],
        "scholarship_context": {
            "primary_school_scholarship_count": primary.get("scholarship_count", 0),
            "sample_names": primary.get("scholarship_names", []),
        },
        "low_confidence_flag": low_confidence,
        "low_confidence_reason": low_reason,
        "explanation_text": explanation_text,
    }


def _build_persisted_rows(session_id: str, model_id: str, recommendations: list[dict]) -> list[dict]:
    created = datetime.now(timezone.utc).isoformat()
    return [
        {
            "session_id": session_id,
            "model_id": model_id,
            "rank": rec["rank"],
            "program_id": rec["program_id"],
            "university_id": rec["primary_school"]["university_id"],
            "model_score": rec["program_score"],
            "created_datetime": created,
        }
        for rec in recommendations
    ]


def _market_context(
    dominant_dim: str,
    saturation: Optional[pd.DataFrame],
    barangay_row: pd.Series,
    warnings: list[str],
) -> dict:
    if saturation is None or saturation.empty or "affinity_field" not in saturation.columns:
        _warn_once(warnings, "MISSING_SATURATION_DATA")
        return _neutral_market_context(dominant_dim, "Municipality saturation data is missing.")

    field_label = FIELD_LABELS[dominant_dim].upper()
    rows = saturation[saturation["affinity_field"].astype(str).str.upper() == field_label].copy()
    muni_code = _series_first(barangay_row, ["municipality_code", "city_municipality_code", "psgc_municipality_code"])
    muni_name = _series_first(barangay_row, ["municipality_name", "city_municipality_name"])

    if muni_code is not None and "municipality_code" in rows.columns:
        rows = rows[rows["municipality_code"].astype(str) == str(muni_code)]
    if rows.empty and muni_name is not None and "municipality_name" in saturation.columns:
        rows = saturation[
            (saturation["affinity_field"].astype(str).str.upper() == field_label)
            & (saturation["municipality_name"].astype(str).str.lower() == str(muni_name).lower())
        ]

    if rows.empty:
        _warn_once(warnings, "MISSING_SATURATION_DATA")
        return _neutral_market_context(dominant_dim, "No saturation row matched this field.")

    row = rows.iloc[0]
    raw = row.get("market_score", row.get("v2_differentiated", NEUTRAL_MARKET_SCORE))
    raw = NEUTRAL_MARKET_SCORE if pd.isna(raw) else float(raw)
    score = raw / 5.0 if raw > 1.0 else raw
    score = float(np.clip(score, 0.0, 1.0))
    province_share = row.get("province_field_share", row.get("pangasinan_share"))
    municipality_share = row.get("municipality_field_share", row.get("pozorrubio_share"))
    ratio = row.get("saturation_ratio")
    if pd.isna(ratio) and pd.notna(province_share) and float(province_share) > 0:
        ratio = float(municipality_share) / float(province_share)
    return {
        "status": "ok",
        "affinity_field": FIELD_LABELS[dominant_dim],
        "market_score": round(score, 6),
        "saturation_ratio": None if pd.isna(ratio) else round(float(ratio), 6),
        "market_score_method": str(row.get("market_score_method", "ecosystem_saturation_v1_1")),
        "explanation": "Local field presence is a small context signal, not guaranteed job demand.",
    }


def _neutral_market_context(dominant_dim: str, explanation: str) -> dict:
    return {
        "status": "neutral_fallback",
        "affinity_field": FIELD_LABELS[dominant_dim],
        "market_score": NEUTRAL_MARKET_SCORE,
        "saturation_ratio": None,
        "market_score_method": "neutral_fallback",
        "explanation": explanation,
    }


def _apply_q12(score: float, q12_response: str, program_row: dict) -> tuple[bool, float]:
    tolerance = Q12_MAP[q12_response]
    duration_score = program_row.get("affinity_duration_score")
    if duration_score is not None and pd.notna(duration_score):
        program_level = int(float(duration_score))
    else:
        duration = float(program_row.get("duration", 4))
        board_exam = bool(program_row.get("board_exam_flag", False))
        program_level = 3 if board_exam or duration > 4 else 2 if duration >= 4 else 1
    if program_level > tolerance:
        return True, score * Q12_PENALTY
    return False, score


def _score_col(df: pd.DataFrame, dim: str, *, question: bool) -> str:
    candidates = [f"{dim}_score"] if question else []
    candidates.extend([f"affinity_{dim}_score", dim])
    for col in candidates:
        if col in df.columns:
            return col
    raise RecommenderError("NO_CANDIDATES", f"Missing score column for {dim}.")


def _program_dim_col(programs: pd.DataFrame, dim: str) -> str:
    for col in [f"affinity_{dim}_score", f"{dim}_score", dim]:
        if col in programs.columns:
            return col
    raise RecommenderError("NO_CANDIDATES", f"program is missing {dim} affinity score.")


def _dominant_dim(program_vector: np.ndarray) -> str:
    max_score = float(np.max(program_vector))
    tied_dims = [
        dim
        for dim, score in zip(DIMS, program_vector)
        if float(score) == max_score
    ]
    return sorted(tied_dims, key=lambda dim: FIELD_LABELS[dim])[0]


def _matched_dimensions(student_vector: np.ndarray, program_vector: np.ndarray) -> list[str]:
    threshold_s = max(float(student_vector.max()) * 0.75, 0.01)
    threshold_p = max(float(program_vector.max()) * 0.75, 0.01)
    matches = [
        FIELD_LABELS[dim]
        for i, dim in enumerate(DIMS)
        if student_vector[i] >= threshold_s and program_vector[i] >= threshold_p
    ]
    return matches or [FIELD_LABELS[_dominant_dim(program_vector)]]


def _school_dict(row: pd.Series) -> dict:
    return {
        "university_id": row["university_id"],
        "university_name": row.get("university_name") or str(row["university_id"]),
        "commute_time_mins": _none_or_float(row.get("commute_time_mins")),
        "distance_km": _none_or_float(row.get("distance_km")),
        "total_annual_burden_php": _none_or_float(row.get("total_annual_burden_php")),
        "tuition_estimate": _none_or_float(row.get("tuition_estimate")),
        "annual_transport_cost_php": _none_or_float(row.get("annual_transport_cost_php")),
        "scholarship_count": int(row.get("scholarship_count", 0)),
        "scholarship_names": row.get("scholarship_names", []),
    }


def _scholarship_details(
    program_id,
    scholarship: Optional[pd.DataFrame],
    dimension_scholarship: Optional[pd.DataFrame],
) -> dict:
    if scholarship is None or scholarship.empty or "program_id" not in scholarship.columns:
        return {"count": 0, "sample_names": []}
    rows = scholarship[scholarship["program_id"].astype(str) == str(program_id)]
    if rows.empty:
        return {"count": 0, "sample_names": []}
    if dimension_scholarship is not None and not dimension_scholarship.empty and "scholarship_code" in rows.columns:
        rows = rows.merge(dimension_scholarship, on="scholarship_code", how="left")
    name_col = _first_existing(rows, ["scholarship_name", "name", "scholarship_title"])
    names = rows[name_col].dropna().astype(str).head(3).tolist() if name_col else []
    return {"count": int(len(rows)), "sample_names": names}


def _low_confidence(selected: list[dict], student_norm: float) -> tuple[bool, Optional[str]]:
    if student_norm < LOW_SIGNAL_FLAG:
        return True, "LOW_SIGNAL"
    spread = float(selected[0]["program_score"]) - float(selected[-1]["program_score"])
    if spread < TIE_ZONE_SPREAD:
        return True, "CLOSE_RANKING"
    return False, None


def _normalize_0_1(values: np.ndarray) -> np.ndarray:
    max_value = float(np.max(values))
    if max_value <= 0.0:
        return values
    return values / max_value


def _first_existing(df: pd.DataFrame, columns: list[str]) -> Optional[str]:
    return next((col for col in columns if col in df.columns), None)


def _series_first(row: pd.Series, columns: list[str]):
    for col in columns:
        if col in row.index and pd.notna(row[col]):
            return row[col]
    return None


def _clean_key(value) -> str:
    return " ".join(str(value).strip().lower().split())


def _none_or_float(value):
    return None if value is None or pd.isna(value) else float(value)


def _warn_once(warnings: list[str], code: str) -> None:
    if code not in warnings:
        warnings.append(code)
