"""SENTINEL API — FastAPI backend hosting the agent and analytics.

Local stand-in for the Cloud Run service. Serves the dashboard with the unified
situational picture, predictions, explainable recommendations, natural-language
Q&A, and the human-in-the-loop action gate.

Run:  uvicorn services.api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sentinel import actions, anomaly, clustering, escalation, forecast, qa, recommend
from sentinel.config import CAPACITY, DISTRICTS
from sentinel.db import Database
from sentinel.llm import get_llm
from sentinel.rag import load_index


def records(df: pd.DataFrame) -> list[dict]:
    """Serialize a DataFrame to JSON-safe records (ISO dates, no numpy types)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database(read_only=False)
    actions.ensure_tables(db)
    app.state.db = db
    app.state.llm = get_llm()
    app.state.protocols = load_index()
    app.state.esc_model = escalation.train(db)
    yield
    db.close()


app = FastAPI(title="SENTINEL API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


class AskBody(BaseModel):
    question: str


def _recs(app) -> list[dict]:
    recs = recommend.build_recommendations(
        app.state.db, app.state.llm, app.state.protocols, app.state.esc_model)
    for r in recs:
        r["status"] = actions.latest_decision(app.state.db, r["id"]) or "proposed"
    return recs


@app.get("/api/health")
def health():
    db = app.state.db
    return {"status": "ok", "llm": app.state.llm.name,
            "incidents": db.scalar("SELECT count(*) FROM raw_incidents")}


@app.get("/api/overview")
def overview():
    db = app.state.db
    today = db.df(
        """SELECT count(*) AS total_today, round(avg(response_time_sec)/60.0,1) AS avg_response_min
           FROM unified_incidents
           WHERE CAST(ts AS DATE) = (SELECT max(CAST(ts AS DATE)) FROM unified_incidents)""").iloc[0]
    active = int(db.scalar("SELECT count(*) FROM raw_incidents WHERE status <> 'cleared'") or 0)

    adf = anomaly.current_anomalies(db)
    z_by_d = {r.district: (float(r.zscore), bool(r.is_anomaly), int(r.incident_count))
              for r in adf.itertuples()}
    fc = forecast.forecast(db, horizon=6)
    next_by_d: dict[str, dict] = {}
    for f in sorted(fc, key=lambda x: x["ts"]):
        next_by_d.setdefault(f["district"], f)

    districts = []
    for d in DISTRICTS:
        z, is_anom, cnt = z_by_d.get(d, (0.0, False, 0))
        nxt = next_by_d.get(d, {})
        districts.append({
            "district": d, "latest_count": cnt, "zscore": z, "is_anomaly": is_anom,
            "next_pred": nxt.get("predicted"), "capacity": CAPACITY.get(d),
            "exceeds": nxt.get("exceeds", False),
        })

    clusters = clustering.detect_clusters(db)
    recent = db.df(
        """SELECT incident_id, ts, district, type, priority, status, reported_text
           FROM unified_incidents ORDER BY ts DESC LIMIT 15""")

    return {
        "kpis": {
            "total_today": int(today["total_today"]),
            "avg_response_min": None if today["avg_response_min"] != today["avg_response_min"]
                                else float(today["avg_response_min"]),
            "active_incidents": active,
            "units_available": sum(CAPACITY.values()) - active,
            "anomalies": int(adf["is_anomaly"].sum()),
            "developing_events": sum(1 for c in clusters if c["is_developing"]),
        },
        "districts": districts,
        "anomalies": records(adf),
        "clusters": clusters,
        "recent_incidents": records(recent),
        "recommendation_count": len(_recs(app)),
    }


@app.get("/api/forecast")
def get_forecast(district: str | None = None, horizon: int = 6):
    fc = forecast.forecast(app.state.db, horizon=horizon)
    if district:
        fc = [f for f in fc if f["district"].lower() == district.lower()]
    return {"forecast": fc}


@app.get("/api/anomalies")
def get_anomalies():
    return {"anomalies": records(anomaly.current_anomalies(app.state.db))}


@app.get("/api/clusters")
def get_clusters():
    return {"clusters": clustering.detect_clusters(app.state.db)}


@app.get("/api/incidents")
def get_incidents(district: str | None = None, limit: int = 25):
    db = app.state.db
    cols = ("incident_id, ts, district, type, priority, status, reported_text, response_time_sec")
    if district:
        df = db.df(f"SELECT {cols} FROM unified_incidents WHERE district = ? "
                   "ORDER BY ts DESC LIMIT ?", [district, limit])
    else:
        df = db.df(f"SELECT {cols} FROM unified_incidents ORDER BY ts DESC LIMIT ?", [limit])
    return {"incidents": records(df)}


@app.get("/api/incidents/{incident_id}")
def incident_detail(incident_id: str):
    df = app.state.db.df("SELECT * FROM unified_incidents WHERE incident_id = ?", [incident_id])
    if df.empty:
        raise HTTPException(404, f"incident {incident_id} not found")
    return records(df)[0]


@app.get("/api/breakdowns")
def breakdowns():
    """Drill-down data behind each KPI tile."""
    db = app.state.db
    active = db.df(
        """SELECT incident_id, ts, district, type, priority, status, reported_text
           FROM unified_incidents WHERE status <> 'cleared' ORDER BY ts DESC""")
    today_by_district = db.df(
        """SELECT district, count(*) AS count FROM unified_incidents
           WHERE CAST(ts AS DATE) = (SELECT max(CAST(ts AS DATE)) FROM unified_incidents)
           GROUP BY district ORDER BY count DESC""")
    today_by_type = db.df(
        """SELECT type, count(*) AS count FROM unified_incidents
           WHERE CAST(ts AS DATE) = (SELECT max(CAST(ts AS DATE)) FROM unified_incidents)
           GROUP BY type ORDER BY count DESC""")
    response_by_district = db.df(
        """SELECT district, round(avg(response_time_sec)/60.0,1) AS avg_min, count(*) AS calls
           FROM unified_incidents
           WHERE CAST(ts AS DATE) = (SELECT max(CAST(ts AS DATE)) FROM unified_incidents)
           GROUP BY district ORDER BY avg_min DESC NULLS LAST""")
    active_by_d = {r.district: int(r.c) for r in
                   db.df("SELECT district, count(*) AS c FROM raw_incidents "
                         "WHERE status <> 'cleared' GROUP BY district").itertuples()}
    capacity = [{"district": d, "capacity": CAPACITY[d], "active": active_by_d.get(d, 0),
                 "available": CAPACITY[d] - active_by_d.get(d, 0)} for d in DISTRICTS]
    return {
        "active": records(active),
        "today_by_district": records(today_by_district),
        "today_by_type": records(today_by_type),
        "response_by_district": records(response_by_district),
        "capacity": capacity,
        "response_target_min": 8,
    }


@app.get("/api/recommendations")
def get_recommendations():
    return {"recommendations": _recs(app)}


@app.post("/api/recommendations/{rec_id}/approve")
def approve(rec_id: str):
    for r in _recs(app):
        if r["id"] == rec_id:
            return actions.approve(app.state.db, r)
    raise HTTPException(404, f"recommendation {rec_id} not found")


@app.post("/api/recommendations/{rec_id}/deny")
def deny(rec_id: str):
    for r in _recs(app):
        if r["id"] == rec_id:
            return actions.deny(app.state.db, r)
    raise HTTPException(404, f"recommendation {rec_id} not found")


@app.get("/api/actions")
def get_actions():
    db = app.state.db
    return {
        "audit": records(actions.audit_records(db)),
        "tickets": records(actions.tickets(db)),
        "alerts": records(actions.alerts(db)),
    }


@app.post("/api/ask")
def ask(body: AskBody):
    return qa.answer_question(app.state.db, body.question, app.state.llm, app.state.protocols)


@app.post("/api/admin/reset")
def reset_actions():
    """Clear all approvals/tickets/alerts — resets the demo to a clean slate."""
    db = app.state.db
    for t in ("audit_log", "dispatch_tickets", "public_alerts"):
        db.execute(f"DELETE FROM {t}")
    return {"reset": True}
