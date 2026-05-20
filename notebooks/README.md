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
`recommender_v2_feedback_response`, then show the
`recommender_v2_session_completeness` row.

**Prerequisites:** set `SUPABASE_DB_URL` in the shell or repo-root `.env.local`.
Install notebook dependencies in your preferred Python environment
(`pandas`, `psycopg`, `ipywidgets`, `nbformat`), then open Jupyter:

```bash
jupyter notebook notebooks/team4_recommender_supabase_smoke_gui.ipynb
```

**To regenerate the notebook structure:**

```bash
python3 notebooks/build_team4_recommender_smoke_notebook.py
```

**To use it interactively:**

Open `notebooks/team4_recommender_supabase_smoke_gui.ipynb` in Jupyter and run
the final code cell. The questionnaire GUI should appear below that cell.
