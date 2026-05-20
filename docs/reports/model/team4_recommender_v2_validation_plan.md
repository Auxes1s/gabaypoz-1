---
title: GabayPoz Recommender v2 — Validation & Improvement Plan
document_id: team4_recommender_v2_validation_plan
version: 1.0
date: 2026-05-17
status: Pre-pilot — no real student data collected yet. This plan must be executed
        before v2 can be considered scientifically validated.
---

# GabayPoz Recommender v2 — Validation & Improvement Plan

## § 1. Validation Question and Success Definition

**Central validation question:** Do GabayPoz v2 recommendations match the programs real students choose or would be satisfied pursuing?

This question is currently unanswerable. Every weight, template, and threshold in the v2 model is an expert prior — the team's best structured guess before seeing any real student outcome data. No real student has yet used the system, and no enrollment or satisfaction data exists. The validation plan exists to give those priors empirical grounding through a designed pilot study.

### Operational Success Definitions

**Relevance:** Among the top-3 recommendations generated for a student, at least one matches the student's own stated first-choice program or program area. Formally, this is Precision@3 — the fraction of students for whom the ground-truth program or field appears in the recommended set. A target threshold (≥ 0.50 exact-match, ≥ 0.70 field-match) is proposed but must first be established from pilot baseline measurement, since no prior GabayPoz recommender exists to benchmark against.

**Acceptance:** The student would consider at least one of the three recommendations when making their actual enrollment decision. Measured directly via feedback question 4 (see `docs/questionnaires/gabaypoz_feedback.docx`). Target: acceptance rate ≥ 0.75.

Both thresholds are provisional until the pilot provides a baseline. The role of this validation plan is to collect the data that makes empirical threshold-setting possible.

---

## § 2. What Counts as Ground Truth

The v2 model has no outcome data. Ground truth must be collected prospectively during and after the pilot. Two evidence levels are defined, in increasing strength of causal signal.

### Level 1 — Stated Preference (Immediate, at Pilot Time)

During the pilot session, immediately after viewing recommendations, the student answers: "Which program are you currently leaning toward or have chosen?" This is administered as a structured field (open text + optional GabayPoz field selector) appended to the feedback survey.

This is a self-report, not an enrollment record. It is subject to social desirability bias and recency effects (students may be influenced by the recommendations they just saw). Despite these limitations, it is the fastest available ground truth and the primary metric for v2 validation and v2.1 weight-fitting.

**Persistence:** Stored in the feedback response table, keyed by `session_id`. The GabayPoz field selection should map to one of the six affinity dimensions (STEM, Health, Arts, Business, Education, Agriculture) to enable field-level Precision@3 computation.

### Level 2 — Enrollment Follow-Up (6–12 Months Later)

Where possible, follow up with consenting pilot participants to record their actual college enrollment: the institution and program they enrolled in. This is the strongest available validation signal because it reflects a real decision under real constraints.

Level 2 ground truth is the evidence most directly relevant to the project's stated goal (helping students make better choices) but requires longitudinal tracking and is subject to high attrition. It should be collected opportunistically for every consenting participant but cannot be the primary basis for near-term model iteration.

**Both levels should be collected.** Level 1 enables fast iteration (weight refitting within weeks of pilot completion). Level 2 gives long-run causal signal and will anchor future model versions.

---

## § 3. Two Validation Tracks

### Track A — Construct Validity of the Questionnaire

Before trusting the student affinity vector `s ∈ [0,1]⁶`, the measurement instrument that produces it must be validated. The v2 questionnaire assumes that each of the 6 fields is measured by 4 items: 2 domain interest items and 2 domain self-efficacy items. Track A verifies that this assumed measurement structure holds in the actual student population.

Track A analyses are run on the raw Likert responses (V2Q01–V2Q24, the 24 affinity items). They do not require ground-truth outcome data — only completed questionnaire responses. Track A can begin as soon as N ≥ 80 sessions are collected.

