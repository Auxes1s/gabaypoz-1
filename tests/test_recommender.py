"""ERD-shaped tests for the official GabayPoz recommender v1.1."""
import pandas as pd

from gabaypoz_recommender import MODEL_ID, recommend_programs


FIELDS = ["stem", "health", "arts", "business", "education", "agriculture"]
LABELS = ["STEM", "Health", "Arts", "Business", "Education", "Agriculture"]


def questions_df() -> pd.DataFrame:
    rows = []
    for qid in [f"Q{i}" for i in range(1, 7)] + ["Q8", "Q9"]:
        for field, label in zip(FIELDS, LABELS):
            row = {"question_id": qid, "option_value": label}
            for f in FIELDS:
                row[f"{f}_score"] = 1.0 if f == field else 0.0
            rows.append(row)
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


def responses(field: str = "STEM", q10: str = "C", q11: str = "C", q12: str = "B") -> dict:
    result = {qid: field for qid in [f"Q{i}" for i in range(1, 7)] + ["Q8", "Q9"]}
    result.update({"Q10": q10, "Q11": q11, "Q12": q12})
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


def test_program_first_recommendations_write_three_rows_with_primary_schools():
    written = []
    result = call(write_recommendations=lambda rows: written.extend(rows))

    assert result["status"] == "ok"
    assert [r["rank"] for r in result["model_recommendation_rows"]] == [1, 2, 3]
    assert len(written) == 3
    assert result["recommendations"][0]["program_id"] == 1
    assert result["recommendations"][0]["primary_school"]["university_id"] == 1
    assert result["recommendations"][0]["alternate_schools"][0]["university_id"] == 2
    assert all("explanation_text" not in row for row in written)
    assert all(row["model_id"] == MODEL_ID for row in written)


def test_q11_filters_school_suggestions_not_program_scores():
    result = call(response_kwargs={"field": "Health", "q11": "B"})

    nursing = next(r for r in result["recommendations"] if r["program_id"] == 2)
    assert nursing["primary_school"]["university_id"] == 2
    assert all(s["commute_time_mins"] <= 90 for s in [nursing["primary_school"], *nursing["alternate_schools"]])


def test_q10_filters_unaffordable_school_suggestions():
    result = call(response_kwargs={"field": "Health", "q10": "A", "q11": "C"})

    nursing = next(r for r in result["recommendations"] if r["program_id"] == 2)
    assert nursing["primary_school"]["university_id"] == 2
    assert all(s["university_id"] != 3 for s in [nursing["primary_school"], *nursing["alternate_schools"]])


def test_missing_q10_burden_data_is_blocking_and_writes_nothing():
    written = []
    result = call(frames={"economic_burden": pd.DataFrame()}, write_recommendations=lambda rows: written.extend(rows))

    assert result["status"] == "error"
    assert result["error_code"] == "MISSING_Q10_BURDEN_DATA"
    assert written == []


def test_missing_saturation_uses_neutral_warning_not_failure():
    result = call(frames={"municipality_field_saturation": pd.DataFrame()})

    assert result["status"] == "ok"
    assert result["warnings"] == ["MISSING_SATURATION_DATA"]
    assert result["recommendations"][0]["market_context"]["status"] == "neutral_fallback"


def test_saturation_can_break_close_ranking_but_not_override_poor_fit():
    frames = base_frames()
    programs = frames["programs"].copy()
    programs.loc[programs["program_id"] == 4, "affinity_stem_score"] = 0.92
    saturation = frames["municipality_field_saturation"].copy()
    saturation.loc[saturation["affinity_field"] == "BUSINESS", "market_score"] = 1.0
    saturation.loc[saturation["affinity_field"] == "HEALTH", "market_score"] = 0.0
    result = call(frames={"programs": programs, "municipality_field_saturation": saturation})

    ids = [r["program_id"] for r in result["recommendations"]]
    assert 4 in ids[:3]
    assert ids[0] == 1


def test_q12_duration_penalty_applies_when_student_prefers_fast_path():
    result = call(response_kwargs={"field": "Health", "q12": "C"})

    nursing = next(r for r in result["recommendations"] if r["program_id"] == 2)
    assert nursing["penalties_applied"] == ["Q12 duration/board-exam penalty x0.85"]


def test_invalid_session_invalid_barangay_and_incomplete_responses_fail_without_rows():
    invalid_session = call(session_id="missing")
    invalid_barangay = call(student_barangay_id=999)
    bad_responses = responses()
    bad_responses.pop("Q8")
    incomplete = call(student_responses=bad_responses)

    assert invalid_session["error_code"] == "INVALID_SESSION"
    assert invalid_barangay["error_code"] == "INVALID_BARANGAY"
    assert incomplete["error_code"] == "INCOMPLETE_RESPONSES"
    assert invalid_session["model_recommendation_rows"] == []
    assert invalid_barangay["model_recommendation_rows"] == []
    assert incomplete["model_recommendation_rows"] == []


def test_name_keyed_team3_burden_data_is_mapped_to_ids():
    frames = base_frames()
    burden = frames["economic_burden"].merge(
        frames["barangay_location"][["barangay_id", "barangay_name"]], on="barangay_id"
    ).merge(frames["universities"][["university_id", "university_name"]], on="university_id")
    burden = burden.drop(columns=["barangay_id", "university_id"]).rename(
        columns={"barangay_name": "barangay", "university_name": "university"}
    )
    result = call(frames={"economic_burden": burden})

    assert result["status"] == "ok"
    assert len(result["model_recommendation_rows"]) == 3
