"""Official GabayPoz recommender v2.

This module implements the DB-aligned Team 4 recommender contract from
``docs/reports/model/team4_tds_recommender_v1.md`` plus the v2
latent-variable questionnaire upgrade:

* validate session and barangay inputs,
* build a six-field student profile from construct-tagged Likert items,
* use Q7 SHS strand only as a small bounded context adjustment,
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

MODEL_ID = "tds_recommender_v2"
Q10_MAP = {"A": 1, "B": 3, "C": 5}
Q11_MAP = {"A": 45.0, "B": 90.0, "C": None}
Q12_MAP = {"A": 3, "B": 2, "C": 1}
STRAND_FIELD_SUPPORT: dict[str, set[str]] = {
    "STEM": {"stem"},
    "ABM": {"business"},
    "HUMSS": {"arts"},
    "TVL": {"stem", "agriculture"},
    "GAS": set(),
    "Sports": {"arts"},
    "Arts and Design": {"arts"},
    "Sports / Arts and Design": {"arts"},
}
_STRAND_LOOKUP = {strand.lower(): fields for strand, fields in STRAND_FIELD_SUPPORT.items()}
Q12_PENALTY = 0.85  # legacy alias — _apply_q12 now uses tiered penalties below
Q12_PENALTY_MILD = 0.75      # programme 1 duration level above student tolerance
Q12_PENALTY_MODERATE = 0.60  # 2 levels above
Q12_PENALTY_SEVERE = 0.45    # 3+ levels above
TRACK_ASPIRATION_PRIMARY_BOOST = 1.35   # was 1.12 — raised to overcome non-health dominant fields
TRACK_ASPIRATION_SECONDARY_BOOST = 1.12  # was 1.06
TRACK_ASPIRATION_FIELD_MAP: dict[str, dict[str, set[str]]] = {
    "medicine":  {"primary": {"health"}, "secondary": {"stem"}},
    "dentistry": {"primary": {"health"}, "secondary": {"stem"}},
    "law":       {"primary": {"arts"},   "secondary": {"business"}},
    "none":      {"primary": set(),      "secondary": set()},
}
Q13_MAP = {"A": "medicine", "B": "dentistry", "C": "law", "D": "none"}
NEUTRAL_MARKET_SCORE = 0.50
LOW_SIGNAL_ABORT = 0.15
LOW_SIGNAL_FLAG = 0.45
TIE_ZONE_SPREAD = 0.05
V2_AFFINITY_QUESTIONS = {f"V2Q{i:02d}" for i in range(1, 25)}
RESPONSE_ALIASES = {
    "V2Q25": "Q7",
    "V2Q26": "Q10",
    "V2Q27": "Q11",
    "V2Q28": "Q12",
    "V2Q29": "Q13",
}
REQUIRED_QUESTIONS = V2_AFFINITY_QUESTIONS | {"Q7", "Q10", "Q11", "Q12", "Q13"}

INTEREST_WEIGHT = 0.60
EFFICACY_WEIGHT = 0.35
STRAND_CONTEXT_WEIGHT = 0.05
BASE_SHAPE_WEIGHT = 0.70
BASE_DIRECTION_WEIGHT = 0.30
# Backward-compatible aliases for older notebooks/imports. In v2 these names
# mean shape/correlation fit and direction/cosine fit, respectively.
BASE_COSINE_WEIGHT = BASE_SHAPE_WEIGHT
BASE_DOT_WEIGHT = BASE_DIRECTION_WEIGHT
PROGRAM_FIT_WEIGHT = 0.90
MARKET_WEIGHT = 0.10
LOW_SPECIFICITY_STD = 0.08
LOW_PROFILE_CONFIDENCE_WEIGHT = 0.95
PROFILE_SCORE_EPSILON = 1e-12


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
    program_profile_v2: Optional[pd.DataFrame] = None,
    write_recommendations: Optional[Callable[[list[dict]], None]] = None,
    model_id: str = MODEL_ID,
    top_n: int = 3,
) -> dict:
    """Return v2 recommendations and optionally persist the top three rows.

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

        student_vector, student_norm, student_profile = _build_student_vector(responses, questions, warnings)
        scoring_programs = _prepare_program_profiles(programs, program_profile_v2)
        program_scores = _score_programs(
            programs=scoring_programs,
            student_vector=student_vector,
            student_norm=student_norm,
            q12_response=responses["Q12"],
            q13_response=responses["Q13"],
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
            warnings=warnings,
            top_n=top_n,
        )
        if len(selected) < top_n:
            raise RecommenderError(
                "NO_CANDIDATES",
                f"Only {len(selected)} feasible program recommendation(s) found.",
            )

        low_confidence, low_reason = _low_confidence(selected, student_vector, student_norm)
        recommendations = [
            _build_explanation(i + 1, row, student_vector, responses, low_confidence, low_reason)
            for i, row in enumerate(selected)
        ]
        rows = _build_persisted_rows(session_id, model_id, recommendations)
        trace_rows = _build_trace_rows(session_id, model_id, recommendations, student_profile, responses, warnings)

        if write_recommendations is not None:
            write_recommendations(rows)

        return {
            "status": "ok",
            "error_code": None,
            "warnings": warnings,
            "model_id": model_id,
            "recommendations": recommendations,
            "model_recommendation_rows": rows,
            "model_recommendation_trace_rows": trace_rows,
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
            "model_recommendation_trace_rows": [],
        }


