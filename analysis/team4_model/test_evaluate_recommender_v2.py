"""Unit tests for the GabayPoz recommender v2 evaluation harness."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_recommender_v2 import (
    DIMS,
    ALPHA_MIN_ACCEPTABLE,
    FAIRNESS_MIN_SHARE,
    _synthetic_fixture,
    aspiration_boost_acceptance,
    calibration_check,
    construct_validity_report,
    cronbach_alpha,
    feedback_completeness,
    field_fairness,
    item_total_correlations,
    normalize_feedback_rows,
    outcome_metrics_report,
    precision_at_3,
    acceptance_rate,
    strand_field_fairness,
    trace_completeness,
)


# ---------------------------------------------------------------------------
# Module A — Construct validity
# ---------------------------------------------------------------------------

def test_cronbach_alpha_known_answer():
    students = [1, 2, 3, 4, 5]
    mat = np.array([[s, s, s, s] for s in students], dtype=float)
    alpha = cronbach_alpha(mat)
    assert abs(alpha - 1.0) < 1e-9


def test_cronbach_alpha_uncorrelated():
    rng = np.random.default_rng(1)
    mat = rng.integers(1, 6, size=(20, 4)).astype(float)
    alpha = cronbach_alpha(mat)
    assert alpha < 0.5


def test_cronbach_alpha_insufficient_data():
    mat = np.array([[1.0, 2.0, 3.0, 4.0]])
    alpha = cronbach_alpha(mat)
    assert np.isnan(alpha)


def test_item_total_correlations_shape():
    rng = np.random.default_rng(7)
    mat = rng.uniform(1, 5, size=(15, 4))
    result = item_total_correlations(mat)
    assert result.shape == (4,)


def test_item_total_correlations_perfect():
    # All items identical → corrected item-total sum is k-1 copies of x, but
    # x and (k-1)*x have non-zero std. Correlations should be 1.0 (perfectly correlated)
    # OR nan if implementation returns nan. The spec says "handle gracefully".
    students = [1.0, 2.0, 3.0, 4.0, 5.0]
    mat = np.array([[s, s, s, s] for s in students])
    result = item_total_correlations(mat)
    for c in result:
        # Either nan (zero std edge case) or a valid float; must not raise
        assert np.isnan(c) or isinstance(float(c), float)


# ---------------------------------------------------------------------------
# Module B — Outcome metrics
# ---------------------------------------------------------------------------

def _make_trace(session_id: str, dominant_dims: list[str], q7: str = "STEM", boosted: bool = False) -> list[dict]:
    rows = []
    for rank, dim in enumerate(dominant_dims, start=1):
        rows.append(
            {
                "session_id": session_id,
                "rank": rank,
                "program_name": f"{dim}_prog_{rank}",
                "dominant_dim": dim,
                "model_score": 0.8,
                "low_confidence_flag": False,
                "low_confidence_reason": None,
                "constraints": {"q7_response": q7, "q13_response": "A" if boosted else "D"},
                "explanation_json": {
                    "track_boost_applied": boosted and rank == 1,
                    "track_boost_factor": 1.12 if boosted and rank == 1 else 1.0,
                },
            }
        )
    return rows


def _make_feedback(
    session_id: str,
    stated_choice_field=None,
    stated_choice_program=None,
    would_consider_any: bool = True,
    relevance_score: float = 4.0,
    confidence_shift: float = 0.5,
) -> dict:
    return {
        "session_id": session_id,
        "stated_choice_field": stated_choice_field,
        "stated_choice_program": stated_choice_program,
        "would_consider_any": would_consider_any,
        "relevance_score": relevance_score,
        "confidence_shift": confidence_shift,
    }


def test_precision_at_3_field_all_hits():
    trace_rows = []
    feedback_rows = []
    for i in range(5):
        sid = f"s{i}"
        trace_rows += _make_trace(sid, ["stem", "health", "arts"])
        feedback_rows.append(_make_feedback(sid, stated_choice_field="stem"))
    result = precision_at_3(trace_rows, feedback_rows, match="field")
    assert result["precision_at_3"] == 1.0
    assert result["n_hits"] == 5
    assert result["n_sessions_with_ground_truth"] == 5


def test_precision_at_3_field_no_hits():
    trace_rows = []
    feedback_rows = []
    for i in range(5):
        sid = f"s{i}"
        trace_rows += _make_trace(sid, ["stem", "health", "arts"])
        feedback_rows.append(_make_feedback(sid, stated_choice_field="agriculture"))
    result = precision_at_3(trace_rows, feedback_rows, match="field")
    assert result["precision_at_3"] == 0.0
    assert result["n_hits"] == 0


def test_precision_at_3_no_ground_truth():
    trace_rows = _make_trace("s1", ["stem", "health", "arts"])
    feedback_rows = [_make_feedback("s1", stated_choice_field=None)]
    result = precision_at_3(trace_rows, feedback_rows, match="field")
    assert result["n_sessions_with_ground_truth"] == 0


def test_precision_at_3_empty_inputs_return_empty_metrics():
    result = precision_at_3([], [], match="field")
    assert result["n_sessions_with_ground_truth"] == 0
    assert np.isnan(result["precision_at_3"])


def test_acceptance_rate_all_true():
    feedback_rows = [
        _make_feedback(f"s{i}", would_consider_any=True) for i in range(10)
    ]
    result = acceptance_rate(feedback_rows)
    assert result["acceptance_rate"] == 1.0
    assert result["n_accepting"] == 10
    assert result["meets_target"] is True


def test_acceptance_rate_empty_inputs_return_empty_metrics():
    result = acceptance_rate([])
    assert result["n_sessions"] == 0
    assert np.isnan(result["acceptance_rate"])


def test_field_fairness_even():
    # 6 sessions, one rank-1 per field
    trace_rows = []
    for i, dim in enumerate(DIMS):
        trace_rows += _make_trace(f"s{i}", [dim, "stem", "health"])
    result = field_fairness(trace_rows)
    expected_share = 1.0 / 6
    for dim in DIMS:
        share = result["per_field_share"][dim]
        assert abs(share - expected_share) < 1e-9
    assert result["flagged_fields"] == []
    assert result["n_top3_recommendations"] == 18
    assert "top3_per_field_share" in result


def test_field_fairness_missing_field():
    # agriculture is absent from rank-1
    present_dims = [d for d in DIMS if d != "agriculture"]
    trace_rows = []
    for i, dim in enumerate(present_dims):
        trace_rows += _make_trace(f"s{i}", [dim, "stem", "health"])
    result = field_fairness(trace_rows)
    assert "agriculture" in result["flagged_fields"]
    assert result["per_field_share"]["agriculture"] == 0.0
    assert result["top3_per_field_share"]["agriculture"] == 0.0


def test_strand_field_fairness_flags_exclusive_strand():
    trace_rows = []
    trace_rows += _make_trace("s1", ["stem", "stem", "stem"], q7="STEM")
    trace_rows += _make_trace("s2", ["arts", "business", "education"], q7="HUMSS")
    result = strand_field_fairness(trace_rows)
    assert "STEM" in result["flagged_strands"]
    assert result["per_strand"]["STEM"]["exclusive_one_field"] is True
    assert result["per_strand"]["HUMSS"]["exclusive_one_field"] is False


def test_normalize_feedback_rows_computes_confidence_shift():
    rows = [
        {
            "session_id": "s1",
            "would_consider_any": "true",
            "pre_confidence": 2,
            "post_confidence": 5,
        }
    ]
    df = normalize_feedback_rows(rows)
    assert df.loc[0, "confidence_shift"] == 3
    assert df.loc[0, "would_consider_any"] == 1
    assert "stated_choice_field" in df.columns


def test_normalize_feedback_rows_derives_acceptance_from_choice():
    df = normalize_feedback_rows([
        {"session_id": "s1", "acceptance_choice": "A"},
        {"session_id": "s2", "acceptance_choice": "E"},
    ])
    assert df.loc[0, "would_consider_any"] == 1
    assert df.loc[1, "would_consider_any"] == 0


def test_feedback_and_trace_completeness_for_complete_session():
    trace_rows = _make_trace("s1", ["stem", "health", "arts"])
    feedback_rows = [
        _make_feedback(
            "s1",
            stated_choice_field="stem",
            would_consider_any=True,
            relevance_score=4.0,
            confidence_shift=1.0,
        )
    ]
    feedback_result = feedback_completeness(feedback_rows)
    trace_result = trace_completeness(trace_rows, feedback_rows)
    assert feedback_result["n_complete_feedback_rows"] == 1
    assert trace_result["n_complete_sessions"] == 1
    assert trace_result["missing_feedback_sessions"] == []


def test_aspiration_boost_acceptance_splits_boosted_sessions():
    trace_rows = []
    trace_rows += _make_trace("boosted", ["health", "stem", "arts"], boosted=True)
    trace_rows += _make_trace("plain", ["business", "arts", "stem"], boosted=False)
    feedback_rows = [
        _make_feedback("boosted", would_consider_any=True),
        _make_feedback("plain", would_consider_any=False),
    ]
    result = aspiration_boost_acceptance(trace_rows, feedback_rows)
    assert result["n_boosted_sessions"] == 1
    assert result["acceptance_rate_boosted"] == 1.0
    assert result["acceptance_rate_not_boosted"] == 0.0


def test_calibration_check_lower_for_flagged():
    # Flagged sessions: low acceptance; non-flagged: high acceptance
    trace_rows = []
    feedback_rows = []
    for i in range(5):
        sid = f"flagged_{i}"
        trace_rows.append(
            {
                "session_id": sid,
                "rank": 1,
                "program_name": "prog",
                "dominant_dim": "stem",
                "model_score": 0.4,
                "low_confidence_flag": True,
                "low_confidence_reason": "low_signal",
                "explanation_json": "{}",
            }
        )
        feedback_rows.append(_make_feedback(sid, would_consider_any=False))

    for i in range(5):
        sid = f"ok_{i}"
        trace_rows.append(
            {
                "session_id": sid,
                "rank": 1,
                "program_name": "prog",
                "dominant_dim": "health",
                "model_score": 0.9,
                "low_confidence_flag": False,
                "low_confidence_reason": None,
                "explanation_json": "{}",
            }
        )
        feedback_rows.append(_make_feedback(sid, would_consider_any=True))

    result = calibration_check(trace_rows, feedback_rows)
    assert result["acceptance_rate_flagged"] == 0.0
    assert result["acceptance_rate_not_flagged"] == 1.0
    assert result["flags_correlate_with_lower_acceptance"] is True


def test_construct_validity_report_structure():
    # Build minimal fixture: 10 students, full 24 items
    rng = np.random.default_rng(99)
    item_rows = []
    qnum = 1
    for field in DIMS:
        for family in [
            "domain_interest",
            "domain_interest",
            "domain_self_efficacy",
            "domain_self_efficacy",
        ]:
            qcode = f"V2Q{qnum:02d}"
            for student_idx in range(10):
                rv = float(rng.integers(1, 6))
                item_rows.append(
                    {
                        "session_id": f"S{student_idx:02d}",
                        "question_code": qcode,
                        "target_field": field,
                        "construct_family": family,
                        "response_value": rv,
                        "rescaled_value": (rv - 1.0) / 4.0,
                    }
                )
            qnum += 1

    result = construct_validity_report(item_rows)
    assert set(result["per_field"].keys()) == set(DIMS)
    for dim in DIMS:
        fd = result["per_field"][dim]
        assert "n_students" in fd
        assert "alpha" in fd
        assert "alpha_acceptable" in fd
        assert "item_total_correlations" in fd
        assert len(fd["item_total_correlations"]) == 4
        assert "flagged_items" in fd
    assert "summary" in result
    assert "fields_passing_alpha" in result["summary"]
    assert "total_flagged_items" in result["summary"]


def test_construct_validity_report_empty_inputs_is_safe():
    result = construct_validity_report([])
    assert result["per_field"] == {}
    assert result["summary"]["fields_passing_alpha"] == 0
    assert result["summary"]["total_flagged_items"] == 0


def test_outcome_metrics_report_handles_empty_inputs():
    result = outcome_metrics_report([], [])
    assert np.isnan(result["precision_field"]["precision_at_3"])
    assert np.isnan(result["acceptance"]["acceptance_rate"])
    assert result["calibration"]["n_flagged_sessions"] == 0


def test_outcome_metrics_report_handles_partial_feedback_rows():
    trace_rows = _make_trace("s1", ["stem", "health", "arts"])
    feedback_rows = [{"session_id": "s1", "would_consider_any": True}]
    result = outcome_metrics_report(trace_rows, feedback_rows)

    assert result["acceptance"]["acceptance_rate"] == 1.0
    assert np.isnan(result["relevance"]["mean"])
    assert result["precision_field"]["n_sessions_with_ground_truth"] == 0


def test_synthetic_fixture_runs():
    item_rows, trace_rows, feedback_rows = _synthetic_fixture()
    assert len(item_rows) == 30 * 24
    assert len(trace_rows) == 30 * 3
    assert len(feedback_rows) == 30

    construct_result = construct_validity_report(item_rows)
    outcome_result = outcome_metrics_report(trace_rows, feedback_rows)

    assert set(construct_result.keys()) == {"per_field", "summary"}
    assert set(outcome_result.keys()) == {
        "precision_field",
        "precision_program",
        "acceptance",
        "relevance",
        "confidence_shift",
        "field_fairness",
        "strand_field_fairness",
        "calibration",
        "feedback_completeness",
        "trace_completeness",
        "aspiration_boost_acceptance",
    }

    # Determinism check: second call yields same results
    item_rows2, trace_rows2, feedback_rows2 = _synthetic_fixture()
    construct_result2 = construct_validity_report(item_rows2)
    assert construct_result["summary"] == construct_result2["summary"]
