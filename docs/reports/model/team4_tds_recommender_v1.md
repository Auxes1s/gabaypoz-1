# GabayPoz Recommender TDS v1.1

| Item        | Value                                                |
| ----------- | ---------------------------------------------------- |
| Document ID | `team4_tds_recommender_v1_1`                         |
| Status      | Plain-language DB-aligned spec for Team 4 and Team 5 |
| Date        | 2026-05-13                                           |
| Owner       | Team 4 Model Development                             |

## 1. Purpose

This document explains how the first GabayPoz recommender should work.

The recommender should help a Grade 11 or Grade 12 student see three college program options that fit:

- what they seem interested in or good at,
- where they live,
- what they can afford,
- how far they can travel,
- how much program length or board-exam burden they can handle.

The model is intentionally rule-based for v1.1. It should be easy to explain to students, teammates, and stakeholders. It is not a black-box machine learning model.

## 2. One-Sentence Summary

The recommender reads a student's answers and barangay, scores which programs fit the student best, then suggests the best feasible school for each recommended program based on commute, affordability, scholarships, and school details.

## 3. Current Decision

| Topic                        | v1.1 decision                                                                         |
| ---------------------------- | ------------------------------------------------------------------------------------- |
| Model type                   | Rule-based recommender                                                                |
| Ranking unit                 | Program first, then school suggestions under each program                             |
| Required location input      | `student_barangay_id`                                                                 |
| Mobility rule                | Q11 filters school suggestions by barangay-to-university commute time                 |
| Affordability rule           | Q10 filters school suggestions once `barangay_university_economic_burden` exists      |
| Program fit                  | Six-field match: STEM, Health, Arts, Business, Education, Agriculture                 |
| Duration handling            | Q12 applies a soft penalty using `program.affinity_duration_score`                    |
| Output stored in DB          | Three rows in `model_recommendation`; each row is one program plus its primary school |
| Explanation storage          | Returned to UI/API, not stored in DB for v1.1                                         |
| Municipality saturation score | Active as a small market-context adjustment, capped at 10% of program score           |
| CHED/RDC priority boosters   | Not active unless the `program` table adds priority fields                            |

## 3.1 Implemented / Generated

| Item | Status | Evidence |
| --- | --- | --- |
| Program-first recommender | Implemented | `analysis/team4_model/recommender_v1_1.py` and packaged mirror in `dist` |
| ERD-shaped regression tests | Implemented | `analysis/team4_model/test_recommender_v1_1.py` and packaged mirror in `dist` |
| Barangay location dataset | Generated | `data/processed/team4_model/barangay_location.parquet` |
| University dataset | Generated | `data/processed/team4_model/university.parquet` |
| Commute matrix | Generated | `data/processed/team4_model/barangay_university_commute_matrix.parquet` |
| Economic burden dataset | Generated | `data/processed/team4_model/barangay_university_economic_burden.parquet` |
| Municipality saturation dataset | Generated | `data/processed/team4_model/municipality_field_saturation.parquet` |
| Dataset manifest | Generated | `data/processed/team4_model/dataset_manifest_v1_1.json` |
| Proposed ERD | Documented | `docs/reports/model/team4_recommender_v1_1_erd.md` |

## 4. Plain-Language Flow

1. Student answers the questionnaire.
2. The interface sends `session_id` and `student_barangay_id` to the recommender.
3. The recommender turns Q1-Q9 into six student scores:
   STEM, Health, Arts, Business, Education, Agriculture.
4. The recommender scores programs by comparing the student scores with the program affinity scores.
5. It applies a small municipality saturation adjustment so the model can reflect local field presence.
6. It applies a small penalty if the program is longer or more board-exam-heavy than the student prefers.
7. It chooses the top three programs.
8. For each program, it finds schools that offer the program through `university_program`.
9. It removes school suggestions outside the student's Q11 travel limit.
10. It removes school suggestions that exceed the student's Q10 affordability tier.
11. It chooses one primary school for each recommended program.
12. It writes three rows to `model_recommendation`.
13. It returns explanation objects to the UI/API so Team 5 can render the program match, primary school, alternate schools, and market context.

