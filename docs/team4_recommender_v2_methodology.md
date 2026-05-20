---
title: GabayPoz Recommender v2 — Methodology White Paper
document_id: team4_recommender_v2_methodology
version: 1.0
date: 2026-05-17
status: Finalised — Audit 2026-05-17. v1→v2 design rationale recorded as an authoritative
        decision (§3). Strand mechanism, limitations, and code citations reconciled.
        Residual ⚑ flags (§4 weight priors, §5 blend ratios) mark quantities awaiting
        pilot refitting — they are documented expert priors, not open questions.
---

# GabayPoz Recommender v2 — Methodology White Paper

## § 1. Purpose and Scope

GabayPoz v2 takes a student's self-reported questionnaire responses and outputs three ranked college-program recommendations, each paired with a feasible school near Pozorrubio. This document is the scientific methodology record for that system. It explains the design of the questionnaire, how student and program "affinities" are derived, how they are matched, and which parts of the system are empirical findings versus expert priors awaiting validation. Versions v1.1 and v1.2 are retained in the codebase for audit continuity but are superseded by v2 for all new sessions.

---

## § 2. The Six-Field Affinity Taxonomy

GabayPoz organizes every program and every student profile into a shared six-dimensional space. Both student and program vectors are defined over the same six fields, and all downstream scoring, filtering, and explanation use these same labels.

| Code          | Field             | Description                                                      |
| ------------- | ----------------- | ---------------------------------------------------------------- |
| `stem`        | STEM              | Sciences, mathematics, engineering, technology, computing        |
| `health`      | Health            | Health sciences, nursing, medicine, allied health                |
| `arts`        | Arts & Humanities | Communication, visual arts, liberal arts, design                 |
| `business`    | Business          | Business administration, management, economics, entrepreneurship |
| `education`   | Education         | Teacher education, pedagogy, educational leadership              |
| `agriculture` | Agriculture       | Agriculture, food tech, veterinary, fisheries, natural resources |

Source: `DIMS` constant at `recommender_v2.py:24`.

---

## § 3. Questionnaire Design Rationale

> **Decision record — 2026-05-17.** The v1→v2 instrument change was formally reviewed and confirmed as necessary during a pre-pilot audit. The rationale below is the authoritative record of that decision.

### 3.1 The v1 → v2 Evolution

v1 used **12 forced-choice questions** (Q1–Q12) where each answer option carried hand-assigned integer point values per field — for example, choosing "Robotics club" awarded `stem +2, agri +1`. This approach had three fundamental weaknesses:

- It **mixed measurement with constraints**: affordability (Q10), commute (Q11), and duration tolerance (Q12) appeared in the same scoring pass as interest items, conflating what a student wants with what a student can access.
- The hand-assigned points **cannot be validated statistically**: there is no way to check whether "Robotics club → stem +2" is correctly calibrated without outcome data.
- With only one categorical choice per dimension area, **internal consistency cannot be computed** — reliability analysis such as Cronbach's alpha requires multiple independent indicators per construct.

**Why the deviation is necessary, and why continuizing the 12 questions does not fix it.**
The pilot's Track A validation (Cronbach's alpha, item-total correlations, EFA, construct validity) requires multiple parallel indicators that each load on a single construct. The original 12-item instrument has zero such items: its forced-choice options cross-load onto several fields simultaneously (e.g. original Q1 option E → Education + Business + Arts). Each field score is a heterogeneous sum across non-parallel items. The blocker is item structure, not response discreteness. Rating each forced-choice option on a continuous scale keeps the cross-loading and still makes Track A impossible — that approach pays the full cost of re-deriving scoring while realising none of the psychometric benefit.

v2 (`V2Q01–V2Q24`): 6 fields × 2 constructs × 2 indicators = 24 parallel, singly-loaded items. This is the minimum structure that makes Track A feasible. The 24 affinity items cannot be trimmed further without breaking the validation design.

v2 separates these concerns: affinity items (V2Q01–V2Q24) measure interest and self-efficacy; constraint items (V2Q25–V2Q28) are inputs to filters and penalty logic only and contribute no affinity points.

### 3.2 The Construct Model

