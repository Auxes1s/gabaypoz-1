"""Run small v1.1 recommendation-weight sensitivity scenarios.

The script uses synthetic ERD-shaped data so the comparison is deterministic
and safe to run without production questionnaire rows.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pandas as pd

import recommender_v1_1 as rec


OUT = Path(__file__).resolve().parents[2] / "reports" / "model"
FIELDS = ["stem", "health", "arts", "business", "education", "agriculture"]
LABELS = ["STEM", "Health", "Arts", "Business", "Education", "Agriculture"]


@contextmanager
def scoring_weights(
    *,
    internal_weight: float,
    aptitude_weight: float,
    program_fit_weight: float,
    market_weight: float,
):
    original = {
        "INTERNAL_WEIGHT": rec.INTERNAL_WEIGHT,
        "APTITUDE_WEIGHT": rec.APTITUDE_WEIGHT,
        "PROGRAM_FIT_WEIGHT": rec.PROGRAM_FIT_WEIGHT,
        "MARKET_WEIGHT": rec.MARKET_WEIGHT,
        "LOW_SIGNAL_ABORT": rec.LOW_SIGNAL_ABORT,
    }
    rec.INTERNAL_WEIGHT = internal_weight
    rec.APTITUDE_WEIGHT = aptitude_weight
    rec.PROGRAM_FIT_WEIGHT = program_fit_weight
    rec.MARKET_WEIGHT = market_weight
    rec.LOW_SIGNAL_ABORT = 0.0
    try:
        yield
    finally:
        for key, value in original.items():
            setattr(rec, key, value)


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
        (1, "BS Computer Science", {"stem": 1.0, "business": 0.20}, 2),
        (2, "BS Nursing", {"health": 1.0, "stem": 0.25}, 3),
        (3, "BS Information Systems", {"stem": 0.78, "business": 0.70}, 2),
        (4, "BS Business Administration", {"business": 1.0, "stem": 0.35}, 2),
        (5, "Bachelor of Elementary Education", {"education": 1.0, "arts": 0.25}, 3),
        (6, "BS Agriculture", {"agriculture": 1.0, "stem": 0.20}, 2),
    ]
    data = []
    for pid, name, scores, duration_score in rows:
        row = {"program_id": pid, "program_name": name, "affinity_duration_score": duration_score}
        for field in FIELDS:
            row[f"affinity_{field}_score"] = scores.get(field, 0.1)
        data.append(row)
    return pd.DataFrame(data)


def frames() -> dict:
    universities = pd.DataFrame(
        [
            {"university_id": 1, "university_name": "Pozorrubio Local College", "university_type": "LUC"},
            {"university_id": 2, "university_name": "Pangasinan State University", "university_type": "SUC"},
        ]
    )
    university_programs = pd.DataFrame(
        [{"program_id": pid, "university_id": 1 if pid in {1, 3, 4} else 2} for pid in range(1, 7)]
    )
    commute = pd.DataFrame(
        [
            {"barangay_id": 10, "university_id": 1, "distance_km": 5, "commute_time_mins": 30},
            {"barangay_id": 10, "university_id": 2, "distance_km": 10, "commute_time_mins": 60},
        ]
    )
    burden = pd.DataFrame(
        [
            burden_row(10, 1, 40000),
            burden_row(10, 2, 55000),
        ]
    )
    saturation = pd.DataFrame(
        [
            {
                "municipality_code": "155522000",
                "municipality_name": "Pozorrubio",
                "affinity_field": label.upper(),
                "municipality_field_share": 0.10,
                "province_field_share": 0.10,
                "saturation_ratio": 1.0,
                "market_score": score,
                "market_score_method": "sensitivity_demo",
            }
            for label, score in zip(LABELS, [0.45, 0.60, 0.50, 1.00, 0.55, 0.40])
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
        "university_programs": university_programs,
        "commute_matrix": commute,
        "economic_burden": burden,
        "scholarship": pd.DataFrame(),
        "dimension_scholarship": pd.DataFrame(),
        "municipality_field_saturation": saturation,
    }


def burden_row(barangay_id: int, university_id: int, burden: float) -> dict:
    row = {
        "barangay_id": barangay_id,
        "university_id": university_id,
        "distance_km": 1.0,
        "commute_time_mins": 1.0,
        "economic_constraint": 1,
        "tuition_estimate": burden - 10000,
        "annual_transport_cost_php": 10000,
        "total_annual_burden_php": burden,
    }
    for tier in range(1, 6):
        row[f"affordability_at_tier_{tier}"] = True
    return row


def responses() -> dict:
    result = {qid: "STEM" for qid in [f"Q{i}" for i in range(1, 7)]}
    result.update({"Q8": "Business", "Q9": "Health"})
    result.update({"Q10": "C", "Q11": "C", "Q12": "B"})
    return result


def scenario_rows() -> list[dict]:
    scenarios = [
        ("student_45_55_market_90_10", 0.45, 0.55, 0.90, 0.10),
        ("student_50_50_market_90_10", 0.50, 0.50, 0.90, 0.10),
        ("student_55_45_market_90_10", 0.55, 0.45, 0.90, 0.10),
        ("student_55_45_market_100_0", 0.55, 0.45, 1.00, 0.00),
        ("student_55_45_market_80_20", 0.55, 0.45, 0.80, 0.20),
    ]
    out = []
    base = frames()
    for name, iw, aw, pfw, mw in scenarios:
        with scoring_weights(
            internal_weight=iw,
            aptitude_weight=aw,
            program_fit_weight=pfw,
            market_weight=mw,
        ):
            result = rec.recommend_programs(
                session_id="s1",
                student_barangay_id=10,
                student_responses=responses(),
                **base,
            )
        if result["status"] != "ok":
            raise RuntimeError(f"{name} failed: {result}")
        for item in result["recommendations"]:
            out.append(
                {
                    "scenario": name,
                    "rank": item["rank"],
                    "program_id": item["program_id"],
                    "program_name": item["program_name"],
                    "program_score": item["program_score"],
                    "base_fit_score": item["base_fit_score"],
                    "market_score": item["market_context"]["market_score"],
                }
            )
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(scenario_rows())
    path = OUT / "team4_recommender_v1_1_weight_sensitivity.csv"
    df.to_csv(path, index=False)
    print(f"Wrote {len(df)} rows to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
