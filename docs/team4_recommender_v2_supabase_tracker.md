# GabayPoz Recommender v2 Supabase Implementation Tracker

| Item | Value |
| --- | --- |
| Tracker ID | `team4_recommender_v2_supabase_tracker` |
| Created | 2026-05-20 |
| Last updated | 2026-05-20 |
| Owner | Team 4 Model Development, with DB owner support |
| Scope | Live Supabase migration, v2 seed loading, v2 recommender persistence, and pilot readiness |
| Model ID | `tds_recommender_v2` |
| Primary migration | `docs/reports/model/team4_recommender_v2_supabase_migration.sql` |

## How To Use This Tracker

Update this document after each implementation session.

- Keep the checkbox open until the stated "Done when" condition is true.
- Update `Status`, `Owner`, `Target date`, `Evidence`, and `Notes` directly inside each task.
- Add dated notes to the execution log at the bottom.
- Do not mark pilot-readiness tasks done based only on local tests; live Supabase evidence is required.

Status values:

- `Open`: not started or not yet assigned.
- `In progress`: actively being worked.
- `Blocked`: cannot proceed until a dependency is resolved.
- `Ready for verification`: implemented, waiting for live verification.
- `Done`: exit criteria met and evidence recorded.

## Live Supabase Baseline

Latest live scan: 2026-05-20, Asia/Manila.

| Table | Current live state |
| --- | ---: |
| `questions` | 41 rows, including 29 v2 rows |
| `answer_option` | 182 rows, including 138 v2 rows |
| `program` | 143 rows |
| `university` | 27 rows |
| `university_program` | 530 rows |
| `barangay_location` | 34 rows |
| `barangay_university_commute_matrix` | 918 rows |
| `barangay_university_economic_burden` | 918 rows |
| `municipality_field_saturation` | 6 rows |
| `guest_tracker` | 1 row |
| `users_response` | 12 rows |
| `model_recommendation` | 3 rows |
| `answer_option_scoring_metadata` | 138 rows |
| `program_profile_v2` | 143 rows |
| `model_recommendation_trace` | 0 rows after rollback smoke check |
| `recommender_v2_feedback_response` | 0 rows after rollback smoke check |
| `recommender_v2_session_completeness` | Present |

Current blocker summary:

- Live Supabase has the v2 schema, v2 seed rows, 143 program profiles, trace table, feedback table, and completeness view.
- Security Studies is profiled with the public-safety/security rule, medium confidence, and `needs_review`.
- Non-writing live smoke returns three recommendations with status `ok`.
- Rollback-only live write smoke succeeds for 29 responses, 3 recommendations, 3 traces, 1 feedback row, and completeness view validation.
- Remaining blockers are Team 5 UI/API persistence, access-control/RLS policy decisions, and real pilot validation sessions.

## Decision Gates

| Gate | Required condition | Status |
| --- | --- | --- |
| Migration ready | UUID/type issues fixed; live-program/profile mismatch resolved or explicitly filtered | Done |
| DB ready | Migration applied; v2 tables exist; seed counts verified | Done |
| Write path ready | Rollback-only write check succeeds for responses, recommendations, traces, and feedback contract | Done |
| UI/API ready | App persists all required v2 artifacts for one complete session | Open |
| Pilot ready | Completeness view identifies valid sessions and validation exports can be produced | Open |

## Task Tracker

### V2-SB-01 - Freeze And Record Live Baseline

- [x] Status: Done
- Owner: Team 4 / DB owner
- Target date: TBD
- Why: The team needs a rollback/reference point before changing live schema or seed data.
- Indicative actions:
  - Export live schemas and row counts for `questions`, `answer_option`, `program`, `university_program`, `guest_tracker`, `users_response`, and `model_recommendation`.
  - Save the export artifact path in this task.
  - Confirm whether the 3 existing `model_recommendation` rows are disposable smoke-test rows or real retained rows.
- Done when:
  - A dated schema/count export exists.
  - The export location is recorded in `Evidence`.
  - Existing recommendation rows have an agreed retention decision.
- Risks and care points:
  - Local exports are not identical to live Supabase; use live evidence.
  - Do not delete or overwrite existing live rows unless their purpose is confirmed.
