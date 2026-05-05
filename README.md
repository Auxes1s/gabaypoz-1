# GabayPoz — Pangasinan Higher-Education EDA

Published EDA snapshot of the Pangasinan higher-education landscape
(**Team 3, GabayPoz**). This repository contains the analysis notebook,
all required datasets, and the compiled PDF report.

## Quickstart

```bash
# Install uv if you haven't already: https://docs.astral.sh/uv/
uv sync
uv run jupyter lab notebooks/team3_eda_figures_v1.ipynb
```

## Repository layout

```
gabaypoz/
├── .gitignore
├── .python-version          # Python 3.11
├── pyproject.toml           # uv project config
├── uv.lock                  # pinned dependency lockfile
├── README.md
├── notebooks/
│   └── team3_eda_figures_v1.ipynb   # standalone EDA notebook
├── data/
│   ├── raw/                 # small source spreadsheets (.xlsx)
│   ├── processed/team3_eda/ # cleaned parquet files
│   └── extracted/           # large shapefiles (not committed; see below)
├── reports/
│   └── eda_v1/tables/       # pre-computed CSV tables read by the notebook
└── docs/
    └── reports/
        └── team3_eda_pangasinan_education_v1.pdf
```

## Shapefile download (required for §13 maps)

The PH_Adm3_MuniCities shapefile (~211 MB) exceeds GitHub's per-file limit and
is **not** committed to this repository. To enable the §13 accessibility-map
cells:

1. **Source:** PhilGIS / PSA Philippine administrative boundaries
   (Adm Level 3 — Municipalities & Cities).

2. Download and extract all component files (`.shp`, `.dbf`, `.shx`, `.prj`, …).

3. Place them inside `data/extracted/PH_Adm3_MuniCities.shp/` so the notebook
   can read:
   
   ```
   data/extracted/PH_Adm3_MuniCities.shp/PH_Adm3_MuniCities.shp.shp
   ```

4. **Without this file:** all other notebook sections run normally; only the §13
   cells will raise a `DriverError`.

See [`data/extracted/README.md`](data/extracted/README.md) for full details.

## Report

The compiled PDF report is located at
[`docs/reports/team3_eda_pangasinan_education_v1.pdf`](docs/reports/team3_eda_pangasinan_education_v1.pdf).

## License

License terms will be set when the repository is published. PSA census datasets
and FIES microdata retain their original terms of use as specified by the
Philippine Statistics Authority.