def _coerce_responses(student_responses: dict | pd.DataFrame) -> dict:
    if isinstance(student_responses, dict):
        rows = {str(k): str(v) for k, v in student_responses.items()}
        _validate_response_collisions(rows)
        return _apply_response_aliases(rows)
    if not {"question_id", "selected_option"} <= set(student_responses.columns):
        raise RecommenderError(
            "INCOMPLETE_RESPONSES",
            "Response rows must include question_id and selected_option.",
        )
    question_ids = student_responses["question_id"].astype(str)
    duplicates = sorted(question_ids[question_ids.duplicated()].unique().tolist())
    if duplicates:
        raise RecommenderError(
            "INCOMPLETE_RESPONSES",
            f"Duplicate response rows found for question_id(s): {duplicates}.",
        )
    rows = {
        str(row.question_id): str(row.selected_option)
        for row in student_responses.itertuples(index=False)
    }
    _validate_response_collisions(rows)
    return _apply_response_aliases(rows)


def _validate_response_collisions(responses: dict) -> None:
    for alias, canonical in RESPONSE_ALIASES.items():
        if alias in responses and canonical in responses and str(responses[alias]) != str(responses[canonical]):
            raise RecommenderError(
                "INCOMPLETE_RESPONSES",
                f"Conflicting responses provided for {canonical} and {alias}.",
            )


def _apply_response_aliases(responses: dict) -> dict:
    normalized = dict(responses)
    for alias, canonical in RESPONSE_ALIASES.items():
        if canonical not in normalized and alias in normalized:
            normalized[canonical] = normalized[alias]
    return normalized


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
    for qid, allowed in {"Q10": Q10_MAP, "Q11": Q11_MAP, "Q12": Q12_MAP, "Q13": Q13_MAP}.items():
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
    available = burden[burden["barangay_id"].astype(str) == str(student_barangay_id)].copy()
    if available.empty:
        raise RecommenderError(
            "MISSING_Q10_BURDEN_DATA",
            "Q10 burden data has no usable rows for this barangay.",
        )
    needed_unis = set(university_programs["university_id"].dropna().astype(str))
    available_unis = set(available["university_id"].dropna().astype(str))
    if not needed_unis or not (needed_unis & available_unis):
        raise RecommenderError(
            "MISSING_Q10_BURDEN_DATA",
            "Q10 burden data has no overlap with the available university offerings.",
        )


