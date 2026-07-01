"""Load SENTINEL data from local DuckDB into BigQuery (for Looker Studio + BQ).

Run in Cloud Shell:
    pip install duckdb pandas numpy google-cloud-bigquery pyarrow
    python data-generator/generate.py --days 14 --db data/sentinel.duckdb
    python scripts/load_bigquery.py --project YOUR_PROJECT --dataset sentinel

Then in Looker Studio: Create -> Data source -> BigQuery -> <project> -> sentinel
-> unified_incidents (and district_hour_metrics).
"""
from __future__ import annotations

import argparse

import duckdb
from google.cloud import bigquery

TABLES = [
    "raw_incidents", "raw_dispatch", "raw_weather", "raw_traffic",
    "raw_citizen_reports", "unified_incidents", "district_hour_metrics",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--dataset", default="sentinel")
    ap.add_argument("--db", default="data/sentinel.duckdb")
    ap.add_argument("--location", default="US")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    client = bigquery.Client(project=args.project)

    ds_id = f"{args.project}.{args.dataset}"
    ds = bigquery.Dataset(ds_id)
    ds.location = args.location
    client.create_dataset(ds, exists_ok=True)
    print(f"dataset ready: {ds_id} ({args.location})")

    cfg = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    for t in TABLES:
        df = con.execute(f"SELECT * FROM {t}").df()
        client.load_table_from_dataframe(df, f"{ds_id}.{t}", job_config=cfg).result()
        print(f"  loaded {t}: {len(df):,} rows")

    con.close()
    print(f"\nDone. In Looker Studio, connect BigQuery -> {ds_id} -> unified_incidents")


if __name__ == "__main__":
    main()