#### A1. Internal Consistency (Cronbach's Alpha)

For each of the 6 fields, compute Cronbach's alpha over the 4 items assigned to that field (2 interest + 2 self-efficacy).

```
α = (k / (k - 1)) · (1 - Σ(σ²ᵢ) / σ²_total)
```

where k = 4 items per field, σ²ᵢ is the variance of item i, and σ²_total is the variance of the 4-item sum.

**Target:** α ≥ 0.65 per field. This is the minimum acceptable for an exploratory scale. Fields falling below this threshold may indicate item wording problems, conflation of distinct constructs, or poor item discrimination. Items failing this threshold must be revised before fitting the model to outcome data.

#### A2. Item-Total Correlations

For each item within a field, compute the Pearson correlation between the item's responses and the mean of the other 3 items in the same field (corrected item-total correlation).

**Target:** All items ≥ 0.30. Items below this threshold are poor indicators of their assigned field and should be reworded or replaced before the next questionnaire version.

#### A3. Dimensionality Check (Inter-Field Correlations)

The 6 field scores should exhibit moderate between-field correlations but remain distinguishable. Compute the 6×6 correlation matrix of field-level affinity scores. Moderately correlated fields (e.g., STEM and Health, due to students interested in nursing having high STEM affinity) are expected; indistinguishable fields (r > 0.85) indicate the questionnaire is not separating the dimensions intended by the model.

If N permits (N ≥ 120 recommended), run an Exploratory Factor Analysis on the 24 affinity items. A clean 6-factor solution would confirm the model's assumed dimensional structure. A solution with fewer clear factors would indicate construct overlap that the current blending weights do not account for.

#### A4. Construct Discriminant Validity

Within-field item correlations should exceed between-field item correlations for the same construct family. Specifically, the average correlation among the 4 items of a given field should be higher than the average correlation between those 4 items and the items of any other field. A failure here indicates that field boundaries in the questionnaire do not match the psychological boundaries students apply when answering.

#### A5. Interest vs. Self-Efficacy Discriminant Check

The model's blending formula treats interest (weight 0.60) and self-efficacy (weight 0.35) as distinct constructs contributing differently to the affinity score. This distinction is only defensible if interest and self-efficacy items for the same field are not perfectly correlated with each other.

Check: for each field, the correlation between the 2 interest items should not substantially exceed the correlation between the 2 interest items and the 2 self-efficacy items. If interest and self-efficacy items within a field are indistinguishable (r > 0.85), the separate-weight design is not supported by the data, and the formula should collapse them into a single affinity weight.

---

### Track B — Outcome Validity of the Recommender

Track B measures whether the recommender's outputs match student preferences and satisfy the project's success metrics. Track B requires both `model_recommendation_trace` data and Level 1 (or Level 2) ground truth. It can begin at N ≥ 30 for interim metrics and should be run in full at N = 150.

#### B1. Precision@3 / Hit Rate

For students where Level 1 or Level 2 ground truth is available, compute the fraction whose stated or actual program choice appears among the 3 recommendations.

Two variants are reported:
- **Exact match:** The student's stated program name maps to one of the 3 recommended programs.
- **Field-level match:** The student's stated program belongs to the same GabayPoz affinity field (STEM, Health, Arts, Business, Education, Agriculture) as at least one of the 3 recommended programs.

Field-level match is the more lenient and more reliable measure given the granularity limitations of Level 1 self-report. Both should be reported.

#### B2. Acceptance Rate

Fraction of students who indicate they would consider at least one recommendation when making their actual enrollment decision. Sourced directly from feedback question 4 (`docs/questionnaires/gabaypoz_feedback.docx`). This is a binary item per student.

#### B3. Relevance Rating

Mean response to feedback question 1 ("Do top three programs reflect your interests and strengths?") on its response scale. Provides a continuous measure of perceived relevance complementing the binary Precision@3.