def _build_student_vector(
    responses: dict,
    questions: pd.DataFrame,
    warnings: Optional[list[str]] = None,
) -> tuple[np.ndarray, float, dict]:
    option_col = "option_value" if "option_value" in questions.columns else "selected_option"
    required_cols = {"question_id", option_col, "construct_family", "target_field", "response_value"}
    if not required_cols <= set(questions.columns):
        raise RecommenderError(
            "INCOMPLETE_RESPONSES",
            "v2 questions must include question_id, option_value/selected_option, "
            "construct_family, target_field, and response_value.",
        )

    interest = np.zeros(len(DIMS), dtype=float)
    efficacy = np.zeros(len(DIMS), dtype=float)
    counts = {
        "domain_interest": np.zeros(len(DIMS), dtype=float),
        "domain_self_efficacy": np.zeros(len(DIMS), dtype=float),
    }

    for qid in sorted(V2_AFFINITY_QUESTIONS):
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
        row = match.iloc[0]
        family = str(row["construct_family"])
        if family not in counts:
            raise RecommenderError("INCOMPLETE_RESPONSES", f"{qid} has unsupported construct_family={family}.")
        target = str(row["target_field"]).strip().lower()
        if target not in DIMS:
            raise RecommenderError("INCOMPLETE_RESPONSES", f"{qid} has unsupported target_field={target}.")
        dim_index = DIMS.index(target)
        value = float(row["response_value"])
        if _truthy(row.get("reverse_scored", False)):
            value = 6.0 - value
        value = float(np.clip((value - 1.0) / 4.0, 0.0, 1.0))
        if family == "domain_interest":
            interest[dim_index] += value
        else:
            efficacy[dim_index] += value
        counts[family][dim_index] += 1.0

    expected_per_family = np.full(len(DIMS), 2.0)
    if not np.array_equal(counts["domain_interest"], expected_per_family):
        raise RecommenderError("INCOMPLETE_RESPONSES", "v2 requires exactly two interest items per field.")
    if not np.array_equal(counts["domain_self_efficacy"], expected_per_family):
        raise RecommenderError("INCOMPLETE_RESPONSES", "v2 requires exactly two self-efficacy items per field.")

    interest = interest / counts["domain_interest"]
    efficacy = efficacy / counts["domain_self_efficacy"]
    strand_context = _strand_context_vector(responses["Q7"], warnings)
    student = (INTEREST_WEIGHT * interest) + (EFFICACY_WEIGHT * efficacy) + (STRAND_CONTEXT_WEIGHT * strand_context)
    norm = float(np.linalg.norm(student))
    if norm < LOW_SIGNAL_ABORT:
        raise RecommenderError("LOW_SIGNAL", "Student answers produced too little signal.")
    profile = {
        "construct_scores": {
            "interest": _vector_dict(interest),
            "self_efficacy": _vector_dict(efficacy),
            "strand_context": _vector_dict(strand_context),
            "student_vector": _vector_dict(student),
        },
        "weights": {
            "interest": INTEREST_WEIGHT,
            "self_efficacy": EFFICACY_WEIGHT,
            "strand_context": STRAND_CONTEXT_WEIGHT,
        },
    }
    return student, norm, profile


def _strand_context_vector(strand: str, warnings: Optional[list[str]]) -> np.ndarray:
    fields = _STRAND_LOOKUP.get(str(strand).strip().lower())
    if fields is None:
        if warnings is not None:
            _warn_once(warnings, "UNKNOWN_Q7_STRAND")
        fields = set()
    return np.array([1.0 if dim in fields else 0.0 for dim in DIMS], dtype=float)