v2 is built on a latent-variable measurement model (documented in `final_questionnaire.docx` and implemented in `seed_recommender_questionnaire_v2.py`). Each of the six fields is treated as a latent variable — something real but not directly observable — with two observable construct families:

| Construct family       | What it measures                                             | Role in student vector                     |
| ---------------------- | ------------------------------------------------------------ | ------------------------------------------ |
| `domain_interest`      | What the student would enjoy doing or learning               | 60% of affinity blend                      |
| `domain_self_efficacy` | What the student believes they can learn or do with practice | 35% of affinity blend                      |
| `context` (strand)     | SHS strand as weak background evidence                       | 5% of affinity blend                       |
| `constraint`           | Budget, commute, duration tolerance                          | Filtering and penalty only; 0% of affinity |

**Why separate interest and self-efficacy?** These are established distinct constructs in educational psychology. Holland's RIASEC theory distinguishes liking an activity from feeling capable at it; Bandura's self-efficacy concept is specifically domain-level perceived capability, distinct from desire. Keeping them separate allows the model to distinguish a student who loves science but doubts their ability (high interest, lower efficacy) from one who is equally confident and interested — and to weight each construct independently once outcome data is available.

**Why 4 indicators per field (2 interest + 2 self-efficacy)?** A single item per construct is unreliable — one question can be misread or evoke a context-specific response. With two indicators per construct per field, the model can compute inter-item correlation and Cronbach's alpha once pilot data is collected. Two indicators per construct is the minimum for basic psychometric validation; 24 total items is the floor for the 6-field design and cannot be reduced without breaking Track A.

**Why 5-point Likert?** The forced-choice format of v1 forced students to pick the "most like me" option, losing information about students who find multiple options relevant. A 5-point Likert scale ("Not like me" to "Strongly like me") captures degree of agreement, enables ordinal analysis, and is standard for self-report affinity instruments in educational and vocational research. Note that Likert scales invite acquiescence bias and straightlining; the `LOW_SIGNAL` and `LOW_SPECIFICITY_PROFILE` guards in the scoring pipeline are the primary mitigation.

### 3.3 The v2 Item Inventory

All V2Q01–V2Q24 are scored on the 5-point Likert scale shown below. Context, constraint, and aspiration items (V2Q25–V2Q29) use categorical response options and contribute no affinity points.

**Likert response scale:**

| Stored value | Label            |
| ------------ | ---------------- |
| 1            | Not like me      |
| 2            | Slightly like me |
| 3            | Somewhat like me |
| 4            | Very like me     |
| 5            | Strongly like me |

**Affinity items (V2Q01–V2Q24)** — source: `seed_recommender_questionnaire_v2.py:48–83`:

| Code  | Construct            | Field       | Item text                                                                                  |
| ----- | -------------------- | ----------- | ------------------------------------------------------------------------------------------ |
| V2Q01 | domain_interest      | STEM        | "I would enjoy building, coding, repairing, or testing how things work."                   |
| V2Q02 | domain_interest      | STEM        | "I like activities that involve numbers, experiments, tools, or technology."               |
| V2Q03 | domain_self_efficacy | STEM        | "I can learn technical or scientific ideas if I practice them step by step."               |
| V2Q04 | domain_self_efficacy | STEM        | "I am confident solving problems that involve math, logic, or systems."                    |
| V2Q05 | domain_interest      | Health      | "I would enjoy learning how to care for people's health and safety."                       |
| V2Q06 | domain_interest      | Health      | "I am interested in biology, medicine, first aid, or community health work."               |
| V2Q07 | domain_self_efficacy | Health      | "I can stay careful and calm when helping someone with a health concern."                  |
| V2Q08 | domain_self_efficacy | Health      | "I am confident following detailed procedures that protect people's well-being."           |
| V2Q09 | domain_interest      | Arts        | "I would enjoy creating, writing, performing, designing, or producing media."              |
| V2Q10 | domain_interest      | Arts        | "I like activities where I can express ideas in original or visual ways."                  |
| V2Q11 | domain_self_efficacy | Arts        | "I can improve creative work after feedback and revision."                                 |
| V2Q12 | domain_self_efficacy | Arts        | "I am confident presenting ideas through words, images, performance, or design."           |
| V2Q13 | domain_interest      | Business    | "I would enjoy planning, selling, budgeting, managing, or starting a venture."             |
| V2Q14 | domain_interest      | Business    | "I like activities involving money decisions, customers, teams, or operations."            |
| V2Q15 | domain_self_efficacy | Business    | "I can organize tasks and persuade people toward a practical goal."                        |
| V2Q16 | domain_self_efficacy | Business    | "I am confident making decisions using costs, benefits, and tradeoffs."                    |
| V2Q17 | domain_interest      | Education   | "I would enjoy explaining lessons, tutoring classmates, or guiding younger learners."      |
| V2Q18 | domain_interest      | Education   | "I like helping people understand ideas and grow through patient support."                 |
| V2Q19 | domain_self_efficacy | Education   | "I can explain a difficult topic clearly to someone who is still learning."                |
| V2Q20 | domain_self_efficacy | Education   | "I am confident leading discussions or learning activities for a group."                   |
| V2Q21 | domain_interest      | Agriculture | "I would enjoy work connected to farming, food production, animals, or natural resources." |
| V2Q22 | domain_interest      | Agriculture | "I like practical outdoor or community work that improves land, crops, or livelihood."     |
| V2Q23 | domain_self_efficacy | Agriculture | "I can learn hands-on methods for growing, producing, or managing resources."              |
| V2Q24 | domain_self_efficacy | Agriculture | "I am confident solving practical problems in farms, food systems, or local enterprises."  |

