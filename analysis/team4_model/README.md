# analysis/team4_model

Team 4 model-development workspace for GabayPoz recommender versions v1.1, v1.2, and v2.

## Current v2 path

| File | Purpose |
| --- | --- |
| `recommender_v2.py` | Current latent-variable recommender implementation used by the packaged `src/gabaypoz_recommender/recommender.py` mirror |
| `supabase_v2.py` | Supabase-shaped v2 questionnaire and option normalization helpers |
| `test_recommender_v2.py` | ERD-shaped v2 regression tests |
| `test_recommender_v2_supabase_contract.py` | Supabase seed/response contract tests |
| `build_program_profile_v2.py` | Deterministic `program_profile_v2` builder; uses the upstream Team 3 occupation bridge when present and a small handoff fallback when absent |
| `evaluate_recommender_v2.py` | Synthetic/pilot evaluation harness for v2 validation metrics |
| `seed_recommender_questionnaire_v2.py` | v2 questionnaire and scoring metadata seed helper |
| `smoke_supabase_v2.py` | Live Supabase read/write smoke-check helper |

## Legacy v1/v1.2 path

| File | Purpose |
| --- | --- |
| `recommender_v1_1.py` / `test_recommender_v1_1.py` | Historical DB-aligned v1.1 recommender and tests |
| `recommender_v1_2.py` / `test_recommender_v1_2.py` | Historical v1.2 recommender with Q7 SHS strand multiplier |
| `build_recommender_v1_1_datasets.py` | Legacy v1.1 dataset builder; expects upstream Team 3 processed parquets not included in this repo snapshot |
| `recommender_v1_1_sensitivity.py` | Legacy v1.1 weight-sensitivity report generator |
| `export_supabase_universities.py` | Read-only Supabase/Postgres export helper for local raw CSV inputs |

## References

- Current package README: `README.md`
- v2 methodology: `docs/reports/model/team4_recommender_v2_methodology.md`
- v2 ERD: `docs/reports/model/team4_recommender_v2_erd.md`
- v2 validation plan: `docs/reports/model/team4_recommender_v2_validation_plan.md`
- v2 Supabase tracker: `docs/reports/model/team4_recommender_v2_supabase_tracker.md`
- Legacy v1 TDS: `docs/reports/model/team4_tds_recommender_v1.md`

## Notes

- Current handoff outputs live under `data/processed/team4_model/` and `reports/model/`.
- v2 live Supabase workflows require `SUPABASE_DB_URL` from the shell or repo-root `.env.local`.
- Legacy v1/v1.2 files are retained for historical handoff and parity checks, not as the primary package path.