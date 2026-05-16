# Team 4 Model Development Project Plan v1.2 Update

| Item           | Value                             |
| -------------- | --------------------------------- |
| Document ID    | `team4_model_dev_project_plan_v1` |
| Status         | Tracker updated with implemented/generated items |
| Owner          | Team 4 Model Development          |
| TDS reference  | `team4_tds_recommender_v1_1` plus v1.2 Q7 update |
| Target handoff | Team 5 Web Development            |

## 1. Goal

Finalize a simple, explainable recommender that can be integrated into the GabayPoz web app.

The model should:

- accept a student session and barangay,
- use questionnaire answers to understand the student's likely program fit,
- include a small municipality saturation signal as market context,
- apply Q7 SHS strand as an aptitude multiplier in v1.2,
- recommend the top three programs first,
- choose one primary school suggestion for each recommended program,
- return alternate feasible schools when available,
- save the top three program recommendations,
- return plain-language explanations for the result page.

## 2. How the Model Works

1. Use inputs `session_id` and `student_barangay_id`.
2. The model reads the student's answers from `users_response`.
3. The model uses `questions` to compute six student scores:
   STEM, Health, Arts, Business, Education, Agriculture.
4. In v1.2, Q7 is required and multiplies the normalized Q8/Q9 aptitude vector using the tested v1 strand map.
5. The model compares the student scores with each program's six affinity scores.
6. The model applies a small municipality saturation adjustment as market context.
7. The model applies a small Q12 penalty when a program is longer or more board-exam-heavy than the student prefers.
8. The model chooses the top three programs.
9. For each selected program, the model finds schools that offer it through `university_program`.
10. The model uses `barangay_university_commute_matrix` to remove school suggestions outside the student's Q11 travel limit.
11. The model uses `barangay_university_economic_burden` to remove school suggestions outside the student's Q10 affordability tier.
12. The model chooses one primary school for each program and returns alternate feasible schools when available.
13. The model writes the top three program recommendations to `model_recommendation`.
14. The model returns explanations to the UI/API response.

## 3. What Is Already Decided

| Decision                | Current agreement                                       |
| ----------------------- | ------------------------------------------------------- |
| Model type              | Rule-based, explainable recommender                     |
| Output count            | Top 3 recommendations                                   |
| Ranking unit            | Program first, then school suggestions                  |
| Required location input | `student_barangay_id`                                   |
| Q11 travel rule         | Hard filter for school suggestions by commute time      |
| Q10 affordability rule  | Hard filter for school suggestions using burden dataset |
| Market context          | Municipality saturation, capped at 10% of program score |
| Q7 strand rule          | Required in v1.2; multiplier on Q8/Q9 aptitude, not additive scoring |
| Q12 duration rule       | Soft penalty using `program.affinity_duration_score`    |
| Stored output           | Three program rows, each with one primary school        |
| Explanation storage     | Returned by API, not stored yet                         |
| CHED/RDC boosters       | Not active until the schema exposes priority fields     |

## 4. Remaining Requirements and Proposals

