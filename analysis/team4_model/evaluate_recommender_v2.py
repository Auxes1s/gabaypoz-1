"""Evaluation harness for the GabayPoz recommender v2.

Computes Module A (construct validity: Cronbach's alpha and item-total
correlations per affinity field) and Module B (outcome metrics: precision@3,
acceptance rate, mean relevance, confidence shift, field fairness, calibration,
trace/feedback completeness, and aspiration-track boost checks) from pilot data
or a synthetic fixture.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


DIMS = ["stem", "health", "arts", "business", "education", "agriculture"]
DIM_LABELS = ["STEM", "Health", "Arts", "Business", "Education", "Agriculture"]
ITEMS_PER_FIELD = 4
ALPHA_MIN_ACCEPTABLE = 0.65
ITEM_TOTAL_CORR_MIN = 0.30
PRECISION_FIELD_MIN = 0.70
ACCEPTANCE_TARGET = 0.75
RELEVANCE_TARGET = 3.5
FAIRNESS_MIN_SHARE = 0.05

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO / "reports" / "model"

TRACE_COLUMNS = [
    "session_id",
    "rank",
    "program_name",
    "dominant_dim",
    "model_score",
    "low_confidence_flag",
    "low_confidence_reason",
    "constraints",
    "explanation_json",
]
FEEDBACK_COLUMNS = [
    "session_id",
    "stated_choice_field",
    "stated_choice_program",
    "would_consider_any",
    "relevance_score",
    "pre_confidence",
    "post_confidence",
    "confidence_shift",
    "surprise_program_text",
    "missing_program_text",
    "acceptance_choice",
    "followup_consent",
]
ITEM_ROW_COLUMNS = [
    "session_id",
    "question_code",
    "target_field",
    "construct_family",
    "response_value",
    "rescaled_value",
]


# ---------------------------------------------------------------------------
# Module A — Construct validity
# ---------------------------------------------------------------------------

def cronbach_alpha(item_matrix: np.ndarray) -> float:
    """Compute Cronbach's alpha for a (N_students, k_items) matrix."""
    n, k = item_matrix.shape
    if n < 2 or k < 2:
        return float("nan")
    item_vars = item_matrix.var(axis=0, ddof=1)
    row_sums = item_matrix.sum(axis=1)
    total_var = row_sums.var(ddof=1)
    if total_var <= 0:
        return float("nan")
    return (k / (k - 1)) * (1.0 - item_vars.sum() / total_var)


