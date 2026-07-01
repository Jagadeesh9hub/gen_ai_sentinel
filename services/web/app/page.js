"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { getJSON, postJSON } from "../lib/api";

const MAP_POS = {
  Central: [300, 210], North: [300, 90], South: [300, 330],
  East: [480, 200], West: [120, 200], Harbor: [175, 320],
};

const SAMPLE_QS = [
  "Which districts have rising incident volume this hour?",
  "Average response time for medical calls in the north zone today?",
  "Are any patterns suggesting a developing situation?",
  "Will any district exceed capacity?",
];

const statusColor = (d) =>
  d.is_anomaly ? "var(--red)" : d.exceeds ? "var(--amber)" : "var(--accent)";

const timeFmt = (ts) => {
  try { return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return ts; }
};
const dateTimeFmt = (ts) => {
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
};
const mins = (s) => (s == null ? "—" : `${(s / 60).toFixed(1)} min`);

/* ---------- Modal ---------- */
function Modal({ title, onClose, children }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>✕</button>
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  );
}

/* ---------- KPI bar ---------- */
function Kpis({ k, onOpen, onAnomalies, onDeveloping }) {
  if (!k) return null;
  const tiles = [
    { label: "Active incidents", value: k.active_incidents, act: () => onOpen("active") },
    { label: "Incidents today", value: k.total_today, act: () => onOpen("today") },
    { label: "Avg response (min)", value: k.avg_response_min ?? "—", act: () => onOpen("response") },
    { label: "Units available", value: k.units_available, act: () => onOpen("units") },
    { label: "Anomalies", value: k.anomalies, cls: k.anomalies ? "alert" : "", act: k.anomalies ? onAnomalies : null },
    { label: "Developing events", value: k.developing_events, cls: k.developing_events ? "warn" : "", act: k.developing_events ? onDeveloping : null },
  ];
  return (
    <div className="kpis">
      {tiles.map((t) => (
        <div key={t.label} className={`kpi ${t.cls || ""} ${t.act ? "clickable" : ""}`} onClick={t.act || undefined}>
          <div className="label">{t.label}</div>
          <div className="value">{t.value}</div>
          {t.act && <div className="kpi-hint">view ›</div>}
        </div>
      ))}
    </div>
  );
}

function KpiModal({ metric, data, onClose, onIncident }) {
  const titles = {
    active: "Active incidents", today: "Incidents today",
    response: "Average response time (today)", units: "Units available by district",
  };
  const body = () => {
    if (!data) return <div className="empty">Loading…</div>;
    if (metric === "active") {
      return !data.active.length ? <div className="empty">No active incidents.</div> : (
        <div className="feed">
          {data.active.map((i) => (
            <div className="feed-item clickable" key={i.incident_id} onClick={() => onIncident(i.incident_id)}>
              <div className="time">{timeFmt(i.ts)}</div>
              <div className="txt"><span className="badge muted">{i.type}</span> <strong>{i.district}</strong> · P{i.priority} <small>{i.status}</small>
                <div><small>{i.reported_text}</small></div></div>
              <div className="chev">›</div>
            </div>
          ))}
        </div>
      );
    }
    if (metric === "today") {
      return (
        <div className="two-col">
          <div><h4>By district</h4>
            {data.today_by_district.map((r) => (
              <div className="member" key={r.district}><span>{r.district}</span><span className="muted">{r.count}</span></div>))}
          </div>
          <div><h4>By type</h4>
            {data.today_by_type.map((r) => (
              <div className="member" key={r.type}><span>{r.type}</span><span className="muted">{r.count}</span></div>))}
          </div>
        </div>
      );
    }
    if (metric === "response") {
      return (
        <>
          <div className="muted" style={{ marginBottom: 8 }}>Target for priority-1 medical: {data.response_target_min} min (per protocol).</div>
          <table className="dtable"><thead><tr><th>District</th><th className="num">Avg (min)</th><th className="num">Calls</th></tr></thead>
            <tbody>{data.response_by_district.map((r) => (
              <tr key={r.district}><td>{r.district}</td>
                <td className="num" style={r.avg_min > data.response_target_min ? { color: "var(--amber)" } : null}>{r.avg_min ?? "—"}</td>
                <td className="num">{r.calls}</td></tr>))}</tbody></table>
        </>
      );
    }
    if (metric === "units") {
      return (
        <table className="dtable"><thead><tr><th>District</th><th className="num">Capacity</th><th className="num">Active</th><th className="num">Available</th></tr></thead>
          <tbody>{data.capacity.map((r) => (
            <tr key={r.district}><td>{r.district}</td><td className="num">{r.capacity}</td>
              <td className="num">{r.active}</td>
              <td className="num" style={r.available <= 0 ? { color: "var(--red)" } : null}>{r.available}</td></tr>))}</tbody></table>
      );
    }
    return null;
  };
  return <Modal title={titles[metric] || "Detail"} onClose={onClose}>{body()}</Modal>;
}