**Context and constraint items (V2Q25–V2Q28):**

| Code  | Type       | Maps to         | Question                                                                                         | Response options                                                                       |
| ----- | ---------- | --------------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| V2Q25 | context    | Q7 (strand)     | "What is your current Senior High School (SHS) strand?"                                          | A=STEM, B=ABM, C=HUMSS, D=TVL, E=GAS                                                   |
| V2Q26 | constraint | Q10 (financial) | "What is your household financial situation?"                                                    | A=Extremely limited, B=Can afford reasonable tuition, C=More flexible budget           |
| V2Q27 | constraint | Q11 (mobility)  | "How do you plan to get to school every day?"                                                    | A=within 30–45 min, B=okay with 1–2 hrs, C=willing to dorm                             |
| V2Q28 | constraint | Q12 (duration)  | "How do you feel about programs that require 5+ years of study or heavy board exam preparation?" | A=Ready for the challenge, B=Prefer 4-year/no board exam, C=Want fastest path to a job |

### 3.4 The Aspiration Context Item (V2Q29)

V2Q29 asks whether the student intends to pursue post-graduate professional school. It is an aspiration declaration, not a latent-variable indicator: it does not contribute to the student affinity vector **s** and is therefore outside the scope of Track A psychometric validation.

**Question text:** "Do you plan to pursue a graduate professional degree after completing your bachelor's program?"

| Label | Text | Resolves to |
| --- | --- | --- |
| A | Medicine (MD) — I plan to enter medical school | `"medicine"` |
| B | Dentistry (DMD) — I plan to enter dental school | `"dentistry"` |
| C | Law (JD/LLB) — I plan to enter law school | `"law"` |
| D | No / Not sure yet — I will decide based on what I enjoy | `"none"` |

The declared track is aliased as Q13 and mapped to GabayPoz affinity fields in `TRACK_ASPIRATION_FIELD_MAP`. Programs whose computed `dominant_dim` falls in the primary or secondary field set receive a multiplicative scoring boost (see §6.7). Option D ("none") produces zero boost.

---

## § 4. Student Profile Derivation

The 24 affinity responses are combined into a 6-dimensional student affinity vector **s** ∈ [0, 1]⁶. The derivation proceeds in five steps.

### Step 1 — Rescale Likert to [0, 1]

For each affinity item response value *v* ∈ {1, 2, 3, 4, 5}:

```
v_rescaled = clip( (v − 1) / 4 , 0.0, 1.0 )
```

This maps 1 → 0.0, 3 → 0.5, 5 → 1.0. Items are reverse-scored before rescaling if flagged (`reverse_scored = True`; all current items are `False`). Source: `recommender_v2.py:346–348`.

### Step 2 — Validate completeness

Exactly 2 interest items and 2 self-efficacy items must be present and resolved for each of the 6 fields. Any mismatch raises `INCOMPLETE_RESPONSES`. Source: `recommender_v2.py:355–359`.