| Area            | Remaining requirement                        | Why it matters                                                     | Proposal                                                                                                   |
| --------------- | -------------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Data            | Create `barangay_university_economic_burden` | Q10 cannot work without a barangay-school affordability table      | Team 3/4 creates it from commute distance, university cost class, tuition estimates, and Q10 thresholds    |
| Data            | Create `municipality_field_saturation`       | Market context needs a municipality-field table                    | Start from Team 3 HEAP occupation shares; use Pozorrubio for launch and generalize later                  |
| Data            | Confirm tuition estimate mapping             | Total burden needs a tuition estimate, not only transport cost     | Use current university `economic_constraint` as the first estimate; improve later with actual tuition data |
| Data            | Confirm commute matrix IDs match DB IDs      | Q11 depends on joining `barangay_id` and `university_id` correctly | Validate all 34 barangays and 20 universities have matching IDs                                            |
| Database schema | Confirm `model_recommendation` fields        | The model must write results Team 5 can read                       | Require `session_id`, `model_id`, `rank`, `program_id`, `university_id`, `model_score`, `created_datetime` |
| Database schema | Decide future explanation storage            | v2 training needs score details and explanations                   | For v1.1 return explanations only; for v2 add `explanation_json` or a separate recommendation trace table  |
| Database schema | Confirm scholarship join                     | Explanations need scholarship names and requirements               | Join `scholarship` to `dimension_scholarship` by `scholarship_code`                                        |
| Questionnaire   | Make scoring rows unambiguous                | The model must know which answer option maps to which score values | Add an answer-option scoring table, or make each selectable answer a unique `question_id` row              |
| Questionnaire   | Add Q7 multiplier support                    | v1.2 requires Q7 but does not score it as additive points          | Add `scoring_type = multiplier` support or document a separate v1.2 Q7 scoring contract                   |
| Questionnaire   | Freeze Q10/Q11/Q12 stored values             | The rules depend on stable option values like A/B/C                | Team 1/Team 5 confirms stored values before backend integration                                            |
| Questionnaire   | Require barangay input                       | Q11 and Q10 both depend on student location                        | Team 5 sends `student_barangay_id` when calling the recommender                                            |
| Model           | Rebuild tests with ERD-shaped data           | Existing tests were built around older parquet-style names         | Team 4 updates fixtures to match DB field names                                                            |
| Model           | Refactor zero-draft implementation           | `recommender_v1.py` ranks school-program pairs and uses old names  | Keep the scoring logic, but change the flow to rank programs first and pick schools second                 |
| Model           | Add saturation to program scoring            | The new market signal belongs to program ranking, not school filtering | Use 90% base program fit plus 10% municipality saturation before the Q12 penalty                         |
| Model           | Confirm primary-school rule                  | The DB stores only one `university_id` per recommendation row      | Persist the best school for each program; return alternate schools in the API response                     |
| Model           | Decide no-data behavior                      | Missing affordability data should not produce misleading results   | Return `MISSING_Q10_BURDEN_DATA` and write no rows                                                         |
| Web/API         | Confirm request and response                 | Integration breaks if Team 4 and Team 5 expect different shapes    | Team 5 sends `session_id` + `student_barangay_id`; Team 4 returns explanations and writes ranked rows      |

## 4.0 Supabase Export Snapshot

Supabase data was pulled locally on 2026-05-16 into `data/raw/supabase_exports/`. These export snapshots are checked into the fork for recommender improvement and demos; `.env.local` and unrelated raw source files remain ignored.

| Export | Rows | Demo implication |
| --- | ---:| --- |
| `university.csv` | 27 | Includes the original universities plus PMMA, PMA, MAAP, University of Baguio, University of Cordilleras, and other schools |
| `program.csv` | 142 | Expanded program universe from Supabase |
| `university_program.csv` | 530 | School-program offerings from Supabase |
| `local_offering_overrides.csv` | 2 | Local demo overrides: PMA = `BACHELOR OF SCIENCE IN MANAGEMENT MAJOR IN SECURITY STUDIES`; MAAP = `Bachelor of Science in Marine Transportation` |
| `barangay_location.csv` | 34 | Complete Pozorrubio barangay list |
| `barangay_university_commute_matrix.csv` | 675 | Original export snapshot; live Supabase was later completed to 918 rows |
| `scholarship.csv` | 2,125 | Program-scholarship bridge rows |
| `dimension_scholarship.csv` | 29 | Scholarship metadata |
| `questions.csv` | 0 | Questionnaire seed data is missing in Supabase |
| `answer_option.csv` | 0 | Option-level scoring seed data is missing in Supabase |
| `guest_tracker.csv`, `users_response.csv`, `model_recommendation.csv` | 0 each | No live demo sessions or persisted recommendations yet |

Current demo blockers: seed `questions` and `answer_option`, add Q7 multiplier handling to the scoring contract, and align `model_recommendation` with the v1.2 write contract. Commute coverage and the derived Q10/saturation datasets have been loaded to live Supabase. The 2026-05-16 Supabase schema has `recommendation_id`, `session_id`, `program_id`, `model_score`, and `created_datetime`, but does not yet expose `model_id`, `rank`, or `university_id`.

## 4.0a Supabase Derived Dataset Generation

Live Supabase schema inspection on 2026-05-16 initially confirmed that `barangay_university_economic_burden` and `municipality_field_saturation` were not present in `public`. A local generation pass produced load-ready files under `/tmp/gabaypoz_supabase_derived/`, and those files were loaded to live Supabase.

| Generated file | Rows | Purpose |
| --- | ---:| --- |
| `commute_missing_insert.csv` | 243 | Rows needed to complete the live `barangay_university_commute_matrix` table |
| `commute_complete_918.csv` | 918 | Full 34 barangays x 27 universities launch matrix |
| `barangay_university_economic_burden_918.csv` | 918 | Full Q10 burden table for the launch university scope |
| `municipality_field_saturation.csv` | 6 | Pozorrubio market-context rows for the six affinity fields |