#### B4. Confidence Shift

Before-vs.-after delta on the student's self-reported confidence in their program choice. Feedback question 6 (`docs/questionnaires/gabaypoz_feedback.docx`) captures this. A positive mean shift across participants is the target outcome — the system should increase decision confidence, not decrease or leave it unchanged.

Pre-recommendation confidence should be captured at the start of Part 3 of the pilot session (before the student views recommendations), and post-recommendation confidence immediately after. The delta is computed per student; the mean delta across all participants is the reported metric.

#### B5. Fairness Across the 6 Fields

Compute the share of top-3 recommendations falling into each of the 6 affinity fields, broken down by student SHS strand (STEM, ABM, HUMSS, TVL, GAS).

The EDA findings (Team 3 headline 5) predict that Agriculture and Education may be systematically underrepresented due to compound disadvantages in the current program profile data. A field receiving fewer than 5% of all recommendations across a diverse pilot sample is a fairness flag requiring investigation.

Expected pattern: STEM-strand students will skew toward STEM/Health recommendations; TVL-strand students should include Agriculture recommendations where affinity supports it. If Agriculture is absent from TVL-strand outputs, the Q12 duration penalty or program profile vectors for that field may need adjustment.

#### B6. Calibration of Low-Confidence Flags

The v2 model emits three guardrail flags:
- `LOW_SIGNAL` — student affinity vector norm < 0.45 (student answered very uniformly low)
- `LOW_SPECIFICITY_PROFILE` — student affinity vector std < 0.08 (student answered uniformly across all fields)
- `CLOSE_RANKING` — top-to-bottom score spread < 0.05 (recommendations are nearly tied)

For well-calibrated flags, sessions where a flag was emitted should have lower acceptance rates and lower relevance ratings than flag-absent sessions. If flagged sessions do not show lower acceptance, the flag thresholds are miscalibrated and need revision. If flagged sessions show dramatically lower acceptance (< 0.50), the system should consider surfacing the flag to the student with an appropriate explanation rather than displaying rankings that may be uninformative.

---

## § 4. Pilot Design

### 4.1 Target Sample Size

**N = 150 complete sessions** is the minimum target for the full validation plan.

The sample size requirement is driven by three separate analyses:
- **Cronbach's alpha stability:** Stabilises around N ≥ 80–100. Track A interim analysis begins at N = 80.
- **Precision@3 reliability:** With N = 150 and a true hit rate of 0.50, the 95% confidence interval width is approximately ±0.08 — narrow enough for a useful baseline estimate.
- **Fairness subgroup analysis:** With 5 SHS strands and N = 150, average cells contain 30 students per strand, enough for strand-level comparison but requiring balanced recruitment.

Dropout and incomplete sessions are expected. Aim to begin pilot recruitment with a target of N = 180 initiated sessions to achieve N = 150 complete (questionnaire + recommendations + feedback).

### 4.2 Recruitment

**Target population:** Grade 11 and Grade 12 senior-high-school students in Pozorrubio and immediately surrounding municipalities in Pangasinan.

**SHS strand representation:** Aim for at least 15–20 participants per strand (STEM, ABM, HUMSS, TVL, GAS). This is required for the fairness analysis in B5. TVL-strand students are especially important given the Agriculture representation concern; do not allow TVL to be underrepresented by defaulting to the most accessible STEM-strand cohort.

**Timing:** Coordinate with school guidance counselors. The optimal window is when Grade 12 students are actively thinking about college enrollment — typically the second semester of Grade 12 (January–April), prior to NCAE and CHED enrollment deadlines. Grade 11 students may also participate; their Level 2 follow-up window will be approximately 12–18 months.

**Access channels:** Coordinate with SK Federation of Pozorrubio and school principals for class scheduling. Group pilot sessions (e.g., using school computer labs) are operationally efficient but require the recommendation system to be accessible by multiple concurrent users.

### 4.3 Session Instrument