- Evidence: Initial pre-migration live counts were captured in this tracker; post-migration live count snapshot is recorded in the Live Supabase Baseline section.
- Notes: Existing 3 `model_recommendation` rows were retained; no existing live rows were deleted during v2 migration/seed work.

### V2-SB-02 - Correct Migration UUID Types

- [x] Status: Done
- Owner: Team 4
- Target date: TBD
- Why: The current draft migration declares some new `session_id` fields as `text`, but live `guest_tracker.session_id` is `uuid`. The foreign keys can fail or produce an unusable contract.
- Indicative actions:
  - Edit `docs/reports/model/team4_recommender_v2_supabase_migration.sql`.
  - Change `model_recommendation_trace.session_id` from `text` to `uuid`.
  - Change `recommender_v2_feedback_response.session_id` from `text` to `uuid`.
  - Confirm `recommendation_id`, `program_id`, `university_id`, `feedback_id`, and `trace_id` are UUID-compatible.
  - Run a dry schema review against live column types before applying.
- Done when:
  - Migration column types match live FK targets.
  - The SQL can be reviewed without type conflicts.
- Risks and care points:
  - This is the highest-risk migration issue.
  - Keep the migration additive; do not rewrite v1/v1.2 data.
  - Check all FK target types, not only `session_id`.
- Evidence: `docs/reports/model/team4_recommender_v2_supabase_migration.sql`; live smoke schema check passed for `model_recommendation_trace` and `recommender_v2_feedback_response`; rollback-only write check inserted UUID-linked trace/feedback rows before rollback.
- Notes: Live scan confirmed `guest_tracker.session_id` is `uuid`; migration also updates `answer_option_question_group_check` to allow v2 `aspiration` options.

### V2-SB-03 - Reconcile 143 Live Programs With 142 Profiles

- [x] Status: Done
- Owner: Team 4
- Target date: TBD
- Why: v2 requires a usable `program_profile_v2` row for every program that can enter scoring. Missing rows cause `PROGRAM_PROFILE_V2_REQUIRED`.
- Indicative actions:
  - Add a profile for live program `33be74f0-7f89-42f3-a9c1-51c75eeda77d`, `Bachelor of Science in Management Major in Security Studies`.
  - Or explicitly exclude that program from v2 scoring with a documented rule.
  - Regenerate `data/processed/team4_model/program_profile_v2.csv` if the profile is added.
  - Re-run `analysis/team4_model/test_program_profile_v2.py`.
- Done when:
  - Every live recommendable `program.program_id` has exactly one v2 profile row, or the exclusion rule is implemented and tested.
  - The final profile count and excluded count are recorded.
- Risks and care points:
  - Loading 142 profiles against 143 live programs will break strict v2 scoring unless code filters the unprofiled program.
  - Avoid creating a weak hand-authored profile without marking confidence/review status honestly.
- Evidence: `reports/model/program_profile_v2_manifest.json` now reports 143 rows and 37 `needs_review` rows; `python3 analysis/team4_model/test_program_profile_v2.py` passed 4 tests.
- Notes: Missing live profile was added from the live row for `33be74f0-7f89-42f3-a9c1-51c75eeda77d`; Security Studies maps to `criminology_public_safety`, medium confidence, `needs_review`.

### V2-SB-04 - Fix Live Smoke Session ID Generation

- [x] Status: Done
- Owner: Team 4
- Target date: TBD
- Why: Rollback-only write checks insert into live `guest_tracker.session_id`, which is `uuid`. The current smoke script uses a prefixed string session ID.
- Indicative actions:
  - Update `analysis/team4_model/smoke_supabase_v2.py` so live write checks use `str(uuid.uuid4())` with no prefix.
  - Keep printed labels human-readable outside the DB value if needed.
  - Re-run local tests that cover Supabase-shaped contract behavior.
- Done when:
  - `python3 analysis/team4_model/smoke_supabase_v2.py --write-check` can attempt UUID-compatible inserts after migration.
- Risks and care points:
  - This bug may be invisible in non-writing smoke mode because the recommender compares session IDs as strings in local data frames.
  - Do not change the recommender API contract casually; normalize at the integration edge.
- Evidence: `analysis/team4_model/smoke_supabase_v2.py` now uses `str(uuid.uuid4())` for the DB `session_id`; `python3 analysis/team4_model/smoke_supabase_v2.py --write-check` passed against live Supabase.
- Notes: Live type scan confirmed `guest_tracker.session_id` is `uuid`.

