"""Escalation prediction — logistic regression on historical incidents.

Predicts the probability an incident/cluster escalates, and exposes the model
coefficients as feature attributions for the evidence trail. Maps to BigQuery ML
(logistic_reg / boosted_tree) in the cloud phase.
"""
from __future__ import annotations

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from .config import TYPES

FEATURE_SQL = """
SELECT i.type, i.priority, EXTRACT(hour FROM i.ts) AS hod,
       COALESCE(w.wind_mph, 8)          AS wind_mph,
       COALESCE(t.congestion_index, 0.3) AS congestion_index,
       CASE WHEN i.escalated THEN 1 ELSE 0 END AS y
FROM raw_incidents i
LEFT JOIN raw_weather w ON w.district = i.district AND date_trunc('hour', w.ts) = date_trunc('hour', i.ts)
LEFT JOIN raw_traffic t ON t.district = i.district AND date_trunc('hour', t.ts) = date_trunc('hour', i.ts)
"""


def _design(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    for t in TYPES:
        X[f"type_{t}"] = (df["type"] == t).astype(int)
    X["priority"] = df["priority"]
    X["hod"] = df["hod"]
    X["wind_mph"] = df["wind_mph"]
    X["congestion_index"] = df["congestion_index"]
    return X


class EscalationModel:
    def __init__(self, model, features, auc, coefs):
        self.model = model
        self.features = features
        self.auc = auc
        self.coefs = coefs  # list[(feature, coefficient)] sorted by |coef|

    def score(self, type_, priority, wind_mph, congestion_index, hod=12) -> float:
        row = {f"type_{t}": 0 for t in TYPES}
        if f"type_{type_}" in row:
            row[f"type_{type_}"] = 1
        row.update(priority=priority, hod=hod, wind_mph=wind_mph,
                   congestion_index=congestion_index)
        X = pd.DataFrame([row])[self.features]
        return float(self.model.predict_proba(X)[0, 1])


def train(db) -> EscalationModel:
    df = db.df(FEATURE_SQL)
    X, y = _design(df), df["y"]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=0, stratify=y)
    model = LogisticRegression(max_iter=1000)
    model.fit(X_tr, y_tr)
    auc = float(roc_auc_score(y_te, model.predict_proba(X_te)[:, 1]))
    coefs = sorted(zip(X.columns, model.coef_[0]), key=lambda kv: -abs(kv[1]))
    return EscalationModel(model, list(X.columns), auc, coefs)
