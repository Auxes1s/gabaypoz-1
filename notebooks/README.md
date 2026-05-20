# Notebooks

## `team3_eda_figures_v1.ipynb`

A Jupyter notebook that exactly reproduces all 14 figures and 15 tables from the
Team 3 EDA report (`docs/reports/team3_eda_pangasinan_education_v1.pdf`).

Sections follow the report: §4 Descriptive profile → §5 Highly educated adults →
§6 Education ladder → §7 School attendance → §8 Occupation → §9 Affordability →
§11 Overseas/SOF → §13 Geographic accessibility.

**Prerequisites:** all source data in `data/` must be present (parquets under
`data/processed/team3_eda/`, raw files under `data/raw/`, shapefile under
`data/extracted/`). Run the upstream extract scripts if needed.

**To re-execute the notebook from scratch:**

```bash
# From the repo root
jupyter nbconvert --to notebook --execute --inplace notebooks/team3_eda_figures_v1.ipynb
```

**To regenerate the `.ipynb` file structure** (e.g., after upstream script changes):

```bash
python3 notebooks/build_team3_eda_notebook.py
jupyter nbconvert --to notebook --execute --inplace notebooks/team3_eda_figures_v1.ipynb
```

---

## `team3_eda_figures_v2.ipynb`

A Jupyter notebook covering all six sections of the Team 3 EDA v2 analysis,
built from the processed parquets in `data/processed/team3_eda/`.

Sections: §1 Barangay accessibility → §2 Economic constraint → §3 Market score →
§4 Program-to-occupation bridge → §5 Program affinity profile & boosters →
§6 Non-gainful opportunity cost → §7 Scholarship coverage & Q11 interaction.

**Prerequisites:** processed parquets must be present (run the six v2 scripts
under `analysis/team3_eda/`). Raw files required: `program_list_FINAL.xlsx`,
`pozorrubio_commute_matrix.xlsx`, and the FIES/Census parquets.

**To regenerate the `.ipynb` file structure:**

```bash
python3 notebooks/build_team3_eda_v2_notebook.py
jupyter nbconvert --to notebook --execute --inplace notebooks/team3_eda_figures_v2.ipynb
```

---

## `team4_recommender_supabase_smoke_gui.ipynb`

An `ipywidgets` GUI notebook for a live Supabase smoke test of recommender v2.
It imports `analysis/team4_model/recommender_v2.py`, loads the live Supabase
tables, renders the seeded v2 questionnaire, runs the recommender, and can
persist one test session into `guest_tracker`, `users_response`,
`model_recommendation`, `model_recommendation_trace`, and
`recommender_v2_feedback_response`, then shows the
`recommender_v2_session_completeness` row.

### Step-by-step: running the smoke test

**Step 1 — Install dependencies**

From the repo root, install the `smoke` extras (or manually install the four packages):

```bash
pip install -e ".[smoke]"
# equivalent: pip install "ipywidgets>=8" "notebook>=7" "psycopg[binary]>=3.1" pandas numpy
```

**Step 2 — Set your database URL**

Copy `.env.example` to `.env.local` at the repo root and fill in the Supabase
Postgres connection string:

```bash
cp .env.example .env.local
# then edit .env.local:
# SUPABASE_DB_URL=postgresql://postgres:<password>@<host>:5432/postgres
```

The notebook reads this file automatically. Alternatively, export the variable
in your shell before starting Jupyter:

```bash
export SUPABASE_DB_URL="postgresql://postgres:<password>@<host>:5432/postgres"
```

**Step 3 — Launch Jupyter from the repo root**

```bash
# from C:\Github\gabaypoz-1
jupyter notebook notebooks/team4_recommender_supabase_smoke_gui.ipynb
```

Or with JupyterLab:

```bash
jupyter lab notebooks/team4_recommender_supabase_smoke_gui.ipynb
```

**Step 4 — Run the notebook**

Open the notebook in your browser and select **Kernel → Restart & Run All** (or
press `Shift+Enter` through the cells). The first cell loads all live Supabase
tables and renders the GUI below. You will see a confirmation table like:

```
frame                    rows  columns
answer_options            138        5
barangays                  27        4
...
```

**Step 5 — Fill in the questionnaire and run**

1. Select a **Barangay** from the dropdown.
2. Answer all **V2Q01–V2Q29** questions using the dropdowns.
3. Adjust the **feedback sliders** (relevance, pre/post confidence, acceptance choice).
4. Check or uncheck **Persist smoke-test session to Supabase** (see below).
5. Click **Run recommender**.

The results table and rank-1 explanation appear in the output area below the button.

**Step 6 — Interpreting the output**

| Column | Meaning |
|---|---|
| `rank` | 1 = highest-scoring program |
| `program` | Program name from the catalogue |
| `primary_school` | Nearest feasible university given the student's commute/burden constraints |
| `score` | Final model score (0–1); higher is better |
| `dominant_dim` | The academic field this program is strongest in |
| `commute_mins` | Estimated one-way travel time from the selected barangay |
| `annual_burden_php` | Estimated annual cost (tuition + fees) |

### Persistence mode

When **Persist smoke-test session to Supabase** is checked, the notebook writes:
- 1 row to `guest_tracker`
- 29 rows to `users_response` (one per question)
- 3 rows to `model_recommendation`
- 3 rows to `model_recommendation_trace`
- 1 row to `recommender_v2_feedback_response`

After writing, it reads the `recommender_v2_session_completeness` view and
displays it. A fully complete session shows `session_complete = true`,
`questionnaire_response_count = 29`, `trace_row_count = 3`, `feedback_row_count = 1`.

To clean up a persisted test session, delete the session ID from each table in
this order:

```sql
delete from recommender_v2_feedback_response where session_id = '<your-session-id>';
delete from model_recommendation_trace       where session_id = '<your-session-id>';
delete from model_recommendation             where session_id = '<your-session-id>';
delete from users_response                   where session_id = '<your-session-id>';
delete from guest_tracker                    where session_id = '<your-session-id>';
```

### To regenerate the notebook structure

```bash
python3 notebooks/build_team4_recommender_smoke_notebook.py
```

### Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `SUPABASE_DB_URL is missing` | `.env.local` not present or not readable | Create `.env.local` from `.env.example` |
| `connection refused` / `timeout` | Wrong host or port in URL, or VPN required | Verify the Supabase connection string |
| `No seeded answer options found for V2Q01` | `answer_option_scoring_metadata` table is empty | Re-run the seed script: `python analysis/team4_model/seed_recommender_questionnaire_v2.py` |
| `Could not find recommender_v2.py` | Jupyter was not started from the repo root | `cd` to the repo root before running `jupyter notebook` |
| `ipywidgets` not rendering | Widgets extension not enabled | Run `jupyter nbextension enable --py widgetsnbextension` |