Each pilot session consists of three sequential parts administered in a single sitting.

**Part 1 — Questionnaire**

The complete v2 questionnaire (V2Q01–V2Q29) delivered via the GabayPoz web interface. All 24 Likert affinity responses, 4 context/constraint responses, and the V2Q29 aspiration response must be persisted to the database with their `question_id`, `construct_family`, `target_field`, and `response_value` before Part 2 begins. If persistence fails, the session should not proceed — incomplete trace data cannot be used for Track A or Track B.

**Part 2 — Recommendations**

The recommender generates and displays the top-3 program recommendations with explanations. The full `model_recommendation_trace` (containing `construct_scores`, `constraints`, `warnings`, `explanation_json` with intermediate scores) is persisted automatically upon recommendation generation. Students should be given adequate time to read each recommendation and its explanation before proceeding to Part 3.

**Part 3 — Feedback Survey**

Immediately after viewing recommendations (same session, before the student leaves), the student completes:

1. The 6 questions from `docs/questionnaires/gabaypoz_feedback.docx`
2. **Pre/post confidence items:** "Before seeing recommendations, how confident were you in your program choice?" (collected at the start of Part 3 as a recall measure) and "After seeing recommendations, how confident are you?" (collected at the end of Part 3). Both on a 1–5 scale.
3. **Level 1 ground truth item:** "Which program are you currently leaning toward or have chosen?" — open text field plus an optional GabayPoz field selector (STEM / Health / Arts / Business / Education / Agriculture).
4. **Enrollment follow-up consent:** Optional consent checkbox for contact 6–12 months later to verify enrollment. If consent is given, a separate contact detail field (not linked to the session trace) should be collected and stored offline according to DepEd data privacy guidelines.

### 4.4 Consent and Anonymization

- All participants must provide written or digital informed consent before Part 1 begins. For minor participants (under 18), parental/guardian consent is additionally required per DepEd data privacy guidelines.
- No personally identifiable information (name, address, contact details) should be stored in the `model_recommendation_trace`, questionnaire response table, or any evaluation export. The session is identified only by an opaque `session_id`.
- Enrollment follow-up contact details (for consenting participants) must be stored in a physically separate, access-controlled record (not in the application database) and destroyed after Level 2 data collection is complete.
- All data exports for Track A and Track B analysis must contain only `session_id`, anonymized response values, and model output fields — no PII.

### 4.5 Data Infrastructure Requirements

The following must be confirmed **operational before pilot launch**:

1. **`model_recommendation_trace` persistence:** Every completed recommendation session must write a trace row. The evaluation harness depends entirely on this. Verify with an end-to-end integration test before pilot begins.
2. **Raw Likert response persistence:** Each questionnaire item response must be stored with (`session_id`, `question_id`, `construct_family`, `target_field`, `response_value`). Without this, Track A (construct validity) cannot be run.
3. **Feedback response persistence:** All feedback form responses must be stored linked to `session_id` in the `recommender_v2_feedback_response` contract: relevance score, surprise/missing program text, acceptance choice, binary `would_consider_any`, pre/post confidence, computed `confidence_shift`, stated-choice program, stated-choice field, and follow-up consent.
4. **Session completeness flag:** The `recommender_v2_session_completeness` view or equivalent should indicate sessions where all three parts (29 questionnaire responses, at least 3 recommendation trace rows, and one feedback row) were fully completed. Incomplete sessions should be excluded from metric computation.

The evaluation harness (`evaluate_recommender_v2.py`) consumes the above exports and produces Track A, Track B, feedback completeness, trace completeness, strand fairness, top-3 field fairness, and V2Q29 boost acceptance outputs.

---

## § 5. Metrics and Thresholds Table

