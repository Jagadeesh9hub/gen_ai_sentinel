"""Human-in-the-loop actions + immutable audit trail.

When a coordinator approves a recommendation, the corresponding action is
executed (a dispatch ticket created, a public alert recorded as drafted, or a
supervisor escalation logged) and every proposal/decision is written to the
audit log with the evidence snapshot at decision time.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    event_id   VARCHAR, ts TIMESTAMP, actor VARCHAR, action_type VARCHAR,
    target_id  VARCHAR, district VARCHAR, title VARCHAR, confidence DOUBLE,
    decision   VARCHAR, evidence VARCHAR, detail VARCHAR
);
CREATE TABLE IF NOT EXISTS dispatch_tickets (
    ticket_id VARCHAR, created_ts TIMESTAMP, district VARCHAR, units INTEGER,
    status VARCHAR, approved_by VARCHAR, source_rec VARCHAR
);
CREATE TABLE IF NOT EXISTS public_alerts (
    alert_id VARCHAR, created_ts TIMESTAMP, district VARCHAR, severity VARCHAR,
    area VARCHAR, draft_text VARCHAR, status VARCHAR, approved_by VARCHAR
);
"""


def ensure_tables(db):
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            db.execute(stmt)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def latest_decision(db, target_id: str) -> str | None:
    return db.scalar(
        "SELECT decision FROM audit_log WHERE target_id=? ORDER BY ts DESC LIMIT 1",
        [target_id])


def _log(db, rec: dict, decision: str, actor: str):
    db.execute(
        "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [str(uuid.uuid4()), _now(), actor, rec["action_type"], rec["id"],
         rec.get("district"), rec.get("title"), float(rec.get("confidence", 0)),
         decision, json.dumps(rec.get("evidence", [])), json.dumps(rec.get("payload", {}))])


def approve(db, rec: dict, actor: str = "coordinator") -> dict:
    """Execute the approved action and log it."""
    result = {"executed": rec["action_type"], "id": rec["id"]}
    payload = rec.get("payload", {})
    if rec["action_type"] == "dispatch_recommendation":
        tid = f"TKT-{uuid.uuid4().hex[:8]}"
        db.execute("INSERT INTO dispatch_tickets VALUES (?,?,?,?,?,?,?)",
                   [tid, _now(), rec["district"], int(payload.get("units", 1)),
                    "open", actor, rec["id"]])
        result["ticket_id"] = tid
    elif rec["action_type"] == "public_alert":
        aid = f"ALT-{uuid.uuid4().hex[:8]}"
        db.execute("INSERT INTO public_alerts VALUES (?,?,?,?,?,?,?,?)",
                   [aid, _now(), rec["district"], payload.get("severity", "high"),
                    payload.get("area", ""), payload.get("draft_text", ""),
                    "drafted", actor])
        result["alert_id"] = aid
    _log(db, rec, "approved", actor)
    return result


def deny(db, rec: dict, actor: str = "coordinator") -> dict:
    _log(db, rec, "denied", actor)
    return {"denied": rec["id"]}


def audit_records(db):
    return db.df("SELECT ts, actor, action_type, district, title, confidence, decision "
                 "FROM audit_log ORDER BY ts DESC")


def tickets(db):
    return db.df("SELECT * FROM dispatch_tickets ORDER BY created_ts DESC")


def alerts(db):
    return db.df("SELECT * FROM public_alerts ORDER BY created_ts DESC")
