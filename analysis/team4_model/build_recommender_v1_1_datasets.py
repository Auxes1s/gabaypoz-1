"""Build v1.1 recommender-ready derived datasets.

Outputs are written to ``data/processed/team4_model`` as both Parquet and CSV
so Team 4 can test locally and Team 5 can inspect the handoff without needing a
Parquet reader.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw"
TEAM3 = REPO / "data" / "processed" / "team3_eda"
OUT = REPO / "data" / "processed" / "team4_model"

MUNICIPALITY_CODE = 30
MUNICIPALITY_NAME = "Pozorrubio"
MARKET_SCORE_METHOD = "ecosystem_saturation_v1_1"
SUPABASE_UNIVERSITY_ADDITIONS = RAW / "supabase_university_additions.csv"
SUPABASE_COMMUTE_ADDITIONS = RAW / "supabase_commute_additions.csv"
TUITION_COST = {1: 10_000, 2: 25_000, 3: 60_000}
PRIMARY_COST_PER_KM = 2.50
SCHOOL_DAYS_PER_YEAR = 180


def clean_key(value) -> str:
    return " ".join(str(value).strip().lower().split())


def write_dataset(df: pd.DataFrame, name: str) -> dict:
    parquet_path = OUT / f"{name}.parquet"
    csv_path = OUT / f"{name}.csv"
    df.to_parquet(parquet_path, index=False)
    df.to_csv(csv_path, index=False)
    return {
        "name": name,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "parquet": str(parquet_path.relative_to(REPO)),
        "csv": str(csv_path.relative_to(REPO)),
    }


def build_barangay_location() -> pd.DataFrame:
    df = pd.read_excel(RAW / "barangay_coords.xlsx")
    df = df.rename(
        columns={
            "origin_barangay": "barangay_name",
            "origin_latitude": "latitude",
            "origin_longitude": "longitude",
        }
    )
    df.insert(0, "barangay_id", range(1, len(df) + 1))
    df["municipality_code"] = MUNICIPALITY_CODE
    df["municipality_name"] = MUNICIPALITY_NAME
    return df[
        [
            "barangay_id",
            "barangay_name",
            "municipality_code",
            "municipality_name",
            "latitude",
            "longitude",
        ]
    ]


def load_supabase_additions(barangay: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if not SUPABASE_UNIVERSITY_ADDITIONS.exists():
        return pd.DataFrame(), pd.DataFrame(), {
            "supabase_additions_present": False,
            "appendable_universities": [],
            "skipped_universities": [],
        }

    additions = pd.read_csv(SUPABASE_UNIVERSITY_ADDITIONS)
    required = {
        "university_name",
        "university_type",
        "address",
        "website",
        "latitude",
        "longitude",
        "distance_band_from_pozorrubio",
        "economic_constraint",
        "mobility_constraint",
        "college",
        "degree",
        "major",
    }
    missing = sorted(required - set(additions.columns))
    if missing:
        raise ValueError(f"{SUPABASE_UNIVERSITY_ADDITIONS} is missing columns: {missing}")

    commute = pd.DataFrame()
    if SUPABASE_COMMUTE_ADDITIONS.exists():
        commute = pd.read_csv(SUPABASE_COMMUTE_ADDITIONS)
        commute_missing = sorted({"Barangay", "University", "Distance_km", "Time_mins"} - set(commute.columns))
        if commute_missing:
            raise ValueError(f"{SUPABASE_COMMUTE_ADDITIONS} is missing columns: {commute_missing}")

    expected_barangays = set(barangay["barangay_name"].map(clean_key))
    appendable = []
    skipped = []
    for name in sorted(additions["university_name"].dropna().unique()):
        rows = commute[commute["University"].map(clean_key) == clean_key(name)] if not commute.empty else pd.DataFrame()
        covered = set(rows["Barangay"].map(clean_key)) if not rows.empty else set()
        if covered == expected_barangays:
            appendable.append(name)
        else:
            skipped.append({
                "university_name": name,
                "reason": f"commute coverage {len(covered)}/{len(expected_barangays)} barangays",
            })

    additions = additions[additions["university_name"].isin(appendable)].copy()
    commute = commute[commute["University"].isin(appendable)].copy() if not commute.empty else commute
    return additions, commute, {
        "supabase_additions_present": True,
        "appendable_universities": appendable,
        "skipped_universities": skipped,
    }


def build_university(additions: pd.DataFrame | None = None) -> pd.DataFrame:
    coords = pd.read_excel(RAW / "Univerisity_coords.xlsx").rename(
        columns={
            "university_name": "university_name",
            "uni_latitude": "latitude",
            "uni_longitude": "longitude",
        }
    )
    coords.insert(0, "university_id", range(1, len(coords) + 1))

    uni_meta = pd.read_excel(RAW / "program_list_FINAL.xlsx", sheet_name="university list")
    uni_meta = uni_meta.rename(
        columns={
            "University": "university_name",
            "Type": "university_type",
            "Distance_km": "distance_band_from_pozorrubio",
        }
    )
    program_list = pd.read_excel(RAW / "program_list_FINAL.xlsx", sheet_name="university program list")
    address = (
        program_list[["University", "Address", "Website"]]
        .drop_duplicates("University")
        .rename(
            columns={
                "University": "university_name",
                "Address": "address",
                "Website": "website",
            }
        )
    )

    df = coords.merge(uni_meta, on="university_name", how="left").merge(
        address, on="university_name", how="left"
    )
    out = df[
        [
            "university_id",
            "university_name",
            "university_type",
            "address",
            "website",
            "latitude",
            "longitude",
            "distance_band_from_pozorrubio",
            "economic_constraint",
            "mobility_constraint",
        ]
    ]
    if additions is not None and not additions.empty:
        extra = additions.drop_duplicates("university_name").copy()
        extra = extra[~extra["university_name"].map(clean_key).isin(out["university_name"].map(clean_key))]
        if not extra.empty:
            extra = extra.rename(
                columns={
                    "distance_band_from_pozorrubio": "distance_band_from_pozorrubio",
                    "latitude": "latitude",
                    "longitude": "longitude",
                }
            )
            extra.insert(0, "university_id", range(len(out) + 1, len(out) + len(extra) + 1))
            out = pd.concat(
                [
                    out,
                    extra[
                        [
                            "university_id",
                            "university_name",
                            "university_type",
                            "address",
                            "website",
                            "latitude",
                            "longitude",
                            "distance_band_from_pozorrubio",
                            "economic_constraint",
                            "mobility_constraint",
                        ]
                    ],
                ],
                ignore_index=True,
            )
    return out


def build_commute_matrix(
    barangay: pd.DataFrame,
    university: pd.DataFrame,
    commute_additions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    commute = pd.read_excel(RAW / "pozorrubio_commute_matrix.xlsx")
    commute = commute.rename(
        columns={
            "Barangay": "barangay_name",
            "University": "university_name",
            "Distance (km)": "distance_km",
            "Time (mins)": "commute_time_mins",
        }
    )
    commute["_barangay_key"] = commute["barangay_name"].map(clean_key)
    commute["_university_key"] = commute["university_name"].map(clean_key)

    brgy_lookup = barangay[["barangay_id", "barangay_name"]].copy()
    brgy_lookup["_barangay_key"] = brgy_lookup["barangay_name"].map(clean_key)
    uni_lookup = university[["university_id", "university_name"]].copy()
    uni_lookup["_university_key"] = uni_lookup["university_name"].map(clean_key)

    out = commute.merge(brgy_lookup[["barangay_id", "_barangay_key"]], on="_barangay_key", how="left")
    out = out.merge(uni_lookup[["university_id", "_university_key"]], on="_university_key", how="left")
    if out[["barangay_id", "university_id"]].isna().any().any():
        missing = out[out[["barangay_id", "university_id"]].isna().any(axis=1)]
        raise ValueError(f"Unmapped commute rows:\n{missing.head(20)}")
    out = out[
        [
            "barangay_id",
            "university_id",
            "barangay_name",
            "university_name",
            "distance_km",
            "commute_time_mins",
        ]
    ].sort_values(["barangay_id", "university_id"]).reset_index(drop=True)
    if commute_additions is not None and not commute_additions.empty:
        extra = commute_additions.rename(
            columns={
                "Barangay": "barangay_name",
                "University": "university_name",
                "Distance_km": "distance_km",
                "Time_mins": "commute_time_mins",
            }
        )
        extra["_barangay_key"] = extra["barangay_name"].map(clean_key)
        extra["_university_key"] = extra["university_name"].map(clean_key)
        brgy_lookup = barangay[["barangay_id", "barangay_name"]].copy()
        brgy_lookup["_barangay_key"] = brgy_lookup["barangay_name"].map(clean_key)
        uni_lookup = university[["university_id", "university_name"]].copy()
        uni_lookup["_university_key"] = uni_lookup["university_name"].map(clean_key)
        extra = extra.merge(brgy_lookup[["barangay_id", "_barangay_key"]], on="_barangay_key", how="left")
        extra = extra.merge(uni_lookup[["university_id", "_university_key"]], on="_university_key", how="left")
        if extra[["barangay_id", "university_id"]].isna().any().any():
            missing = extra[extra[["barangay_id", "university_id"]].isna().any(axis=1)]
            raise ValueError(f"Unmapped Supabase commute rows:\n{missing.head(20)}")
        extra = extra[
            [
                "barangay_id",
                "university_id",
                "barangay_name",
                "university_name",
                "distance_km",
                "commute_time_mins",
            ]
        ]
        out = pd.concat([out, extra], ignore_index=True)
        out = out.drop_duplicates(["barangay_id", "university_id"], keep="first")
    return out.sort_values(["barangay_id", "university_id"]).reset_index(drop=True)


def build_economic_burden(
    barangay: pd.DataFrame,
    university: pd.DataFrame,
    commute: pd.DataFrame,
) -> pd.DataFrame:
    burden = pd.read_parquet(TEAM3 / "barangay_university_economic_burden.parquet")
    burden = burden.rename(columns={"barangay": "barangay_name", "university": "university_name"})
    burden["_barangay_key"] = burden["barangay_name"].map(clean_key)
    burden["_university_key"] = burden["university_name"].map(clean_key)

    brgy_lookup = barangay[["barangay_id", "barangay_name"]].copy()
    brgy_lookup["_barangay_key"] = brgy_lookup["barangay_name"].map(clean_key)
    uni_lookup = university[["university_id", "university_name"]].copy()
    uni_lookup["_university_key"] = uni_lookup["university_name"].map(clean_key)

    out = burden.merge(brgy_lookup[["barangay_id", "_barangay_key"]], on="_barangay_key", how="left")
    out = out.merge(uni_lookup[["university_id", "_university_key"]], on="_university_key", how="left")
    if out[["barangay_id", "university_id"]].isna().any().any():
        missing = out[out[["barangay_id", "university_id"]].isna().any(axis=1)]
        raise ValueError(f"Unmapped economic burden rows:\n{missing.head(20)}")

    # Use the raw commute matrix time as the authoritative Q11 time. Team 3's
    # burden table carries distance and costs but not commute_time_mins.
    commute_cols = commute[["barangay_id", "university_id", "commute_time_mins"]]
    out = out.drop(columns=["commute_time_mins"], errors="ignore").merge(
        commute_cols, on=["barangay_id", "university_id"], how="left"
    )

    columns = [
        "barangay_id",
        "university_id",
        "barangay_name",
        "university_name",
        "distance_km",
        "commute_time_mins",
        "distance_km_mid",
        "economic_constraint",
        "tuition_estimate",
        "annual_transport_cost_php",
        "total_annual_burden_php",
        "affordability_at_tier_1",
        "affordability_at_tier_2",
        "affordability_at_tier_3",
        "affordability_at_tier_4",
        "affordability_at_tier_5",
    ]
    out = out[columns].sort_values(["barangay_id", "university_id"]).reset_index(drop=True)
    missing_pairs = commute[["barangay_id", "university_id"]].merge(
        out[["barangay_id", "university_id"]],
        on=["barangay_id", "university_id"],
        how="left",
        indicator=True,
    )
    missing_pairs = missing_pairs[missing_pairs["_merge"] == "left_only"].drop(columns=["_merge"])
    if not missing_pairs.empty:
        out = pd.concat(
            [out, _build_added_burden_rows(missing_pairs, commute, university, out)],
            ignore_index=True,
        )
    return out[columns].sort_values(["barangay_id", "university_id"]).reset_index(drop=True)


def _build_added_burden_rows(
    missing_pairs: pd.DataFrame,
    commute: pd.DataFrame,
    university: pd.DataFrame,
    existing_burden: pd.DataFrame,
) -> pd.DataFrame:
    rows = missing_pairs.merge(
        commute[
            [
                "barangay_id",
                "university_id",
                "barangay_name",
                "university_name",
                "distance_km",
                "commute_time_mins",
            ]
        ],
        on=["barangay_id", "university_id"],
        how="left",
    ).merge(
        university[["university_id", "distance_band_from_pozorrubio", "economic_constraint"]],
        on="university_id",
        how="left",
    )
    rows["distance_km_mid"] = rows["distance_band_from_pozorrubio"].apply(_parse_distance_range)
    rows["tuition_estimate"] = rows["economic_constraint"].astype(int).map(TUITION_COST)
    rows["annual_transport_cost_php"] = (
        rows["distance_km"].astype(float) * 2 * PRIMARY_COST_PER_KM * SCHOOL_DAYS_PER_YEAR
    )
    rows["total_annual_burden_php"] = rows["tuition_estimate"] + rows["annual_transport_cost_php"]

    for tier in range(1, 6):
        flag = f"affordability_at_tier_{tier}"
        cutoff = existing_burden.loc[existing_burden[flag].astype(bool), "total_annual_burden_php"].max()
        rows[flag] = rows["total_annual_burden_php"] <= cutoff
    return rows


def build_saturation() -> pd.DataFrame:
    heap = pd.read_parquet(TEAM3 / "heap_occupation_by_field.parquet")
    rows = []
    for row in heap.itertuples(index=False):
        field = str(row.affinity_field).upper()
        province_share = float(row.pangasinan_share)
        municipality_share = float(row.pozorrubio_share)
        ratio = municipality_share / province_share if province_share > 0 else np.nan
        raw_score = float(getattr(row, "v2_differentiated", ratio * 2.5))
        market_score = float(np.clip(raw_score / 5.0, 0.0, 1.0))
        rows.append(
            {
                "municipality_code": MUNICIPALITY_CODE,
                "municipality_name": MUNICIPALITY_NAME,
                "affinity_field": field,
                "municipality_field_share": municipality_share,
                "province_field_share": province_share,
                "saturation_ratio": ratio,
                "market_score": market_score,
                "market_score_method": MARKET_SCORE_METHOD,
                "source_reference": "data/processed/team3_eda/heap_occupation_by_field.parquet",
            }
        )
    return pd.DataFrame(rows)


def validate_outputs(
    barangay: pd.DataFrame,
    university: pd.DataFrame,
    commute: pd.DataFrame,
    burden: pd.DataFrame,
    saturation: pd.DataFrame,
) -> dict:
    expected_pairs = len(barangay) * len(university)
    tier_cols = [f"affordability_at_tier_{i}" for i in range(1, 6)]
    checks = {
        "barangay_count": int(len(barangay)),
        "university_count": int(len(university)),
        "expected_barangay_university_pairs": int(expected_pairs),
        "commute_pair_count": int(len(commute)),
        "economic_burden_pair_count": int(len(burden)),
        "saturation_field_count": int(len(saturation)),
        "commute_complete": bool(len(commute) == expected_pairs),
        "economic_burden_complete": bool(len(burden) == expected_pairs),
        "tier_columns_present": bool(set(tier_cols) <= set(burden.columns)),
        "saturation_fields": sorted(saturation["affinity_field"].tolist()),
        "market_score_min": float(saturation["market_score"].min()),
        "market_score_max": float(saturation["market_score"].max()),
    }
    if not checks["commute_complete"]:
        raise ValueError(f"Commute matrix has {len(commute)} rows; expected {expected_pairs}.")
    if not checks["economic_burden_complete"]:
        raise ValueError(f"Economic burden has {len(burden)} rows; expected {expected_pairs}.")
    if saturation["market_score"].lt(0).any() or saturation["market_score"].gt(1).any():
        raise ValueError("Saturation market_score must be in [0, 1].")
    return checks


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    barangay = build_barangay_location()
    supabase_additions, supabase_commute, supabase_status = load_supabase_additions(barangay)
    university = build_university(supabase_additions)
    commute = build_commute_matrix(barangay, university, supabase_commute)
    burden = build_economic_burden(barangay, university, commute)
    saturation = build_saturation()
    checks = validate_outputs(barangay, university, commute, burden, saturation)

    manifest = {
        "dataset_version": "team4_recommender_v1_1",
        "created_by": "analysis/team4_model/build_recommender_v1_1_datasets.py",
        "sources": [
            "data/raw/barangay_coords.xlsx",
            "data/raw/Univerisity_coords.xlsx",
            "data/raw/pozorrubio_commute_matrix.xlsx",
            "data/raw/program_list_FINAL.xlsx",
            "data/processed/team3_eda/barangay_university_economic_burden.parquet",
            "data/processed/team3_eda/heap_occupation_by_field.parquet",
        ],
        "validation": checks,
        "supabase_additions": supabase_status,
        "datasets": [
            write_dataset(barangay, "barangay_location"),
            write_dataset(university, "university"),
            write_dataset(commute, "barangay_university_commute_matrix"),
            write_dataset(burden, "barangay_university_economic_burden"),
            write_dataset(saturation, "municipality_field_saturation"),
        ],
    }
    manifest_path = OUT / "dataset_manifest_v1_1.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