| Metric | Definition | Target | Data source | Track |
|---|---|---|---|---|
| Cronbach's alpha per field | Internal consistency over 4 items (2 interest + 2 efficacy) per field | ≥ 0.65 all 6 fields | Pilot Likert responses | A |
| Item-total correlation | Corrected correlation of each item with its field's mean | ≥ 0.30 all 24 items | Pilot Likert responses | A |
| Inter-field discriminant | Within-field avg correlation > between-field avg correlation | Pass for all 6 fields | Pilot Likert responses | A |
| Precision@3 (exact) | Fraction of students whose stated/actual program is in top-3 | Establish baseline first; target ≥ 0.50 in v2.1 | Trace + Level 1/2 ground truth | B |
| Precision@3 (field-level) | Fraction where the ground-truth field appears in top-3 recommended fields | ≥ 0.70 | Trace + ground truth | B |
| Acceptance rate | Fraction of students who would consider at least one recommendation (feedback Q4) | ≥ 0.75 | Feedback Q4 | B |
| Relevance rating | Mean feedback Q1 score on 1–5 scale | ≥ 3.5 / 5 | Feedback Q1 | B |
| Confidence shift | Mean (post-recommendation confidence – pre-recommendation confidence) | > 0 (positive shift) | Feedback Q6 / pre-post items | B |
| Field distribution fairness | Share of rank-1 and top-3 recommendations in each of 6 fields across full pilot sample | All fields ≥ 5% of total recommendations | Trace | B |
| Low-confidence calibration | Acceptance rate for sessions with flag=True vs. flag=False | flag=True sessions consistently lower | Trace + feedback | B |
| Strand fairness | Field recommendation distribution broken down by SHS strand | No strand receives exclusively 1-field recommendations | Trace + strand from questionnaire | B |

**Note on Precision@3 baseline:** Because no prior GabayPoz recommender exists, the pilot is the first measurement of this metric. The pilot baseline should be measured first, reported honestly, and then used to set v2.1 improvement targets. A baseline below 0.35 (exact-match) would indicate the model needs substantial revision before a second pilot. A baseline above 0.55 would indicate the expert prior is well-calibrated.

---

## § 6. The Bayesian Improvement Loop — Improving on the Prior

The current v2 model is a **prior**: every weight and template is the team's best expert guess constructed before observing real student outcomes. Pilot data provides the **likelihood** — the empirical probability that the current model's outputs match observed choices and satisfaction. Combining these yields the **posterior**, which is the basis for model v2.1.

This framing is operationally important: the pilot is not just a pass/fail test of v2. It is the data collection mechanism that enables the first fitted version of the model.

### 6.1 What Gets Updated

| Component | Current prior value | How to update from pilot data |
|---|---|---|
| Interest/efficacy/strand weights (0.60/0.35/0.05) | Expert guess | Ridge regression: predict acceptance or satisfaction score from the three construct sub-scores across pilot sessions; refit weights as regression coefficients |
| Prior/template blend (0.55/0.45) | Expert guess | For programs with ground-truth choices, compare how close the prior-only vs. template-only profile was to the accepted student vector; adjust blend toward the better performer |
| Shape/direction split (0.70/0.30) | Expert guess | Grid search over (shape_w, 1 − shape_w) in 0.05 increments to maximise Precision@3 on held-out pilot sessions |
| Q12 penalty (×0.85) | Expert guess | Compare acceptance rate for sessions where Q12 penalty was applied vs. not; if acceptance rates are equal, the penalty is not validated and should be reduced |
| LOW_SPECIFICITY_STD threshold (0.08) | Expert guess | Plot acceptance rate as a function of student vector std; set threshold at the std value below which acceptance drops meaningfully |
| Program family templates (hand-authored 6-vectors) | Hand-authored expert priors | Re-label using clustering of pilot student vectors who accepted the recommendation for each program; replace template centroid with cluster centroid |
| 36 human-review program profiles | Flagged, not yet re-assigned | Assign `profile_confidence = high/medium/low` based on observed acceptance rate per program across pilot sessions; programs with zero pilot acceptances remain at low confidence |

### 6.2 Protocol for v2.1

