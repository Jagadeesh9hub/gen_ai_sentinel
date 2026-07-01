"""Natural-language Q&A.

Primary path (if a real LLM/Gemini is configured): build a grounded context pack
and let the LLM answer anything, with dynamic suggestions.
Fallback path (mock / no free quota): a broad rule-based responder that answers
many natural questions about the data (counts, busiest/quietest district, response
times, forecast, developing events, units, escalation, recent incidents, per-district
summaries), and a clean "out of scope" message only when the question truly isn't
about this city's public-safety data. Always returns follow-up suggestions.
"""
from __future__ import annotations

from . import anomaly, clustering, forecast
from .config import CAPACITY, DISTRICTS, TYPES

DEFAULT_SUGGESTIONS = [
    "Which district is busiest today?",
    "How many hazmat incidents are there today?",
    "What's happening in North right now?",
    "Will any district exceed responder capacity?",
]

TYPE_SYNONYMS = {
    "medical": ["medical", "ambulance", "ems", "medic", "injury", "health"],
    "fire": ["fire", "smoke", "flame"],
    "police": ["police", "crime", "theft", "assault", "law enforcement"],
    "hazmat": ["hazmat", "gas", "chemical", "spill", "fumes", "leak"],
    "traffic": ["traffic", "crash", "collision", "accident", "vehicle"],
}

TODAY = "(SELECT max(CAST(ts AS DATE)) FROM unified_incidents)"


def _detect_district(q: str) -> str | None:
    ql = q.lower()
    for d in DISTRICTS:
        if d.lower() in ql:
            return d
    return None


def _detect_type(q: str) -> str | None:
    ql = q.lower()
    for t, syns in TYPE_SYNONYMS.items():
        if any(s in ql for s in syns):
            return t
    return None


def build_context(db, protocols, question: str):
    """Compact grounded snapshot for the LLM path."""
    kpi = db.df(
        f"""SELECT count(*) AS total_today, round(avg(response_time_sec)/60.0,1) AS avg_resp
            FROM unified_incidents WHERE CAST(ts AS DATE) = {TODAY}""").iloc[0]
    active = int(db.scalar("SELECT count(*) FROM raw_incidents WHERE status <> 'cleared'") or 0)
    adf = anomaly.current_anomalies(db)
    fc = forecast.forecast(db, horizon=3)
    nxt: dict = {}
    for f in sorted(fc, key=lambda x: x["ts"]):
        nxt.setdefault(f["district"], f)
    clusters = [c for c in clustering.detect_clusters(db) if c["is_developing"]]
    recent = db.df(
        """SELECT ts, district, type, priority, status, reported_text
           FROM unified_incidents ORDER BY ts DESC LIMIT 8""")
    resp = db.df(
        f"""SELECT district, type, round(avg(response_time_sec)/60.0,1) AS avg_min, count(*) AS n
            FROM unified_incidents WHERE CAST(ts AS DATE) = {TODAY}
            GROUP BY district, type ORDER BY district, type""")
    rag = protocols.search(question, k=3) if protocols else []

    L = [f"KPIs: incidents_today={int(kpi.total_today)}, avg_response_min={kpi.avg_resp}, "
         f"active_incidents={active}, anomalies={int(adf['is_anomaly'].sum())}, developing_events={len(clusters)}",
         "Per-district (latest hour):"]
    for r in adf.itertuples():
        n = nxt.get(r.district, {})
        L.append(f"  {r.district}: count={int(r.incident_count)}, zscore={r.zscore}, "
                 f"anomaly={'yes' if r.is_anomaly else 'no'}, forecast_next_hour={n.get('predicted')}, "
                 f"capacity={n.get('capacity')}, exceeds_capacity={n.get('exceeds')}")
    if clusters:
        L.append("Developing events:")
        for c in clusters:
            L.append(f"  {c['district']}: {c['size']} correlated reports "
                     f"({c['incident_count']} incidents + {c['citizen_count']} citizen), types={c['types']}")
    L.append("Avg response time today (min) by district/type:")
    for r in resp.itertuples():
        L.append(f"  {r.district}/{r.type}: {r.avg_min} min ({int(r.n)} calls)")
    L.append("Recent incidents:")
    for r in recent.itertuples():
        L.append(f"  {str(r.ts)[:16]} {r.district} {r.type} P{int(r.priority)} [{r.status}] {r.reported_text}")
    if rag:
        L.append("Relevant protocols:")
        for h in rag:
            L.append(f"  - {h['citation']}: {h['snippet']}")
    return "\n".join(L), rag