## 5. Required Inputs

### 5.1 Request Inputs

| Input                 | Required? | Notes                                                                  |
| --------------------- | ---------:| ---------------------------------------------------------------------- |
| `session_id`          | Yes       | Links the run to `guest_tracker` and `users_response`                  |
| `student_barangay_id` | Yes       | Must come from the interface and match `barangay_location.barangay_id` |

### 5.2 Database Tables

| Table                                 | Needed fields                                                                  | Used for                            |
| ------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------- |
| `guest_tracker`                       | `session_id`, `is_completed`, `email`                                          | Session validation                  |
| `users_response`                      | `session_id`, `question_id`, `option_id`                                       | Student answers                     |
| `questions`                           | `question_id`, `question_text`                                                 | Question metadata                   |
| `answer_option`                       | `option_id`, `question_id`, six score columns                                  | Convert answers into student scores |
| `barangay_location`                   | `barangay_id`, `barangay_name`                                                 | Validate student barangay           |
| `municipality_field_saturation`       | See section 7                                                                  | Market-context adjustment           |
| `barangay_university_commute_matrix`  | `barangay_id`, `university_id`, `distance_km`, `commute_time_mins`             | Q11 travel filter                   |
| `barangay_university_economic_burden` | See section 6                                                                  | Q10 affordability filter            |
| `program`                             | `program_id`, six affinity score columns, `affinity_duration_score`            | Program fit and Q12 penalty         |
| `university_program`                  | `program_id`, `university_id`, names and field labels                          | Schools that offer each program     |
| `university`                          | `university_id`, `university_name`, type/address fields                        | School display and school ranking   |
| `scholarship`                         | `program_id`, `scholarship_code`, nearby/outside flags                         | Scholarship context                 |
| `dimension_scholarship`               | `scholarship_code`, scholarship details                                        | Scholarship names and requirements  |
| `model_recommendation`                | `session_id`, `model_id`, `rank`, `program_id`, `university_id`, `model_score` | Stored output                       |

### 5.3 Local Supabase Snapshot

Supabase was exported locally on 2026-05-16 into `data/raw/supabase_exports/` for recommender improvement and demos. This Supabase export snapshot is intentionally unignored so the fork can carry the demo data; unrelated raw files remain ignored.

| Export | Rows | Status |
| --- | ---:| --- |
| `barangay_location.csv` | 34 | Complete barangay base |
| `university.csv` | 27 | Includes added universities |
| `program.csv` | 142 | Expanded program catalog |
| `university_program.csv` | 530 | Supabase school-program offerings |
| `local_offering_overrides.csv` | 2 | PMA = `BACHELOR OF SCIENCE IN MANAGEMENT MAJOR IN SECURITY STUDIES`; MAAP = `Bachelor of Science in Marine Transportation` |
| `barangay_university_commute_matrix.csv` | 675 | Incomplete for all 27 universities |
| `scholarship.csv` | 2,125 | Available for scholarship context |
| `dimension_scholarship.csv` | 29 | Available for scholarship names/details |
| `questions.csv` | 0 | Needs questionnaire seed data |
| `answer_option.csv` | 0 | Needs option scoring seed data |
| `guest_tracker.csv`, `users_response.csv`, `model_recommendation.csv` | 0 each | No persisted demo runs yet |

Schema gap: the exported `model_recommendation` table currently has `recommendation_id`, `session_id`, `program_id`, `model_score`, and `created_datetime`. The v1.1 persistence contract still needs `model_id`, `rank`, and `university_id`.

Derived dataset gap, checked against live Supabase on 2026-05-16: `barangay_university_economic_burden` and `municipality_field_saturation` do not exist in `public` yet. Load-ready local files were generated under `/tmp/gabaypoz_supabase_derived/`: 243 missing commute rows, a complete 918-row commute matrix, a 918-row Q10 burden table, and a 6-row saturation table.

