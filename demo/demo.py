"""Small v1.1 demo for the packaged GabayPoz recommender."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA = ROOT / "data" / "sample"
PROCESSED_DATA = ROOT / "data" / "processed" / "team4_model"
OUT = Path(__file__).resolve().parent / "results.tex"

sys.path.insert(0, str(ROOT / "src"))

from gabaypoz_recommender import recommend_programs


@dataclass
class Profile:
    code: str
    title: str
    barangay_id: int
    responses: dict


def load_fixtures() -> dict[str, pd.DataFrame]:
    university_programs = pd.read_csv(SAMPLE_DATA / "university_programs.csv")[
        ["program_id", "university_id"]
    ]
    return {
        "programs": pd.read_csv(SAMPLE_DATA / "programs.csv"),
        "university_programs": university_programs,
        "universities": pd.read_csv(PROCESSED_DATA / "university.csv"),
        "commute_matrix": pd.read_csv(PROCESSED_DATA / "barangay_university_commute_matrix.csv"),
        "economic_burden": pd.read_csv(PROCESSED_DATA / "barangay_university_economic_burden.csv"),
        "scholarship": pd.read_csv(SAMPLE_DATA / "scholarship_bridge.csv"),
        "questions": pd.read_csv(SAMPLE_DATA / "questions.csv"),
        "barangay_location": pd.read_csv(PROCESSED_DATA / "barangay_location.csv"),
        "municipality_field_saturation": pd.read_csv(
            PROCESSED_DATA / "municipality_field_saturation.csv"
        ),
    }


def _max_for(dim: str) -> dict:
    return {f"Q{i}": f"OPT_{dim}" for i in [1, 2, 3, 4, 5, 6, 8, 9]}


PROFILES = [
    Profile(
        "D1",
        "Health-oriented, ready for board-exam programs",
        1,
        {**_max_for("HEALTH"), "Q10": "C", "Q11": "C", "Q12": "A"},
    ),
    Profile(
        "D2",
        "Arts-oriented, nearby-only travel",
        1,
        {**_max_for("ARTS"), "Q10": "B", "Q11": "A", "Q12": "B"},
    ),
    Profile(
        "D3",
        "Agriculture-oriented, moderate budget",
        3,
        {**_max_for("AGRICULTURE"), "Q10": "B", "Q11": "B", "Q12": "B"},
    ),
    Profile(
        "D4",
        "STEM-oriented, tight budget",
        2,
        {**_max_for("STEM"), "Q10": "A", "Q11": "A", "Q12": "B"},
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


def _fmt_money(value) -> str:
    if value is None or pd.isna(value):
        return "--"
    return f"PHP {float(value):,.0f}"


def _fmt_number(value, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "--"
    return f"{float(value):.1f}{suffix}"


def _fmt_commute_ceiling(value) -> str:
    if value is None or pd.isna(value):
        return "none"
    return f"{float(value):.1f} min"


def _school_summary(school: dict) -> str:
    return (
        f"{school['university_name']} "
        f"({_fmt_number(school.get('distance_km'), ' km')}, "
        f"{_fmt_number(school.get('commute_time_mins'), ' min')}, "
        f"{_fmt_money(school.get('total_annual_burden_php'))})"
    )


def _field_list(values: list) -> str:
    return ", ".join(str(value) for value in values) if values else "--"


def _warning_text(result: dict) -> str:
    warnings = result.get("warnings") or []
    return ", ".join(warnings) if warnings else "none"


def render_profile(profile: Profile, result: dict) -> str:
    parts = [
        r"\subsection*{" + _tex_escape(f"{profile.code}: {profile.title}") + "}",
        rf"\noindent Barangay id: \texttt{{{profile.barangay_id}}}; "
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
            rf"\noindent Model id: \texttt{{{_tex_escape(result['model_id'])}}}; "
            rf"warnings: \texttt{{{_tex_escape(_warning_text(result))}}}.",
            "",
            r"\paragraph{Top recommendations.}",
            r"\begingroup\scriptsize\setlength{\tabcolsep}{4pt}",
            r"\noindent\begin{tabular}{@{}c p{3.3cm} p{3.5cm} r r r@{}}",
            r"\toprule",
            r"Rank & Program & Primary school & Score & Distance & Commute \\",
            r"\midrule",
        ]
    )
    for rec in result["recommendations"]:
        primary = rec["primary_school"]
        parts.append(
            rf"{rec['rank']} & {_tex_escape(rec['program_name'])} & "
            rf"{_tex_escape(primary['university_name'])} & "
            rf"{rec['program_score']:.3f} & "
            rf"{_tex_escape(_fmt_number(primary.get('distance_km'), ' km'))} & "
            rf"{_tex_escape(_fmt_number(primary.get('commute_time_mins'), ' min'))} \\"
        )
    top = result["recommendations"][0]
    top_constraints = top["constraints_applied"]
    top_market = top["market_context"]
    top_scholarship = top["scholarship_context"]
    parts.extend(
        [
            r"\bottomrule",
            r"\end{tabular}\endgroup",
            "",
            r"\paragraph{Primary and alternate school suggestions.}",
            r"\begin{itemize}",
        ]
    )
    for rec in result["recommendations"]:
        parts.append(
            rf"  \item {_tex_escape(rec['program_name'])}: "
            rf"\textbf{{Primary}} -- {_tex_escape(_school_summary(rec['primary_school']))}."
        )
        alternates = rec["alternate_schools"]
        if alternates:
            parts.append(
                rf"        \textbf{{Alternates}} -- "
                rf"{_tex_escape('; '.join(_school_summary(school) for school in alternates))}."
            )
        else:
            parts.append(r"        \textbf{Alternates} -- none after Q10/Q11 filters.")
    parts.extend(
        [
            r"\end{itemize}",
            "",
            r"\paragraph{Rank-1 structured details.}",
            r"\begin{itemize}",
            rf"  \item Matched dimensions: {_tex_escape(_field_list(top['matched_dimensions']))}.",
            rf"  \item Alternate feasible schools: {len(top['alternate_schools'])}.",
            rf"  \item Q10 tier: \texttt{{{top_constraints['q10_tier']}}}; "
            rf"Q11 commute ceiling: \texttt{{{_tex_escape(_fmt_commute_ceiling(top_constraints['q11_max_commute_mins']))}}}; "
            rf"Q12 response: \texttt{{{_tex_escape(profile.responses['Q12'])}}}.",
            rf"  \item Market context: {_tex_escape(top_market['affinity_field'])} "
            rf"score {_tex_escape(top_market['market_score'])} "
            rf"via \texttt{{{_tex_escape(top_market['market_score_method'])}}}.",
            rf"  \item Penalties: {_tex_escape(_field_list(top['penalties_applied']))}.",
            rf"  \item Scholarships at primary school: "
            rf"{top_scholarship['primary_school_scholarship_count']} "
            rf"({_tex_escape(_field_list(top_scholarship['sample_names']))}).",
            rf"  \item Low confidence flag: \texttt{{{str(top['low_confidence_flag']).lower()}}}; "
            rf"reason: \texttt{{{_tex_escape(top['low_confidence_reason'] or 'none')}}}.",
            r"\end{itemize}",
            "",
            r"\paragraph{Rank-1 explanation.}",
            _tex_escape(top["explanation_text"]),
            "",
            r"\paragraph{Persisted rows.}",
            r"\begingroup\scriptsize\setlength{\tabcolsep}{4pt}",
            r"\noindent\begin{tabular}{@{}c r r r@{}}",
            r"\toprule",
            r"Rank & Program id & University id & Model score \\",
            r"\midrule",
        ]
    )
    for row in result["model_recommendation_rows"]:
        parts.append(
            rf"{row['rank']} & {row['program_id']} & {row['university_id']} & "
            rf"{row['model_score']:.3f} \\"
        )
    parts.extend(
        [
            r"\bottomrule",
            r"\end{tabular}\endgroup",
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