### Step 3 — Per-field means

For each field *f*, compute the mean of the two rescaled items in each construct family:

```
interest_f  = mean( rescaled values of the 2 domain_interest items for f )
efficacy_f  = mean( rescaled values of the 2 domain_self_efficacy items for f )
```

### Step 4 — Strand context vector

The strand response (V2Q25, aliased as Q7) is converted to a binary 6-vector:

```
strand_context_f = 1.0   if the strand supports field f
                 = 0.0   otherwise
```

The strand-to-field support mapping is (`STRAND_FIELD_SUPPORT`, `recommender_v2.py:32–41`):

| Strand                  | Supported fields      | Selectable in V2Q25? |
| ----------------------- | --------------------- | -------------------- |
| STEM                    | `stem`                | Yes (A)              |
| ABM                     | `business`            | Yes (B)              |
| HUMSS                   | `arts`                | Yes (C)              |
| TVL                     | `stem`, `agriculture` | Yes (D)              |
| GAS                     | none                  | Yes (E)              |
| Sports                  | `arts`                | No — defensive only  |
| Arts and Design         | `arts`                | No — defensive only  |
| Sports / Arts and Design| `arts`                | No — defensive only  |

Sports, Arts and Design, and Sports / Arts and Design are retained in `STRAND_FIELD_SUPPORT` as defensive lookups for sessions where the strand string is set outside the V2Q25 option list (e.g., via direct data entry). They are not selectable options in the standard questionnaire flow. New K–12 curriculum tracks (Academic, Elective, Technical-Professional) are not yet mapped and are treated as unknown strands (`UNKNOWN_Q7_STRAND` warning, zero strand context).

### Step 5 — Weighted blend

```
s_f = 0.60 · interest_f  +  0.35 · efficacy_f  +  0.05 · strand_context_f
```

Constants: `INTEREST_WEIGHT = 0.60`, `EFFICACY_WEIGHT = 0.35`, `STRAND_CONTEXT_WEIGHT = 0.05` (`recommender_v2.py:57–59`). Because all three components are in [0, 1] and the weights sum to 1.0, the resulting vector **s** ∈ [0, 1]⁶ by construction. Source: `recommender_v2.py:364`.

> **⚑ Weight note:** The 0.60 / 0.35 / 0.05 split is an expert prior, not an empirically fit quantity. The interest-over-efficacy emphasis follows educational guidance that interest is the stronger long-run predictor of engagement and persistence, with self-efficacy as a supporting signal. The strand context weight is intentionally small to prevent SHS track from overriding student-expressed preference. These weights should be re-estimated from pilot outcome data.

### Low-signal and low-specificity guards

Before producing recommendations, the model tests whether the student vector carries useful signal. Three flags are applied (`recommender_v2.py:990–998`):

| Flag                      | Condition                       | Meaning                                                                                       |
| ------------------------- | ------------------------------- | --------------------------------------------------------------------------------------------- |
| `LOW_SIGNAL`              | ‖**s**‖₂ < 0.45                 | Near-zero vector — student gave near-"Not like me" on nearly everything                       |
| `LOW_SPECIFICITY_PROFILE` | std(**s**) < 0.08               | Uniform vector — student gave nearly the same score on all 6 fields, yielding no differential |
| `CLOSE_RANKING`           | top score − bottom score < 0.05 | Program scores too close to rank confidently                                                  |

A hard abort (`LOW_SIGNAL_ABORT = 0.15`) is triggered before reaching the scoring stage if ‖**s**‖₂ < 0.15. When any flag is set at the guard stage, `low_confidence_flag = True` and `low_confidence_reason` is recorded in the recommendation trace.

---

## § 5. Program Profile Derivation

Each program is represented by a 6-dimensional program environment vector **p** ∈ [0, 5]⁶ stored in the `program_profile_v2` table. The different scale from student vectors ([0, 1] vs. [0, 5]) does not cause bias because the scoring functions (Pearson correlation and cosine similarity) normalize both vectors.

> **Authoritative v2 scoring contract.** For v2, `program_profile_v2` should be treated as the only authoritative program-side scoring index. Legacy affinity columns may remain in storage for audit continuity, but they should not substitute for missing `program_profile_v2` rows in any run that is presented as a true v2 recommendation output.

