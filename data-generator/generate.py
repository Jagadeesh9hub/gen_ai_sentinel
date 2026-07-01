"""SENTINEL synthetic data generator (Phase 1 — local).

Generates realistic public-safety signals — incidents, dispatch, weather,
traffic, and citizen text reports — over a time window and loads them into a
local DuckDB database, then builds the curated views the rest of the platform
reads. Pure local: no GCP required. The same schema maps to BigQuery for the
cloud phase (see docs/data-model.md).

Usage:
    python data-generator/generate.py --days 14 --db data/sentinel.duckdb --seed 7
"""
from __future__ import annotations

import argparse
import math
import os
import uuid
from datetime import datetime, timedelta, timezone

import duckdb
import numpy as np
import pandas as pd

# --- City model -------------------------------------------------------------

DISTRICTS = {
    "Central": dict(center=(40.758, -73.973), base_rate=3.0,
                    mix=dict(medical=.40, fire=.08, police=.34, hazmat=.04, traffic=.14)),
    "North":   dict(center=(40.802, -73.965), base_rate=2.0,
                    mix=dict(medical=.44, fire=.12, police=.26, hazmat=.04, traffic=.14)),
    "South":   dict(center=(40.705, -73.992), base_rate=1.8,
                    mix=dict(medical=.42, fire=.12, police=.28, hazmat=.04, traffic=.14)),
    "East":    dict(center=(40.752, -73.918), base_rate=1.6,
                    mix=dict(medical=.40, fire=.12, police=.28, hazmat=.05, traffic=.15)),
    "West":    dict(center=(40.751, -74.018), base_rate=1.7,
                    mix=dict(medical=.42, fire=.12, police=.27, hazmat=.05, traffic=.14)),
    "Harbor":  dict(center=(40.690, -74.040), base_rate=1.1,
                    mix=dict(medical=.30, fire=.12, police=.24, hazmat=.12, traffic=.22)),
}

TYPES = ["medical", "fire", "police", "hazmat", "traffic"]
UNIT = {"medical": "AMB", "fire": "ENG", "police": "PD", "hazmat": "HZ", "traffic": "PD"}
UNIT_TYPE = {"medical": "ambulance", "fire": "engine", "police": "patrol",
             "hazmat": "hazmat", "traffic": "patrol"}

# Relative incident rate by hour-of-day (0..23): quiet overnight, busy evening.
DIURNAL = [0.40, 0.35, 0.30, 0.30, 0.35, 0.45, 0.60, 0.80, 0.95, 1.00, 1.00, 1.05,
           1.10, 1.10, 1.15, 1.20, 1.30, 1.35, 1.30, 1.20, 1.05, 0.90, 0.70, 0.55]

SERVICE_SEC = {"medical": 1800, "fire": 3600, "police": 2400, "hazmat": 5400, "traffic": 2700}
RESP_BASE_SEC = {1: 240, 2: 420, 3: 660}

INCIDENT_TEXT = {
    "medical": ["chest pains reported", "person collapsed", "difficulty breathing",
                "fall with injury", "allergic reaction", "unconscious person"],
    "fire":    ["smoke reported", "structure fire", "smell of smoke",
                "electrical fire", "brush fire", "flames visible"],
    "police":  ["disturbance reported", "suspicious activity", "theft in progress",
                "noise complaint", "physical altercation", "trespassing"],
    "hazmat":  ["chemical smell reported", "gas odor", "spill on roadway",
                "fumes reported", "unknown substance", "strong gas smell"],
    "traffic": ["multi-vehicle collision", "car off road", "signal light out",
                "pedestrian struck", "vehicle fire", "rollover crash"],
}

CITIZEN_TEXT = {
    "hazmat":  ["strong smell of gas near {loc}", "chemical odor in the air around {loc}",
                "fumes coming from {loc}, feeling dizzy"],
    "fire":    ["smoke near {loc}", "i see flames at {loc}", "building smoking on {loc}"],
    "medical": ["someone collapsed at {loc}", "person needs help near {loc}"],
    "police":  ["loud altercation at {loc}", "suspicious person near {loc}"],
    "traffic": ["bad crash at {loc}", "cars stopped, looks like an accident at {loc}"],
    "general": ["something seems off near {loc}", "lots of sirens around {loc}"],
}
STREETS = ["5th & Oak", "Main St", "Harbor Rd", "Elm Ave", "Park Blvd", "2nd & Pine",
           "River Rd", "Market St", "Lincoln Ave", "Bridge St"]