### V2-SB-05 - Apply Owner-Side v2 Migration

- [x] Status: Done
- Owner: DB owner
- Target date: TBD
- Why: Live Supabase is missing the required v2 tables for scoring metadata, program profiles, recommendation traces, feedback, and completeness tracking.
- Indicative actions:
  - Run the corrected migration as the owner/admin of the public tables.
  - Confirm these tables exist: `answer_option_scoring_metadata`, `program_profile_v2`, `model_recommendation_trace`, `recommender_v2_feedback_response`.
  - Confirm the `recommender_v2_session_completeness` view exists.
  - Confirm indexes and FKs were created.
- Done when:
  - Live schema check passes for all v2 tables and the completeness view.
  - No v1/v1.2 rows are removed or rewritten.
- Risks and care points:
  - Migration must be additive.
  - Supabase RLS/policies may still need explicit configuration after table creation.
  - FK creation can fail if any type mismatch remains.
- Evidence: DB owner applied the migration through Supabase SQL editor; `python3 analysis/team4_model/smoke_supabase_v2.py` schema check printed `ok` for all v2 tables and `recommender_v2_session_completeness`.
- Notes: The live `answer_option_question_group_check` also required an owner-side patch to allow `aspiration`; this was verified before seeding.

### V2-SB-06 - Seed v2 Questionnaire And Scoring Metadata

- [x] Status: Done
- Owner: Team 4 / DB owner
- Target date: TBD
- Why: v2 needs 29 questions, 138 answer options, and 138 scoring metadata rows to build the latent-variable student profile.
- Indicative actions:
  - Confirm local seed files exist:
    - `data/processed/team4_model/supabase_seed/questions_seed_v2.csv`
    - `data/processed/team4_model/supabase_seed/answer_option_seed_v2.csv`
    - `data/processed/team4_model/supabase_seed/answer_option_scoring_metadata_seed_v2.csv`
  - Apply seed rows with `python3 analysis/team4_model/seed_recommender_questionnaire_v2.py --apply --verify`.
  - Verify counts: 29 v2 questions, 138 v2 answer options, 138 v2 scoring metadata rows.
- Done when:
  - Live counts match expected v2 seed counts.
  - Existing 12-question v1/v1.2 contract still exists.
- Risks and care points:
  - Seed order matters because metadata references question and option IDs.
  - Use deterministic UUIDs from the seed script; do not generate random question/option IDs.
  - Existing v1/v1.2 questionnaire rows must not be overwritten.
- Evidence: `python3 analysis/team4_model/seed_recommender_questionnaire_v2.py --apply --verify` seeded 29 questions, 138 answer options, 138 scoring metadata rows, and 143 program profiles; live verify returned 29 v2 questions, 138 v2 options, and 138 v2 metadata rows.
- Notes: Existing 12-question v1/v1.2 contract remains present; total live counts are now 41 questions and 182 answer options.

### V2-SB-07 - Load `program_profile_v2`

- [x] Status: Done
- Owner: Team 4 / DB owner
- Target date: TBD
- Why: `program_profile_v2` is the program-side scoring bridge. v2 should not score directly from legacy degree-title affinities.
- Indicative actions:
  - Review the 36 rows in `reports/model/program_profile_v2_review.csv`.
  - Update profile confidence and review status where human review resolves ambiguity.
  - Load profiles with `python3 analysis/team4_model/seed_recommender_questionnaire_v2.py --apply --verify`.
  - Confirm all six affinity columns are numeric, non-null, and within `0` to `5`.
- Done when:
  - Live `program_profile_v2` row count equals the live recommendable program count, or excluded programs are explicitly documented.
  - No duplicate `program_id` rows exist.
- Risks and care points:
  - Unreviewed profiles can still work technically, but they weaken interpretability.
  - Do not hide uncertain profiles as high-confidence rows.
  - The recommender treats low-confidence profiles with a reliability penalty; confidence labels matter.
- Evidence: Local profile inventory after reconciliation: 143 rows; 55 high confidence, 88 medium confidence, 37 `needs_review`; live verify returned 143 `program_profile_v2` rows.
- Notes: Security Studies is included as `criminology_public_safety`, medium confidence, `needs_review`.