### 5.1 The Prior

`program.csv` (from Supabase exports) carries six affinity score columns already assigned to each program:

| Column                          | Field       |
| ------------------------------- | ----------- |
| `affinity_stem_score`           | STEM        |
| `affinity_health_science_score` | Health      |
| `affinity_art_humanities_score` | Arts        |
| `affinity_business_score`       | Business    |
| `affinity_education_score`      | Education   |
| `affinity_agriculture_score`    | Agriculture |

These constitute the **prior** — the team's existing domain knowledge about which programs belong in which fields, encoded as per-program scores.

### 5.2 Family Templates

20 deterministic family templates are hand-authored as 6-vectors on the [0, 5] scale (`build_program_profile_v2.py:49–70`). Each template encodes the field emphasis of a program family. A representative selection:

| Family key                   | Representative programs                         | Dominant dimension(s)     |
| ---------------------------- | ----------------------------------------------- | ------------------------- |
| `health_clinical`            | BS Nursing, BS Pharmacy, BS Medical Technology  | health 5.0, stem 3.8      |
| `engineering`                | BS Civil Engineering, BS Electrical Engineering | stem 5.0                  |
| `ict`                        | BS Information Technology, BS Computer Science  | stem 5.0                  |
| `education`                  | BEEd, BSEd                                      | education 5.0, arts 3.6   |
| `business_accounting`        | BS Accountancy                                  | business 5.0, stem 2.8    |
| `business_general`           | BSBA, BS Entrepreneurship                       | business 5.0              |
| `agriculture`                | BS Agriculture, BS Fisheries                    | agriculture 5.0, stem 3.4 |
| `criminology_public_safety`  | BS Criminology                                  | arts 3.6, health 2.8      |
| `marine_transport`           | BS Marine Engineering, BS Marine Transportation | stem 4.3                  |
| `industrial_technology`      | BS Industrial Technology                        | stem 4.4, business 2.8    |
| `textile_fashion_technology` | BS Textile Technology                           | arts 5.0, business 3.2    |

Each program is assigned a template family through a **deterministic regex cascade** on the lowercased program name (`classify_program`, `build_program_profile_v2.py:142–199`). Rules for narrower families (marine transport, industrial technology, textile/fashion) are placed before broader patterns (engineering, arts) to prevent misclassification.

### 5.3 Blending Prior and Template

The final program profile vector is:

```
profile_vector = clip( 0.55 · prior  +  0.45 · template , 0.0, 5.0 )
```

Constants: `PRIOR_WEIGHT = 0.55`, `TEMPLATE_WEIGHT = 0.45` (`build_program_profile_v2.py:46–47`). The prior carries more weight because it is program-specific and reflects real data; the template provides a disciplined regularizing signal grounded in curriculum family. Source: `build_program_profile_v2.py:258`. ⚑

### 5.4 Occupation-Bridge Evidence

Where a match is found in `program_occupation_bridge.parquet`, the profile is enriched with occupation-bridge confidence, Philippine Standard Occupational Classification labor-market groups (`p21_groups` and `p21_labels`), and CMO evidence text. These populate the `evidence_text` and `evidence_sources` fields in the recommendation trace. Matching uses up to four strategies in order: exact name, exact subject key, fuzzy name (cutoff 0.93), and fuzzy subject key (cutoff 0.95). Source: `build_program_profile_v2.py:212–245`.

### 5.5 Confidence Tiers and Human Review

Each profile is assigned `profile_confidence ∈ {high, medium, low}` by blending the family-classification confidence with occupation-bridge confidence (`build_program_profile_v2.py:264–273`). The effective confidence rules are:

- A family rule marked `high` is downgraded to `medium` if no safe occupation-bridge match is found.
- A `medium` family result combined with a `High`-confidence bridge match stays at `medium`.
- A `low` family result combined with a `High`-confidence bridge match is promoted to `medium`.

Any profile where `review_status = "needs_review"` is exported to `program_profile_v2_review.csv` for manual inspection. The scoring pipeline applies a reliability penalty to `low`-confidence profiles (see § 6.4). Current inventory: **142 programs total — 55 high, 87 medium, 0 low, 36 needs-review**.