CHANNELS = ["sms", "app", "web", "social"]


def pick_type(rng: np.random.Generator, mix: dict) -> str:
    w = np.array([mix[t] for t in TYPES], dtype=float)
    w /= w.sum()
    return TYPES[int(rng.choice(len(TYPES), p=w))]


def pick_priority(rng: np.random.Generator, t: str) -> int:
    if t in ("medical", "fire", "hazmat"):
        return int(rng.choice([1, 2, 3], p=[0.45, 0.40, 0.15]))
    return int(rng.choice([1, 2, 3], p=[0.15, 0.45, 0.40]))


def did_escalate(rng, t, priority, wind, congestion) -> bool:
    p = 0.04
    if t == "hazmat":
        p += 0.22
    elif t == "fire":
        p += 0.12 + (0.15 if wind > 20 else 0.0)
    elif t == "traffic":
        p += 0.05 + (0.10 if congestion > 0.7 else 0.0)
    elif t == "medical":
        p += 0.05
    if priority == 1:
        p += 0.10
    return bool(rng.random() < min(p, 0.85))


def build_environment(hours, rng):
    """Hourly weather + traffic per district. Returns (weather_df, traffic_df, wmap, tmap)."""
    weather, traffic, wmap, tmap = [], [], {}, {}
    # A few windy days to create fire/hazmat correlation.
    windy_days = set(rng.choice(np.arange(len({h.date() for h in hours})), size=2, replace=False).tolist())
    day_index = {d: i for i, d in enumerate(sorted({h.date() for h in hours}))}

    for d, meta in DISTRICTS.items():
        for h in hours:
            hod = h.hour
            temp = 60 + 12 * math.sin((hod - 15) / 24 * 2 * math.pi) + float(rng.normal(0, 3))
            windy = day_index[h.date()] in windy_days
            wind = max(0.0, (18 if windy else 8) + float(rng.normal(0, 4)))
            precip = max(0.0, float(rng.normal(-0.02, 0.08)))
            rain = precip > 0.05
            condition = ("windy" if wind > 22 else "rain" if rain else
                         "cloudy" if rng.random() < 0.35 else "clear")
            weather.append(dict(ts=h, district=d, temp_f=round(temp, 1),
                                wind_mph=round(wind, 1), precip=round(precip, 3),
                                condition=condition))
            wmap[(d, h)] = (wind, rain)

            rush = 1.0 if hod in (7, 8, 9, 16, 17, 18, 19) else 0.0
            cong = 0.12 + 0.55 * rush + (0.15 if rain else 0.0) + float(rng.normal(0, 0.05))
            cong = min(0.98, max(0.02, cong))
            closures = int(rng.random() < 0.03)
            traffic.append(dict(ts=h, district=d, congestion_index=round(cong, 3),
                                road_closures=closures))
            tmap[(d, h)] = cong

    return pd.DataFrame(weather), pd.DataFrame(traffic), wmap, tmap


