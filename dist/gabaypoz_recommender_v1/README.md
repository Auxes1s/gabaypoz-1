# GabayPoz Recommender v1.2

This package is the Team 4 handoff for the DB-aligned, program-first GabayPoz recommender with the v1.2 Q7 strand multiplier.

## What is implemented

- `recommend_programs(...)` in `src/gabaypoz_recommender/recommender.py`
- ERD-shaped regression tests in `tests/test_recommender.py`
- ID-keyed handoff datasets under `data/processed/team4_model/`
- Proposed ERD and tracker docs under `docs/`

## Current contract

- Inputs: `session_id`, `student_barangay_id`, questionnaire responses, and ERD-shaped tables
- Output: top 3 program recommendations, each with one primary school and alternate feasible schools
- Persistence: exactly 3 `model_recommendation` rows via caller-provided write callback
- Market context: municipality saturation, capped as a small context signal
- Constraint handling: Q10 affordability and Q11 commute are hard filters; Q12 is a soft penalty
- Q7: required SHS strand response, applied as an aptitude multiplier after Q8/Q9 scoring

## Generated datasets

- `barangay_location`
- `university`
- `barangay_university_commute_matrix`
- `barangay_university_economic_burden`
- `municipality_field_saturation`
- `dataset_manifest_v1_1.json`

## Version

- Package version: `1.2.0`
- Model ID: `tds_recommender_v1_2`

## Supabase/data requirements still upstream

- Seed `questions` with the final questionnaire text and IDs.
- Seed `answer_option` with option-level scoring; Q7 needs multiplier support or a dedicated v1.2 scoring contract.
- Complete `barangay_university_commute_matrix`: current Supabase coverage is 675 of 918 expected barangay-university rows.
- Add/map `model_id`, `rank`, and `university_id` in `model_recommendation`.
- Decide whether `barangay_university_economic_burden` and `municipality_field_saturation` live in Supabase or backend files.
- Move PMA/MAAP local offering overrides into Supabase or merge them into official offerings.
- Run one end-to-end Supabase-backed smoke test.