The following steps must be completed in order. Steps should not be skipped even if early results look promising.

1. **Collect pilot data** to N ≥ 150 complete sessions with trace, feedback, and Level 1 ground truth.
2. **Run Track A** (construct validity). If any field fails α < 0.65, item wording must be revised before fitting the model to outcome data. Fitting the model on a poorly measured affinity dimension will produce spurious refits.
3. **Audit trace completeness.** Remove incomplete sessions (missing trace, missing feedback, or missing Level 1 ground truth item) from the fitting dataset.
4. **Split pilot data** 70% train / 30% test using stratified sampling by SHS strand. The test set is held out until final v2 vs. v2.1 comparison and must not be used for weight selection.
5. **Refit weights** on the train set. Use the train set for all regression, grid search, and template clustering steps in §6.1. Apply appropriate regularization (ridge for regression steps) to reduce overfitting given small N.
6. **Evaluate v2 vs. v2.1** on the held-out test set using the full metrics table in §5. v2.1 must improve on at least two primary metrics (Precision@3 field-level and acceptance rate) without substantially degrading any metric to be adopted as the production model.
7. **Document all changes.** Every updated prior must be recorded with: pilot sample size used, old value, new value, 95% confidence interval or standard error, and the evaluation metric that motivated the change.
8. **Keep v2 as a versioned baseline.** Do not overwrite the v2 implementation or parameter file. Bump to v2.1, update `model_id` in the recommendation trace, and document the version transition in a new TDS revision.

### 6.3 Versioning Discipline

- Each model version is identified by a `model_id` field in `model_recommendation` rows. Every session's trace records which model version produced the output.
- v2 priors — the current interest/efficacy/strand weights, blend ratios, shape/direction split, penalty factors, and program templates — must remain in the codebase and documentation as the reference baseline. They represent the starting point and are required for v2 vs. v2.1 comparison.
- v2.1 (the first fitted model) must be fully documented in a new TDS version identifying each changed component, the data that drove the change, and the confidence interval on the new value.
- If Track A reveals measurement problems that require questionnaire revision, the revised questionnaire constitutes a new version of the instrument (e.g., V2.1Q01–V2.1Q28), and the pilot must be re-run on the new instrument before fitting. Do not fit v2.1 weights on data collected under a defective measurement instrument.

---

## § 7. Phased Timeline

| Phase | Activity | When | Owner |
|---|---|---|---|
| Pre-pilot setup | Confirm `model_recommendation_trace` persistence is active end-to-end | Before pilot launch | Team 4 |
| Pre-pilot setup | Confirm raw Likert response persistence is active | Before pilot launch | Team 4 |
| Pre-pilot setup | Deploy feedback instrument (6 core questions + pre/post confidence + Level 1 ground truth item + consent) | Before pilot launch | Team 4 + Team 5 |
| Pre-pilot setup | Human-review the 36 flagged program profiles; assign preliminary `profile_confidence` | Before pilot launch | Team 4 + domain expert |
| Pre-pilot setup | Keep `evaluate_recommender_v2.py` green with Track A, Track B, completeness, top-3 fairness, strand fairness, and V2Q29 boost metrics | Before pilot launch | Team 4 |
| Pilot data collection | Administer pilot to N = 150–180 participants across SHS strands | TBD — coordinate with schools | Team 4 + Team 6 + school partners |
| Track A interim | Run Cronbach's alpha and item-total correlations at N ≥ 80 | After N = 80 complete sessions | Team 4 |
| Track B interim | Compute acceptance rate and relevance rating (interim estimates) | After N ≥ 30; repeat at N = 80 | Team 4 |
| Full Track A analysis | All construct validity metrics including inter-field correlations and EFA (if N ≥ 120) | After N = 150 | Team 4 |
| Full Track B analysis | All outcome metrics including fairness, Precision@3, calibration | After N = 150 | Team 4 |
| v2.1 weight fitting | Refit all components (§6.1); evaluate on held-out test set | After full pilot analysis | Team 4 |
| v2.1 documentation | New TDS version with updated parameters and confidence intervals | After v2.1 fitting | Team 4 |
| Level 2 follow-up | Enrollment verification for consenting participants | 6–12 months post-pilot | Team 4 + Team 6 |
| Level 2 analysis | Compute Precision@3 (enrollment) and confidence shift (long-run) | After Level 2 data collection | Team 4 |

