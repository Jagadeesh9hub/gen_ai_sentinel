"""Spatial-temporal clustering — turn many calls into one "developing event".

Gathers recent incidents and citizen reports and clusters them in space AND time
(DBSCAN over local-km coordinates plus a scaled time axis). A tight, recent
cluster spanning multiple sources is the early signature of one developing
situation — distinct from unrelated background incidents in the same area.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DISTRICT_CENTERS

# Severity order (most severe first) for choosing a cluster's risk-dominant type.
SEVERITY = ["hazmat", "fire", "medical", "traffic", "police"]

RECENT_SQL = """
SELECT incident_id AS id, ts, lat, lng, type, 'incident' AS source
FROM raw_incidents
WHERE ts >= (SELECT max(ts) FROM raw_incidents) - (? * INTERVAL 1 HOUR)
UNION ALL
SELECT report_id AS id, ts, lat, lng, NULL AS type, 'citizen' AS source
FROM raw_citizen_reports
WHERE ts >= (SELECT max(ts) FROM raw_citizen_reports) - (? * INTERVAL 1 HOUR)
"""


def _nearest_district(lat: float, lng: float) -> str:
    return min(DISTRICT_CENTERS,
               key=lambda d: (DISTRICT_CENTERS[d][0] - lat) ** 2 + (DISTRICT_CENTERS[d][1] - lng) ** 2)


def _dominant_type(types: list[str]) -> str | None:
    for t in SEVERITY:
        if t in types:
            return t
    return None


def detect_clusters(db, window_hours: int = 6, eps_km: float = 0.6,
                    eps_minutes: float = 25.0, min_samples: int = 3) -> list[dict]:
    """Detect developing-event clusters in space and time."""
    from sklearn.cluster import DBSCAN

    df = db.df(RECENT_SQL, [window_hours, window_hours])
    if len(df) < min_samples:
        return []
    df["ts"] = pd.to_datetime(df["ts"])
    now = df["ts"].max()

    # Project to local kilometres + a time axis scaled so eps_minutes == eps_km.
    lat0 = float(df["lat"].mean())
    x_km = df["lng"].to_numpy() * np.cos(np.radians(lat0)) * 111.32
    y_km = df["lat"].to_numpy() * 111.32
    t_min = (df["ts"] - df["ts"].min()).dt.total_seconds().to_numpy() / 60.0
    t_km = t_min * (eps_km / eps_minutes)
    feats = np.column_stack([x_km, y_km, t_km])

    labels = DBSCAN(eps=eps_km, min_samples=min_samples, metric="euclidean").fit_predict(feats)
    df = df.assign(cluster=labels)

    clusters: list[dict] = []
    for cid, g in df[df.cluster >= 0].groupby("cluster"):
        lat, lng = float(g.lat.mean()), float(g.lng.mean())
        last_ts = g.ts.max()
        types = sorted(t for t in g["type"].dropna().unique().tolist())
        duration_min = round((g.ts.max() - g.ts.min()).total_seconds() / 60.0, 1)
        clusters.append(dict(
            cluster_id=int(cid),
            size=int(len(g)),
            incident_count=int((g.source == "incident").sum()),
            citizen_count=int((g.source == "citizen").sum()),
            district=_nearest_district(lat, lng),
            centroid_lat=round(lat, 5),
            centroid_lng=round(lng, 5),
            types=types,
            dominant_type=_dominant_type(types),
            first_ts=str(g.ts.min()),
            last_ts=str(last_ts),
            duration_min=duration_min,
            members=[
                {"id": row.id, "type": (row.type if pd.notna(row.type) else None),
                 "source": row.source, "ts": str(row.ts)}
                for row in g.sort_values("ts").itertuples()
            ],
            # "Developing" = active (recent) and dense.
            is_developing=bool((now - last_ts).total_seconds() <= 3600 and len(g) >= min_samples),
        ))
    clusters.sort(key=lambda c: (not c["is_developing"], -c["size"]))
    return clusters