### 5.6 Program-Profile Index Scoring Contract

The program-side index is not just a lookup table. It is the formal scoring object that v2 matches against the student profile. For each program, the following fields should be documented and considered part of the scoring contract:

- `affinity_stem_score`
- `affinity_health_score`
- `affinity_arts_score`
- `affinity_business_score`
- `affinity_education_score`
- `affinity_agriculture_score`
- `dominant_dim`
- `secondary_dims`
- `profile_family`
- `profile_confidence`
- `review_status`
- `evidence_text`
- `evidence_sources`

The six affinity scores are the program-profile index itself. All other fields exist to justify, audit, and quality-control that index.

The construction logic is:

1. Read the legacy per-program prior scores from `program.csv`.
2. Assign the program to one deterministic family template.
3. Blend prior and template on the [0, 5] scale with the 0.55 / 0.45 rule.
4. Derive `dominant_dim` and `secondary_dims` from the resulting six-score vector.
5. Attach confidence and evidence metadata.
6. Export any uncertain rows to `program_profile_v2_review.csv`.

The practical implication is important: if a program lacks a valid `program_profile_v2` row, then the program lacks a valid v2 scoring index and should not be silently scored as though it had one.

---

## § 6. Scientific Matching Method

Given a student vector **s** ∈ [0, 1]⁶ and a program vector **p** ∈ [0, 5]⁶, the recommender computes a `program_score` for every program, ranks them, and returns the top 3. The scoring pipeline proceeds through six stages.

Before the student-to-program match is computed, both sides of the system must already have valid scoring indexes:

- the **student-profile index** `s`, derived from the 24 affinity items plus bounded strand context
- the **program-profile index** `p`, derived from the blended `program_profile_v2` vector

These two indexes are the core intellectual object of v2. Constraints and context signals refine the result after the index match; they do not replace the underlying index construction.

### 6.1 Shape Fit (Pearson Correlation)

```
corr      = Pearson_correlation( s , p )
shape_fit = clip( (corr + 1) / 2 , 0.0, 1.0 )
```

`shape_fit ∈ [0, 1]`. A score of 1.0 means the two vectors have identical relative emphasis; 0.5 means uncorrelated; 0.0 means perfectly anti-correlated. This captures **profile shape agreement** — whether the student's relative strength pattern matches the program's relative field emphasis, independent of absolute magnitude. Falls back to 0.5 if either vector has near-zero variance. Source: `recommender_v2.py:557–563`.

**Limitation:** Pearson r computed over 6-element vectors is statistically noisy — a single field can shift the correlation substantially. This is an accepted trade-off of the six-field design; the 70/30 shape/direction blend partially mitigates it by incorporating the more stable cosine signal.

### 6.2 Direction Fit (Cosine Similarity)

```
direction_fit = max( cosine_similarity( s , p ) , 0.0 )
```

`direction_fit ∈ [0, 1]`. Clamped at zero — negative cosine values offer no useful differentiation. This captures **overall directional alignment** of the student and program vectors. Source: `recommender_v2.py:522–524`.

### 6.3 Base Fit

```
base_fit = 0.70 · shape_fit  +  0.30 · direction_fit
```

Constants: `BASE_SHAPE_WEIGHT = 0.70`, `BASE_DIRECTION_WEIGHT = 0.30` (`recommender_v2.py:60–61`). Shape (Pearson correlation) is the primary signal because it is scale-invariant and captures the relative pattern; direction (cosine) is a secondary reinforcing signal. ⚑ Source: `recommender_v2.py:525`.

### 6.3a Why the Index Match Matters

The v2 recommendation logic is strongest when it is explained as an index-matching system:

- The **student-profile index** answers: "What is this student's relative field pattern across STEM, Health, Arts, Business, Education, and Agriculture?"
- The **program-profile index** answers: "What field pattern does this program demand or reward?"
- The base match asks: "How similar are those two patterns?"

This framing is better than describing the model as a checklist of filters or heuristics. The filters matter, but the conceptual center of v2 is the matching of two six-dimensional indexes built from explicit scoring rules.

### 6.4 Evidence-Adjusted Fit

Programs with `low` confidence profiles receive a penalty to reflect uncertainty in their profile vectors:

```
profile_reliability_weight = 1.00   (high or medium confidence)
                           = 0.95   (low confidence)

evidence_adjusted_fit = base_fit × profile_reliability_weight
```

There are currently no programs at the `low` tier, so this penalty is not active. Source: `recommender_v2.py:526–527`, `578–582`.

### 6.5 Market Context Signal

A municipality field saturation dataset (`municipality_field_saturation`) provides a `market_score ∈ [0, 1]` per (municipality, affinity field), representing Pozorrubio's share of a field relative to the Pangasinan provincial share. This is applied as a small exploratory signal:

```
score_before_q12 = 0.90 · evidence_adjusted_fit  +  0.10 · market_score
```

Constants: `PROGRAM_FIT_WEIGHT = 0.90`, `MARKET_WEIGHT = 0.10` (`recommender_v2.py:66–67`). If no saturation data is available, `market_score` defaults to `NEUTRAL_MARKET_SCORE = 0.50` (`recommender_v2.py:44`), which keeps the 90/10 blend mathematically neutral. Method tag: `ecosystem_saturation_v1_1`. Source: `recommender_v2.py:531`.

> **⚑ Market weight note:** The 10% market signal is a small exploratory addition. Its basis in local labor-market data is noted as a headline finding in EDA v2 documentation, but the 0.10 weight itself is an expert prior. The signal should not be interpreted as a job-demand guarantee.

### 6.6 Q12 Duration Penalty

If a program's duration or board-exam level exceeds the student's stated tolerance (V2Q28 ≡ Q12), the score is discounted:

```
program_score = score_before_q12 × 0.85   (if penalty applies)
             = score_before_q12            (otherwise)
```

The tolerance map is: `A (open) = 3`, `B (somewhat) = 2`, `C (prefer shorter) = 1`. Programs whose `affinity_duration_score` exceeds the student's tolerance value receive the ×0.85 penalty (`Q12_PENALTY = 0.85`, `recommender_v2.py:43`). Source: `recommender_v2.py:532`.

### 6.7 Track Aspiration Boost

If the student declared a post-graduate professional track (V2Q29 ≡ Q13), programs whose `dominant_dim` matches the declared track's field map receive a final multiplicative boost:

```text
TRACK_ASPIRATION_FIELD_MAP:
  medicine / dentistry → primary: health (×1.12), secondary: stem (×1.06)
  law                  → primary: arts  (×1.12), secondary: business (×1.06)
  none                 → no boost

program_score = program_score × TRACK_ASPIRATION_PRIMARY_BOOST    (if dominant_dim in primary)
             = program_score × TRACK_ASPIRATION_SECONDARY_BOOST   (if dominant_dim in secondary)
             = program_score                                        (otherwise)
```

The boost is applied after the Q12 penalty. A student's affinity profile remains the primary signal — the boost is a moderate nudge (≤12%) for programs recognized as effective undergraduate springboards for the declared track. Option D ("none") produces no effect.

Constants: `TRACK_ASPIRATION_PRIMARY_BOOST = 1.12`, `TRACK_ASPIRATION_SECONDARY_BOOST = 1.06` (`recommender_v2.py`). Both are expert priors; see §7. The declared track and per-recommendation boost factor are recorded in the recommendation trace.

### 6.8 Ranking and School Selection

Programs are sorted by `(program_score DESC, base_fit_score DESC, program_name ASC)`. For each top-ranked program, feasible schools are identified by applying Q10 affordability and Q11 commute constraints. A **light diversity pass** on the 3rd recommendation slot attempts to include a program from a different dominant field if all top picks share the same `dominant_dim` and the best alternative is within 0.15 of the top score.

### 6.9 Trace and Audit

Every session writes one `model_recommendation_trace` row per recommendation slot, containing:

- `construct_scores`: the full per-field interest, self-efficacy, strand-context, and combined student-vector breakdown.
- `constraints`: Q10, Q11, Q12 responses and their mapped values.
- `warnings`: any flags raised during the session (e.g., unknown strand, invalid affinity score).
- `explanation_json`: all intermediate scores — `shape_fit`, `direction_fit`, `base_fit`, `evidence_adjusted_fit`, `market_score`, `program_score`.

This trace is the primary data substrate for future model validation and weight re-estimation.

---