### V2-SB-08 - Validate v2 Read Path Against Live Supabase

- [x] Status: Done
- Owner: Team 4
- Target date: TBD
- Why: The recommender must be able to read live tables, normalize v2 questions, load profiles, and return three recommendations before UI/API work proceeds.
- Indicative actions:
  - Run `python3 analysis/team4_model/smoke_supabase_v2.py`.
  - Confirm schema check prints `ok` for all required v2 tables.
  - Confirm it loads 29 v2 questions and all required profiles.
  - Confirm result status is `ok` and three recommendations print.
- Done when:
  - Non-writing live smoke test completes successfully.
- Risks and care points:
  - Passing local tests is not enough because live table types and counts differ from local exports.
  - Common failures: missing metadata rows, missing profile row, affordability coverage gap, or RLS restriction.
- Evidence: `python3 analysis/team4_model/smoke_supabase_v2.py` completed with status `ok`, loaded 138 v2 scoring rows and 143 profiles, and printed 3 recommendations.
- Notes: Smoke warning `UNKNOWN_Q7_STRAND` is from the synthetic default response and does not block the read path.

### V2-SB-09 - Validate Rollback-Only Write Path

- [x] Status: Done
- Owner: Team 4 / Team 5 backend
- Target date: TBD
- Why: The app must persist questionnaire responses, recommendation rows, and trace rows without breaking FK or type constraints.
- Indicative actions:
  - Run `python3 analysis/team4_model/smoke_supabase_v2.py --write-check`.
  - Confirm inserts succeed for `guest_tracker`, `users_response`, `model_recommendation`, and `model_recommendation_trace`.
  - Confirm the script rolls back test writes.
  - Add a feedback insert check if the smoke script is extended to cover `recommender_v2_feedback_response`.
- Done when:
  - Rollback-only write check succeeds against live Supabase.
  - The test leaves no committed smoke data.
- Risks and care points:
  - Trace rows must reference the exact `recommendation_id` generated for each inserted recommendation row.
  - UUID generation belongs at the server/integration layer, not in browser-only logic.
  - A partial write can make sessions appear complete incorrectly unless writes are transactional.
- Evidence: `python3 analysis/team4_model/smoke_supabase_v2.py --write-check` passed; completeness before rollback was `responses=29, traces=3, feedback=1, complete=True`.
- Notes: The script rolled back the smoke writes; live `model_recommendation_trace` and `recommender_v2_feedback_response` counts returned to 0.

### V2-SB-10 - Wire Team 5 UI/API Persistence Contract

- [ ] Status: Open
- Owner: Team 5 backend/frontend, with Team 4 support
- Target date: TBD
- Why: The UI/API must persist all artifacts needed for recommendations and validation, not only the final three result cards.
- Indicative actions:
  - Save 29 `users_response` rows with `question_id` and `option_id`.
  - Generate and save 3 `model_recommendation` rows.
  - Generate and save 3 matching `model_recommendation_trace` rows.
  - Save 1 `recommender_v2_feedback_response` row after the feedback form.
  - Treat the full write as one logical session operation where possible.
- Done when:
  - One end-to-end app session creates 29 responses, 3 recommendations, 3 traces, and 1 feedback row.
  - The completeness view reports the session as complete.
- Risks and care points:
  - Persisting only `model_recommendation` rows makes the pilot scientifically unusable.
  - Do not mark `guest_tracker.is_completed = true` until required writes succeed.
  - Avoid storing personal contact data in recommender trace or feedback tables.
- Evidence: TBD
- Notes: Team 4 should provide the exact response and trace shape expected by the API.

### V2-SB-11 - Implement Feedback Capture For Validation

- [ ] Status: Open
- Owner: Team 5 frontend/backend, with Team 4 validation support
- Target date: TBD
- Why: v2 validation requires feedback, acceptance, confidence shift, and stated-choice ground truth.
- Indicative actions:
  - Capture relevance score.
  - Capture acceptance choice and derive `would_consider_any`.
  - Capture pre-confidence and post-confidence.
  - Capture stated-choice program and stated-choice field.
  - Capture follow-up consent as a boolean.
  - Store personal contact details separately from the application DB if follow-up is needed.