The generation pass kept existing Supabase commute rows where available and generated only missing commute rows with a coordinate-based, calibrated proxy. The calibration used the existing Supabase commute rows: median distance multiplier 1.2389622701602832 and median minutes per km 1.2082551594746718. The UP Open University row had no Supabase coordinates, so generation used an approximate UP Open University Headquarters location in Maahas, Los Banos, Laguna.

Live verification after load:

- `barangay_university_commute_matrix`: 918 rows, 0 missing barangay-university pairs.
- `barangay_university_economic_burden`: 918 rows, 0 missing barangay-university pairs.
- `municipality_field_saturation`: 6 rows.

## 4.1 Implemented / Generated

| Area | Status | Evidence |
| --- | --- | --- |
| Recommender module | Implemented | `analysis/team4_model/recommender_v1_1.py` and packaged `dist/gabaypoz_recommender_v1/src/gabaypoz_recommender/recommender.py` |
| ERD-shaped tests | Implemented | `analysis/team4_model/test_recommender_v1_1.py` and packaged test mirror |
| v1.2 Q7 multiplier | Implemented | `analysis/team4_model/recommender_v1_2.py`, `analysis/team4_model/test_recommender_v1_2.py`, and packaged demo mirror |
| Barangay location dataset | Generated | `data/processed/team4_model/barangay_location.parquet` |
| University dataset | Generated | `data/processed/team4_model/university.parquet` |
| Commute matrix | Generated | `data/processed/team4_model/barangay_university_commute_matrix.parquet` |
| Economic burden dataset | Generated | `data/processed/team4_model/barangay_university_economic_burden.parquet` |
| Municipality saturation dataset | Generated | `data/processed/team4_model/municipality_field_saturation.parquet` |
| Dataset manifest | Generated | `data/processed/team4_model/dataset_manifest_v1_1.json` |
| Proposed ERD | Documented | `docs/reports/model/team4_recommender_v1_1_erd.md` |
| Dist handoff mirror | Updated | `dist/gabaypoz_recommender_v1/` mirrors the current v1.1 package and generated datasets |

## 5. Deliverables

| Deliverable                                   | Owner           | Done when                                                                             |
| --------------------------------------------- | --------------- | ------------------------------------------------------------------------------------- |
| Plain-language TDS v1.1                       | Team 4          | Rules, inputs, outputs, remaining requirements, and tests are understandable          |
| DB-aligned recommender contract               | Team 4 / Team 5 | Request, persisted program rows, primary school, and returned explanations are agreed |
| `barangay_university_economic_burden` dataset | Team 3 / Team 4 | Dataset exists in ID-keyed handoff form and is mirrored in `dist`                     |
| `municipality_field_saturation` dataset       | Team 3 / Team 4 | Dataset exists for Pozorrubio launch and is mirrored in `dist`                        |
| ERD-shaped T1-T7 tests                        | Team 4          | Tests use DB field names and pass                                                     |
| Sample request/response payloads              | Team 4 / Team 5 | Team 5 can integrate without guessing                                                 |
| Decision on v2 logging                        | Team 4 / Team 5 | Team chooses `explanation_json` or separate trace table for future training           |

## 6. Definition of Done

The model is ready for Team 5 integration when:

- `student_barangay_id` is required and validated.
- program-first ranking returns three distinct programs when possible.
- municipality saturation contributes up to 10% of program score.
- missing saturation data uses a neutral fallback and returns a warning.
- each recommended program has one primary school suggestion.
- alternate schools are returned in the API response when available.
- Q11 commute filtering works for school suggestions.
- Q10 affordability filtering works for school suggestions or fails safely with `MISSING_Q10_BURDEN_DATA`.
- Q12 duration penalty works.
- Q7 is required in v1.2 and applies only as an aptitude multiplier.
- exactly three rows are written to `model_recommendation`.
- rank values are 1, 2, and 3.
- explanations are returned but not stored.
- scholarship names and requirements can be shown.
- scholarships are context only in v1.1 and do not bypass Q10/Q11 feasibility.
- dominant-field ties are deterministic by alphabetical affinity-field label.
- weight-sensitivity output is generated for 45/55, 50/50, 55/45, and saturation-weight comparisons.
- T1-T7 tests pass with ERD-shaped fixtures.
- Team 5 has sample request and response payloads.

## 7. Risks

