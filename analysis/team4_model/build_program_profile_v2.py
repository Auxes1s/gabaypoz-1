"""Build the GabayPoz program_profile_v2 dataset.

The profile is the program-side counterpart to the v2 student questionnaire:
every recommendable degree program receives a six-dimensional program
environment vector plus confidence and evidence fields. The builder is
deterministic and intentionally conservative: existing affinity scores are kept
as a prior, then blended with transparent program-family templates.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[2]
RAW_PROGRAMS = REPO / "data" / "raw" / "supabase_exports" / "program.csv"
OCCUPATION_BRIDGE = REPO / "data" / "processed" / "team3_eda" / "program_occupation_bridge.parquet"
OUT_DIR = REPO / "data" / "processed" / "team4_model"
REPORT_DIR = REPO / "reports" / "model"

PROFILE_VERSION = "program_profile_v2"
DIMS = ["stem", "health", "arts", "business", "education", "agriculture"]
DIM_LABELS = {
    "stem": "STEM",
    "health": "Health",
    "arts": "Arts",
    "business": "Business",
    "education": "Education",
    "agriculture": "Agriculture",
}
CURRENT_SCORE_COLS = {
    "stem": "affinity_stem_score",
    "health": "affinity_health_science_score",
    "arts": "affinity_art_humanities_score",
    "business": "affinity_business_score",
    "education": "affinity_education_score",
    "agriculture": "affinity_agriculture_score",
}

PRIOR_WEIGHT = 0.55
TEMPLATE_WEIGHT = 0.45

TEMPLATES: dict[str, dict[str, float]] = {
    "health_clinical": {"stem": 3.8, "health": 5.0, "arts": 2.0, "business": 1.2, "education": 2.6, "agriculture": 0.8},
    "health_psych_sports": {"stem": 2.7, "health": 4.2, "arts": 3.0, "business": 1.8, "education": 3.4, "agriculture": 0.8},
    "education": {"stem": 2.5, "health": 1.8, "arts": 3.6, "business": 1.8, "education": 5.0, "agriculture": 1.2},
    "technical_vocational_education": {"stem": 3.8, "health": 1.6, "arts": 2.7, "business": 2.6, "education": 5.0, "agriculture": 2.8},
    "business_accounting": {"stem": 2.8, "health": 0.6, "arts": 1.8, "business": 5.0, "education": 1.2, "agriculture": 0.8},
    "business_general": {"stem": 2.0, "health": 0.8, "arts": 2.4, "business": 5.0, "education": 1.6, "agriculture": 1.0},
    "public_admin": {"stem": 1.8, "health": 1.6, "arts": 3.4, "business": 4.2, "education": 3.2, "agriculture": 1.0},
    "engineering": {"stem": 5.0, "health": 0.6, "arts": 1.5, "business": 2.0, "education": 1.0, "agriculture": 1.2},
    "architecture_design": {"stem": 4.0, "health": 0.8, "arts": 4.3, "business": 2.0, "education": 1.2, "agriculture": 1.4},
    "ict": {"stem": 5.0, "health": 0.6, "arts": 2.2, "business": 2.6, "education": 1.0, "agriculture": 0.8},
    "science_math": {"stem": 5.0, "health": 1.8, "arts": 1.4, "business": 1.2, "education": 2.0, "agriculture": 1.4},
    "agriculture": {"stem": 3.4, "health": 1.4, "arts": 1.2, "business": 2.4, "education": 1.8, "agriculture": 5.0},
    "arts_humanities": {"stem": 0.8, "health": 0.8, "arts": 5.0, "business": 1.8, "education": 3.0, "agriculture": 0.6},
    "communication_media": {"stem": 1.4, "health": 0.8, "arts": 5.0, "business": 2.6, "education": 2.6, "agriculture": 0.6},
    "social_science": {"stem": 1.5, "health": 1.8, "arts": 4.4, "business": 2.4, "education": 3.8, "agriculture": 0.8},
    "hospitality_tourism": {"stem": 1.2, "health": 1.4, "arts": 3.0, "business": 4.4, "education": 1.6, "agriculture": 1.2},
    "criminology_public_safety": {"stem": 2.0, "health": 2.8, "arts": 3.6, "business": 1.8, "education": 2.5, "agriculture": 0.6},
    "textile_fashion_technology": {"stem": 2.5, "health": 0.8, "arts": 5.0, "business": 3.2, "education": 1.6, "agriculture": 1.0},
    "industrial_technology": {"stem": 4.4, "health": 1.2, "arts": 2.0, "business": 2.8, "education": 1.4, "agriculture": 1.4},
    "marine_transport": {"stem": 4.3, "health": 1.0, "arts": 1.2, "business": 2.2, "education": 1.0, "agriculture": 0.8},
}


def _clean(value: object) -> str:
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _shorten_degree_name(value: object) -> str:
    text = _clean(value)
    text = text.replace("bachelor of science in", "bs")
    text = text.replace("bachelor of arts in", "ba")
    text = text.replace("bachelor of", "bachelor")
    text = text.replace("doctor of", "doctor")
    return " ".join(text.split())


def _subject_key(value: object) -> str:
    text = _clean(value)
    patterns = [
        r"^bachelor of science in ",
        r"^bachelor of arts in ",
        r"^bachelor of science ",
        r"^bachelor of arts ",
        r"^bachelor in ",
        r"^bachelor of ",
        r"^bachelor ",
        r"^bs in ",
        r"^bs ",
        r"^ba in ",
        r"^ba ",
        r"^aa ",
        r"^associate in ",
        r"^associate ",
        r"^doctor of ",
        r"^doctor ",
        r"^diploma in ",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return " ".join(text.split())


def _template_array(template_name: str) -> np.ndarray:
    return np.array([TEMPLATES[template_name][dim] for dim in DIMS], dtype=float)


def _prior_array(row: pd.Series) -> np.ndarray:
    values = []
    for dim in DIMS:
        value = row.get(CURRENT_SCORE_COLS[dim], 0.0)
        values.append(0.0 if pd.isna(value) else float(value))
    return np.array(values, dtype=float)


def _dominant_dim(values: np.ndarray) -> str:
    max_value = float(values.max())
    tied = [dim for dim, value in zip(DIMS, values) if float(value) == max_value]
    return sorted(tied, key=lambda dim: DIM_LABELS[dim])[0]


def _secondary_dims(values: np.ndarray, dominant: str) -> list[str]:
    threshold = max(float(values.max()) - 0.75, 0.0)
    return [
        dim
        for dim, value in sorted(zip(DIMS, values), key=lambda pair: pair[1], reverse=True)
        if dim != dominant and float(value) >= threshold
    ][:2]


def classify_program(program_name: str, program_code: str | float = "") -> tuple[str, str, str, str]:
    """Return template, confidence, review_status, and a short family rationale."""
    name = _clean(program_name)
    code_prefix = str(program_code or "").split("-")[0].upper()

    if re.search(r"nursing|midwifery|pharmacy|pharmaceutical|medical laboratory|radiologic|occupational therapy|speech pathology|dental|public health|nutrition|basic medical", name):
        return "health_clinical", "high", "reviewed_by_rule", "health licensure or clinical health pathway"
    if re.search(r"psychology|sports science|physical therapy|exercise and sports", name):
        return "health_psych_sports", "medium", "needs_review", "health-adjacent behavioral, therapy, or sports science pathway"
    if re.search(r"technical vocational teacher|technology and livelihood education|business technology and livelihood", name):
        return "technical_vocational_education", "high", "reviewed_by_rule", "teacher education with technical or livelihood content"
    if re.search(r"education|teacher", name):
        return "education", "high", "reviewed_by_rule", "teacher education or education studies pathway"
    if re.search(r"accountancy|accounting|management accounting|accountancy technology", name):
        return "business_accounting", "high", "reviewed_by_rule", "accounting/accountancy professional pathway"
    if re.search(r"security studies|public safety|security management", name):
        return "criminology_public_safety", "medium", "needs_review", "security studies and public safety management pathway"
    if re.search(r"business administration|entrepreneurship|office administration|economics|cooperatives|transportation management|management economics", name):
        return "business_general", "medium", "reviewed_by_rule", "business, management, or economics pathway"
    if "public administration" in name:
        return "public_admin", "medium", "needs_review", "public administration and governance pathway"
    if re.search(r"marine engineering|marine transportation", name):
        return "marine_transport", "medium", "needs_review", "maritime transport and engineering pathway"
    if re.search(r"industrial technology", name):
        return "industrial_technology", "medium", "needs_review", "applied industrial technology pathway"
    if re.search(r"clothing technology|garments.*textile|textile.*fashion|fashion tech|textile technology", name):
        return "textile_fashion_technology", "medium", "reviewed_by_rule", "textile, clothing, garment, or fashion technology pathway"
    if re.search(r"engineering|architecture|geodetic|landscape architecture|environmental and sanitary", name):
        if "architecture" in name:
            return "architecture_design", "high", "reviewed_by_rule", "design-heavy built-environment professional pathway"
        return "engineering", "high", "reviewed_by_rule", "engineering or technical licensure pathway"
    if re.search(r"information technology|computer science|information systems|computer engineering|digital entrepreneurship", name):
        return "ict", "high", "reviewed_by_rule", "ICT and computing pathway"
    if re.search(r"physics|mathematics|statistics|biology|chemistry|biochemistry|geology|geography|molecular biology|applied physics|applied mathematics|food technology|environmental planning", name):
        return "science_math", "high", "reviewed_by_rule", "science, mathematics, or applied science pathway"
    if re.search(r"agriculture|agribusiness|fisheries|veterinary|biosystems", name) or code_prefix == "AG":
        return "agriculture", "high", "reviewed_by_rule", "agriculture, fisheries, veterinary, or agribusiness pathway"
    if re.search(r"communication|journalism|broadcast|film|multimedia|advertising|public relations|development communication|organizational communication", name):
        return "communication_media", "medium", "reviewed_by_rule", "communication, media, or public-facing creative pathway"
    if re.search(r"literature|creative writing|english|language|filipino|panitikan|filipinology|music|theatre|performing arts|fine arts|interior design|fashion|textile|arts|philosophy|history|library", name):
        return "arts_humanities", "medium", "reviewed_by_rule", "arts, humanities, language, or design pathway"
    if re.search(r"anthropology|sociology|behavioral sciences|political science|social sciences|social work|community development|international studies|political economy|family life", name):
        return "social_science", "medium", "needs_review", "social science, social service, or community pathway"
    if re.search(r"hospitality|hotel|restaurant|tourism", name):
        return "hospitality_tourism", "medium", "reviewed_by_rule", "hospitality and tourism business-service pathway"
    if "criminology" in name:
        return "criminology_public_safety", "medium", "needs_review", "public safety and criminology pathway"

    if code_prefix == "HE":
        return "health_clinical", "low", "needs_review", "health-coded program with unmatched title"
    if code_prefix == "ST":
        return "science_math", "low", "needs_review", "STEM-coded program with unmatched title"
    if code_prefix in {"BU", "BA"}:
        return "business_general", "low", "needs_review", "business-coded program with unmatched title"
    if code_prefix == "ED":
        return "education", "low", "needs_review", "education-coded program with unmatched title"
    if code_prefix == "AR":
        return "arts_humanities", "low", "needs_review", "arts-coded program with unmatched title"

    return "arts_humanities", "low", "needs_review", "fallback template; manual review required"


def _fallback_occupation_bridge() -> pd.DataFrame:
    """Return minimal bridge rows needed when the upstream Team 3 parquet is absent."""
    rows = [
        {
            "program": "Bachelor of Science in Nursing",
            "confidence": "High",
            "cmo_evidence": "BS Nursing: clinical/health practice leads to licensed professional (PSOC Group 02 Professionals) and auxiliary/support roles (Group 03 Technicians)",
            "p21_groups": "02|03",
            "p21_labels": "Professionals|Technicians and associate professionals",
        },
        {
            "program": "Bachelor of Industrial Technology",
            "confidence": "Medium",
            "cmo_evidence": "Bachelor of Industrial Technology: engineering/architecture licensure exam (PRC) leads to PSOC Group 02 Professionals; trade-level roles in Group 07 Craft and related trades",
            "p21_groups": "02|07",
            "p21_labels": "Professionals|Craft and related trades workers",
        },
    ]
    return pd.DataFrame(rows)


def load_occupation_bridge() -> pd.DataFrame:
    if OCCUPATION_BRIDGE.exists():
        bridge = pd.read_parquet(OCCUPATION_BRIDGE)
    else:
        bridge = _fallback_occupation_bridge()
    bridge = bridge.copy()
    bridge["_name_key"] = bridge["program"].map(_shorten_degree_name)
    bridge["_subject_key"] = bridge["program"].map(_subject_key)
    return bridge


def match_bridge(program_name: str, bridge: pd.DataFrame) -> dict | None:
    if bridge.empty:
        return None
    key = _shorten_degree_name(program_name)
    exact = bridge[bridge["_name_key"] == key]
    if not exact.empty:
        row = exact.iloc[0].to_dict()
        row["_match_type"] = "exact_name"
        return row
    subject = _subject_key(program_name)
    if "_subject_key" in bridge.columns and subject:
        subject_exact = bridge[bridge["_subject_key"] == subject]
        if len(subject_exact) == 1:
            row = subject_exact.iloc[0].to_dict()
            row["_match_type"] = "exact_subject"
            return row
    choices = bridge["_name_key"].dropna().unique().tolist()
    match = difflib.get_close_matches(key, choices, n=1, cutoff=0.93)
    if match:
        row = bridge[bridge["_name_key"] == match[0]].iloc[0].to_dict()
        row["_fuzzy_match_key"] = match[0]
        row["_match_type"] = "fuzzy_name"
        return row
    if "_subject_key" in bridge.columns and subject:
        subject_choices = bridge["_subject_key"].dropna().unique().tolist()
        subject_match = difflib.get_close_matches(subject, subject_choices, n=1, cutoff=0.95)
        if subject_match:
            rows = bridge[bridge["_subject_key"] == subject_match[0]]
            if len(rows) == 1:
                row = rows.iloc[0].to_dict()
                row["_fuzzy_match_key"] = subject_match[0]
                row["_match_type"] = "fuzzy_subject"
                return row
    return None


def build_profiles(programs: pd.DataFrame, bridge: pd.DataFrame | None = None) -> pd.DataFrame:
    bridge = bridge if bridge is not None else pd.DataFrame()
    records = []
    for _, row in programs.iterrows():
        template_name, family_confidence, review_status, family_rationale = classify_program(
            row["program_name"],
            row.get("program_code", ""),
        )
        prior = _prior_array(row)
        template = _template_array(template_name)
        blended = np.clip((PRIOR_WEIGHT * prior) + (TEMPLATE_WEIGHT * template), 0.0, 5.0)
        blended = np.round(blended, 3)
        dominant = _dominant_dim(blended)
        secondary = _secondary_dims(blended, dominant)

        occ = match_bridge(row["program_name"], bridge) if bridge is not None else None
        occ_conf = (occ or {}).get("confidence")
        confidence = family_confidence
        if family_confidence == "high" and occ_conf in {"Medium", "Low"}:
            confidence = "medium"
        if family_confidence == "medium" and occ_conf == "High":
            confidence = "medium"
        if family_confidence == "low" and occ_conf == "High":
            confidence = "medium"
        if occ is None and confidence == "high":
            confidence = "medium"

        evidence_sources = ["existing_program_affinity_scores", "program_family_template"]
        evidence_bits = [
            f"Family rule: {family_rationale}.",
            f"Blended current affinity prior ({PRIOR_WEIGHT:.2f}) with {template_name} template ({TEMPLATE_WEIGHT:.2f}).",
        ]
        if occ is not None:
            evidence_sources.append("program_occupation_bridge")
            match_type = occ.get("_match_type")
            bridge_note = f"Occupation bridge: {occ.get('cmo_evidence')}"
            if match_type:
                bridge_note += f" Match type: {match_type}."
            evidence_bits.append(bridge_note)
        else:
            evidence_bits.append("No safe occupation-bridge match found; profile should be reviewed if used in high-stakes reporting.")
            if review_status == "reviewed_by_rule":
                review_status = "needs_review"

        record = {
            "program_id": row["program_id"],
            "program_name": row["program_name"],
            "program_code": row.get("program_code"),
            "profile_version": PROFILE_VERSION,
            "profile_method": "weighted_prior_template_v2",
            "profile_confidence": confidence,
            "profile_family": template_name,
            "dominant_dim": dominant,
            "dominant_dim_label": DIM_LABELS[dominant],
            "secondary_dims": "|".join(secondary),
            "evidence_text": " ".join(evidence_bits),
            "evidence_sources": "|".join(evidence_sources),
            "review_status": review_status if confidence != "low" else "needs_review",
            "occupation_bridge_confidence": occ_conf,
            "occupation_bridge_p21_groups": (occ or {}).get("p21_groups"),
            "occupation_bridge_p21_labels": (occ or {}).get("p21_labels"),
        }
        for i, dim in enumerate(DIMS):
            record[f"affinity_{dim}_score"] = float(blended[i])
            record[f"current_{dim}_score"] = float(prior[i])
            record[f"template_{dim}_score"] = float(template[i])
        duration = row.get("affinity_duration_score")
        record["affinity_duration_score"] = None if pd.isna(duration) else float(duration)
        records.append(record)

    return pd.DataFrame(records)


def validate_profiles(profiles: pd.DataFrame, expected_count: int) -> None:
    if len(profiles) != expected_count:
        raise ValueError(f"Expected {expected_count} profiles, got {len(profiles)}.")
    if profiles["program_id"].duplicated().any():
        dupes = profiles.loc[profiles["program_id"].duplicated(), "program_id"].tolist()
        raise ValueError(f"Duplicate profile program_id values: {dupes}")
    score_cols = [f"affinity_{dim}_score" for dim in DIMS]
    if profiles[score_cols].isna().any().any():
        raise ValueError("Program profiles contain missing affinity scores.")
    bad_range = profiles[(profiles[score_cols] < 0).any(axis=1) | (profiles[score_cols] > 5).any(axis=1)]
    if not bad_range.empty:
        raise ValueError(f"Out-of-range profile scores: {bad_range['program_name'].tolist()}")
    all_zero = profiles[profiles[score_cols].sum(axis=1) <= 0]
    if not all_zero.empty:
        raise ValueError(f"All-zero profile vectors: {all_zero['program_name'].tolist()}")
    recomputed = profiles[score_cols].to_numpy().argmax(axis=1)
    expected = [DIMS[i] for i in recomputed]
    mismatched = profiles[profiles["dominant_dim"].to_numpy() != np.array(expected)]
    if not mismatched.empty:
        raise ValueError(f"Dominant dimension mismatch: {mismatched['program_name'].tolist()}")


def write_outputs(profiles: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    profiles.to_csv(OUT_DIR / "program_profile_v2.csv", index=False)
    profiles.to_parquet(OUT_DIR / "program_profile_v2.parquet", index=False)
    review = profiles[profiles["review_status"] == "needs_review"].copy()
    review.to_csv(REPORT_DIR / "program_profile_v2_review.csv", index=False)
    manifest = {
        "profile_version": PROFILE_VERSION,
        "rows": int(len(profiles)),
        "needs_review_rows": int(len(review)),
        "prior_weight": PRIOR_WEIGHT,
        "template_weight": TEMPLATE_WEIGHT,
        "source_programs": str(RAW_PROGRAMS.relative_to(REPO)),
        "source_occupation_bridge": str(OCCUPATION_BRIDGE.relative_to(REPO)),
        "outputs": [
            str((OUT_DIR / "program_profile_v2.csv").relative_to(REPO)),
            str((OUT_DIR / "program_profile_v2.parquet").relative_to(REPO)),
            str((REPORT_DIR / "program_profile_v2_review.csv").relative_to(REPO)),
        ],
    }
    (REPORT_DIR / "program_profile_v2_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build GabayPoz program_profile_v2.")
    parser.add_argument("--no-write", action="store_true", help="Validate profiles without writing outputs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    programs = pd.read_csv(RAW_PROGRAMS)
    bridge = load_occupation_bridge()
    profiles = build_profiles(programs, bridge)
    validate_profiles(profiles, expected_count=len(programs))
    if not args.no_write:
        write_outputs(profiles)
    print(
        f"Built {len(profiles)} program profiles; "
        f"{int((profiles['review_status'] == 'needs_review').sum())} need review."
    )
    print(profiles["profile_confidence"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