## 6. Blocking Dataset: Affordability

Q10 is supposed to remove school options that are not financially realistic for the student.

Status: generated for the handoff package as `data/processed/team4_model/barangay_university_economic_burden.parquet` and mirrored in `dist`.

The current ERD does not yet include the full dataset needed for this rule. The team must create:

`barangay_university_economic_burden`

This dataset should have one row per `barangay_id` and `university_id`.

| Field                                                  | Why it is needed                            |
| ------------------------------------------------------ | ------------------------------------------- |
| `barangay_id`                                          | Student origin                              |
| `university_id`                                        | School option                               |
| `distance_km`                                          | Audit field copied from commute matrix      |
| `commute_time_mins`                                    | Audit field copied from commute matrix      |
| `economic_constraint`                                  | School cost class                           |
| `tuition_estimate`                                     | Estimated annual tuition                    |
| `annual_transport_cost_php`                            | Estimated school-year transport cost        |
| `total_annual_burden_php`                              | Tuition plus transport                      |
| `affordability_at_tier_1` to `affordability_at_tier_5` | Whether each Q10 tier can afford the school |

If this dataset is missing, the recommender must stop with `MISSING_Q10_BURDEN_DATA`. It must not skip Q10 silently.

## 7. Market Context Dataset: Municipality Saturation

Market scoring in v1.1 should use municipality saturation, not broad national labor demand.

Status: generated for the handoff package as `data/processed/team4_model/municipality_field_saturation.parquet` and mirrored in `dist`.

In this TDS, saturation means:

```text
How common a field is among highly educated workers in the student's municipality.
```

This is not the same as job demand. A high saturation value can mean a stronger local field ecosystem, more role models, and more visible local pathways. It can also mean the field is crowded. Because the interpretation is not perfect, the recommender uses saturation as a small context adjustment, not as a hard filter.

The team should create:

`municipality_field_saturation`

This dataset should have one row per municipality and affinity field.

| Field                       | Why it is needed                                      |
| --------------------------- | ----------------------------------------------------- |
| `municipality_code`         | Student municipality key                              |
| `municipality_name`         | Human-readable municipality name                      |
| `affinity_field`            | STEM, Health, Arts, Business, Education, Agriculture  |
| `municipality_field_share`  | Local share of highly educated workers in this field  |
| `province_field_share`      | Province-wide comparison share                        |
| `saturation_ratio`          | Municipality share divided by province share          |
| `market_score`              | Normalized score used by the recommender              |
| `market_score_method`       | Method label, for example `ecosystem_saturation_v1_1` |
| `source_reference`          | Data source or script used to create the score        |

For Pozorrubio-only launch, this can be derived from the existing Team 3 output:

```text
data/processed/team3_eda/heap_occupation_by_field.parquet
```

That file already contains Pozorrubio and Pangasinan field shares. For future multi-municipality use, the team should build the same fields for every municipality in scope.

If the saturation dataset is missing, the recommender should fall back to a neutral `market_score = 0.5` after logging or returning a warning. It should not fail the recommendation run. Q10 affordability data remains the blocking dataset.

## 8. Questionnaire Requirements

The current schema needs one clarification before implementation is final.

Status note: the recommender code already implements option-level scoring from `questions`, and the ERD-shaped tests cover that behavior. The DB schema still needs to adopt the same option-level contract everywhere Team 5 reads the answers from.

Implementation note, 2026-05-16: the Supabase schema now includes `answer_option.option_id` and `users_response.option_id`. That is the preferred integration contract. The recommender can still accept ERD-shaped `question_id` + selected option values for local tests, but production reads should resolve each response through `option_id`.