- Done when:
  - Feedback rows can be persisted and linked to `session_id`.
  - `confidence_shift` is computed by the database.
  - Completeness view includes the feedback row.
- Risks and care points:
  - Do not store PII in `recommender_v2_feedback_response`.
  - Open-text fields can contain accidental PII; keep exports controlled.
  - Follow-up consent is not the same as storing contact details in the recommender database.
- Evidence: TBD
- Notes: This table is needed before any pilot validation claims.

### V2-SB-12 - Configure Access Control And RLS

- [ ] Status: Open
- Owner: DB owner / Team 5 backend
- Target date: TBD
- Why: New tables need read/write behavior that supports the app while protecting student data.
- Indicative actions:
  - Review Supabase RLS status for new tables.
  - Define which role can insert `users_response`, `model_recommendation`, `model_recommendation_trace`, and feedback rows.
  - Restrict broad reads of trace and feedback data.
  - Confirm server-side routes use an appropriate key for privileged writes if needed.
- Done when:
  - App can perform required writes.
  - Unauthorized clients cannot read broad trace/feedback data.
- Risks and care points:
  - Overly strict policies can make smoke tests pass locally but fail in the app.
  - Overly broad policies can expose sensitive response and feedback data.
- Evidence: TBD
- Notes: Policy decisions should be made before pilot data collection.

### V2-SB-13 - Use Completeness View As Pilot Readiness Signal

- [ ] Status: Blocked until V2-SB-10 and V2-SB-11 are done
- Owner: Team 4 / Team 5
- Target date: TBD
- Why: `guest_tracker.is_completed` alone is not enough to identify analyzable pilot sessions.
- Indicative actions:
  - Query `public.recommender_v2_session_completeness`.
  - Confirm a complete session requires 29 v2 responses, at least 3 trace rows, and 1 feedback row.
  - Add admin/reporting query or dashboard card for complete-session count.
- Done when:
  - A real or controlled end-to-end session appears with `session_complete = true`.
- Risks and care points:
  - Incomplete sessions should be excluded from validation metrics.
  - Do not use old 12-response sessions as v2-complete sessions.
- Evidence: TBD
- Notes: Completeness view is created by the v2 migration.

### V2-SB-14 - Run Real Pilot Validation Harness

- [ ] Status: Blocked until real pilot sessions exist
- Owner: Team 4 validation
- Target date: TBD
- Why: Current v2 evaluation output is synthetic and cannot be presented as validation evidence.
- Indicative actions:
  - Export completed v2 questionnaire responses, traces, recommendations, and feedback.
  - Run `analysis/team4_model/evaluate_recommender_v2.py`.
  - Report construct validity, item-total correlations, field Precision@3, acceptance, confidence shift, and fairness.
  - Label early metrics as pilot evidence only after real student sessions exist.
- Done when:
  - A dated validation report is generated from real completed sessions.
  - The report states sample size, inclusion criteria, and limitations.
- Risks and care points:
  - Do not use `reports/model/recommender_v2_evaluation.md` as pilot proof; it is synthetic fixture output.
  - Small samples can guide debugging but should not be overclaimed.
- Evidence: TBD
- Notes: The validation plan targets larger N for defensible claims.

## Execution Log

| Date | Actor | Update | Evidence |
| --- | --- | --- | --- |
| 2026-05-20 | Codex | Created persistent tracker from live Supabase scan and v2 task brief. | This file |
| 2026-05-20 | Codex | Implemented local migration/type fixes, reconciled the 143rd program profile, regenerated v2 profile artifacts, extended smoke feedback/completeness coverage, and ran focused tests. Live migration attempt is blocked by owner privilege. | `reports/model/program_profile_v2_manifest.json`; `python3 -m pytest analysis/team4_model/test_program_profile_v2.py`; `python3 -m pytest analysis/team4_model/test_recommender_v2_supabase_contract.py`; live migration error `must be owner of table questions` |
| 2026-05-20 | Codex / DB owner | DB owner applied the migration and `aspiration` constraint patch; Team 4 seeded v2 data and verified live read/write smoke checks. | `python3 analysis/team4_model/seed_recommender_questionnaire_v2.py --apply --verify`; `python3 analysis/team4_model/smoke_supabase_v2.py`; `python3 analysis/team4_model/smoke_supabase_v2.py --write-check` |
