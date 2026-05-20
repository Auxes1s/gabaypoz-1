"""ERD-shaped tests for the GabayPoz latent-variable recommender v2."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recommender_v2 import (
    MODEL_ID,
    V2_AFFINITY_QUESTIONS,
    _build_student_vector,
    _dominant_dim,
    _strand_context_vector,
    recommend_programs,
)


FIELDS = ["stem", "health", "arts", "business", "education", "agriculture"]
LABELS = ["STEM", "Health", "Arts", "Business", "Education", "Agriculture"]
SCALE = ["1", "2", "3", "4", "5"]


def question_blueprint() -> list[tuple[str, str, str]]:
    rows = []
    qnum = 1
    for field in FIELDS:
        for family in ["domain_interest", "domain_interest", "domain_self_efficacy", "domain_self_efficacy"]:
            rows.append((f"V2Q{qnum:02d}", field, family))
            qnum += 1
    return rows


def questions_df() -> pd.DataFrame:
    rows = []
    for question_id, field, family in question_blueprint():
        for value in SCALE:
            rows.append(
                {
                    "question_id": question_id,
                    "option_value": value,
                    "construct_family": family,
                    "target_field": field,
                    "response_value": int(value),
                    "reverse_scored": False,
                }
            )
    return pd.DataFrame(rows)


def programs_df() -> pd.DataFrame:
    rows = [
        (1, "BS Computer Science", "stem", 2),
        (2, "BS Nursing", "health", 3),
        (3, "AB Communication", "arts", 2),
        (4, "BS Business Administration", "business", 2),
        (5, "Bachelor of Elementary Education", "education", 3),
        (6, "BS Agriculture", "agriculture", 2),
    ]
    data = []
    for pid, name, dominant, duration_score in rows:
        row = {"program_id": pid, "program_name": name, "affinity_duration_score": duration_score}
        for field in FIELDS:
            row[f"affinity_{field}_score"] = 1.0 if field == dominant else 0.1
        data.append(row)
    return pd.DataFrame(data)


def program_profile_df() -> pd.DataFrame:
    profile = programs_df().copy()
    profile["profile_version"] = "program_profile_v2"
    profile["profile_method"] = "test_profile"
    profile["profile_confidence"] = "medium"
    profile["profile_family"] = "test_family"
    profile["dominant_dim"] = [
        row for row in ["stem", "health", "arts", "business", "education", "agriculture"]
    ]
    profile["dominant_dim_label"] = [
        label for label in ["STEM", "Health", "Arts", "Business", "Education", "Agriculture"]
    ]
    profile["secondary_dims"] = "business"
    profile["evidence_text"] = "Test profile evidence."
    profile["evidence_sources"] = "test_source"
    profile["review_status"] = "reviewed_by_rule"
    return profile


def burden_row(barangay_id: int, university_id: int, burden: float, tier1: bool, tier3: bool, tier5: bool) -> dict:
    return {
        "barangay_id": barangay_id,
        "university_id": university_id,
        "distance_km": 1.0,
        "commute_time_mins": 1.0,
        "economic_constraint": 1,
        "tuition_estimate": burden - 10000,
        "annual_transport_cost_php": 10000,
        "total_annual_burden_php": burden,
        "affordability_at_tier_1": tier1,
        "affordability_at_tier_2": tier1 or tier3,
        "affordability_at_tier_3": tier3,
        "affordability_at_tier_4": tier3 or tier5,
        "affordability_at_tier_5": tier5,
    }


def base_frames() -> dict:
    universities = pd.DataFrame(
        [
            {"university_id": 1, "university_name": "Pozorrubio Local College", "university_type": "LUC"},
            {"university_id": 2, "university_name": "Pangasinan State University", "university_type": "SUC"},
            {"university_id": 3, "university_name": "Dagupan Private College", "university_type": "Private"},
            {"university_id": 4, "university_name": "Urdaneta City University", "university_type": "LUC"},
        ]
    )
    return {
        "guest_tracker": pd.DataFrame([{"session_id": "s1", "is_completed": True}]),
        "barangay_location": pd.DataFrame(
            [
                {
                    "barangay_id": 10,
                    "barangay_name": "Poblacion",
                    "municipality_code": "155522000",
                    "municipality_name": "Pozorrubio",
                }
            ]
        ),
        "questions": questions_df(),
        "programs": programs_df(),
        "program_profile_v2": program_profile_df(),
        "universities": universities,
        "university_programs": pd.DataFrame(
            [
                {"program_id": 1, "university_id": 1},
                {"program_id": 1, "university_id": 2},
                {"program_id": 2, "university_id": 2},
                {"program_id": 2, "university_id": 3},
                {"program_id": 3, "university_id": 1},
                {"program_id": 3, "university_id": 4},
                {"program_id": 4, "university_id": 1},
                {"program_id": 4, "university_id": 3},
                {"program_id": 5, "university_id": 2},
                {"program_id": 5, "university_id": 4},
                {"program_id": 6, "university_id": 4},
            ]
        ),
        "commute_matrix": pd.DataFrame(
            [
                {"barangay_id": 10, "university_id": 1, "distance_km": 5, "commute_time_mins": 30},
                {"barangay_id": 10, "university_id": 2, "distance_km": 10, "commute_time_mins": 60},
                {"barangay_id": 10, "university_id": 3, "distance_km": 20, "commute_time_mins": 100},
                {"barangay_id": 10, "university_id": 4, "distance_km": 8, "commute_time_mins": 40},
            ]
        ),
        "economic_burden": pd.DataFrame(
            [
                burden_row(10, 1, 40000, True, True, True),
                burden_row(10, 2, 55000, True, True, True),
                burden_row(10, 3, 120000, False, True, True),
                burden_row(10, 4, 50000, True, True, True),
            ]
        ),
        "scholarship": pd.DataFrame(
            [
                {"program_id": 1, "scholarship_code": "DOST", "scholarship_name": "DOST-SEI"},
                {"program_id": 2, "scholarship_code": "CHED", "scholarship_name": "CHED Merit"},
                {"program_id": 6, "scholarship_code": "DA", "scholarship_name": "DA-ATI"},
            ]
        ),
        "dimension_scholarship": pd.DataFrame(
            [
                {"scholarship_code": "DOST", "benefactor": "DOST"},
                {"scholarship_code": "CHED", "benefactor": "CHED"},
                {"scholarship_code": "DA", "benefactor": "DA"},
            ]
        ),
        "municipality_field_saturation": pd.DataFrame(
            [
                {
                    "municipality_code": "155522000",
                    "municipality_name": "Pozorrubio",
                    "affinity_field": label.upper(),
                    "municipality_field_share": 0.10,
                    "province_field_share": 0.10,
                    "saturation_ratio": 1.0,
                    "market_score": 0.5,
                    "market_score_method": "ecosystem_saturation_v1_1",
                }
                for label in LABELS
            ]
        ),
    }


def responses(field: str = "stem", q7: str = "GAS", q10: str = "C", q11: str = "C", q12: str = "B", q13: str = "D") -> dict:
    high = field.lower()
    result = {}
    for question_id, target, _family in question_blueprint():
        result[question_id] = "5" if target == high else "1"
    result.update({"Q7": q7, "Q10": q10, "Q11": q11, "Q12": q12, "Q13": q13})
    return result


def uniform_responses(q13: str = "D", q12: str = "B") -> dict:
    """All Likert items at '3' (neutral) so aspiration boost is the only score differentiator."""
    result = {}
    for question_id, _field, _family in question_blueprint():
        result[question_id] = "3"
    result.update({"Q7": "GAS", "Q10": "C", "Q11": "C", "Q12": q12, "Q13": q13})
    return result


def call(**overrides) -> dict:
    frames = base_frames()
    frames.update(overrides.pop("frames", {}))
    payload = {
        "session_id": "s1",
        "student_barangay_id": 10,
        "student_responses": responses(**overrides.pop("response_kwargs", {})),
        **frames,
    }
    payload.update(overrides)
    return recommend_programs(**payload)


def test_v2_questionnaire_has_24_affinity_items_and_5_options_each():
    questions = questions_df()
    assert len(V2_AFFINITY_QUESTIONS) == 24
    assert set(questions["question_id"].unique()) == V2_AFFINITY_QUESTIONS
    assert questions.groupby("question_id")["option_value"].nunique().eq(5).all()
    by_field_family = questions.drop_duplicates("question_id").groupby(["target_field", "construct_family"]).size()
    for field in FIELDS:
        assert by_field_family[(field, "domain_interest")] == 2
        assert by_field_family[(field, "domain_self_efficacy")] == 2


def test_construct_scores_are_weighted_into_student_vector():
    vector, norm, profile = _build_student_vector(responses("stem"), questions_df(), [])

    assert norm > 0
    assert profile["construct_scores"]["interest"]["stem"] == 1.0
    assert profile["construct_scores"]["self_efficacy"]["stem"] == 1.0
    assert profile["construct_scores"]["student_vector"]["stem"] == pytest.approx(0.95)
    assert profile["construct_scores"]["student_vector"]["health"] == 0.0


def test_q7_is_bounded_context_not_additive_scoring():
    base, _, base_profile = _build_student_vector(responses("business", q7="GAS"), questions_df(), [])
    boosted, _, boosted_profile = _build_student_vector(responses("business", q7="ABM"), questions_df(), [])

    assert boosted[FIELDS.index("business")] == pytest.approx(base[FIELDS.index("business")] + 0.05)
    assert boosted_profile["construct_scores"]["strand_context"]["business"] == 1.0
    assert base_profile["construct_scores"]["strand_context"]["business"] == 0.0


def test_unknown_q7_warns_and_uses_no_context_adjustment():
    warnings = []
    context = _strand_context_vector("Bogus", warnings)

    assert warnings == ["UNKNOWN_Q7_STRAND"]
    assert list(context) == [0.0] * 6


def test_program_first_recommendations_write_three_rows_and_trace_rows():
    written = []
    result = call(write_recommendations=lambda rows: written.extend(rows))

    assert result["status"] == "ok"
    assert result["model_id"] == MODEL_ID == "tds_recommender_v2"
    assert [r["rank"] for r in result["model_recommendation_rows"]] == [1, 2, 3]
    assert len(written) == 3
    assert len(result["model_recommendation_trace_rows"]) == 3
    assert result["recommendations"][0]["program_id"] == 1
    assert result["model_recommendation_trace_rows"][0]["construct_scores"]["student_vector"]["stem"] == 0.95
    assert "explanation_json" in result["model_recommendation_trace_rows"][0]
    assert all("explanation_text" not in row for row in written)


def test_program_profile_v2_overrides_legacy_program_affinity_columns():
    profile = program_profile_df()
    for field in FIELDS:
        profile[f"affinity_{field}_score"] = 0.1
    profile.loc[profile["program_id"] == 4, "affinity_stem_score"] = 1.0
    profile.loc[profile["program_id"] == 4, "profile_confidence"] = "high"
    profile.loc[profile["program_id"] == 4, "profile_family"] = "ict"

    result = call(program_profile_v2=profile)

    assert result["status"] == "ok"
    assert result["recommendations"][0]["program_id"] == 4
    assert result["recommendations"][0]["program_profile"]["profile_version"] == "program_profile_v2"
    assert "MISSING_PROGRAM_PROFILE_V2" not in result["warnings"]
    assert result["recommendations"][0]["shape_fit_score"] > result["recommendations"][0]["direction_fit_score"]


def test_missing_program_profile_v2_fails_v2_scoring():
    result = call(program_profile_v2=None)

    assert result["status"] == "error"
    assert result["error_code"] == "PROGRAM_PROFILE_V2_REQUIRED"
    assert result["model_recommendation_rows"] == []


def test_partial_program_profile_v2_fails_v2_scoring():
    profile = program_profile_df()
    profile = profile[profile["program_id"] != 6].copy()

    result = call(program_profile_v2=profile)

    assert result["status"] == "error"
    assert result["error_code"] == "PROGRAM_PROFILE_V2_REQUIRED"


def test_malformed_program_profile_v2_fails_v2_scoring():
    profile = program_profile_df()
    duplicate = profile[profile["program_id"] == 1].copy()
    profile = pd.concat([profile, duplicate], ignore_index=True)
    profile.loc[profile["program_id"] == 1, "affinity_stem_score"] = 99.0

    result = call(program_profile_v2=profile)

    assert result["status"] == "error"
    assert result["error_code"] == "INVALID_PROGRAM_PROFILE_V2"


def test_uniform_answers_are_flagged_as_low_specificity_not_false_precision():
    flat = responses("stem")
    for qid in V2_AFFINITY_QUESTIONS:
        flat[qid] = "5"

    result = call(student_responses=flat)

    assert result["status"] == "ok"
    assert {rec["low_confidence_reason"] for rec in result["recommendations"]} == {"LOW_SPECIFICITY_PROFILE"}


def test_constraint_only_changes_do_not_change_affinity_vector():
    easy = responses("health", q10="C", q11="C", q12="A")
    strict = responses("health", q10="A", q11="A", q12="C")

    easy_vector, _, _ = _build_student_vector(easy, questions_df(), [])
    strict_vector, _, _ = _build_student_vector(strict, questions_df(), [])

    assert list(easy_vector) == list(strict_vector)


def test_q11_filters_school_suggestions_not_program_scores():
    result = call(response_kwargs={"field": "health", "q11": "B"})

    nursing = next(r for r in result["recommendations"] if r["program_id"] == 2)
    assert nursing["primary_school"]["university_id"] == 2
    assert all(s["commute_time_mins"] <= 90 for s in [nursing["primary_school"], *nursing["alternate_schools"]])


def test_q10_filters_unaffordable_school_suggestions():
    result = call(response_kwargs={"field": "health", "q10": "A", "q11": "C"})

    nursing = next(r for r in result["recommendations"] if r["program_id"] == 2)
    assert nursing["primary_school"]["university_id"] == 2
    assert all(s["university_id"] != 3 for s in [nursing["primary_school"], *nursing["alternate_schools"]])


def test_missing_required_v2_response_fails_without_rows():
    bad_responses = responses()
    bad_responses.pop("V2Q08")
    result = call(student_responses=bad_responses)

    assert result["status"] == "error"
    assert result["error_code"] == "INCOMPLETE_RESPONSES"
    assert result["model_recommendation_rows"] == []
    assert result["model_recommendation_trace_rows"] == []


def test_duplicate_affinity_response_rows_fail():
    duplicated = pd.DataFrame(
        [{"question_id": qid, "selected_option": answer} for qid, answer in responses("stem").items()]
        + [{"question_id": "V2Q01", "selected_option": "1"}]
    )

    result = call(student_responses=duplicated)

    assert result["status"] == "error"
    assert result["error_code"] == "INCOMPLETE_RESPONSES"


def test_conflicting_alias_and_canonical_responses_fail():
    bad = responses("stem")
    bad["V2Q25"] = "ABM"

    result = call(student_responses=bad)

    assert result["status"] == "error"
    assert result["error_code"] == "INCOMPLETE_RESPONSES"


def test_v2_constraint_aliases_are_supported():
    aliased = responses("arts")
    aliased["V2Q25"] = aliased.pop("Q7")
    aliased["V2Q26"] = aliased.pop("Q10")
    aliased["V2Q27"] = aliased.pop("Q11")
    aliased["V2Q28"] = aliased.pop("Q12")

    result = call(student_responses=aliased)

    assert result["status"] == "ok"
    assert result["recommendations"][0]["program_id"] == 3


def test_partial_burden_coverage_warns_but_still_succeeds_if_three_recommendations_remain():
    frames = base_frames()
    frames["economic_burden"] = frames["economic_burden"][frames["economic_burden"]["university_id"] != 3].copy()

    result = recommend_programs(
        session_id="s1",
        student_barangay_id=10,
        student_responses=responses("business"),
        **frames,
    )

    assert result["status"] == "ok"
    assert "PARTIAL_Q10_BURDEN_COVERAGE" in result["warnings"]
    assert len(result["recommendations"]) == 3


def test_partial_burden_coverage_fails_when_fewer_than_three_recommendations_remain():
    frames = base_frames()
    frames["economic_burden"] = pd.DataFrame(
        [
            burden_row(10, 1, 40000, False, True, True),
            burden_row(10, 4, 50000, False, True, True),
        ]
    )

    result = recommend_programs(
        session_id="s1",
        student_barangay_id=10,
        student_responses=responses("stem", q10="A"),
        **frames,
    )

    assert result["status"] == "error"
    assert result["error_code"] == "NO_CANDIDATES"


def test_dominant_field_tie_breaks_alphabetically_by_label():
    assert _dominant_dim(pd.Series([5, 5, 1, 1, 1, 1]).to_numpy()) == "health"
    assert _dominant_dim(pd.Series([1, 1, 5, 5, 1, 5]).to_numpy()) == "agriculture"


def test_q12_duration_penalty_applies_when_student_prefers_fast_path():
    result = call(response_kwargs={"field": "health", "q12": "C"})

    nursing = next(r for r in result["recommendations"] if r["program_id"] == 2)
    assert nursing["penalties_applied"] == ["Q12 duration/board-exam penalty x0.85"]


def test_medicine_aspiration_boosts_health_above_stem():
    # Uniform affinity (all "3") → all programs score equally before the boost.
    # q12="A" (board-exam tolerant) so BS Nursing's duration_score=3 is not penalised.
    # medicine aspiration: health ×1.12 (primary), stem ×1.06 (secondary).
    result = recommend_programs(
        session_id="s1",
        student_barangay_id=10,
        student_responses=uniform_responses(q13="A", q12="A"),
        **base_frames(),
    )
    assert result["status"] == "ok"
    recs = result["recommendations"]
    assert recs[0]["program_name"] == "BS Nursing"            # health-dominant ×1.12
    assert recs[1]["program_name"] == "BS Computer Science"   # stem-dominant ×1.06
    traces = result["model_recommendation_trace_rows"]
    assert traces[0]["explanation_json"]["track_boost_factor"] == pytest.approx(1.12)
    assert traces[1]["explanation_json"]["track_boost_factor"] == pytest.approx(1.06)
    assert traces[2]["explanation_json"]["track_boost_factor"] == pytest.approx(1.0)


def test_law_aspiration_boosts_arts_above_business():
    # Uniform affinity → all programs score equally before the boost.
    # q12="B" so BS Nursing (duration 3) is penalised and cannot interfere.
    # law aspiration: arts ×1.12 (primary), business ×1.06 (secondary).
    result = recommend_programs(
        session_id="s1",
        student_barangay_id=10,
        student_responses=uniform_responses(q13="C", q12="B"),
        **base_frames(),
    )
    assert result["status"] == "ok"
    recs = result["recommendations"]
    assert recs[0]["program_name"] == "AB Communication"            # arts-dominant ×1.12
    assert recs[1]["program_name"] == "BS Business Administration"  # business-dominant ×1.06
    traces = result["model_recommendation_trace_rows"]
    assert traces[0]["explanation_json"]["track_boost_factor"] == pytest.approx(1.12)
    assert traces[1]["explanation_json"]["track_boost_factor"] == pytest.approx(1.06)


def test_no_aspiration_produces_no_track_boost_in_trace():
    # q13="D" (none) → track_boost_factor must be 1.0 for every recommendation.
    result = recommend_programs(
        session_id="s1",
        student_barangay_id=10,
        student_responses=uniform_responses(q13="D", q12="B"),
        **base_frames(),
    )
    assert result["status"] == "ok"
    traces = result["model_recommendation_trace_rows"]
    for trace in traces:
        assert trace["explanation_json"]["track_boost_factor"] == pytest.approx(1.0)
        assert trace["explanation_json"]["track_boost_applied"] is False
    assert traces[0]["constraints"]["q13_response"] == "D"