---

## § 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Small pilot N (< 80 complete sessions) | Medium | High — Track A results unreliable; confidence intervals too wide for weight fitting | Engage multiple schools before pilot launch; set N = 150 as minimum for full analysis reporting; do not refit weights on N < 80 |
| Self-report bias in Level 1 ground truth | High | Medium — stated preferences may be influenced by recommendations just seen | Collect pre-recommendation program preference at start of Part 3 (before displaying recommendations) as a contamination check; report both pre- and post-display ground truth |
| Enrollment follow-up attrition (Level 2) | High | Medium — Level 2 ground truth sparse | Design consent process to maximise opt-in; offer a brief follow-up channel (SMS or email); treat Level 1 as the primary metric and Level 2 as supplementary |
| Field imbalance in pilot sample | Medium | Medium — fairness metrics unreliable if Agriculture/TVL is underrepresented | Stratify recruitment by SHS strand; explicitly target TVL-strand schools and sessions; do not report B5 fairness metric if any strand has N < 10 |
| Model recommendation trace not persisted for some sessions | Low | High — evaluation harness has no data for those sessions | Verify trace persistence with integration test before pilot; add a session-completeness check that blocks feedback form if trace write failed |
| Raw Likert responses not persisted (Track A blocked) | Low | High — Track A cannot be run; questionnaire validity unknown | Verify Likert persistence in pre-pilot infrastructure check; Track A is a go/no-go gate before pilot begins |
| v2.1 overfits to small pilot N | Medium | Medium — refitted weights not generalisable beyond Pozorrubio | Report 95% CI on all refitted quantities; hold out 30% test set strictly; flag components with CI width > 0.2 as requiring a larger follow-up sample |
| Agriculture/Education underrepresented in recommendations (B5) | Medium | Medium — model biased against these fields | If detected in Track B, check program profile vector norms for Agriculture/Education; check Q12 penalty application rate; investigate whether `LOW_SIGNAL` flag rate is higher for Agriculture-leaning students |
| Questionnaire construct fails Track A (α < 0.65 for a field) | Medium | High — model fitting must be paused pending item revision | Document failing fields; revise item wording with domain experts; run a small N = 40 re-test of revised items before re-launching pilot |
| School access delays push pilot past enrollment decision window | Medium | High — Level 1 ground truth less meaningful if students have already chosen | Coordinate with school partners early; identify a second-semester Grade 12 window as the primary target; Grade 11 students are acceptable but require longer Level 2 follow-up |

---

## Appendix: File References

The following files are referenced in this plan and should be reviewed by the team before pilot launch.

| File | Role |
|---|---|
| `docs/questionnaires/gabaypoz_feedback.docx` | The 6 core feedback questions; source of acceptance, relevance, surprise, and confidence metrics |
| `docs/project/project_management_roadmap.md` | Defines success metrics (relevance, acceptance, confidence shift, engagement) and project phase ownership |
| `analysis/team4_model/recommender_v1_1_sensitivity.py` | Existing pattern for weight-sweep analysis; adapt for grid search in v2.1 fitting |
| `analysis/team4_model/test_recommender_v2.py` | Existing synthetic test profiles; use as smoke tests alongside pilot sessions |
| `analysis/team4_model/recommender_v2.py` | Current v2 model implementation; `model_id` here is the version baseline |
| `docs/reports/model/team4_recommender_v2_erd.md` | Data model for trace, response, and recommendation tables |