def _prepare_program_profiles(
    programs: pd.DataFrame,
    program_profile_v2: Optional[pd.DataFrame],
) -> pd.DataFrame:
    if program_profile_v2 is None or program_profile_v2.empty:
        raise RecommenderError(
            "PROGRAM_PROFILE_V2_REQUIRED",
            "program_profile_v2 is required for v2 scoring.",
        )
    if "program_id" not in program_profile_v2.columns:
        raise RecommenderError(
            "INVALID_PROGRAM_PROFILE_V2",
            "program_profile_v2 is missing required column: program_id.",
        )

    profile = program_profile_v2.copy()
    profile = profile[profile["program_id"].notna()].copy()
    if profile.empty:
        raise RecommenderError(
            "PROGRAM_PROFILE_V2_REQUIRED",
            "program_profile_v2 has no non-null program_id rows.",
        )
    if profile["program_id"].duplicated().any():
        duplicates = sorted(profile.loc[profile["program_id"].duplicated(), "program_id"].astype(str).unique().tolist())
        raise RecommenderError(
            "INVALID_PROGRAM_PROFILE_V2",
            f"program_profile_v2 contains duplicate program_id values: {duplicates}.",
        )

    required_meta_cols = [
        "profile_version",
        "profile_method",
        "profile_confidence",
        "profile_family",
        "dominant_dim",
        "dominant_dim_label",
        "evidence_text",
        "evidence_sources",
        "review_status",
        "affinity_duration_score",
    ]
    missing_meta_cols = sorted(col for col in required_meta_cols if col not in profile.columns)
    if missing_meta_cols:
        raise RecommenderError(
            "INVALID_PROGRAM_PROFILE_V2",
            f"program_profile_v2 is missing required column(s): {missing_meta_cols}.",
        )

    profile_dim_cols = {
        dim: _find_program_profile_dim_col(profile, dim)
        for dim in DIMS
    }
    if any(col is None for col in profile_dim_cols.values()):
        missing_dims = sorted(dim for dim, col in profile_dim_cols.items() if col is None)
        raise RecommenderError(
            "INVALID_PROGRAM_PROFILE_V2",
            f"program_profile_v2 is missing dimension score column(s) for: {missing_dims}.",
        )
    for col in sorted({col for col in profile_dim_cols.values() if col is not None}):
        numeric = pd.to_numeric(profile[col], errors="coerce")
        invalid = profile[col].notna() & numeric.isna()
        out_of_range = numeric.notna() & ((numeric < 0.0) | (numeric > 5.0))
        if invalid.any() or out_of_range.any():
            raise RecommenderError(
                "INVALID_PROGRAM_PROFILE_V2",
                f"program_profile_v2 contains invalid values in {col}; scores must be numeric and within [0, 5].",
            )
        profile[col] = numeric
    for col in required_meta_cols:
        if profile[col].isna().any():
            raise RecommenderError(
                "INVALID_PROGRAM_PROFILE_V2",
                f"program_profile_v2 contains null values in required column: {col}.",
            )

    keep_cols = [
        "program_id",
        "program_name",
        "program_code",
        "profile_version",
        "profile_method",
        "profile_confidence",
        "profile_family",
        "dominant_dim",
        "dominant_dim_label",
        "secondary_dims",
        "evidence_text",
        "evidence_sources",
        "review_status",
        "affinity_duration_score",
        *[col for col in profile_dim_cols.values() if col is not None],
    ]
    keep_cols = [col for col in keep_cols if col in profile.columns]
    merged = programs.copy().merge(
        profile[keep_cols],
        on="program_id",
        how="left",
        suffixes=("", "_profile_v2"),
    )
    missing_rows = merged["profile_version"].isna() if "profile_version" in merged.columns else pd.Series(True, index=merged.index)
    if missing_rows.any():
        missing_ids = merged.loc[missing_rows, "program_id"].astype(str).tolist()
        preview = missing_ids[:10]
        suffix = "" if len(missing_ids) <= 10 else f" (and {len(missing_ids) - 10} more)"
        raise RecommenderError(
            "PROGRAM_PROFILE_V2_REQUIRED",
            f"program_profile_v2 is missing row(s) for program_id(s): {preview}{suffix}.",
        )
    for dim in DIMS:
        profile_col = profile_dim_cols[dim]
        if profile_col is None:
            continue
        merged_profile_col = f"{profile_col}_profile_v2" if profile_col in programs.columns else profile_col
        if merged_profile_col in merged.columns:
            base_col = f"affinity_{dim}_score"
            if merged[merged_profile_col].isna().any():
                missing_ids = merged.loc[merged[merged_profile_col].isna(), "program_id"].astype(str).tolist()
                raise RecommenderError(
                    "INVALID_PROGRAM_PROFILE_V2",
                    f"program_profile_v2 has null {profile_col} values for program_id(s): {missing_ids}.",
                )
            merged[base_col] = merged[merged_profile_col]
    if "program_name_profile_v2" in merged.columns:
        merged["program_name"] = merged["program_name_profile_v2"].fillna(merged.get("program_name"))
    if "affinity_duration_score_profile_v2" in merged.columns:
        if merged["affinity_duration_score_profile_v2"].isna().any():
            missing_ids = merged.loc[merged["affinity_duration_score_profile_v2"].isna(), "program_id"].astype(str).tolist()
            raise RecommenderError(
                "INVALID_PROGRAM_PROFILE_V2",
                f"program_profile_v2 has null affinity_duration_score values for program_id(s): {missing_ids}.",
            )
        merged["affinity_duration_score"] = merged["affinity_duration_score_profile_v2"]
    return merged


