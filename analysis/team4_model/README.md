# analysis/team4_model

Team 4 Model Development — GabayPoz Recommender System v1.2

## Expected files

| File                                      | Description                                                         |
| ----------------------------------------- | ------------------------------------------------------------------- |
| `recommender_v1_1.py`                     | Official DB-aligned v1.1 `recommend_programs()` implementation       |
| `test_recommender_v1_1.py`                | ERD-shaped v1.1 test suite                                           |
| `recommender_v1_2.py`                     | v1.2 recommender with required Q7 SHS strand aptitude multiplier     |
| `test_recommender_v1_2.py`                | v1.2 regression tests for Q7 multiplier behavior and v1.1 parity     |
| `build_recommender_v1_1_datasets.py`      | Builds v1.1 handoff datasets and validates Supabase additions        |
| `export_supabase_universities.py`         | Read-only Supabase/Postgres export helper for local raw CSV inputs   |
| `recommender_v1_1_sensitivity.py`         | Generates the v1.1 weight-sensitivity comparison table               |

## Reference

- TDS: `docs/reports/model/team4_tds_recommender_v1.md`
- Project plan: `docs/reports/model/team4_model_dev_project_plan_v1.md`
- All required parquets: `data/processed/team3_eda/`
- Model output parquets: `data/processed/team4_model/`

## Notes

- v1.1 does not use scholarship rescue. Scholarships are context only after Q10/Q11 feasibility passes.
- Supabase additions are loaded from ignored raw CSV exports. A new university is appended only when it has full 34-barangay commute coverage.
- v1.2 requires Q7 and applies it as a multiplier to the normalized Q8/Q9 aptitude vector. This is supported by the Team 3 scoring contract's multiplier type and Team 4's model notes, but it is not a causal EDA finding.
- The packaged demo in `dist/gabaypoz_recommender_v1/` now mirrors the v1.2 code path and emits `tds_recommender_v1_2`.
