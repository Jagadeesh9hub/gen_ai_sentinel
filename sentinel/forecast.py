"""Demand forecasting — transparent seasonal baseline + recent-surge adjustment.

For each district we learn the average incident count by (day-of-week, hour-of-day)
and scale it by a recency-weighted trend (the latest hour weighted most, so an
emerging surge is reflected quickly). Fully explainable and dependency-light. In
the cloud phase this maps to BigQuery ML ARIMA_PLUS behind the same interface.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CAPACITY


def _expected(season, overall, d, ts) -> float:
    return float(season.get((d, ts.dayofweek, ts.hour), overall[d]))


def forecast(db, horizon: int = 6) -> list[dict]:
    df = db.df("SELECT district, hour, incident_count FROM district_hour_metrics ORDER BY hour")
    if df.empty:
        return []
    df["hour"] = pd.to_datetime(df["hour"])
    df["dow"] = df["hour"].dt.dayofweek
    df["hod"] = df["hour"].dt.hour
    max_hour = df["hour"].max()

    # Fit the seasonal baseline on history EXCLUDING the current hour, so an
    # in-progress surge doesn't inflate the very expectation it's compared to.
    hist = df[df["hour"] < max_hour]
    if hist.empty:
        hist = df
    season = hist.groupby(["district", "dow", "hod"])["incident_count"].mean()
    overall = hist.groupby("district")["incident_count"].mean()

    out: list[dict] = []
    for d in df["district"].unique():
        dd = df[df.district == d].sort_values("hour")
        hrs = list(dd["hour"]); cnts = list(dd["incident_count"])

        # Recency-weighted trend: latest hour weighted most heavily.
        if hrs:
            e1 = _expected(season, overall, d, hrs[-1])
            r1 = cnts[-1] / e1 if e1 > 0 else 1.0
            last3, last3h = cnts[-3:], hrs[-3:]
            e3 = sum(_expected(season, overall, d, h) for h in last3h)
            r3 = sum(last3) / e3 if e3 > 0 else 1.0
            trend = float(np.clip(0.8 * r1 + 0.2 * r3, 0.5, 3.5))
        else:
            trend = 1.0

        for k in range(1, horizon + 1):
            ts = max_hour + pd.Timedelta(hours=k)
            base = _expected(season, overall, d, ts)
            pred = base * trend
            spread = 1.96 * np.sqrt(max(pred, 1e-6))
            cap = CAPACITY.get(d, 6)
            out.append(dict(
                district=d, ts=ts.isoformat(), predicted=round(pred, 2),
                lower=round(max(0.0, pred - spread), 2), upper=round(pred + spread, 2),
                capacity=cap, exceeds=bool(pred > cap), trend=round(trend, 2),
            ))
    return out
