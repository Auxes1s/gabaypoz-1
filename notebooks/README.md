# Notebooks

## Current notebook

### `team4_recommender_supabase_smoke_gui.ipynb`

Interactive `ipywidgets` notebook for a live GabayPoz recommender v2 Supabase smoke test. It imports `analysis/team4_model/recommender_v2.py`, loads the live Supabase tables, renders the seeded v2 questionnaire, runs the recommender, and can persist one rollback-cleanable test session into `guest_tracker`, `users_response`, `model_recommendation`, `model_recommendation_trace`, and `recommender_v2_feedback_response`.

Install the smoke dependencies from the repo root:

```bash
pip install -e ".[smoke]"
```

Set `SUPABASE_DB_URL` in your shell or copy `.env.example` to `.env.local` and fill in the Supabase Postgres connection string:

```bash
cp .env.example .env.local
# SUPABASE_DB_URL=postgresql://postgres:<password>@<host>:5432/postgres
```

Launch Jupyter from the repo root:

```bash
jupyter notebook notebooks/team4_recommender_supabase_smoke_gui.ipynb
```

To regenerate the notebook structure from source:

```bash
python notebooks/build_team4_recommender_smoke_notebook.py
```

## Legacy imported notebook

### `team3_eda_figures_v1.ipynb`

Legacy Team 3 EDA notebook retained for reference. The upstream Team 3 scripts, processed parquets, extracted shapefiles, and notebook builder referenced inside that notebook are not part of this repository snapshot, so it should not be treated as a reproducible current workflow here.

## Persistence cleanup

When persistence mode is enabled, the smoke notebook writes one test session. Delete that session ID in this order if manual cleanup is needed:

```sql
delete from recommender_v2_feedback_response where session_id = '<your-session-id>';
delete from model_recommendation_trace       where session_id = '<your-session-id>';
delete from model_recommendation             where session_id = '<your-session-id>';
delete from users_response                   where session_id = '<your-session-id>';
delete from guest_tracker                    where session_id = '<your-session-id>';
```

## Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `SUPABASE_DB_URL is missing` | `.env.local` not present or not readable | Create `.env.local` from `.env.example` |
| `connection refused` / `timeout` | Wrong host or port in URL, or VPN required | Verify the Supabase connection string |
| `No seeded answer options found for V2Q01` | `answer_option_scoring_metadata` table is empty | Re-run `python analysis/team4_model/seed_recommender_questionnaire_v2.py` |
| `Could not find recommender_v2.py` | Jupyter was not started from the repo root | Start Jupyter from the repo root |
| `ipywidgets` not rendering | Widgets extension not enabled in the active environment | Install the `smoke` extra and restart the kernel |