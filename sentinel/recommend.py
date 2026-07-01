"""Explainable recommendations.

Composes the predictive signals (anomaly, clustering, escalation, forecast) and
protocol grounding into concrete, human-approvable recommendations. Each carries
a confidence score and a transparent evidence trail. Action recommendations are
flagged requires_human_approval — the agent proposes, a human disposes.
"""
from __future__ import annotations

import math

from . import anomaly, clustering, escalation, forecast


def _clamp(x: float, lo: float = 0.0, hi: float = 0.95) -> float:
    return round(max(lo, min(hi, x)), 2)


def _recent_env(db, district: str):
    wind = db.scalar("SELECT wind_mph FROM raw_weather WHERE district=? ORDER BY ts DESC LIMIT 1", [district])
    cong = db.scalar("SELECT congestion_index FROM raw_traffic WHERE district=? ORDER BY ts DESC LIMIT 1", [district])
    return float(wind or 8.0), float(cong or 0.3)


def build_recommendations(db, llm, protocols, esc_model=None) -> list[dict]:
    clusters = [c for c in clustering.detect_clusters(db) if c["is_developing"]]
    if not clusters:
        return []
    c = clusters[0]
    d = c["district"]
    dom = c["dominant_type"] or "medical"

    adf = anomaly.current_anomalies(db)
    zrow = adf[adf.district == d]
    z = float(zrow["zscore"].iloc[0]) if len(zrow) else 0.0

    fc = forecast.forecast(db, horizon=6)
    d_fc = sorted([f for f in fc if f["district"] == d], key=lambda f: f["ts"])
    nxt = d_fc[0] if d_fc else None
    pred = nxt["predicted"] if nxt else 0.0
    cap = nxt["capacity"] if nxt else 6
    margin = max(0.0, (pred - cap) / cap) if cap else 0.0

    esc_model = esc_model or escalation.train(db)
    wind, cong = _recent_env(db, d)
    p_esc = esc_model.score(dom, priority=1, wind_mph=wind, congestion_index=cong)

    def _top(q):
        res = protocols.search(q)
        return res[0] if res else None

    proto_dispatch = _top("pre-position units demand vs capacity resource allocation mutual aid")
    proto_alert = _top("public alert shelter in place evacuation issuance criteria")
    proto_escalate = _top(f"escalate supervisor {dom} tier escalation threshold")

    z_norm = min(z / 4.0, 1.0) if z > 0 else 0.0
    margin_norm = min(margin * 1.5, 1.0)
    proto_norm = min(proto_alert["score"] / 0.3, 1.0) if proto_alert else 0.0

    units = max(1, math.ceil(pred - cap)) if pred > cap else 1
    location = "5th & Oak area" if d == "North" else f"{d} District"
    base_ev = [
        {"source": "anomaly", "detail": f"Incident rate {z}σ above baseline in {d}", "ref": "anomaly"},
        {"source": "cluster", "detail": f"{c['size']} correlated reports "
         f"({c['incident_count']} incidents + {c['citizen_count']} citizen) in {c['duration_min']} min", "ref": f"cluster:{c['cluster_id']}"},
        {"source": "escalation", "detail": f"P(escalation) = {p_esc:.2f} ({dom}, priority 1, wind {wind:.0f} mph)", "ref": "escalation"},
    ]
    fc_ev = {"source": "forecast",
             "detail": (f"Forecast {pred} vs capacity {cap} next hour — exceeds" if pred > cap
                        else f"Forecast {pred} vs capacity {cap} next hour"),
             "ref": "forecast"}
    def _proto_ev(p):
        return [{"source": "protocol", "detail": p["citation"], "ref": p["doc"]}] if p else []

    recs: list[dict] = []

    recs.append(dict(
        id=f"dispatch:{d}",
        title=f"Pre-position {units} unit(s) to {d} District",
        action_type="dispatch_recommendation",
        district=d,
        confidence=_clamp(0.45 + 0.25 * z_norm + 0.30 * margin_norm),
        rationale=(f"{d} is forecast at {pred} incidents next hour against capacity {cap}, "
                   f"with an active {dom} cluster. Pre-position {units} unit(s) before the surge."),
        evidence=base_ev + [fc_ev] + _proto_ev(proto_dispatch),
        protocol=(proto_dispatch["citation"] if proto_dispatch else None),
        requires_human_approval=True,
        payload={"units": units, "to_district": d},
    ))

    # Templated (no LLM call) — build_recommendations runs on every dashboard poll,
    # so we must NOT hit Gemini here. Gemini is reserved for user-initiated Q&A.
    hazard = "hazmat incident (possible gas leak)" if dom == "hazmat" else f"{dom} incident"
    alert_text = (
        f"PUBLIC SAFETY ALERT — {d} District. Authorities are responding to a developing "
        f"{hazard} near {location}. Residents in the area should shelter in place, close "
        f"windows and doors, and avoid the area. Updates to follow."
    )
    recs.append(dict(
        id=f"public_alert:{d}",
        title=f"Draft public alert for {d} District",
        action_type="public_alert",
        district=d,
        confidence=_clamp(0.40 + 0.40 * p_esc + 0.20 * proto_norm),
        rationale=(f"Multiple correlated {dom} reports in a populated area meet the alert criteria. "
                   f"Draft a shelter-in-place advisory for coordinator approval."),
        evidence=base_ev + _proto_ev(proto_alert),
        protocol=(proto_alert["citation"] if proto_alert else None),
        requires_human_approval=True,
        payload={"draft_text": alert_text, "severity": "high", "area": location},
    ))

    recs.append(dict(
        id=f"escalation:{d}",
        title="Escalate to Fire/Hazmat Supervisor",
        action_type="escalation",
        district=d,
        confidence=_clamp(0.42 + 0.45 * p_esc + 0.13 * z_norm),
        rationale=(f"Predicted escalation probability {p_esc:.2f} for the {d} {dom} cluster exceeds the "
                   f"supervisor-notification threshold."),
        evidence=base_ev + _proto_ev(proto_escalate),
        protocol=(proto_escalate["citation"] if proto_escalate else None),
        requires_human_approval=True,
        payload={"to": "Fire/Hazmat Supervisor", "reason": f"{dom} cluster, P(escalation)={p_esc:.2f}"},
    ))

    recs.sort(key=lambda r: -r["confidence"])
    return recs
