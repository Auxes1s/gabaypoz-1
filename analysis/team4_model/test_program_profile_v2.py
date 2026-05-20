"""Tests for deterministic program_profile_v2 generation."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_program_profile_v2 import (
    DIMS,
    RAW_PROGRAMS,
    build_profiles,
    classify_program,
    load_occupation_bridge,
    match_bridge,
    validate_profiles,
)


def test_program_family_classifier_handles_clear_degree_families():
    assert classify_program("Bachelor of Science in Nursing", "HE-BN-01")[0] == "health_clinical"
    assert classify_program("Bachelor of Secondary Education", "ED-BoSE-01")[0] == "education"
    assert classify_program("Bachelor of Science in Accountancy", "BU-BA-01")[0] == "business_accounting"
    assert classify_program("Bachelor of Science in Computer Science", "ST-BCS-01")[0] == "ict"
    assert classify_program("Bachelor of Science in Agriculture", "AG-BA-01")[0] == "agriculture"
    assert classify_program("Bachelor of Science in Marine Engineering", "BA-BoSiME-01")[0] == "marine_transport"
    assert classify_program("Bachelor of Science in Textile & Fashion Tech", "AR-BT&FT-01")[0] == "textile_fashion_technology"
    assert classify_program("Bachelor of Science in Industrial Technology", "ST-BIT-01")[0] == "industrial_technology"
    assert classify_program("Bachelor of Science in Management Major in Security Studies", "BA-SiMaMaSeSt-01")[0] == "criminology_public_safety"


def test_occupation_bridge_matches_safe_subject_equivalents():
    bridge = load_occupation_bridge()
    match = match_bridge("Bachelor of Science in Industrial Technology", bridge)

    assert match is not None
    assert match["program"] == "Bachelor of Industrial Technology"
    assert match["_match_type"] == "exact_subject"


def test_build_program_profile_v2_covers_all_supabase_programs():
    programs = pd.read_csv(RAW_PROGRAMS)
    profiles = build_profiles(programs, load_occupation_bridge())
    validate_profiles(profiles, expected_count=len(programs))

    assert len(profiles) == 143
    assert profiles["program_id"].is_unique
    assert set(profiles["profile_version"]) == {"program_profile_v2"}
    assert set(f"affinity_{dim}_score" for dim in DIMS) <= set(profiles.columns)
    scores = profiles[[f"affinity_{dim}_score" for dim in DIMS]]
    assert ((scores >= 0) & (scores <= 5)).all().all()
    assert (profiles[[f"affinity_{dim}_score" for dim in DIMS]].sum(axis=1) > 0).all()
    assert {"high", "medium", "low"} >= set(profiles["profile_confidence"])
    assert (profiles["review_status"] == "needs_review").sum() > 0


def test_program_profile_v2_contains_explainable_evidence_for_key_programs():
    programs = pd.read_csv(RAW_PROGRAMS)
    profiles = build_profiles(programs, load_occupation_bridge())

    nursing = profiles[profiles["program_name"].str.contains("Nursing", case=False)].iloc[0]
    accountancy = profiles[profiles["program_name"].str.contains("Accountancy$", case=False, regex=True)].iloc[0]
    agriculture = profiles[profiles["program_name"].str.contains("Science in Agriculture", case=False)].iloc[0]
    criminology = profiles[profiles["program_name"].str.contains("Criminology", case=False)].iloc[0]
    security_studies = profiles[profiles["program_name"].str.contains("Security Studies", case=False)].iloc[0]

    assert nursing["dominant_dim"] == "health"
    assert nursing["profile_confidence"] == "high"
    assert "health" in nursing["evidence_text"].lower()
    assert accountancy["dominant_dim"] == "business"
    assert agriculture["dominant_dim"] == "agriculture"
    assert criminology["dominant_dim"] == "arts"
    assert security_studies["profile_family"] == "criminology_public_safety"
    assert security_studies["profile_confidence"] == "medium"
    assert security_studies["review_status"] == "needs_review"
