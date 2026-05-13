# GabayPoz Recommender v1.1

This package is the Team 4 handoff for the first official, program-first GabayPoz recommender.

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

## Generated datasets

- `barangay_location`
- `university`
- `barangay_university_commute_matrix`
- `barangay_university_economic_burden`
- `municipality_field_saturation`
- `dataset_manifest_v1_1.json`

## Version

- Package version: `1.1.0`
- Model ID: `tds_recommender_v1_1`