/* ---------- Map ---------- */
function DistrictMap({ districts, clusters, onSelectDistrict, onSelectCluster, selected }) {
  const dev = (clusters || []).filter((c) => c.is_developing);
  return (
    <div className="map-wrap">
      <svg viewBox="0 0 600 410" width="100%" height="320">
        {districts.map((d) => {
          const [x, y] = MAP_POS[d.district] || [300, 200];
          const r = Math.min(34, 12 + (d.latest_count || 0) * 2.4);
          const color = statusColor(d);
          return (
            <g key={d.district} className="clickable" onClick={() => onSelectDistrict(d.district)}>
              {d.is_anomaly && (
                <circle className="pulse" cx={x} cy={y} r={16} fill="none" stroke="var(--red)" strokeWidth="2" />
              )}
              {selected === d.district && (
                <circle cx={x} cy={y} r={r + 6} fill="none" stroke="var(--accent)"
                  strokeDasharray="4 3" strokeWidth="2" />
              )}
              <circle cx={x} cy={y} r={r} fill={color} fillOpacity="0.22" stroke={color} strokeWidth="2" />
              <circle cx={x} cy={y} r={Math.max(r, 26)} fill="transparent" />
              <text className="district-label" x={x} y={y - r - 6} textAnchor="middle">{d.district}</text>
              <text className="district-sub" x={x} y={y + 4} textAnchor="middle">{d.latest_count}</text>
            </g>
          );
        })}
        {dev.map((c) => {
          const [x, y] = MAP_POS[c.district] || [300, 200];
          return (
            <text key={c.cluster_id} className="district-sub clickable" x={x} y={y + 18}
              textAnchor="middle" fill="var(--red)" onClick={() => onSelectCluster(c)}>
              ⚠ {c.size} correlated
            </text>
          );
        })}
      </svg>
    </div>
  );
}