def generate(days: int, seed: int):
    rng = np.random.default_rng(seed)
    end = datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    hours = pd.date_range(start, end, freq="h", inclusive="left").to_pydatetime().tolist()

    weather_df, traffic_df, wmap, tmap = build_environment(hours, rng)

    incidents, dispatch, citizens = [], [], []
    for d, meta in DISTRICTS.items():
        clat, clng = meta["center"]
        for h in hours:
            wind, rain = wmap[(d, h)]
            cong = tmap[(d, h)]
            wfac = 1.0 + (0.25 if rain else 0.0) + (0.20 if wind > 22 else 0.0)
            lam = meta["base_rate"] * DIURNAL[h.hour] * wfac * (1.0 + 0.3 * cong)
            n = int(rng.poisson(lam))

            for _ in range(n):
                t = pick_type(rng, meta["mix"])
                pr = pick_priority(rng, t)
                ts = h + timedelta(seconds=int(rng.integers(0, 3600)))
                lat = clat + float(rng.normal(0, 0.012))
                lng = clng + float(rng.normal(0, 0.012))
                iid = f"INC-{uuid.uuid4().hex[:10]}"
                incidents.append(dict(
                    incident_id=iid, ts=ts, district=d, lat=round(lat, 5), lng=round(lng, 5),
                    type=t, priority=pr, source="911" if rng.random() < 0.8 else "dispatch",
                    reported_text=str(rng.choice(INCIDENT_TEXT[t])), status="cleared",
                    escalated=did_escalate(rng, t, pr, wind, cong)))

                proc = int(rng.integers(40, 150))
                dispatched = ts + timedelta(seconds=proc)
                resp = max(60.0, RESP_BASE_SEC[pr] * (1 + 0.6 * cong) + float(rng.normal(0, 60)))
                on_scene = dispatched + timedelta(seconds=int(resp))
                svc = max(300.0, SERVICE_SEC[t] * (1 + float(rng.normal(0, 0.2))))
                cleared = on_scene + timedelta(seconds=int(svc))
                dispatch.append(dict(
                    dispatch_id=f"DSP-{uuid.uuid4().hex[:10]}", incident_id=iid,
                    unit_id=f"{UNIT[t]}-{d[0]}{int(rng.integers(1, 20)):02d}",
                    unit_type=UNIT_TYPE[t], dispatched_ts=dispatched, on_scene_ts=on_scene,
                    cleared_ts=cleared, district=d))

            # Citizen reports: loosely correlated with activity.
            cn = int(rng.poisson(0.4 * meta["base_rate"] * DIURNAL[h.hour]))
            for _ in range(cn):
                flavor = pick_type(rng, meta["mix"]) if rng.random() < 0.6 else "general"
                loc = str(rng.choice(STREETS))
                citizens.append(dict(
                    report_id=f"CIT-{uuid.uuid4().hex[:10]}",
                    ts=h + timedelta(seconds=int(rng.integers(0, 3600))),
                    lat=round(clat + float(rng.normal(0, 0.015)), 5),
                    lng=round(clng + float(rng.normal(0, 0.015)), 5),
                    raw_text=str(rng.choice(CITIZEN_TEXT[flavor])).format(loc=loc),
                    channel=str(rng.choice(CHANNELS))))

    return dict(
        raw_incidents=pd.DataFrame(incidents),
        raw_dispatch=pd.DataFrame(dispatch),
        raw_weather=weather_df,
        raw_traffic=traffic_df,
        raw_citizen_reports=pd.DataFrame(citizens),
    )


VIEWS_SQL = """
CREATE OR REPLACE VIEW unified_incidents AS
SELECT
    i.incident_id, i.ts, i.district, i.lat, i.lng, i.type, i.priority,
    i.source, i.reported_text, i.status, i.escalated,
    d.unit_id, d.unit_type, d.dispatched_ts, d.on_scene_ts, d.cleared_ts,
    date_diff('second', d.dispatched_ts, d.on_scene_ts) AS response_time_sec,
    w.temp_f, w.wind_mph, w.condition,
    t.congestion_index
FROM raw_incidents i
LEFT JOIN raw_dispatch d ON d.incident_id = i.incident_id
LEFT JOIN raw_weather w  ON w.district = i.district AND date_trunc('hour', w.ts) = date_trunc('hour', i.ts)
LEFT JOIN raw_traffic t  ON t.district = i.district AND date_trunc('hour', t.ts) = date_trunc('hour', i.ts);

CREATE OR REPLACE VIEW district_hour_metrics AS
SELECT
    district,
    date_trunc('hour', ts) AS hour,
    count(*) AS incident_count,
    count(*) FILTER (WHERE type = 'medical') AS medical_count,
    count(*) FILTER (WHERE type = 'fire')    AS fire_count,
    count(*) FILTER (WHERE type = 'police')  AS police_count,
    count(*) FILTER (WHERE type = 'hazmat')  AS hazmat_count,
    count(*) FILTER (WHERE type = 'traffic') AS traffic_count,
    count(*) FILTER (WHERE priority = 1)     AS priority1_count,
    round(avg(response_time_sec), 1)         AS avg_response_time_sec
FROM unified_incidents
GROUP BY 1, 2;
"""