def _summarize_district(db, d: str) -> str:
    adf = anomaly.current_anomalies(db)
    row = adf[adf.district == d]
    z = float(row.zscore.iloc[0]) if len(row) else 0.0
    cnt = int(row.incident_count.iloc[0]) if len(row) else 0
    anom = bool(row.is_anomaly.iloc[0]) if len(row) else False
    fc = [f for f in forecast.forecast(db, horizon=1) if f["district"] == d]
    nxt = fc[0] if fc else {}
    cl = [c for c in clustering.detect_clusters(db) if c["is_developing"] and c["district"] == d]
    s = f"{d}: {cnt} incidents in the latest hour ({z} sigma vs baseline{', anomalous' if anom else ''})."
    if nxt:
        s += f" Forecast next hour: {nxt['predicted']} vs capacity {nxt['capacity']}" + \
             (" (exceeds capacity)." if nxt.get("exceeds") else ".")
    if cl:
        s += f" Developing {cl[0]['types']} event: {cl[0]['size']} correlated reports."
    return s


def _keyword_answer(db, question: str, llm) -> dict:
    ql = question.lower()
    d = _detect_district(question)
    t = _detect_type(question)
    ev: list = []

    if any(k in ql for k in ("response time", "respond", "how fast", "how long", "how quick", "arrival")):
        dd, tt = d or "North", t or "medical"
        row = db.df(f"""SELECT count(*) n, round(avg(response_time_sec)/60.0,1) mins
                        FROM unified_incidents WHERE type=? AND district=? AND CAST(ts AS DATE)={TODAY}""",
                    [tt, dd]).iloc[0]
        n = int(row.n); mins = None if row.mins != row.mins else float(row.mins)
        facts = (f"Average response time for {tt} calls in {dd} today is {mins} minutes across {n} calls."
                 if n else f"No {tt} calls recorded in {dd} today.")
        ev = [{"source": "query", "detail": f"{n} {tt} calls in {dd} today", "ref": "unified_incidents"}]

    elif any(k in ql for k in ("busiest", "most incidents", "highest", "worst", "hardest hit", "hotspot")):
        df = db.df(f"SELECT district, count(*) c FROM unified_incidents WHERE CAST(ts AS DATE)={TODAY} GROUP BY district ORDER BY c DESC")
        facts = f"{df.iloc[0].district} is the busiest district today with {int(df.iloc[0].c)} incidents. " + \
                "Full order: " + ", ".join(f"{r.district} ({int(r.c)})" for r in df.itertuples()) + "."
        ev = [{"source": "query", "detail": f"{r.district}: {int(r.c)}", "ref": "unified_incidents"} for r in df.itertuples()]

    elif any(k in ql for k in ("quietest", "least", "fewest", "safest", "calmest", "lowest")):
        df = db.df(f"SELECT district, count(*) c FROM unified_incidents WHERE CAST(ts AS DATE)={TODAY} GROUP BY district ORDER BY c ASC")
        facts = f"{df.iloc[0].district} is the quietest district today with {int(df.iloc[0].c)} incidents."
        ev = [{"source": "query", "detail": f"{r.district}: {int(r.c)}", "ref": "unified_incidents"} for r in df.itertuples()]

    elif any(k in ql for k in ("unit", "available", "resource", "responder", "staff", "free unit")):
        active = int(db.scalar("SELECT count(*) FROM raw_incidents WHERE status <> 'cleared'") or 0)
        total = sum(CAPACITY.values())
        facts = f"{total - active} of {total} responder units are currently available ({active} committed to active incidents)."
        ev = [{"source": "query", "detail": f"{active} active incidents", "ref": "raw_incidents"}]

    elif any(k in ql for k in ("how many", "number of", "count", "total incidents", "incidents today", "incidents in", "are there")):
        where, params = f"CAST(ts AS DATE)={TODAY}", []
        if d:
            where += " AND district=?"; params.append(d)
        if t:
            where += " AND type=?"; params.append(t)
        n = int(db.scalar(f"SELECT count(*) FROM unified_incidents WHERE {where}", params) or 0)
        scope = (f"{t} " if t else "") + "incidents" + (f" in {d}" if d else "") + " today"
        facts = f"There are {n} {scope}."
        ev = [{"source": "query", "detail": f"{scope}: {n}", "ref": "unified_incidents"}]

    elif any(k in ql for k in ("rising", "increasing", "busier", "trend", "volume", "going up")):
        df = db.df(f"""WITH m AS (SELECT district, hour, incident_count FROM district_hour_metrics),
                           latest AS (SELECT max(hour) h FROM m)
                       SELECT cur.district, cur.incident_count this_hour,
                              cur.incident_count - COALESCE(prev.incident_count,0) delta
                       FROM m cur JOIN latest ON cur.hour=latest.h
                       LEFT JOIN m prev ON prev.district=cur.district AND prev.hour=cur.hour - INTERVAL 1 HOUR
                       ORDER BY delta DESC""")
        rising = df[df.delta > 0]
        facts = ("Districts with rising incident volume this hour: " +
                 ", ".join(f"{r.district} (+{int(r.delta)})" for r in rising.itertuples()) + "."
                 if len(rising) else "No districts show rising incident volume this hour.")
        ev = [{"source": "query", "detail": f"{r.district}: {int(r.this_hour)} now ({int(r.delta):+d})", "ref": "district_hour_metrics"} for r in df.itertuples()]

    elif any(k in ql for k in ("forecast", "predict", "expect", "next hour", "upcoming", "demand", "capacity", "exceed", "overwhelm", "run out", "short-staffed")):
        if d:
            fc = [f for f in forecast.forecast(db, horizon=3) if f["district"] == d]
            if fc:
                nx = fc[0]
                facts = (f"{d} is forecast at {nx['predicted']} incidents next hour vs capacity {nx['capacity']}" +
                         (" - a projected breach." if nx["exceeds"] else " - within capacity."))
                ev = [{"source": "forecast", "detail": f"{d} {ff['ts'][11:16]}: {ff['predicted']} vs cap {ff['capacity']}", "ref": "forecast"} for ff in fc]
            else:
                facts = f"No forecast available for {d}."
        else:
            fc = forecast.forecast(db, horizon=6)
            breaches = [f for f in fc if f["exceeds"]]
            if breaches:
                top = max(breaches, key=lambda f: f["predicted"])
                facts = f"{top['district']} is forecast at {top['predicted']} incidents next hour vs capacity {top['capacity']} - a projected breach."
                ev = [{"source": "forecast", "detail": f"{b['district']} {b['ts'][11:16]}: {b['predicted']} vs cap {b['capacity']}", "ref": "forecast"} for b in breaches[:4]]
            else:
                facts = "No district is forecast to exceed capacity in the next 6 hours."

    elif any(k in ql for k in ("developing", "pattern", "situation", "anomal", "unusual", "spike", "cluster", "happening", "emerging", "going on", "concern")):
        clusters = [c for c in clustering.detect_clusters(db) if c["is_developing"]]
        adf = anomaly.current_anomalies(db)
        if d:
            facts = _summarize_district(db, d)
        elif clusters:
            c = clusters[0]
            zr = adf.loc[adf.district == c["district"], "zscore"]
            zval = float(zr.iloc[0]) if len(zr) else 0.0
            facts = (f"Yes - a developing event is likely in {c['district']}: {c['size']} correlated reports "
                     f"({c['incident_count']} incidents + {c['citizen_count']} citizen) of type {c['types']}, "
                     f"with the incident rate {zval} sigma above baseline.")
            ev = [{"source": "cluster", "detail": f"{c['size']} correlated reports in {c['district']}", "ref": f"cluster:{c['cluster_id']}"}]
        else:
            facts = "No developing situations detected; all districts are near baseline."

    elif any(k in ql for k in ("escalat", "serious", "severe", "priority", "critical", "high-risk")):
        p1 = int(db.scalar(f"SELECT count(*) FROM unified_incidents WHERE priority=1 AND CAST(ts AS DATE)={TODAY}") or 0)
        cl = [c for c in clustering.detect_clusters(db) if c["is_developing"]]
        facts = f"There are {p1} priority-1 incidents today."
        if cl:
            facts += f" Highest escalation risk right now: the {cl[0]['types']} cluster in {cl[0]['district']} ({cl[0]['size']} correlated reports)."
        ev = [{"source": "query", "detail": f"{p1} priority-1 today", "ref": "unified_incidents"}]

    elif any(k in ql for k in ("recent", "latest", "last few", "list", "show me", "what incidents", "which incidents")):
        where, params = ("WHERE district=?", [d]) if d else ("", [])
        df = db.df(f"SELECT ts,district,type,priority,reported_text FROM unified_incidents {where} ORDER BY ts DESC LIMIT 5", params)
        lines = [f"{str(r.ts)[11:16]} {r.district} {r.type} P{int(r.priority)} ({r.reported_text})" for r in df.itertuples()]
        facts = "Most recent incidents" + (f" in {d}" if d else "") + ": " + "; ".join(lines) + "."
        ev = [{"source": "feed", "detail": f"{len(df)} recent shown", "ref": "unified_incidents"}]

    elif d:
        facts = _summarize_district(db, d)
        ev = [{"source": "data", "detail": f"{d} summary", "ref": "overview"}]

    elif t:
        n = int(db.scalar(f"SELECT count(*) FROM unified_incidents WHERE type=? AND CAST(ts AS DATE)={TODAY}", [t]) or 0)
        facts = f"There are {n} {t} incidents today across all districts."
        ev = [{"source": "query", "detail": f"{t}: {n} today", "ref": "unified_incidents"}]

    elif any(k in ql for k in ("summary", "overview", "status", "picture", "how are things", "sitrep", "situation report", "brief me")):
        adf = anomaly.current_anomalies(db); hot = adf[adf.is_anomaly]
        cl = [c for c in clustering.detect_clusters(db) if c["is_developing"]]
        total = int(db.scalar(f"SELECT count(*) FROM unified_incidents WHERE CAST(ts AS DATE)={TODAY}") or 0)
        facts = f"{total} incidents today. "
        facts += (f"{hot.iloc[0].district} is {hot.iloc[0].zscore} sigma above baseline. " if len(hot) else "No anomalies flagged. ")
        facts += (f"A developing {cl[0]['types']} event is active in {cl[0]['district']}." if cl else "No developing events.")

    else:
        facts = "I focus on this city's public-safety operations, so I can't answer that. Try one of the questions below."

    return {"intent": "keyword", "answer": llm.answer(question, facts), "facts": facts, "evidence": ev}


def answer_question(db, question: str, llm, protocols=None) -> dict:
    # LLM path only when a real generative provider is configured (Gemini).
    if getattr(llm, "name", "").startswith("gemini"):
        context, rag = build_context(db, protocols, question)
        res = llm.ask(question, context)
        if res:
            evidence = [{"source": "protocol", "detail": h["citation"], "ref": h["doc"]} for h in rag[:2]]
            evidence.append({"source": "data", "detail": "grounded in live situational data", "ref": "overview"})
            sugg = [s for s in (res.get("suggestions") or []) if s][:3] or DEFAULT_SUGGESTIONS[:3]
            return {"intent": "freeform", "answer": res["answer"], "evidence": evidence, "suggestions": sugg}

    out = _keyword_answer(db, question, llm)
    out["suggestions"] = out.get("suggestions") or DEFAULT_SUGGESTIONS
    return out
