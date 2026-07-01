"""Statistical anomaly detection — rolling z-score of incident volume.

Compares each district's latest-hour incident count to its trailing 7-day
(168-hour) baseline. A high z-score is an early signal of a spike.
"""
from __future__ import annotations

CURRENT_ANOMALY_SQL = """
WITH base AS (
    SELECT district, hour, incident_count,
           avg(incident_count)        OVER w AS roll_mean,
           stddev_samp(incident_count) OVER w AS roll_std
    FROM district_hour_metrics
    WINDOW w AS (PARTITION BY district ORDER BY hour
                 ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING)
)
SELECT district, hour, incident_count,
       round(roll_mean, 2) AS baseline,
       round((incident_count - roll_mean) / NULLIF(roll_std, 0), 2) AS zscore
FROM base
WHERE hour = (SELECT max(hour) FROM district_hour_metrics)
ORDER BY zscore DESC NULLS LAST
"""


def current_anomalies(db, threshold: float = 2.0):
    """Return a DataFrame of per-district anomaly status for the latest hour."""
    df = db.df(CURRENT_ANOMALY_SQL)
    df["zscore"] = df["zscore"].fillna(0.0)
    df["is_anomaly"] = df["zscore"] >= threshold
    return df