def _rows_to_frame(rows: list[dict], expected_columns: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in expected_columns:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    return df


def _json_obj(value) -> dict:
    if isinstance(value, dict):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _extract_nested(row: pd.Series, direct_col: str, json_col: str, *keys: str):
    if direct_col in row.index and pd.notna(row[direct_col]):
        return row[direct_col]
    obj = _json_obj(row.get(json_col))
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def _coerce_boolish(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return 1
    if text in {"0", "false", "f", "no", "n"}:
        return 0
    return np.nan


def normalize_feedback_rows(feedback_rows: list[dict]) -> pd.DataFrame:
    """Return feedback rows with stable pilot-evaluation columns.

    This is the API/export contract expected from the pilot feedback table. It
    accepts partial exports so early pilot extracts can be audited without
    crashing.
    """
    df = _rows_to_frame(feedback_rows, FEEDBACK_COLUMNS)
    df["would_consider_any"] = df["would_consider_any"].map(_coerce_boolish)
    from_choice = df["acceptance_choice"].astype(str).str.upper().map({"A": 1, "B": 1, "C": 0, "D": 0, "E": 0})
    df["would_consider_any"] = df["would_consider_any"].fillna(from_choice)
    for col in ["relevance_score", "pre_confidence", "post_confidence", "confidence_shift"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    missing_shift = df["confidence_shift"].isna() & df["pre_confidence"].notna() & df["post_confidence"].notna()
    df.loc[missing_shift, "confidence_shift"] = (
        df.loc[missing_shift, "post_confidence"] - df.loc[missing_shift, "pre_confidence"]
    )
    return df


def normalize_trace_rows(trace_rows: list[dict]) -> pd.DataFrame:
    """Return trace rows with derived strand and aspiration boost columns."""
    df = _rows_to_frame(trace_rows, TRACE_COLUMNS)
    if df.empty:
        df["q7_response"] = pd.Series(dtype="object")
        df["q13_response"] = pd.Series(dtype="object")
        df["track_boost_applied"] = pd.Series(dtype="object")
        df["track_boost_factor"] = pd.Series(dtype="float")
        return df

    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    df["q7_response"] = df.apply(
        lambda row: _extract_nested(row, "q7_response", "constraints", "q7_response", "q7"),
        axis=1,
    )
    df["q13_response"] = df.apply(
        lambda row: _extract_nested(row, "q13_response", "constraints", "q13_response", "q13"),
        axis=1,
    )
    df["track_boost_applied"] = df.apply(
        lambda row: _extract_nested(row, "track_boost_applied", "explanation_json", "track_boost_applied"),
        axis=1,
    )
    df["track_boost_factor"] = pd.to_numeric(
        df.apply(
            lambda row: _extract_nested(row, "track_boost_factor", "explanation_json", "track_boost_factor"),
            axis=1,
        ),
        errors="coerce",
    )
    return df


def item_total_correlations(item_matrix: np.ndarray) -> np.ndarray:
    """Compute corrected item-total correlations for each item column."""
    n, k = item_matrix.shape
    result = np.full(k, float("nan"))
    for i in range(k):
        x = item_matrix[:, i]
        rest = item_matrix[:, [j for j in range(k) if j != i]].sum(axis=1)
        std_x = x.std()
        std_rest = rest.std()
        if std_x == 0 or std_rest == 0:
            continue
        cov = np.mean(x * rest) - np.mean(x) * np.mean(rest)
        result[i] = cov / (std_x * std_rest)
    return result


def construct_validity_report(item_rows: list[dict]) -> dict:
    """Compute alpha and item-total correlations per affinity field."""
    df = _rows_to_frame(item_rows, ITEM_ROW_COLUMNS)
    if df["target_field"].dropna().empty:
        return {
            "per_field": {},
            "summary": {
                "fields_passing_alpha": 0,
                "total_flagged_items": 0,
            },
        }
    per_field: dict[str, dict] = {}
    for dim in DIMS:
        sub = df[df["target_field"] == dim].copy()
        if sub.empty:
            warnings.warn(f"No item rows found for field '{dim}'; skipping.")
            continue
        sub = sub.sort_values("question_code")
        pivot = sub.pivot_table(
            index="session_id",
            columns="question_code",
            values="rescaled_value",
            aggfunc="first",
        )
        pivot = pivot.dropna()
        mat = pivot.values
        alpha = cronbach_alpha(mat)
        itc = item_total_correlations(mat)
        codes = list(pivot.columns)
        flagged = [
            codes[i]
            for i, c in enumerate(itc)
            if not np.isnan(c) and c < ITEM_TOTAL_CORR_MIN
        ]
        per_field[dim] = {
            "n_students": int(mat.shape[0]),
            "alpha": float(alpha),
            "alpha_acceptable": bool(not np.isnan(alpha) and alpha >= ALPHA_MIN_ACCEPTABLE),
            "item_total_correlations": [float(c) for c in itc],
            "flagged_items": flagged,
        }
    fields_passing = sum(1 for v in per_field.values() if v["alpha_acceptable"])
    total_flagged = sum(len(v["flagged_items"]) for v in per_field.values())
    return {
        "per_field": per_field,
        "summary": {
            "fields_passing_alpha": fields_passing,
            "total_flagged_items": total_flagged,
        },
    }


# ---------------------------------------------------------------------------
# Module B — Outcome metrics
# ---------------------------------------------------------------------------

def precision_at_3(
    trace_rows: list[dict],
    feedback_rows: list[dict],
    match: str = "field",
) -> dict:
    """Compute precision@3 using field or program match."""
    traces = normalize_trace_rows(trace_rows)
    feedback = normalize_feedback_rows(feedback_rows)

    if match == "field":
        gt_col = "stated_choice_field"
        rec_col = "dominant_dim"
    else:
        gt_col = "stated_choice_program"
        rec_col = "program_name"

    eligible = feedback[feedback[gt_col].notna()].copy()
    n_gt = len(eligible)
    if n_gt == 0:
        return {
            "n_sessions_with_ground_truth": 0,
            "n_hits": 0,
            "precision_at_3": float("nan"),
            "target": PRECISION_FIELD_MIN if match == "field" else None,
            "meets_target": None,
        }

    hits = 0
    for _, row in eligible.iterrows():
        sid = row["session_id"]
        ground_truth = row[gt_col]
        recs = traces[traces["session_id"] == sid][rec_col].tolist()
        if ground_truth in recs:
            hits += 1

    p3 = hits / n_gt
    target = PRECISION_FIELD_MIN if match == "field" else None
    meets = (p3 >= target) if target is not None else None
    return {
        "n_sessions_with_ground_truth": n_gt,
        "n_hits": hits,
        "precision_at_3": float(p3),
        "target": target,
        "meets_target": meets,
    }


def acceptance_rate(feedback_rows: list[dict]) -> dict:
    """Compute overall acceptance rate from feedback rows."""
    df = normalize_feedback_rows(feedback_rows)
    n = len(df)
    values = pd.to_numeric(df["would_consider_any"], errors="coerce").fillna(0)
    n_accepting = int(values.sum())
    rate = n_accepting / n if n > 0 else float("nan")
    return {
        "n_sessions": n,
        "n_accepting": n_accepting,
        "acceptance_rate": float(rate),
        "target": ACCEPTANCE_TARGET,
        "meets_target": bool(not np.isnan(rate) and rate >= ACCEPTANCE_TARGET),
    }


def mean_relevance(feedback_rows: list[dict]) -> dict:
    """Compute mean relevance score from feedback rows (excludes NaN)."""
    df = normalize_feedback_rows(feedback_rows)
    scores = pd.to_numeric(df["relevance_score"], errors="coerce").dropna()
    n = len(scores)
    if n == 0:
        return {
            "n_sessions": 0,
            "mean": float("nan"),
            "std": float("nan"),
            "target": RELEVANCE_TARGET,
            "meets_target": None,
        }
    m = float(scores.mean())
    s = float(scores.std(ddof=1)) if n > 1 else float("nan")
    return {
        "n_sessions": n,
        "mean": m,
        "std": s,
        "target": RELEVANCE_TARGET,
        "meets_target": bool(m >= RELEVANCE_TARGET),
    }


def mean_confidence_shift(feedback_rows: list[dict]) -> dict:
    """Compute mean confidence shift from feedback rows (excludes NaN)."""
    df = normalize_feedback_rows(feedback_rows)
    shifts = pd.to_numeric(df["confidence_shift"], errors="coerce").dropna()
    n = len(shifts)
    if n == 0:
        return {
            "n_sessions": 0,
            "mean": float("nan"),
            "std": float("nan"),
            "positive_shift": None,
        }
    m = float(shifts.mean())
    s = float(shifts.std(ddof=1)) if n > 1 else float("nan")
    return {
        "n_sessions": n,
        "mean": m,
        "std": s,
        "positive_shift": bool(m > 0),
    }


def field_fairness(trace_rows: list[dict]) -> dict:
    """Compute rank-1 and top-3 field shares; flag under-represented fields."""
    df = normalize_trace_rows(trace_rows)
    rank1 = df[df["rank"] == 1].copy()
    top3 = df[df["rank"].isin([1, 2, 3])].copy()

    def _shares(sub: pd.DataFrame) -> tuple[int, dict[str, float], list[str]]:
        total = len(sub)
        per_field: dict[str, float] = {}
        for dim in DIMS:
            count = int((sub["dominant_dim"] == dim).sum())
            per_field[dim] = count / total if total > 0 else float("nan")
        flagged = [
            dim
            for dim, share in per_field.items()
            if not np.isnan(share) and share < FAIRNESS_MIN_SHARE
        ]
        return total, per_field, flagged

    rank1_total, rank1_share, rank1_flagged = _shares(rank1)
    top3_total, top3_share, top3_flagged = _shares(top3)
    return {
        "n_rank1_recommendations": rank1_total,
        "per_field_share": rank1_share,
        "flagged_fields": rank1_flagged,
        "n_top3_recommendations": top3_total,
        "top3_per_field_share": top3_share,
        "top3_flagged_fields": top3_flagged,
    }


def strand_field_fairness(trace_rows: list[dict]) -> dict:
    """Compute top-3 field distribution by SHS strand."""
    df = normalize_trace_rows(trace_rows)
    top3 = df[df["rank"].isin([1, 2, 3]) & df["q7_response"].notna()].copy()
    if top3.empty:
        return {"per_strand": {}, "flagged_strands": []}

    per_strand: dict[str, dict] = {}
    flagged: list[str] = []
    for strand, sub in top3.groupby(top3["q7_response"].astype(str)):
        total = len(sub)
        shares = {}
        nonzero_fields = 0
        for dim in DIMS:
            count = int((sub["dominant_dim"] == dim).sum())
            share = count / total if total > 0 else float("nan")
            shares[dim] = share
            if count > 0:
                nonzero_fields += 1
        exclusively_one_field = nonzero_fields <= 1 and total > 0
        if exclusively_one_field:
            flagged.append(str(strand))
        per_strand[str(strand)] = {
            "n_top3_recommendations": total,
            "top3_per_field_share": shares,
            "exclusive_one_field": exclusively_one_field,
        }
    return {"per_strand": per_strand, "flagged_strands": flagged}


def feedback_completeness(feedback_rows: list[dict]) -> dict:
    """Report missingness for the pilot feedback contract."""
    df = normalize_feedback_rows(feedback_rows)
    required = [
        "session_id",
        "stated_choice_field",
        "would_consider_any",
        "relevance_score",
        "confidence_shift",
    ]
    missing_by_column = {
        col: int(df[col].isna().sum()) if col in df.columns else len(df)
        for col in required
    }
    complete_mask = pd.Series(True, index=df.index)
    for col in required:
        complete_mask &= df[col].notna()
    return {
        "n_feedback_rows": int(len(df)),
        "n_complete_feedback_rows": int(complete_mask.sum()),
        "missing_by_column": missing_by_column,
    }


def trace_completeness(trace_rows: list[dict], feedback_rows: list[dict]) -> dict:
    """Check whether sessions have three trace rows and feedback rows."""
    traces = normalize_trace_rows(trace_rows)
    feedback = normalize_feedback_rows(feedback_rows)
    if "session_id" in traces.columns and not traces.empty:
        trace_counts = traces.assign(_session_id_str=traces["session_id"].astype(str)).groupby("_session_id_str").size()
    else:
        trace_counts = pd.Series(dtype=int)
    trace_sessions = set(trace_counts.index.astype(str))
    feedback_sessions = set(feedback["session_id"].dropna().astype(str))
    all_sessions = sorted(trace_sessions | feedback_sessions)
    complete_sessions = [
        sid for sid in all_sessions
        if int(trace_counts.get(sid, 0)) >= 3 and sid in feedback_sessions
    ]
    return {
        "n_sessions": len(all_sessions),
        "n_sessions_with_3_traces": int((trace_counts >= 3).sum()),
        "n_sessions_with_feedback": len(feedback_sessions),
        "n_complete_sessions": len(complete_sessions),
        "missing_trace_sessions": [sid for sid in all_sessions if int(trace_counts.get(sid, 0)) < 3],
        "missing_feedback_sessions": [sid for sid in all_sessions if sid not in feedback_sessions],
    }


def aspiration_boost_acceptance(trace_rows: list[dict], feedback_rows: list[dict]) -> dict:
    """Compare acceptance for sessions with and without an applied V2Q29 boost."""
    traces = normalize_trace_rows(trace_rows)
    feedback = normalize_feedback_rows(feedback_rows)
    if traces.empty or feedback.empty:
        return {
            "n_boosted_sessions": 0,
            "n_not_boosted_sessions": 0,
            "acceptance_rate_boosted": None,
            "acceptance_rate_not_boosted": None,
        }
    boosted_sessions = set(
        traces[
            (traces["track_boost_applied"] == True)  # noqa: E712
            | (pd.to_numeric(traces["track_boost_factor"], errors="coerce").fillna(1.0) > 1.0)
        ]["session_id"].dropna().astype(str)
    )
    feedback = feedback[feedback["session_id"].notna()].copy()
    feedback["_session_id_str"] = feedback["session_id"].astype(str)

    def _rate(mask: pd.Series) -> Optional[float]:
        sub = feedback[mask]
        if sub.empty:
            return None
        return float(pd.to_numeric(sub["would_consider_any"], errors="coerce").fillna(0).sum() / len(sub))

    boosted_mask = feedback["_session_id_str"].isin(boosted_sessions)
    return {
        "n_boosted_sessions": int(boosted_mask.sum()),
        "n_not_boosted_sessions": int((~boosted_mask).sum()),
        "acceptance_rate_boosted": _rate(boosted_mask),
        "acceptance_rate_not_boosted": _rate(~boosted_mask),
    }


def calibration_check(
    trace_rows: list[dict],
    feedback_rows: list[dict],
) -> dict:
    """Compare acceptance rates for flagged vs. non-flagged sessions."""
    traces = normalize_trace_rows(trace_rows)
    feedback = normalize_feedback_rows(feedback_rows)

    flagged_sessions = set(
        traces[traces["low_confidence_flag"] == True]["session_id"].unique()
    )

    flagged_fb = feedback[feedback["session_id"].isin(flagged_sessions)]
    not_flagged_fb = feedback[~feedback["session_id"].isin(flagged_sessions)]

    def _rate(sub: pd.DataFrame) -> Optional[float]:
        if len(sub) == 0:
            return None
        values = pd.to_numeric(sub["would_consider_any"], errors="coerce").fillna(0)
        return float(values.sum() / len(sub))

    flagged_rate = _rate(flagged_fb)
    not_flagged_rate = _rate(not_flagged_fb)

    if flagged_rate is not None and not_flagged_rate is not None:
        flags_correlate_with_lower = bool(flagged_rate < not_flagged_rate)
    else:
        flags_correlate_with_lower = None

    return {
        "n_flagged_sessions": len(flagged_fb),
        "n_not_flagged_sessions": len(not_flagged_fb),
        "acceptance_rate_flagged": flagged_rate,
        "acceptance_rate_not_flagged": not_flagged_rate,
        "flags_correlate_with_lower_acceptance": flags_correlate_with_lower,
    }


def outcome_metrics_report(
    trace_rows: list[dict],
    feedback_rows: list[dict],
) -> dict:
    """Assemble all Module B outcome metrics into a single dict."""
    return {
        "precision_field": precision_at_3(trace_rows, feedback_rows, match="field"),
        "precision_program": precision_at_3(trace_rows, feedback_rows, match="program"),
        "acceptance": acceptance_rate(feedback_rows),
        "relevance": mean_relevance(feedback_rows),
        "confidence_shift": mean_confidence_shift(feedback_rows),
        "field_fairness": field_fairness(trace_rows),
        "strand_field_fairness": strand_field_fairness(trace_rows),
        "calibration": calibration_check(trace_rows, feedback_rows),
        "feedback_completeness": feedback_completeness(feedback_rows),
        "trace_completeness": trace_completeness(trace_rows, feedback_rows),
        "aspiration_boost_acceptance": aspiration_boost_acceptance(trace_rows, feedback_rows),
    }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt(value: object, decimals: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        if np.isnan(value):
            return "nan"
        return f"{value:.{decimals}f}"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def write_report(
    construct_result: dict,
    outcome_result: dict,
    output_dir: Path,
    *,
    data_source: str = "pilot_export",
) -> None:
    """Write evaluation JSON and markdown report to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    full = {
        "data_source": data_source,
        "synthetic_fixture": data_source == "synthetic_fixture",
        "construct_validity": construct_result,
        "outcome_metrics": outcome_result,
    }
    json_path = output_dir / "recommender_v2_evaluation.json"
    json_path.write_text(json.dumps(full, indent=2, default=str))

    lines: list[str] = ["# Recommender v2 Evaluation Report", ""]
    if data_source == "synthetic_fixture":
        lines += [
            "> Synthetic fixture report. These numbers test the reporting pipeline only and must not be presented as pilot validation evidence.",
            "",
        ]
    else:
        lines += [f"Data source: `{data_source}`", ""]

    # Construct validity section
    lines += ["## Construct Validity", ""]
    lines += [
        f"Fields passing alpha (≥{ALPHA_MIN_ACCEPTABLE}): "
        f"**{construct_result['summary']['fields_passing_alpha']}** / {len(DIMS)}",
        f"Total flagged items (corr < {ITEM_TOTAL_CORR_MIN}): "
        f"**{construct_result['summary']['total_flagged_items']}**",
        "",
    ]
    lines += [
        "| Field | N | Alpha | Acceptable | Flagged Items |",
        "|-------|---|-------|------------|---------------|",
    ]
    for dim in DIMS:
        if dim not in construct_result["per_field"]:
            lines.append(f"| {dim} | — | — | — | — |")
            continue
        fd = construct_result["per_field"][dim]
        flagged_str = ", ".join(fd["flagged_items"]) if fd["flagged_items"] else "none"
        lines.append(
            f"| {dim} | {fd['n_students']} | {_fmt(fd['alpha'])} "
            f"| {_fmt(fd['alpha_acceptable'])} | {flagged_str} |"
        )
    lines.append("")

    # Item-total correlations sub-table
    lines += ["### Item-Total Correlations", ""]
    header_dims = [
        dim for dim in DIMS if dim in construct_result["per_field"]
    ]
    if header_dims:
        item_header = "| Item | " + " | ".join(header_dims) + " |"
        item_sep = "|------|" + "|".join(["------"] * len(header_dims)) + "|"
        lines += [item_header, item_sep]
        for i in range(ITEMS_PER_FIELD):
            vals = []
            for dim in header_dims:
                itc = construct_result["per_field"][dim]["item_total_correlations"]
                vals.append(_fmt(itc[i]) if i < len(itc) else "—")
            lines.append(f"| item {i+1} | " + " | ".join(vals) + " |")
        lines.append("")

    # Outcome metrics section
    lines += ["## Outcome Metrics", ""]

    acc = outcome_result["acceptance"]
    rel = outcome_result["relevance"]
    cs = outcome_result["confidence_shift"]
    p3f = outcome_result["precision_field"]
    p3p = outcome_result["precision_program"]

    lines += [
        "| Metric | Value | Target | Meets Target |",
        "|--------|-------|--------|--------------|",
        f"| Precision@3 (field) | {_fmt(p3f['precision_at_3'])} "
        f"| {_fmt(p3f['target'])} | {_fmt(p3f['meets_target'])} |",
        f"| Precision@3 (program) | {_fmt(p3p['precision_at_3'])} | — | — |",
        f"| Acceptance rate | {_fmt(acc['acceptance_rate'])} "
        f"| {_fmt(acc['target'])} | {_fmt(acc['meets_target'])} |",
        f"| Mean relevance | {_fmt(rel['mean'])} "
        f"| {_fmt(rel['target'])} | {_fmt(rel['meets_target'])} |",
        f"| Mean confidence shift | {_fmt(cs['mean'])} | — | {_fmt(cs['positive_shift'])} |",
        "",
    ]

    ff = outcome_result["field_fairness"]
    lines += ["### Field Fairness (rank-1 share)", ""]
    lines += [
        "| Field | Share | Flagged |",
        "|-------|-------|---------|",
    ]
    for dim in DIMS:
        share = ff["per_field_share"].get(dim, float("nan"))
        flagged = dim in ff["flagged_fields"]
        lines.append(f"| {dim} | {_fmt(share)} | {_fmt(flagged)} |")
    lines.append("")

    lines += ["### Field Fairness (top-3 share)", ""]
    lines += [
        "| Field | Share | Flagged |",
        "|-------|-------|---------|",
    ]
    for dim in DIMS:
        share = ff["top3_per_field_share"].get(dim, float("nan"))
        flagged = dim in ff["top3_flagged_fields"]
        lines.append(f"| {dim} | {_fmt(share)} | {_fmt(flagged)} |")
    lines.append("")

    strand = outcome_result["strand_field_fairness"]
    lines += ["### Strand Fairness (top-3 share)", ""]
    if not strand["per_strand"]:
        lines += ["No strand-tagged trace rows available.", ""]
    else:
        lines += [
            "| Strand | N top-3 rows | Exclusive one field |",
            "|--------|--------------|---------------------|",
        ]
        for strand_name, data in sorted(strand["per_strand"].items()):
            lines.append(
                f"| {strand_name} | {data['n_top3_recommendations']} | "
                f"{_fmt(data['exclusive_one_field'])} |"
            )
        lines.append("")

    cal = outcome_result["calibration"]
    lines += [
        "### Calibration",
        "",
        f"- Flagged sessions: {cal['n_flagged_sessions']} — "
        f"acceptance {_fmt(cal['acceptance_rate_flagged'])}",
        f"- Non-flagged sessions: {cal['n_not_flagged_sessions']} — "
        f"acceptance {_fmt(cal['acceptance_rate_not_flagged'])}",
        f"- Flags correlate with lower acceptance: "
        f"**{_fmt(cal['flags_correlate_with_lower_acceptance'])}**",
        "",
    ]

    complete = outcome_result["trace_completeness"]
    feedback = outcome_result["feedback_completeness"]
    boost = outcome_result["aspiration_boost_acceptance"]
    lines += [
        "### Pilot Readiness Checks",
        "",
        f"- Complete sessions (3 traces + feedback): {complete['n_complete_sessions']} / {complete['n_sessions']}",
        f"- Complete feedback rows: {feedback['n_complete_feedback_rows']} / {feedback['n_feedback_rows']}",
        f"- V2Q29 boosted sessions: {boost['n_boosted_sessions']} — acceptance {_fmt(boost['acceptance_rate_boosted'])}",
        f"- Non-boosted sessions: {boost['n_not_boosted_sessions']} — acceptance {_fmt(boost['acceptance_rate_not_boosted'])}",
        "",
    ]

    md_path = output_dir / "recommender_v2_evaluation.md"
    md_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------

def _synthetic_fixture() -> tuple[list[dict], list[dict], list[dict]]:
    """Generate deterministic synthetic pilot data for N=30 students."""
    rng = np.random.default_rng(42)
    N = 30
    question_blueprint: list[tuple[str, str, str]] = []
    qnum = 1
    for field in DIMS:
        for family in [
            "domain_interest",
            "domain_interest",
            "domain_self_efficacy",
            "domain_self_efficacy",
        ]:
            question_blueprint.append((f"V2Q{qnum:02d}", field, family))
            qnum += 1

    item_rows: list[dict] = []
    for student_idx in range(N):
        sid = f"S{student_idx:03d}"
        field_offsets = rng.uniform(-0.5, 0.5, len(DIMS))
        for q_idx, (qcode, field, family) in enumerate(question_blueprint):
            dim_idx = DIMS.index(field)
            base = rng.uniform(2.0, 4.0)
            response_value = float(
                np.clip(
                    round(base + field_offsets[dim_idx] + rng.normal(0, 0.3)),
                    1,
                    5,
                )
            )
            rescaled = (response_value - 1.0) / 4.0
            item_rows.append(
                {
                    "session_id": sid,
                    "question_code": qcode,
                    "target_field": field,
                    "construct_family": family,
                    "response_value": response_value,
                    "rescaled_value": rescaled,
                }
            )

    rank1_dims = rng.choice(DIMS, size=N)
    rank2_dims = rng.choice(DIMS, size=N)
    rank3_dims = rng.choice(DIMS, size=N)

    trace_rows: list[dict] = []
    for student_idx in range(N):
        sid = f"S{student_idx:03d}"
        for rank, dominant_dim in enumerate(
            [rank1_dims[student_idx], rank2_dims[student_idx], rank3_dims[student_idx]],
            start=1,
        ):
            score = float(rng.uniform(0.5, 1.0))
            low_flag = bool(score < 0.55)
            boost_applied = bool(rank == 1 and rng.random() < 0.25)
            trace_rows.append(
                {
                    "session_id": sid,
                    "rank": rank,
                    "program_name": f"{dominant_dim.title()} Program {rank}",
                    "dominant_dim": dominant_dim,
                    "model_score": score,
                    "low_confidence_flag": low_flag,
                    "low_confidence_reason": "low_signal" if low_flag else None,
                    "constraints": json.dumps({
                        "q7_response": str(rng.choice(["STEM", "ABM", "HUMSS", "TVL", "GAS"])),
                        "q13_response": str(rng.choice(["A", "B", "C", "D"])),
                    }),
                    "explanation_json": json.dumps({
                        "dim": dominant_dim,
                        "track_boost_applied": boost_applied,
                        "track_boost_factor": 1.12 if boost_applied else 1.0,
                    }),
                }
            )

    feedback_rows: list[dict] = []
    for student_idx in range(N):
        sid = f"S{student_idx:03d}"
        would_consider = bool(rng.random() < 0.60)
        relevance = float(rng.uniform(2.0, 5.0))
        conf_shift = float(rng.uniform(-1.0, 2.0))
        pre_conf = float(rng.integers(1, 6))
        post_conf = float(np.clip(pre_conf + round(conf_shift), 1, 5))
        stated_field = (
            str(rng.choice(DIMS)) if rng.random() < 0.50 else None
        )
        feedback_rows.append(
            {
                "session_id": sid,
                "stated_choice_field": stated_field,
                "stated_choice_program": None,
                "would_consider_any": would_consider,
                "relevance_score": relevance,
                "pre_confidence": pre_conf,
                "post_confidence": post_conf,
                "confidence_shift": conf_shift,
                "surprise_program_text": None,
                "missing_program_text": None,
                "acceptance_choice": "B" if would_consider else "D",
                "followup_consent": bool(rng.random() < 0.50),
            }
        )

    return item_rows, trace_rows, feedback_rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_rows(path: str) -> list[dict]:
    df = pd.read_csv(path)
    return df.to_dict(orient="records")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate GabayPoz recommender v2."
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Run against synthetic fixture instead of real data.",
    )
    parser.add_argument("--item-rows", metavar="CSV", help="Path to item-response CSV.")
    parser.add_argument("--trace-rows", metavar="CSV", help="Path to trace rows CSV.")
    parser.add_argument("--feedback-rows", metavar="CSV", help="Path to feedback rows CSV.")
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    if args.fixture:
        print("Running against synthetic fixture (N=30 students) ...")
        item_rows, trace_rows, feedback_rows = _synthetic_fixture()
        data_source = "synthetic_fixture"
    else:
        if not (args.item_rows and args.trace_rows and args.feedback_rows):
            parser.error(
                "Provide --item-rows, --trace-rows, and --feedback-rows, or use --fixture."
            )
        item_rows = _load_rows(args.item_rows)
        trace_rows = _load_rows(args.trace_rows)
        feedback_rows = _load_rows(args.feedback_rows)
        data_source = "pilot_export"

    construct_result = construct_validity_report(item_rows)
    outcome_result = outcome_metrics_report(trace_rows, feedback_rows)
    write_report(construct_result, outcome_result, output_dir, data_source=data_source)

    summary = construct_result["summary"]
    acc = outcome_result["acceptance"]
    print(
        f"Construct validity: {summary['fields_passing_alpha']}/{len(DIMS)} fields pass alpha, "
        f"{summary['total_flagged_items']} flagged items."
    )
    print(
        f"Outcome metrics: acceptance={acc['acceptance_rate']:.2f} "
        f"(target={ACCEPTANCE_TARGET}), "
        f"precision@3(field)={outcome_result['precision_field']['precision_at_3']:.2f}."
    )
    print(f"Reports written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
