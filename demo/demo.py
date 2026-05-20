"""Small v2 demo for the packaged GabayPoz recommender."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample"
OUT = Path(__file__).resolve().parent / "results.tex"

sys.path.insert(0, str(ROOT / "src"))

from gabaypoz_recommender import MODEL_ID, recommend_programs


DIMS = ["stem", "health", "arts", "business", "education", "agriculture"]
DIM_LABELS = {
    "stem": "STEM",
    "health": "Health",
    "arts": "Arts",
    "business": "Business",
    "education": "Education",
    "agriculture": "Agriculture",
}


@dataclass
class Profile:
    code: str
    title: str
    barangay_id: int
    high_field: str
    responses: dict[str, str]


def _question_blueprint() -> list[tuple[str, str, str]]:
    rows = []
    qnum = 1
    for field in DIMS:
        for family in ["domain_interest", "domain_interest", "domain_self_efficacy", "domain_self_efficacy"]:
            rows.append((f"V2Q{qnum:02d}", field, family))
            qnum += 1
    return rows


def build_v2_questions() -> pd.DataFrame:
    rows = []
    for question_id, field, family in _question_blueprint():
        for value in ["1", "2", "3", "4", "5"]:
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


def _demo_programs() -> pd.DataFrame:
    raw = pd.read_csv(DATA / "programs.csv")
    programs = raw.rename(columns={"program": "program_name"}).copy()
    for dim in DIMS:
        programs[f"affinity_{dim}_score"] = programs[dim].astype(float)
    programs["affinity_duration_score"] = programs["duration"].astype(float)
    return programs[["program_id", "program_name", "affinity_duration_score", *[f"affinity_{dim}_score" for dim in DIMS]]]


def _program_profiles(programs: pd.DataFrame) -> pd.DataFrame:
    profiles = programs.copy()
    score_cols = [f"affinity_{dim}_score" for dim in DIMS]
    dominant_idx = profiles[score_cols].to_numpy().argmax(axis=1)
    profiles["profile_version"] = "program_profile_v2"
    profiles["profile_method"] = "demo_profile_from_sample_fixture"
    profiles["profile_confidence"] = "medium"
    profiles["profile_family"] = "demo_fixture"
    profiles["dominant_dim"] = [DIMS[idx] for idx in dominant_idx]
    profiles["dominant_dim_label"] = profiles["dominant_dim"].map(DIM_LABELS)
    profiles["secondary_dims"] = ""
    profiles["evidence_text"] = "Demo fixture profile generated from bundled sample program affinity scores."
    profiles["evidence_sources"] = "sample_programs_csv"
    profiles["review_status"] = "demo_fixture"
    profiles["program_code"] = profiles["program_id"].map(lambda value: f"DEMO-{value}")
    return profiles


def load_fixtures() -> dict[str, pd.DataFrame]:
    university_programs = pd.read_csv(DATA / "university_programs.csv")
    universities = (
        university_programs[["university_id", "university_name"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    commute = pd.read_csv(DATA / "commute_matrix.csv")
    barangays = (
        commute[["barangay_id"]]
        .drop_duplicates()
        .assign(
            barangay_name=lambda df: "Barangay " + df["barangay_id"].astype(str),
            municipality_code="155522000",
            municipality_name="Pozorrubio",
        )
    )
    saturation = pd.DataFrame(
        {
            "municipality_code": "155522000",
            "municipality_name": "Pozorrubio",
            "affinity_field": [label.upper() for label in DIM_LABELS.values()],
            "market_score": [0.5] * len(DIMS),
            "market_score_method": "ecosystem_saturation_v1_1",
        }
    )
    programs = _demo_programs()
    return {
        "programs": programs,
        "program_profile_v2": _program_profiles(programs),
        "university_programs": university_programs,
        "universities": universities,
        "commute_matrix": commute,
        "economic_burden": pd.read_csv(DATA / "economic_burden.csv"),
        "scholarship": pd.read_csv(DATA / "scholarship_bridge.csv"),
        "questions": build_v2_questions(),
        "barangay_location": barangays,
        "municipality_field_saturation": saturation,
    }


def _responses(high_field: str, *, q7: str, q10: str, q11: str, q12: str, q13: str = "D") -> dict[str, str]:
    result = {}
    for question_id, target, _family in _question_blueprint():
        result[question_id] = "5" if target == high_field else "1"
    result.update({"Q7": q7, "Q10": q10, "Q11": q11, "Q12": q12, "Q13": q13})
    return result


PROFILES = [
    Profile(
        "D1",
        "Health-oriented STEM strand, medicine aspiration, ready for board-exam programs",
        1,
        "health",
        _responses("health", q7="STEM", q10="C", q11="C", q12="A", q13="A"),
    ),
    Profile(
        "D2",
        "Arts-oriented HUMSS strand, nearby-only travel",
        1,
        "arts",
        _responses("arts", q7="HUMSS", q10="B", q11="A", q12="B"),
    ),
    Profile(
        "D3",
        "Agriculture-oriented TVL strand, moderate budget",
        3,
        "agriculture",
        _responses("agriculture", q7="TVL", q10="B", q11="B", q12="B"),
    ),
    Profile(
        "D4",
        "STEM-oriented GAS strand, moderate budget",
        2,
        "stem",
        _responses("stem", q7="GAS", q10="B", q11="B", q12="B"),
    ),
]


def run_profile(profile: Profile, fixtures: dict[str, pd.DataFrame]) -> dict:
    return recommend_programs(
        session_id=f"demo-{profile.code}",
        student_barangay_id=profile.barangay_id,
        student_responses=profile.responses,
        guest_tracker=pd.DataFrame([{"session_id": f"demo-{profile.code}", "is_completed": True}]),
        **fixtures,
    )


def _tex_escape(value) -> str:
    text = "" if value is None else str(value)
    for old, new in [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]:
        text = text.replace(old, new)
    return text


def render_profile(profile: Profile, result: dict) -> str:
    parts = [
        r"\subsection*{" + _tex_escape(f"{profile.code}: {profile.title}") + "}",
        rf"\noindent Model: \texttt{{{_tex_escape(result.get('model_id', MODEL_ID))}}}; "
        rf"Barangay id: \texttt{{{profile.barangay_id}}}; "
        rf"High field: \texttt{{{_tex_escape(profile.high_field)}}}; "
        rf"Q7: \texttt{{{_tex_escape(profile.responses['Q7'])}}}; "
        rf"Q10: \texttt{{{profile.responses['Q10']}}}; "
        rf"Q11: \texttt{{{profile.responses['Q11']}}}; "
        rf"Q12: \texttt{{{profile.responses['Q12']}}}; "
        rf"Q13: \texttt{{{profile.responses['Q13']}}}.",
        "",
    ]
    if result["status"] != "ok":
        parts.extend(
            [
                r"\paragraph{Outcome.}",
                rf"Run failed with \texttt{{{_tex_escape(result['error_code'])}}}: "
                rf"{_tex_escape(result.get('message', ''))}.",
                "",
            ]
        )
        return "\n".join(parts)

    parts.extend(
        [
            r"\paragraph{Top recommendations.}",
            r"\begingroup\small\setlength{\tabcolsep}{6pt}",
            r"\noindent\begin{tabular}{@{}c p{4.4cm} p{4.4cm} r@{}}",
            r"\toprule",
            r"Rank & Program & Primary school & Score \\",
            r"\midrule",
        ]
    )
    for rec in result["recommendations"]:
        parts.append(
            rf"{rec['rank']} & {_tex_escape(rec['program_name'])} & "
            rf"{_tex_escape(rec['primary_school']['university_name'])} & "
            rf"{rec['program_score']:.3f} \\"
        )
    top = result["recommendations"][0]
    trace = result["model_recommendation_trace_rows"][0]["explanation_json"]
    parts.extend(
        [
            r"\bottomrule",
            r"\end{tabular}\endgroup",
            "",
            r"\paragraph{Rank-1 explanation.}",
            _tex_escape(top["explanation_text"]),
            "",
            r"\paragraph{Rank-1 trace.}",
            rf"Dominant field: \texttt{{{_tex_escape(top['program_profile']['dominant_dim'])}}}; "
            rf"track boost factor: \texttt{{{trace.get('track_boost_factor', 1.0):.2f}}}; "
            rf"low-confidence reason: \texttt{{{_tex_escape(top.get('low_confidence_reason'))}}}.",
            "",
        ]
    )
    return "\n".join(parts)


def main() -> int:
    fixtures = load_fixtures()
    sections = []
    for profile in PROFILES:
        result = run_profile(profile, fixtures)
        print(profile.code, result["status"], result.get("error_code"))
        sections.append(render_profile(profile, result))
    OUT.write_text("\n\n".join(sections), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