Implementation note, 2026-05-16: recommender v1.2 reintroduces Q7 as a required SHS strand aptitude multiplier under `model_id = tds_recommender_v1_2`. The support is methodological rather than causal: Team 3's questionnaire-scoring contract includes multiplier-style scoring, and the Team 4 model notes specify that Q7 should multiply matching aptitude dimensions. v1.2 uses the already-tested v1 multiplier map and keeps Q7 separate from additive `questions` scoring rows.

| Requirement                              | Problem                                                                                                                                                                                                                | Proposed fix                                                                                            |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Answer scoring must be unambiguous       | `users_response` stores `question_id` and `selected_option`, while `questions` stores one set of scores per row. If one question has multiple answer options, the recommender needs to know which scoring row applies. | Add an option/scoring lookup table, or make `question_id` uniquely identify each selectable answer row. |
| Barangay must be captured                | Q11 needs the student's actual barangay, not just municipality.                                                                                                                                                        | Team 5 sends `student_barangay_id` when calling the recommender.                                        |
| Q10/Q11/Q12 answer values must be stable | The model maps answers like A/B/C to rules. If labels change, rules can break.                                                                                                                                         | Freeze stored option values for Q10, Q11, and Q12 before integration.                                   |

## 9. Recommendation Rules

### Rule 1: Build Student Scores

Use Q1-Q9 to create six scores:

- STEM
- Health
- Arts
- Business
- Education
- Agriculture

The student score should only represent the student. Do not put market saturation inside the student vector.

Plain formula:

```text
student_score = 55% interest/internal score + 45% aptitude score
```

### Rule 2: Score Program Fit

Compare the student's six scores with each program's six affinity scores.

The program score uses:

- cosine similarity: checks whether the student and program point toward the same field interests,
- dot product: gives a small advantage when both student and program are strongly aligned.

Plain formula:

```text
base_score = 70% cosine similarity + 30% normalized dot product
```

### Rule 3: Apply Municipality Saturation Adjustment

Look up the program's dominant affinity field in `municipality_field_saturation`, using the student's municipality.

The saturation score should be normalized to a 0.0 to 1.0 scale before it is blended into the program score.

Plain formula:

```text
program_score_before_q12 = 90% base_score + 10% municipality_saturation_score
```

The saturation score must never override a poor student-program fit. It should only break close cases or slightly strengthen programs with relevant local context.

For v1.1, use the ecosystem interpretation:

```text
higher saturation = stronger local field presence = small positive context signal
```

The explanation must describe this carefully as local field presence, not guaranteed job demand.

### Rule 4: Apply Q12 Duration Penalty

If a student prefers a faster or less board-exam-heavy path, and the program has a high `affinity_duration_score`, apply a small penalty:

```text
program_score = program_score_before_q12 * 0.85
```

If the program fits the student's Q12 tolerance, no penalty is applied.

### Rule 5: Pick Top Three Programs

Rank programs by `program_score`, then apply a small diversity rule so the top three are not unnecessarily repetitive.

If scores are tied, break ties in this order:

1. Higher base fit score.
2. Fewer penalties.
3. Different dominant field from programs already selected.
4. Alphabetical program name.

For the program's own dominant affinity field, ties inside the six affinity scores are resolved alphabetically by field label. This keeps cases like Health = 5 and STEM = 5 deterministic.

### Rule 6: Find Schools For Each Recommended Program

For each selected program, find schools that offer it by joining:

```text
program -> university_program -> university
```

This step is where school-specific constraints are applied. Program fit should not be recalculated separately for every school.

### Rule 7: Apply Q11 Travel Filter To School Suggestions

| Q11 answer | Meaning              | Rule                                |
| ---------- | -------------------- | ----------------------------------- |
| A          | Nearby only          | Keep schools at or below 45 minutes |
| B          | Willing to travel    | Keep schools at or below 90 minutes |
| C          | Can dorm or relocate | No commute limit                    |

Commute must come from `barangay_university_commute_matrix`, using the student's `barangay_id`.

### Rule 8: Apply Q10 Affordability Filter To School Suggestions

