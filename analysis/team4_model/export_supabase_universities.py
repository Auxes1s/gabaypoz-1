"""Export Supabase university data to local raw CSV files.

This helper is intentionally read-only. It loads SUPABASE_DB_URL from the
environment or from a repo-root .env.local file, then can either inspect table
names/columns or export a selected table/query result to data/raw/.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Iterable

try:
    import psycopg
except ImportError:  # pragma: no cover - exercised manually when missing
    psycopg = None


REPO = Path(__file__).resolve().parents[2]
ENV_LOCAL = REPO / ".env.local"
RAW = REPO / "data" / "raw"
DEFAULT_OUTPUT = RAW / "supabase_university_additions.csv"

REQUIRED_EXPORT_COLUMNS = [
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
]

REQUIRED_COMMUTE_COLUMNS = [
    "Barangay",
    "University",
    "Distance_km",
    "Time_mins",
]


def load_env_local() -> None:
    """Load simple KEY=VALUE lines from .env.local without extra dependencies."""
    if not ENV_LOCAL.exists():
        return
    for raw_line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def db_url() -> str:
    load_env_local()
    value = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not value:
        raise SystemExit(
            "SUPABASE_DB_URL is missing. Set it in your shell or in .env.local."
        )
    return value


def connect():
    if psycopg is None:
        raise SystemExit(
            "Missing dependency: psycopg. Install it with `python3 -m pip install psycopg[binary]`."
        )
    return psycopg.connect(db_url(), connect_timeout=15)


def write_csv(path: Path, columns: Iterable[str], rows: Iterable[Iterable[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(list(columns))
        writer.writerows(rows)


def inspect_schema(schema: str) -> None:
    sql = """
        select table_name, column_name, data_type
        from information_schema.columns
        where table_schema = %s
        order by table_name, ordinal_position
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (schema,))
        rows = cur.fetchall()
    if not rows:
        raise SystemExit(f"No tables or columns found in schema {schema!r}.")

    current = None
    for table_name, column_name, data_type in rows:
        if table_name != current:
            current = table_name
            print(f"\n{schema}.{table_name}")
        print(f"  {column_name}: {data_type}")


def export_table(schema: str, table: str, output: Path, limit: int | None) -> None:
    limit_sql = "" if limit is None else " limit %s"
    sql = f'select * from "{schema}"."{table}"' + limit_sql
    params = () if limit is None else (limit,)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]
    write_csv(output, columns, rows)
    print(f"Wrote {len(rows)} rows to {output}")


def export_university_query(schema: str, query: str, output: Path) -> None:
    """Export a user-supplied SELECT after validating the resulting columns."""
    if not query.lstrip().lower().startswith("select"):
        raise SystemExit("Only SELECT queries are allowed.")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    missing = [col for col in REQUIRED_EXPORT_COLUMNS if col not in columns]
    if missing:
        raise SystemExit(
            "Query result is missing required columns for v1.1 export: "
            + ", ".join(missing)
        )
    ordered = [columns.index(col) for col in REQUIRED_EXPORT_COLUMNS]
    ordered_rows = ([row[i] for i in ordered] for row in rows)
    write_csv(output, REQUIRED_EXPORT_COLUMNS, ordered_rows)
    print(f"Wrote {len(rows)} university-program rows to {output}")


def export_commute_query(query: str, output: Path) -> None:
    """Export a user-supplied SELECT shaped like the raw commute matrix."""
    if not query.lstrip().lower().startswith("select"):
        raise SystemExit("Only SELECT queries are allowed.")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        columns = [desc.name for desc in cur.description]

    missing = [col for col in REQUIRED_COMMUTE_COLUMNS if col not in columns]
    if missing:
        raise SystemExit(
            "Query result is missing required commute columns: "
            + ", ".join(missing)
        )
    ordered = [columns.index(col) for col in REQUIRED_COMMUTE_COLUMNS]
    ordered_rows = ([row[i] for i in ordered] for row in rows)
    write_csv(output, REQUIRED_COMMUTE_COLUMNS, ordered_rows)
    print(f"Wrote {len(rows)} commute rows to {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect/export Supabase Postgres university data for GabayPoz."
    )
    parser.add_argument("--schema", default="public", help="Postgres schema to inspect/export.")
    parser.add_argument("--inspect", action="store_true", help="List tables and columns.")
    parser.add_argument("--table", help="Export an entire table to CSV.")
    parser.add_argument("--query", help="Export a SELECT result shaped for university additions.")
    parser.add_argument("--commute-query", help="Export a SELECT result shaped for commute additions.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV output path.")
    parser.add_argument("--limit", type=int, help="Optional row limit for --table exports.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    actions = sum(bool(x) for x in [args.inspect, args.table, args.query, args.commute_query])
    if actions != 1:
        raise SystemExit("Choose exactly one action: --inspect, --table, or --query.")

    if args.inspect:
        inspect_schema(args.schema)
    elif args.table:
        export_table(args.schema, args.table, args.output, args.limit)
    elif args.commute_query:
        export_commute_query(args.commute_query, args.output)
    else:
        export_university_query(args.schema, args.query, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
