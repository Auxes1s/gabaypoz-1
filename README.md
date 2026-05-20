# GabayPoz Recommender v2

This package is the Team 4 handoff for the DB-aligned, program-first GabayPoz recommender with the v2 latent-variable questionnaire and `program_profile_v2` scoring contract.

## What is implemented

- `recommend_programs(...)` in `src/gabaypoz_recommender/recommender.py`
- ERD-shaped regression tests in `tests/test_recommender.py`
- ID-keyed handoff datasets under `data/processed/team4_model/`
- Proposed ERD, methodology, validation, and tracker docs under `docs/`


## Clone and test

From a fresh clone of this fork:

```bash
git clone https://github.com/Auxes1s/gabaypoz-1.git
cd gabaypoz-1
python -m pip install -e ".[test]"
python -m pytest -q
```

Optional focused v2 handoff checks:

```bash
python -m pytest -q analysis/team4_model/test_recommender_v2.py analysis/team4_model/test_recommender_v2_supabase_contract.py analysis/team4_model/test_program_profile_v2.py
```

Optional live Supabase smoke tooling requires database access:

```bash
python -m pip install -e ".[smoke]"
# set SUPABASE_DB_URL in your shell or in .env.local first
python analysis/team4_model/smoke_supabase_v2.py
```
## Current contract

- Inputs: `session_id`, `student_barangay_id`, v2 questionnaire responses, `program_profile_v2`, and ERD-shaped tables
- Output: top 3 program recommendations, each with one primary school and alternate feasible schools
- Persistence: 3 `model_recommendation` rows plus 3 `model_recommendation_trace` rows in the response payload
- Market context: municipality saturation, capped as a small context signal
- Constraint handling: Q10 affordability and Q11 commute are hard filters; Q12 is a soft penalty
- Q7/V2Q25: bounded strand-context signal only
- V2Q29/Q13: optional professional-track aspiration boost for medicine, dentistry, or law pathways

## Generated datasets

- `barangay_location`
- `university`
- `barangay_university_commute_matrix`
- `barangay_university_economic_burden`
- `municipality_field_saturation`
- `program_profile_v2`
- `dataset_manifest_v1_1.json`

## Version

- Package version: `2.0.0`
- Model ID: `tds_recommender_v2`

## Supabase/data status

- v2 live Supabase schema is present: scoring metadata, program profiles, recommendation trace, feedback, and completeness view.
- v2 seed rows are live: 29 questions, 138 answer options, 138 scoring metadata rows, and 143 program profiles.
- `barangay_university_commute_matrix` is now complete in live Supabase: 918 of 918 expected barangay-university rows.
- `barangay_university_economic_burden` and `municipality_field_saturation` now live in Supabase.
- `model_recommendation` now exposes `model_id`, `rank`, and `university_id`.
- `model_recommendation_trace` and `recommender_v2_feedback_response` are empty until real or persisted pilot sessions are written.
- The live rollback-only write smoke test passes for 29 responses, 3 recommendations, 3 traces, 1 feedback row, and completeness view validation.