## § 7. Limitations — Priors vs. Validated

**Every numerical weight and threshold in the v2 system is an expert prior, not a quantity fit to outcome data.** The table below enumerates all tunable parameters, their current values, and their validation status.

| Component                             | Value                                 | Basis                                  | Needs validation?                            |
| ------------------------------------- | ------------------------------------- | -------------------------------------- | -------------------------------------------- |
| Interest weight                       | 0.60                                  | Expert judgment                        | Yes — refit from pilot data                  |
| Self-efficacy weight                  | 0.35                                  | Expert judgment                        | Yes — refit from pilot data                  |
| Strand context weight                 | 0.05                                  | Expert judgment                        | Yes                                          |
| Prior / template blend                | 0.55 / 0.45                           | Expert judgment                        | Yes                                          |
| Shape / direction split               | 0.70 / 0.30                           | Expert judgment                        | Yes                                          |
| Program fit / market blend            | 0.90 / 0.10                           | EDA headline finding + expert judgment | Review — 0.10 is a prior, not a fitted value |
| Profile reliability weight (low tier) | 0.95                                  | Expert judgment                        | Monitor — currently no programs at low tier  |
| Q12 penalty multiplier                | 0.85                                  | Expert judgment                        | Yes                                          |
| Track aspiration primary boost | 1.12 | Expert judgment | Yes — compare acceptance rate of boosted vs. non-boosted sessions |
| Track aspiration secondary boost | 1.06 | Expert judgment | Yes — compare acceptance rate of boosted vs. non-boosted sessions |
| `LOW_SIGNAL_FLAG` threshold           | 0.45                                  | Expert judgment                        | Yes                                          |
| `LOW_SIGNAL_ABORT` threshold          | 0.15                                  | Expert judgment                        | Yes                                          |
| `LOW_SPECIFICITY_STD` threshold       | 0.08                                  | Expert judgment                        | Yes                                          |
| `TIE_ZONE_SPREAD` threshold           | 0.05                                  | Expert judgment                        | Yes                                          |
| 20 family templates                   | Hand-authored 6-vectors on [0, 5]     | Expert + curriculum knowledge          | Yes — re-label from pilot choices            |
| 36 needs-review program profiles      | Flagged; not yet manually re-assigned | Manual review pending                  | Yes — required before high-stakes use        |

**One governance decision should be explicit:** a recommendation output should not be called "v2" unless both the student-profile index and the program-profile index were built using the documented v2 scoring contract. If program-side fallback logic is ever used, that run should be treated as a degraded or mixed-mode output, not a pure v2 result.

**The questionnaire has not undergone psychometric validation.** Internal consistency (Cronbach's alpha) and construct validity (do the six fields separate as intended in the student population) will not be known until pilot data is collected and analysed. The four-item-per-field design was chosen specifically to make this validation feasible once data exists.

**Self-efficacy items replace a demonstrated-capability signal.** The original v1 instrument included Q8 ("Which subjects were easier and more enjoyable? Choose at most two") — a relative-performance indicator tapping demonstrated aptitude relative to classmates. v2 replaces this with `domain_self_efficacy` Likert items, which measure perceived capability, not demonstrated performance. This is an accepted trade-off: self-efficacy items are construct-pure and psychometrically analysable in ways Q8 is not, but they are purely self-report. The validation plan should monitor whether self-efficacy sub-scores correlate with track-relevant demonstrated-performance proxies (e.g., strand alignment, subject preference from V2Q25) as a convergent-validity check.

**Pearson r on 6-element vectors is statistically noisy.** The `shape_fit` score (§6.1) is a Pearson correlation computed over 6 dimensions. With n = 6, a single field can substantially shift the correlation. This is an accepted trade-off; the 70/30 shape/direction blend partially mitigates single-field sensitivity by incorporating the more stable cosine signal (§6.2). The pilot validation should report `shape_fit` distribution statistics to flag any systematic bias.

**Geographic coverage is limited.** School feasibility is determined by commute and affordability constraints relative to Pozorrubio, Pangasinan. The municipality field saturation signal is derived from provincial data and may not reflect individual barangay conditions.

The companion Validation and Improvement Plan (`team4_recommender_v2_validation_plan.md`) describes how expert priors will be updated once real student data is available.
