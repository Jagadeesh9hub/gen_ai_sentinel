"""Local validation for SENTINEL Phase 1.

Runs sanity checks plus the three sample natural-language questions from the
requirements against the local DuckDB, proving the unified view and analytics
work end-to-end before any LLM or cloud is involved.

    python scripts/validate_local.py --db data/sentinel.duckdb
"""
from __future__ import annotations

import argparse
import sys

import duckdb
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 160)


def section(title: str):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/sentinel.duckdb")
    args = ap.parse_args()

    try:
        con = duckdb.connect(args.db, read_only=True)
    except duckdb.Error as e:
        print(f"Could not open {args.db}: {e}\nRun data-generator/generate.py first.")
        sys.exit(1)

    section("Sanity: row counts")
    for tbl in ("raw_incidents", "raw_dispatch", "raw_weather",
                "raw_traffic", "raw_citizen_reports"):
        n = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:22s} {n:>8,}")

    section("Unified view sample (capability 1: unified data)")
    print(con.execute("""
        SELECT incident_id, ts, district, type, priority,
               response_time_sec, condition, congestion_index
        FROM unified_incidents
        ORDER BY ts DESC LIMIT 5
    """).df().to_string(index=False))

    section('Q1: "Which districts have rising incident volume this hour?"')
    print(con.execute("""
        WITH m AS (SELECT district, hour, incident_count FROM district_hour_metrics),
             latest AS (SELECT max(hour) AS h FROM m)
        SELECT cur.district,
               COALESCE(prev.incident_count, 0) AS prev_hour,
               cur.incident_count               AS this_hour,
               cur.incident_count - COALESCE(prev.incident_count, 0) AS delta
        FROM m cur
        JOIN latest ON cur.hour = latest.h
        LEFT JOIN m prev
          ON prev.district = cur.district AND prev.hour = cur.hour - INTERVAL 1 HOUR
        ORDER BY delta DESC
    """).df().to_string(index=False))

    section('Q2: "Average response time for medical calls in the north zone today?"')
    print(con.execute("""
        SELECT count(*) AS medical_calls,
               round(avg(response_time_sec) / 60.0, 1) AS avg_response_min
        FROM unified_incidents
        WHERE type = 'medical' AND district = 'North'
          AND CAST(ts AS DATE) = (SELECT max(CAST(ts AS DATE)) FROM unified_incidents)
    """).df().to_string(index=False))

    section('Q3: "Any patterns suggesting a developing situation?" (anomaly z-score)')
    print(con.execute("""
        WITH base AS (
            SELECT district, hour, incident_count,
                   avg(incident_count) OVER w  AS roll_mean,
                   stddev_samp(incident_count) OVER w AS roll_std
            FROM district_hour_metrics
            WINDOW w AS (PARTITION BY district ORDER BY hour
                         ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING)
        )
        SELECT district, incident_count,
               round(roll_mean, 2) AS baseline,
               round((incident_count - roll_mean) / NULLIF(roll_std, 0), 2) AS zscore
        FROM base
        WHERE hour = (SELECT max(hour) FROM district_hour_metrics)
        ORDER BY zscore DESC NULLS LAST
    """).df().to_string(index=False))

    con.close()
    print("\nLocal validation complete.\n")


if __name__ == "__main__":
    main()