| Q10 answer | Meaning              | Rule                                   |
| ---------- | -------------------- | -------------------------------------- |
| A          | Very limited budget  | Keep only schools affordable at tier 1 |
| B          | Moderate budget      | Keep schools affordable at tier 3      |
| C          | More flexible budget | Keep schools affordable at tier 5      |

Affordability must come from `barangay_university_economic_burden`.

### Rule 9: Choose Primary And Alternate Schools

For each recommended program, rank feasible schools in this order:

1. Passes both Q10 affordability and Q11 travel rules.
2. Lower `total_annual_burden_php`.
3. Shorter `commute_time_mins`.
4. More relevant scholarship availability.
5. University type or metadata needed by Team 5.
6. Alphabetical university name.

The first school becomes the primary school suggestion. Other feasible schools are returned as `alternate_schools` in the API response.

If a recommended program has no feasible school after Q10/Q11, the recommender should try the next-highest program. If fewer than three programs have feasible schools, return `NO_CANDIDATES` and write no rows.

Scholarships are context only in v1.1. They can improve the explanation and school ordering among already feasible schools, but they do not bypass Q10 affordability or Q11 mobility filters. There is no scholarship-rescue mechanism in v1.1.

## 10. Stored Output

The recommender writes exactly three primary rows to `model_recommendation`.

Each row represents one recommended program. The stored `university_id` is the primary school suggestion for that program.

| Column              | Meaning                                                             |
| ------------------- | ------------------------------------------------------------------- |
| `recommendation_id` | Unique row ID                                                       |
| `session_id`        | Student session                                                     |
| `model_id`          | Model version; use `tds_recommender_v1_1` for v1.1 and `tds_recommender_v1_2` for Q7-enabled v1.2 unless backend uses UUIDs |
| `rank`              | 1, 2, or 3; this ranks the recommended programs                     |
| `program_id`        | Recommended program                                                 |
| `university_id`     | Primary suggested school for the recommended program                |
| `model_score`       | Final program score after fit, saturation, and Q12 adjustment        |
| `created_datetime`  | Time created                                                        |

The table should not store explanation JSON in v1.1.

## 11. Returned Explanation

The API should return an explanation object for each of the three rows.

The explanation should answer:

- Why this program matched the student.
- Which school is the primary suggestion for that program.
- Which alternate schools are also feasible.
- Whether school suggestions passed travel and affordability filters.
- Whether Q12 caused a duration penalty.
- What municipality saturation contributed to the score.
- What scholarship information is available.
- Whether any warning or context should be shown, such as low confidence or limited nearby scholarships.

Minimum returned fields:

| Field                        | Meaning                                                  |
| ---------------------------- | -------------------------------------------------------- |
| `rank`                       | 1, 2, or 3                                               |
| `program_id`, `program_name` | Recommended program                                      |
| `primary_school`             | Stored school suggestion for this program                |
| `alternate_schools`          | Other feasible schools for the same program              |
| `program_score`              | Program score after fit scoring and Q12 penalty          |
| `market_context`             | Municipality saturation score and explanation            |
| `matched_dimensions`         | Fields that match the student's answers                  |
| `constraints_applied`        | Q10/Q11 results and commute/burden details               |
| `penalties_applied`          | Q12 duration penalty if any                              |
| `scholarship_context`        | Scholarship counts and sample names                      |
| `low_confidence_flag`        | Whether results are very close or student signal is weak |
| `explanation_text`           | Plain-language explanation for the UI                    |

## 12. Error Cases

| Error                     | When it happens                                            | Expected behavior             |
| ------------------------- | ---------------------------------------------------------- | ----------------------------- |
| `INVALID_SESSION`         | Session is missing or invalid                              | Do not write recommendations  |
| `INCOMPLETE_RESPONSES`    | Required questionnaire answers are missing                 | Do not write recommendations  |
| `INVALID_BARANGAY`        | `student_barangay_id` is not found                         | Do not write recommendations  |
| `MISSING_Q10_BURDEN_DATA` | Affordability dataset is missing or incomplete             | Do not write recommendations  |
| `MISSING_SATURATION_DATA` | Municipality saturation data is missing or incomplete      | Use neutral score and warn     |
| `LOW_SIGNAL`              | Student answers produce almost no useful signal            | Ask student to review answers |
| `NO_CANDIDATES`           | Fewer than three programs have feasible school suggestions | Return guidance message       |

