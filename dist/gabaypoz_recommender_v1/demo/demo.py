"""Small v1.2 demo for the packaged GabayPoz recommender."""
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


@dataclass
class Profile:
    code: str
    title: str
    barangay_id: int
    responses: dict


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
    labels = ["STEM", "HEALTH", "ARTS", "BUSINESS", "EDUCATION", "AGRICULTURE"]
    saturation = pd.DataFrame(
        {
            "municipality_code": "155522000",
            "municipality_name": "Pozorrubio",
            "affinity_field": labels,
            "market_score": [0.5] * len(labels),
            "market_score_method": "ecosystem_saturation_v1_1",
        }
    )
    return {
        "programs": pd.read_csv(DATA / "programs.csv"),
        "university_programs": university_programs,
        "universities": universities,
        "commute_matrix": commute,
        "economic_burden": pd.read_csv(DATA / "economic_burden.csv"),
        "scholarship": pd.read_csv(DATA / "scholarship_bridge.csv"),
        "questions": pd.read_csv(DATA / "questions.csv"),
        "barangay_location": barangays,
        "municipality_field_saturation": saturation,
    }


def _max_for(dim: str) -> dict:
    return {f"Q{i}": f"OPT_{dim}" for i in [1, 2, 3, 4, 5, 6, 8, 9]}


PROFILES = [
    Profile(
        "D1",
        "Health-oriented STEM strand, ready for board-exam programs",
        1,
        {**_max_for("HEALTH"), "Q7": "STEM", "Q10": "C", "Q11": "C", "Q12": "A"},
    ),
    Profile(
        "D2",
        "Arts-oriented HUMSS strand, nearby-only travel",
        1,
        {**_max_for("ARTS"), "Q7": "HUMSS", "Q10": "B", "Q11": "A", "Q12": "B"},
    ),
    Profile(
        "D3",
        "Agriculture-oriented TVL strand, moderate budget",
        3,
        {**_max_for("AGRICULTURE"), "Q7": "TVL", "Q10": "B", "Q11": "B", "Q12": "B"},
    ),
    Profile(
        "D4",
        "STEM-oriented GAS strand, moderate budget",
        2,
        {**_max_for("STEM"), "Q7": "GAS", "Q10": "B", "Q11": "B", "Q12": "B"},
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
        rf"Q7: \texttt{{{_tex_escape(profile.responses['Q7'])}}}; "
        rf"Q10: \texttt{{{profile.responses['Q10']}}}; "
        rf"Q11: \texttt{{{profile.responses['Q11']}}}; "
        rf"Q12: \texttt{{{profile.responses['Q12']}}}.",
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
    parts.extend(
        [
            r"\bottomrule",
            r"\end{tabular}\endgroup",
            "",
            r"\paragraph{Rank-1 explanation.}",
            _tex_escape(top["explanation_text"]),
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