def inject_scenario(tables: dict):
    """Append the scripted North-District gas-leak 'developing event' at the most
    recent timestamps so anomaly/clustering/forecast/escalation all light up."""
    inc, disp = tables["raw_incidents"], tables["raw_dispatch"]
    cit, wx = tables["raw_citizen_reports"], tables["raw_weather"]
    base = inc["ts"].max()
    clat, clng = DISTRICTS["North"]["center"]

    # (minutes_before_now, type, priority, text)
    events = [
        (35, "hazmat", 1, "reported gas leak, evacuating area"),
        (30, "medical", 1, "difficulty breathing, possible gas exposure"),
        (24, "medical", 1, "person collapsed, complains of fumes"),
        (18, "medical", 2, "elderly resident dizzy and nauseous"),
        (11, "hazmat", 1, "strong gas smell, multiple people affected"),
        (5, "medical", 1, "unconscious person near gas odor"),
    ]
    offs = [(0.0008, 0.0006), (-0.0007, 0.0009), (0.0011, -0.0005),
            (-0.0009, -0.0008), (0.0005, 0.0012), (-0.0004, -0.0011)]
    new_inc, new_disp = [], []
    for i, (mins, t, pr, text) in enumerate(events):
        ts = base - timedelta(minutes=mins)
        iid = f"INC-evt{i:02d}"
        dlat, dlng = offs[i]
        new_inc.append(dict(
            incident_id=iid, ts=ts, district="North",
            lat=round(clat + dlat, 5), lng=round(clng + dlng, 5),
            type=t, priority=pr, source="911", reported_text=text,
            status="on_scene", escalated=True))
        new_disp.append(dict(
            dispatch_id=f"DSP-evt{i:02d}", incident_id=iid,
            unit_id=f"{UNIT[t]}-N{i + 1:02d}", unit_type=UNIT_TYPE[t],
            dispatched_ts=ts + timedelta(seconds=60),
            on_scene_ts=ts + timedelta(seconds=300), cleared_ts=None,
            district="North"))

    citizen_texts = [
        "strong smell of gas near 5th & Oak",
        "smoke coming from a building on Oak St, feeling dizzy",
        "chemical odor in the air, hard to breathe",
        "more people coughing outside near Oak & 6th",
        "everyone evacuating, gas smell is strong",
    ]
    new_cit = []
    for i, text in enumerate(citizen_texts):
        new_cit.append(dict(
            report_id=f"CIT-evt{i:02d}", ts=base - timedelta(minutes=33 - i * 6),
            lat=round(clat + 0.0006 * (i - 2), 5), lng=round(clng + 0.0007 * (2 - i), 5),
            raw_text=text, channel="app"))

    # High wind in North for the last two hours, matching the scenario.
    hour_floor = base.replace(minute=0, second=0, microsecond=0)
    mask = (wx["district"] == "North") & (wx["ts"] >= hour_floor - timedelta(hours=1))
    wx.loc[mask, "wind_mph"] = 28.0
    wx.loc[mask, "condition"] = "windy"

    tables["raw_incidents"] = pd.concat([inc, pd.DataFrame(new_inc)], ignore_index=True)
    tables["raw_dispatch"] = pd.concat([disp, pd.DataFrame(new_disp)], ignore_index=True)
    tables["raw_citizen_reports"] = pd.concat([cit, pd.DataFrame(new_cit)], ignore_index=True)


def main():
    ap = argparse.ArgumentParser(description="SENTINEL synthetic data generator")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--db", default="data/sentinel.duckdb")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-inject", dest="inject", action="store_false",
                    help="Do not inject the scripted developing-event scenario")
    ap.set_defaults(inject=True)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    print(f"Generating {args.days} days of data (seed={args.seed}) ...")
    tables = generate(args.days, args.seed)
    if args.inject:
        inject_scenario(tables)
        print("  injected scenario: north-gas-leak (developing event)")

    con = duckdb.connect(args.db)
    for name, df in tables.items():
        con.register("_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
        con.unregister("_df")
        print(f"  {name:22s} {len(df):>7,} rows")
    con.execute(VIEWS_SQL)
    n_views = con.execute(
        "SELECT count(*) FROM unified_incidents").fetchone()[0]
    esc = con.execute(
        "SELECT round(100.0*avg(CASE WHEN escalated THEN 1 ELSE 0 END),1) FROM raw_incidents").fetchone()[0]
    con.close()
    print(f"  views: unified_incidents ({n_views:,} rows), district_hour_metrics")
    print(f"  historical escalation rate: {esc}%")
    print(f"Done -> {args.db}")


if __name__ == "__main__":
    main()