| Risk                                           | Impact                                                    | Mitigation                                                                                           |
| ---------------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Affordability dataset is not ready             | Q10 cannot be finalized                                   | Assign owner and delivery date immediately                                                           |
| Saturation is mistaken for guaranteed demand   | Students may over-read the market context                 | Label it as local field presence, not job guarantee                                                   |
| Questionnaire scoring is ambiguous             | Student scores may be wrong                               | Add option-level scoring or make scoring rows unique                                                 |
| Q7 is seeded as additive scores                | Strand could overweight or distort aptitude               | Keep Q7 as multiplier-only in v1.2; do not add it into additive Q1-Q6/Q8-Q9 scoring rows              |
| Team 5 expects explanations in DB              | Integration delay                                         | Confirm explanations are returned by API for v1.1                                                    |
| `model_recommendation` schema differs from TDS | Write failure or missing rank                             | Confirm schema before implementation                                                                 |
| Program-first output is misunderstood          | Team 5 may display one school as the whole recommendation | Explain that `program_id` is the recommendation and `university_id` is the primary school suggestion |
| Commute IDs do not match DB IDs                | Q11 filter gives wrong results                            | Run ID coverage checks before deployment                                                             |
| No trace logging for v2                        | Future model training lacks data                          | Add `explanation_json` or trace table before v2                                                      |

## 8. Slack-Ready Checklist

```text
Team 4 final model checklist / agreements to close:

1. Confirm recommender input: `session_id` + `student_barangay_id`. The model needs to know which student session to read and which barangay the student lives in. `session_id` gets the student's answers; `student_barangay_id` is needed for commute and affordability rules.

2. Confirm persisted output: exactly 3 rows in `model_recommendation` with `session_id`, `model_id`, `rank`, `program_id`, `university_id`, and `model_score`. After the model runs, it should save only the final top 3 program recommendations. Each row says which session it belongs to, which model version made it, the program rank, the recommended program, the primary school suggestion for that program, and the score.

3. Confirm explanations are returned by the API/UI response and are not stored in DB for v1.1. For now, the database only stores the recommendation rows. The longer explanation shown to students should be sent directly to the frontend when the model runs, including primary school details and alternate schools.

4. Verify `barangay_university_economic_burden` in Supabase during the smoke test. The live table has 918 rows and is required for the Q10 affordability rule.

5. Confirm Q10 burden dataset fields: `barangay_id`, `university_id`, `distance_km`, `commute_time_mins`, `economic_constraint`, `tuition_estimate`, `annual_transport_cost_php`, `total_annual_burden_php`, and affordability flags for tiers 1-5. These fields let the model estimate whether a school is affordable for a student from a specific barangay. It combines tuition and transport cost, then marks which Q10 budget tiers can afford it.

6. Verify `municipality_field_saturation` in Supabase during the smoke test. The live table has 6 rows with `municipality_code`, `municipality_name`, `affinity_field`, `municipality_field_share`, `province_field_share`, `saturation_ratio`, `market_score`, `market_score_method`, and `source_reference`.

7. Confirm questionnaire scoring is unambiguous: either option-level scoring table or unique scoring rows per selectable answer. The model must know exactly how each selected answer translates into STEM, Health, Arts, Business, Education, and Agriculture scores. For v1.2, Q7 must be handled as a multiplier, not as additive option points.

8. Confirm Q10/Q11/Q12 stored option values are frozen before integration. The model rules depend on stable answer values. For example, Q11=A means nearby only, Q11=B means willing to travel, and Q11=C means dorm/relocation is acceptable. These values should not change after integration starts.

9. Re-run v1.1 tests using ERD-shaped fixtures. Include tests showing saturation can affect close rankings but cannot override poor student-program fit, dominant-field ties are deterministic, and scholarships do not bypass Q10/Q11 filters.

10. Confirm scholarship explanation join through `scholarship_code`. The model needs to connect program scholarship rows to scholarship details like name, benefactor, grade requirement, exam requirement, and application period. `scholarship_code` is the shared key for that join.

11. Confirm program-first display: program is the recommendation; school is the suggested place to take it. This prevents Team 5 from presenting the result as if the model jointly chose one school-program pair. The UI should make the program the main result and show the primary school plus alternates underneath.

12. Decide v2 logging path: add `explanation_json` later or create a separate recommendation trace table. Version 2 will need more detailed logs for training and auditing. We need to decide whether to store explanations inside `model_recommendation` or create a separate table for detailed model traces.
```

## 9. Proposed Ownership

| Item                                 | Proposed owner            |
| ------------------------------------ | ------------------------- |
| Affordability burden dataset         | Team 3 with Team 4 review |
| Municipality saturation dataset      | Team 3 with Team 4 review |
| Questionnaire option scoring clarity | Team 1 and Team 5         |
| Recommender rules and tests          | Team 4                    |
| API integration and UI rendering     | Team 5                    |
| Future trace/explanation storage     | Team 4 and Team 5         |