def _find_program_profile_dim_col(profile: pd.DataFrame, dim: str) -> Optional[str]:
    candidates = [f"affinity_{dim}_score", f"program_profile_{dim}_score", f"{dim}_score", dim]
    for col in candidates:
        if col in profile.columns:
            return col
    return None


def _program_profile_dim_col(profile: pd.DataFrame, dim: str) -> str:
    return _find_program_profile_dim_col(profile, dim) or f"affinity_{dim}_score"


def _score_programs(
    *,
    programs: pd.DataFrame,
    student_vector: np.ndarray,
    student_norm: float,
    q12_response: str,
    q13_response: str,
    saturation: Optional[pd.DataFrame],
    barangay_row: pd.Series,
    warnings: list[str],
) -> pd.DataFrame:
    prog = programs.copy()
    rows = []
    for row in prog.itertuples(index=False):
        r = row._asdict()
        program_vector = _program_vector_from_row(r, prog, warnings)
        norm_p = float(np.linalg.norm(program_vector))
        if norm_p <= PROFILE_SCORE_EPSILON:
            continue
        dot = float(student_vector @ program_vector)
        cosine = dot / (student_norm * norm_p)
        shape_fit = _profile_shape_fit(student_vector, program_vector)
        direction_fit = max(float(cosine), 0.0)
        base_fit = (BASE_SHAPE_WEIGHT * shape_fit) + (BASE_DIRECTION_WEIGHT * direction_fit)
        profile_reliability_weight = _profile_reliability_weight(r.get("profile_confidence"))
        evidence_adjusted_fit = base_fit * profile_reliability_weight

        dominant_dim = _dominant_dim(program_vector)
        market_context = _market_context(dominant_dim, saturation, barangay_row, warnings)
        before_q12 = (PROGRAM_FIT_WEIGHT * evidence_adjusted_fit) + (MARKET_WEIGHT * market_context["market_score"])
        penalty_applied, score_after_q12 = _apply_q12(before_q12, q12_response, r)
        track_boost_factor, final_score = _apply_q13(score_after_q12, q13_response, dominant_dim)

        rows.append({
            "program_id": r["program_id"],
            "program_name": r.get("program_name") or r.get("program") or str(r["program_id"]),
            "program_vector": program_vector,
            "dominant_dim": dominant_dim,
            "base_fit_score": float(base_fit),
            "shape_fit_score": float(shape_fit),
            "direction_fit_score": float(direction_fit),
            "profile_reliability_weight": float(profile_reliability_weight),
            "evidence_adjusted_fit_score": float(evidence_adjusted_fit),
            "program_score_before_q12": float(before_q12),
            "program_score": float(final_score),
            "track_boost_applied": track_boost_factor != 1.0,
            "track_boost_factor": float(track_boost_factor),
            "market_context": market_context,
            "penalties_applied": ["Q12 duration/board-exam penalty (tiered)"] if penalty_applied else [],
            "program_profile": _program_profile_meta(r, dominant_dim),
        })

    return pd.DataFrame(rows).sort_values(
        ["program_score", "base_fit_score", "program_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _profile_shape_fit(student_vector: np.ndarray, program_vector: np.ndarray) -> float:
    if float(np.std(student_vector)) <= PROFILE_SCORE_EPSILON or float(np.std(program_vector)) <= PROFILE_SCORE_EPSILON:
        return 0.5
    corr = float(np.corrcoef(student_vector, program_vector)[0, 1])
    if np.isnan(corr):
        return 0.5
    return float(np.clip((corr + 1.0) / 2.0, 0.0, 1.0))


def _program_vector_from_row(row: dict, programs: pd.DataFrame, warnings: list[str]) -> np.ndarray:
    values = []
    for dim in DIMS:
        raw = row.get(_program_dim_col(programs, dim), 0.0)
        value = pd.to_numeric(pd.Series([raw]), errors="coerce").iloc[0]
        if pd.isna(value) or float(value) < 0.0 or float(value) > 5.0:
            _warn_once(warnings, "INVALID_PROGRAM_AFFINITY_SCORE")
            value = 0.0
        values.append(float(value))
    return np.array(values, dtype=float)


def _profile_reliability_weight(profile_confidence) -> float:
    value = _text_or_none(profile_confidence)
    if value is not None and value.lower() == "low":
        return LOW_PROFILE_CONFIDENCE_WEIGHT
    return 1.0


def _program_profile_meta(row: dict, dominant_dim: str) -> dict:
    return {
        "profile_version": _text_or_none(row.get("profile_version")),
        "profile_method": _text_or_none(row.get("profile_method")),
        "profile_confidence": _text_or_none(row.get("profile_confidence")),
        "profile_family": _text_or_none(row.get("profile_family")),
        "dominant_dim": _text_or_none(row.get("dominant_dim")) or dominant_dim,
        "dominant_dim_label": _text_or_none(row.get("dominant_dim_label")) or FIELD_LABELS[dominant_dim],
        "secondary_dims": _text_or_none(row.get("secondary_dims")),
        "evidence_text": _text_or_none(row.get("evidence_text")),
        "evidence_sources": _text_or_none(row.get("evidence_sources")),
        "review_status": _text_or_none(row.get("review_status")),
    }


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
    warnings: list[str],
    top_n: int,
) -> list[dict]:
    selected: list[dict] = []
    field_count: dict[str, int] = {}

    for row in program_scores.itertuples(index=False):
        candidate = row._asdict()
        dom = candidate["dominant_dim"]
        if field_count.get(dom, 0) >= 2:
            continue  # Already have 2 programmes from this field in the top set
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
            warnings,
        )
        if schools.empty:
            continue

        enriched = dict(candidate)
        enriched["primary_school"] = _school_dict(schools.iloc[0])
        enriched["alternate_schools"] = [_school_dict(s) for _, s in schools.iloc[1:].iterrows()]
        enriched["matched_dimensions"] = _matched_dimensions(student_vector, candidate["program_vector"])
        selected.append(enriched)
        field_count[dom] = field_count.get(dom, 0) + 1
        if len(selected) == top_n:
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
    warnings: list[str],
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
    burden_university_ids = set(burden["university_id"].dropna().astype(str))
    offered_university_ids = set(offered["university_id"].dropna().astype(str))
    if offered_university_ids - burden_university_ids:
        _warn_once(warnings, "PARTIAL_Q10_BURDEN_COVERAGE")
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
        "shape_fit_score": round(float(row["shape_fit_score"]), 6),
        "direction_fit_score": round(float(row["direction_fit_score"]), 6),
        "profile_reliability_weight": round(float(row["profile_reliability_weight"]), 6),
        "evidence_adjusted_fit_score": round(float(row["evidence_adjusted_fit_score"]), 6),
        "market_context": row["market_context"],
        "program_profile": row["program_profile"],
        "matched_dimensions": row["matched_dimensions"],
        "constraints_applied": {
            "q7_response": responses["Q7"],
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
        "track_boost_applied": bool(row["track_boost_applied"]),
        "track_boost_factor": float(row["track_boost_factor"]),
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


def _build_trace_rows(
    session_id: str,
    model_id: str,
    recommendations: list[dict],
    student_profile: dict,
    responses: dict,
    warnings: list[str],
) -> list[dict]:
    created = datetime.now(timezone.utc).isoformat()
    return [
        {
            "session_id": session_id,
            "model_id": model_id,
            "rank": rec["rank"],
            "program_id": rec["program_id"],
            "construct_scores": student_profile["construct_scores"],
            "constraints": {
                "q7_response": responses["Q7"],
                "q10_response": responses["Q10"],
                "q11_response": responses["Q11"],
                "q12_response": responses["Q12"],
                "q13_response": responses["Q13"],
            },
            "warnings": list(warnings),
            "explanation_json": {
                "matched_dimensions": rec["matched_dimensions"],
                "shape_fit_score": rec["shape_fit_score"],
                "direction_fit_score": rec["direction_fit_score"],
                "profile_reliability_weight": rec["profile_reliability_weight"],
                "evidence_adjusted_fit_score": rec["evidence_adjusted_fit_score"],
                "program_profile": rec["program_profile"],
                "market_context": rec["market_context"],
                "penalties_applied": rec["penalties_applied"],
                "track_boost_applied": rec["track_boost_applied"],
                "track_boost_factor": rec["track_boost_factor"],
                "low_confidence_flag": rec["low_confidence_flag"],
                "low_confidence_reason": rec["low_confidence_reason"],
            },
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
        overshoot = program_level - tolerance
        if overshoot >= 3:
            penalty = Q12_PENALTY_SEVERE
        elif overshoot == 2:
            penalty = Q12_PENALTY_MODERATE
        else:
            penalty = Q12_PENALTY_MILD
        return True, score * penalty
    return False, score


def _apply_q13(score: float, q13_response: str, dominant_dim: str) -> tuple[float, float]:
    track = Q13_MAP.get(q13_response, "none")
    fields = TRACK_ASPIRATION_FIELD_MAP.get(track, TRACK_ASPIRATION_FIELD_MAP["none"])
    if dominant_dim in fields["primary"]:
        factor = TRACK_ASPIRATION_PRIMARY_BOOST
    elif dominant_dim in fields["secondary"]:
        factor = TRACK_ASPIRATION_SECONDARY_BOOST
    else:
        factor = 1.0
    return factor, min(score * factor, 1.0)


def _score_col(df: pd.DataFrame, dim: str, *, question: bool) -> str:
    candidates = [f"{dim}_score"] if question else []
    candidates.extend([f"affinity_{dim}_score", dim])
    for col in candidates:
        if col in df.columns:
            return col
    raise RecommenderError("NO_CANDIDATES", f"Missing score column for {dim}.")


def _program_dim_col(programs: pd.DataFrame, dim: str) -> str:
    aliases = {
        "health": ["affinity_health_science_score"],
        "arts": ["affinity_art_humanities_score"],
    }
    for col in [f"affinity_{dim}_score", *aliases.get(dim, []), f"{dim}_score", dim]:
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


def _low_confidence(selected: list[dict], student_vector: np.ndarray, student_norm: float) -> tuple[bool, Optional[str]]:
    if student_norm < LOW_SIGNAL_FLAG:
        return True, "LOW_SIGNAL"
    if float(np.std(student_vector)) < LOW_SPECIFICITY_STD:
        return True, "LOW_SPECIFICITY_PROFILE"
    spread = float(selected[0]["program_score"]) - float(selected[-1]["program_score"])
    if spread < TIE_ZONE_SPREAD:
        return True, "CLOSE_RANKING"
    return False, None


def _normalize_0_1(values: np.ndarray) -> np.ndarray:
    max_value = float(np.max(values))
    if max_value <= 0.0:
        return values
    return values / max_value


def _vector_dict(values: np.ndarray) -> dict[str, float]:
    return {dim: round(float(values[i]), 6) for i, dim in enumerate(DIMS)}


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


def _text_or_none(value) -> Optional[str]:
    if value is None:
        return None
    try:
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def _warn_once(warnings: list[str], code: str) -> None:
    if code not in warnings:
        warnings.append(code)