/* ---------- District table ---------- */
function DistrictTable({ districts, onSelect, selected }) {
  return (
    <table className="dtable">
      <thead>
        <tr><th>District</th><th className="num">Now</th><th className="num">z-score</th>
          <th className="num">Next hr</th><th className="num">Cap</th><th>Status</th></tr>
      </thead>
      <tbody>
        {districts.map((d) => (
          <tr key={d.district} className="clickable" onClick={() => onSelect(d.district)}
            style={selected === d.district ? { background: "#1b2440" } : null}>
            <td>{d.district}</td>
            <td className="num">{d.latest_count}</td>
            <td className="num">{d.zscore}</td>
            <td className="num">{d.next_pred ?? "—"}</td>
            <td className="num">{d.capacity}</td>
            <td>
              {d.is_anomaly && <span className="badge red">ANOMALY</span>}
              {!d.is_anomaly && d.exceeds && <span className="badge amber">OVER CAP</span>}
              {!d.is_anomaly && !d.exceeds && <span className="badge green">normal</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ---------- Incident feed ---------- */
function Feed({ items, onSelect }) {
  if (!items || !items.length) return <div className="empty">No incidents.</div>;
  return (
    <div className="feed">
      {items.map((i) => (
        <div className="feed-item clickable" key={i.incident_id} onClick={() => onSelect(i.incident_id)}>
          <div className="time">{timeFmt(i.ts)}</div>
          <div className="txt">
            <span className="badge muted">{i.type}</span>{" "}
            <strong>{i.district}</strong> · P{i.priority} <small>{i.status}</small>
            <div><small>{i.reported_text}</small></div>
          </div>
          <div className="chev">›</div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Recommendations ---------- */
function Recommendations({ recs, onAct }) {
  if (!recs) return null;
  if (!recs.length) return <div className="empty">No active recommendations — all districts near baseline.</div>;
  return recs.map((r) => {
    const decided = r.status === "approved" || r.status === "denied";
    return (
      <div className="rec" key={r.id}>
        <div className="rec-head">
          <div className="rec-title">{r.title}</div>
          <div className="confidence">
            <div className="bar"><div style={{ width: `${Math.round(r.confidence * 100)}%` }} /></div>
            <div className="pct">{Math.round(r.confidence * 100)}%</div>
          </div>
        </div>
        <div className="rationale">{r.rationale}</div>
        <ul className="evidence">
          {r.evidence.map((e, idx) => (
            <li key={idx}><span className="src">{e.source}</span><span>{e.detail}</span></li>
          ))}
        </ul>
        {r.protocol && <div className="proto">📖 {r.protocol}</div>}
        {r.payload?.draft_text && <div className="alert-draft">{r.payload.draft_text}</div>}
        <div className="actions">
          {decided ? (
            <span className={`badge ${r.status === "approved" ? "green" : "muted"}`}>
              {r.status === "approved" ? "✓ APPROVED" : "✕ DENIED"}
            </span>
          ) : (
            <>
              <button className="approve" onClick={() => onAct(r.id, "approve")}>Approve</button>
              <button className="deny" onClick={() => onAct(r.id, "deny")}>Deny</button>
            </>
          )}
        </div>
      </div>
    );
  });
}

/* ---------- Ask ---------- */
function Ask() {
  const [q, setQ] = useState("");
  const [a, setA] = useState(null);
  const [busy, setBusy] = useState(false);
  const ask = async (question) => {
    const text = question ?? q;
    if (!text.trim()) return;
    setBusy(true);
    try { setA(await postJSON("/api/ask", { question: text })); }
    catch (e) { setA({ answer: "Error: " + e.message, evidence: [] }); }
    setBusy(false);
  };
  return (
    <div>
      <div className="ask-input">
        <input value={q} placeholder="Ask about incidents, response times, patterns, forecast…"
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} />
        <button className="ghost" onClick={() => ask()} disabled={busy}>{busy ? "…" : "Ask"}</button>
      </div>
      <div className="suggestions">
        {SAMPLE_QS.map((s) => <button key={s} onClick={() => { setQ(s); ask(s); }}>{s}</button>)}
      </div>
      {a && (
        <div className="ask-answer">
          <div>{a.answer}</div>
          {a.evidence?.length > 0 && (
            <div className="ev">{a.evidence.map((e, i) => <span className="chip" key={i}>{e.source}: {e.detail}</span>)}</div>
          )}
          {a.suggestions?.length > 0 && (
            <div className="suggestions" style={{ marginTop: 10 }}>
              <span className="muted" style={{ fontSize: 11, marginRight: 4 }}>Try:</span>
              {a.suggestions.map((s, i) => (
                <button key={i} onClick={() => { setQ(s); ask(s); }}>{s}</button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- Forecast ---------- */
function Forecast() {
  const [fc, setFc] = useState([]);
  const [district, setDistrict] = useState("North");
  useEffect(() => { getJSON("/api/forecast?horizon=6").then((d) => setFc(d.forecast)).catch(() => {}); }, []);
  const series = fc.filter((f) => f.district === district);
  const districts = [...new Set(fc.map((f) => f.district))];
  const cap = series[0]?.capacity || 6;
  const max = Math.max(cap, ...series.map((s) => s.predicted), 1) * 1.15;
  return (
    <div>
      <div className="tabs">
        {districts.map((d) => (
          <button key={d} className={d === district ? "active" : ""} onClick={() => setDistrict(d)}>{d}</button>
        ))}
      </div>
      <div className="fc">
        {series.map((s) => (
          <div className="col" key={s.ts}>
            <div className="val">{s.predicted}</div>
            <div className="barwrap">
              <div className={`b ${s.exceeds ? "over" : ""}`} style={{ height: `${(s.predicted / max) * 120}px` }} />
            </div>
            <div className="lbl">{timeFmt(s.ts)}</div>
          </div>
        ))}
      </div>
      <div className="muted" style={{ marginTop: 8 }}>
        Capacity for {district}: <strong>{cap}</strong> /hr · red bars exceed capacity.
      </div>
    </div>
  );
}

/* ---------- Audit ---------- */
function Audit({ actions }) {
  if (!actions) return null;
  const { audit, tickets, alerts } = actions;
  return (
    <div>
      <div className="muted" style={{ marginBottom: 8 }}>
        {tickets.length} dispatch ticket(s) · {alerts.length} alert draft(s) · {audit.length} audit record(s)
      </div>
      {audit.length === 0 && <div className="empty">No actions yet. Approve a recommendation to populate the audit trail.</div>}
      {audit.map((a, i) => (
        <div className="audit-row" key={i}>
          <span className="muted">{timeFmt(a.ts)}</span>
          <span className={`badge ${a.decision === "approved" ? "green" : "muted"}`}>{a.decision}</span>
          <span>{a.title}</span>
          <span className="muted" style={{ textAlign: "right" }}>{Math.round(a.confidence * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

/* ---------- Incident detail body ---------- */
function IncidentDetail({ data }) {
  if (!data) return <div className="empty">Loading…</div>;
  const rows = [
    ["Incident ID", data.incident_id], ["Time", dateTimeFmt(data.ts)],
    ["District", data.district], ["Type", data.type], ["Priority", `P${data.priority}`],
    ["Status", data.status], ["Reported", data.reported_text],
    ["Unit", data.unit_id ? `${data.unit_id} (${data.unit_type})` : "—"],
    ["Dispatched", data.dispatched_ts ? dateTimeFmt(data.dispatched_ts) : "—"],
    ["On scene", data.on_scene_ts ? dateTimeFmt(data.on_scene_ts) : "—"],
    ["Response time", mins(data.response_time_sec)],
    ["Weather", data.condition ? `${data.condition}, ${data.temp_f}°F, wind ${data.wind_mph} mph` : "—"],
    ["Congestion", data.congestion_index != null ? `${Math.round(data.congestion_index * 100)}%` : "—"],
    ["Escalated", data.escalated ? "yes" : "no"],
  ];
  return (
    <div className="kv">
      {rows.map(([k, v]) => (
        <Fragment key={k}><div className="k">{k}</div><div>{String(v)}</div></Fragment>
      ))}
    </div>
  );
}

/* ---------- Cluster detail body ---------- */
function ClusterDetail({ cluster, onSelectIncident }) {
  return (
    <div>
      <div className="kv">
        <div className="k">District</div><div>{cluster.district}</div>
        <div className="k">Size</div><div>{cluster.size} ({cluster.incident_count} incidents + {cluster.citizen_count} citizen)</div>
        <div className="k">Types</div><div>{cluster.types.join(", ")}</div>
        <div className="k">Dominant</div><div>{cluster.dominant_type}</div>
        <div className="k">Window</div><div>{cluster.duration_min} min ({timeFmt(cluster.first_ts)} → {timeFmt(cluster.last_ts)})</div>
      </div>
      <h4 style={{ margin: "14px 0 6px", color: "var(--muted)" }}>Members</h4>
      {cluster.members.map((m) => (
        <div className="member" key={m.id}
          onClick={() => m.source === "incident" && onSelectIncident(m.id)}>
          <span>{m.source === "incident" ? "🚨" : "💬"} {m.type || "citizen report"}</span>
          <span className="muted">{timeFmt(m.ts)} {m.source === "incident" ? "›" : ""}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------- Dashboard ---------- */
export default function Dashboard() {
  const [ov, setOv] = useState(null);
  const [recs, setRecs] = useState(null);
  const [actions, setActions] = useState(null);
  const [tab, setTab] = useState("recommend");
  const [err, setErr] = useState(null);

  const [districtFilter, setDistrictFilter] = useState(null);
  const [filtered, setFiltered] = useState([]);
  const [incident, setIncident] = useState(null);   // detail data
  const [cluster, setCluster] = useState(null);     // selected cluster
  const [kpiMetric, setKpiMetric] = useState(null);
  const [breakdowns, setBreakdowns] = useState(null);
  const timer = useRef(null);
  const feedRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [o, r, a] = await Promise.all([
        getJSON("/api/overview"), getJSON("/api/recommendations"), getJSON("/api/actions"),
      ]);
      setOv(o); setRecs(r.recommendations); setActions(a); setErr(null);
    } catch (e) { setErr(e.message); }
  }, []);

  useEffect(() => {
    refresh();
    timer.current = setInterval(refresh, 6000);
    return () => clearInterval(timer.current);
  }, [refresh]);

  useEffect(() => {
    if (!districtFilter) return;
    getJSON(`/api/incidents?district=${districtFilter}&limit=25`)
      .then((d) => setFiltered(d.incidents)).catch(() => setFiltered([]));
    feedRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [districtFilter]);

  const onAct = async (id, verb) => {
    await postJSON(`/api/recommendations/${id}/${verb}`, {});
    refresh();
  };
  const openIncident = async (id) => {
    setCluster(null);
    try { setIncident(await getJSON(`/api/incidents/${id}`)); }
    catch { setIncident({ incident_id: id, reported_text: "Could not load." }); }
  };
  const openKpi = (m) => {
    setKpiMetric(m);
    getJSON("/api/breakdowns").then(setBreakdowns).catch(() => setBreakdowns(null));
  };

  const feedItems = districtFilter ? filtered : ov?.recent_incidents;

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1><span className="shield">◆</span> SENTINEL</h1>
          <div className="sub">Public Safety Decision Intelligence · Situational Overview</div>
        </div>
        <div className="status-pill">
          <span className="dot" style={{ background: err ? "var(--red)" : "var(--green)" }} />
          {err ? "API offline" : "Live · synthetic feed"}
        </div>
      </header>

      <Kpis k={ov?.kpis} onOpen={openKpi}
        onAnomalies={() => { const a = ov?.districts?.find((d) => d.is_anomaly); if (a) setDistrictFilter(a.district); }}
        onDeveloping={() => { const c = ov?.clusters?.find((x) => x.is_developing); if (c) setCluster(c); }} />

      <div className="grid">
        <div>
          <div className="card">
            <h2>Situational map <span className="muted" style={{ textTransform: "none", fontWeight: 400 }}>· click a district or cluster</span></h2>
            {ov && <DistrictMap districts={ov.districts} clusters={ov.clusters}
              onSelectDistrict={setDistrictFilter} onSelectCluster={setCluster} selected={districtFilter} />}
          </div>
          <div className="card">
            <h2>District status</h2>
            {ov && <DistrictTable districts={ov.districts} onSelect={setDistrictFilter} selected={districtFilter} />}
          </div>
          <div className="card" ref={feedRef}>
            <h2>{districtFilter ? `${districtFilter} incidents` : "Live incident feed"} <span className="muted" style={{ textTransform: "none", fontWeight: 400 }}>· click for details</span></h2>
            {districtFilter && (
              <span className="filter-chip" onClick={() => setDistrictFilter(null)}>{districtFilter} ✕</span>
            )}
            <Feed items={feedItems} onSelect={openIncident} />
          </div>
        </div>

        <div>
          <div className="card">
            <h2>Ask SENTINEL</h2>
            <Ask />
          </div>
          <div className="card">
            <div className="tabs">
              <button className={tab === "recommend" ? "active" : ""} onClick={() => setTab("recommend")}>
                Recommendations{recs?.length ? ` (${recs.length})` : ""}
              </button>
              <button className={tab === "forecast" ? "active" : ""} onClick={() => setTab("forecast")}>Forecast</button>
              <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>Audit trail</button>
            </div>
            {tab === "recommend" && <Recommendations recs={recs} onAct={onAct} />}
            {tab === "forecast" && <Forecast />}
            {tab === "audit" && <Audit actions={actions} />}
          </div>
        </div>
      </div>

      {incident && (
        <Modal title="Incident detail" onClose={() => setIncident(null)}>
          <IncidentDetail data={incident} />
        </Modal>
      )}
      {cluster && (
        <Modal title={`Developing event · ${cluster.district}`} onClose={() => setCluster(null)}>
          <ClusterDetail cluster={cluster} onSelectIncident={openIncident} />
        </Modal>
      )}
      {kpiMetric && (
        <KpiModal metric={kpiMetric} data={breakdowns}
          onClose={() => setKpiMetric(null)}
          onIncident={(id) => { setKpiMetric(null); openIncident(id); }} />
      )}
    </div>
  );
}
