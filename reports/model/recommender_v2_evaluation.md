# Recommender v2 Evaluation Report

> Synthetic fixture report. These numbers test the reporting pipeline only and must not be presented as pilot validation evidence.

## Construct Validity

Fields passing alpha (≥0.65): **0** / 6
Total flagged items (corr < 0.3): **17**

| Field | N | Alpha | Acceptable | Flagged Items |
|-------|---|-------|------------|---------------|
| stem | 30 | 0.221 | No | V2Q01, V2Q02, V2Q03, V2Q04 |
| health | 30 | 0.541 | No | V2Q06, V2Q07 |
| arts | 30 | 0.344 | No | V2Q09, V2Q11, V2Q12 |
| business | 30 | 0.123 | No | V2Q13, V2Q14, V2Q15, V2Q16 |
| education | 30 | 0.468 | No | V2Q17, V2Q19, V2Q20 |
| agriculture | 30 | 0.533 | No | V2Q21 |

### Item-Total Correlations

| Item | stem | health | arts | business | education | agriculture |
|------|------|------|------|------|------|------|
| item 1 | 0.139 | 0.578 | 0.124 | 0.144 | 0.297 | 0.211 |
| item 2 | -0.049 | 0.085 | 0.342 | 0.052 | 0.382 | 0.387 |
| item 3 | 0.135 | 0.258 | 0.035 | 0.024 | 0.287 | 0.342 |
| item 4 | 0.227 | 0.443 | 0.233 | 0.018 | 0.145 | 0.374 |

## Outcome Metrics

| Metric | Value | Target | Meets Target |
|--------|-------|--------|--------------|
| Precision@3 (field) | 0.500 | 0.700 | No |
| Precision@3 (program) | nan | — | — |
| Acceptance rate | 0.800 | 0.750 | Yes |
| Mean relevance | 3.598 | 3.500 | Yes |
| Mean confidence shift | 0.476 | — | Yes |

### Field Fairness (rank-1 share)

| Field | Share | Flagged |
|-------|-------|---------|
| stem | 0.167 | No |
| health | 0.367 | No |
| arts | 0.133 | No |
| business | 0.100 | No |
| education | 0.133 | No |
| agriculture | 0.100 | No |

### Field Fairness (top-3 share)

| Field | Share | Flagged |
|-------|-------|---------|
| stem | 0.233 | No |
| health | 0.211 | No |
| arts | 0.111 | No |
| business | 0.144 | No |
| education | 0.133 | No |
| agriculture | 0.167 | No |

### Strand Fairness (top-3 share)

| Strand | N top-3 rows | Exclusive one field |
|--------|--------------|---------------------|
| ABM | 17 | No |
| GAS | 16 | No |
| HUMSS | 16 | No |
| STEM | 19 | No |
| TVL | 22 | No |

### Calibration

- Flagged sessions: 7 — acceptance 1.000
- Non-flagged sessions: 23 — acceptance 0.739
- Flags correlate with lower acceptance: **No**

### Pilot Readiness Checks

- Complete sessions (3 traces + feedback): 30 / 30
- Complete feedback rows: 16 / 30
- V2Q29 boosted sessions: 7 — acceptance 0.857
- Non-boosted sessions: 23 — acceptance 0.783