## 13. Remaining Requirements

| Area          | Requirement                                                | Proposal                                                                                                |
| ------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Data          | Complete Supabase commute coverage                         | Add missing barangay-university rows for newly added schools before appending them to v1.1 datasets     |
| Data          | Add PMA and MAAP commute rows                              | Their local demo offerings are defined, but both still have 0/34 barangay commute coverage              |
| Data          | Load `barangay_university_economic_burden` to Supabase     | A 918-row local load file has been generated from the completed commute matrix and Q10 burden rules     |
| Data          | Load `municipality_field_saturation` to Supabase           | A 6-row local load file has been generated from Team 3 HEAP occupation shares for Pozorrubio            |
| Database      | Confirm `model_recommendation.rank` exists and is writable | Team 5 confirms schema before integration                                                               |
| Database      | Decide future explanation logging                          | For v1.1, return explanations only; for v2, add `explanation_json` or a separate trace table            |
| Questionnaire | Seed `questions` and `answer_option`                       | The tables exist in Supabase, but the 2026-05-16 export has zero rows                                   |
| Questionnaire | Capture barangay reliably                                  | Team 5 sends `student_barangay_id` to recommender                                                       |
| Model         | Maintain program-first v1.1 tests                          | Tests must cover saturation, Q10/Q11 filtering, scholarship context, and deterministic tie-breaks       |
| Web/API       | Confirm request and response contract                      | Team 5 consumes stored rows plus returned explanations                                                  |

## 14. Test Plan

Before Team 5 integration, verify:

- Q1-Q9 create the expected six student scores.
- program-first ranking returns three distinct programs when possible.
- municipality saturation changes close program rankings without overriding poor student-program fit.
- missing saturation data falls back to a neutral score and returns a warning.
- saturation context appears in the returned explanation but is not persisted in `model_recommendation`.
- each recommended program has one primary school.
- alternate schools are returned but not persisted.
- Q11 removes school suggestions beyond the travel limit.
- missing `barangay_university_economic_burden` returns `MISSING_Q10_BURDEN_DATA`.
- Q10 removes unaffordable school suggestions when burden data is present.
- Q12 applies the duration penalty only when needed.
- dominant-field ties resolve deterministically by alphabetical field label.
- scholarships do not bypass Q10/Q11 feasibility filters.
- weight-sensitivity output is generated at `reports/model/team4_recommender_v1_1_weight_sensitivity.csv`.
- exactly three rows are written to `model_recommendation`.
- persisted `rank` values rank programs, not alternate schools.
- returned explanations are not written to `model_recommendation`.
- scholarship details join through `scholarship_code`.
- the same input returns the same ranking every time.

## 15. Version 2 Notes

Do not activate Learning to Rank yet.

Before v2, the team needs:

- enough real feedback rows,
- stored recommendation traces or explanation JSON,
- a fairness check so Agriculture and Education are not unfairly pushed down by incomplete market context,
- validation that municipality saturation improves explanations and does not create misleading job-demand claims.

## 16. Handoff Checklist

- TDS v1.1 is approved.
- `barangay_university_economic_burden` has owner, schema, and delivery date.
- `municipality_field_saturation` has owner, schema, and launch data for Pozorrubio.
- Team 5 confirms `student_barangay_id` input.
- Team 5 confirms `model_recommendation` write contract.
- Team 5 confirms returned explanation rendering for primary and alternate schools.
- Team 4 confirms ERD-shaped tests pass.
- Team 4 and Team 5 decide whether v2 will use `explanation_json` or a separate trace table.
