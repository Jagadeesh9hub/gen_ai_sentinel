"""Local validation for SENTINEL Phase 2 (prediction & detection).

Runs the anomaly, clustering, escalation, and forecast modules against the local
DuckDB and prints results — proving the predictive layer works before any LLM,
API, or cloud is involved.

    python scripts/validate_phase2.py
"""
from __future__ import annotations

from sentinel import anomaly, clustering, escalation, forecast
from sentinel.db import Database


def section(title: str):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def main():
    db = Database(read_only=True)

    section("Anomaly detection — latest hour vs 7-day baseline")
    adf = anomaly.current_anomalies(db)
    print(adf.to_string(index=False))

    section("Spatial-temporal clustering — developing events")
    clusters = clustering.detect_clusters(db, window_hours=6)
    if not clusters:
        print("  (no clusters detected in the recent window)")
    for c in clusters:
        print(f"  cluster #{c['cluster_id']}: {c['size']} events "
              f"({c['incident_count']} incidents + {c['citizen_count']} citizen) "
              f"in {c['district']}  types={c['types']}")
        print(f"     centroid=({c['centroid_lat']}, {c['centroid_lng']})  "
              f"{c['first_ts']} -> {c['last_ts']}")

    section("Escalation classifier — train + evaluate")
    model = escalation.train(db)
    print(f"  test ROC-AUC: {model.auc:.3f}")
    print("  top feature attributions (|coefficient|):")
    for feat, coef in model.coefs[:6]:
        print(f"     {feat:22s} {coef:+.3f}")
    # Score the detected developing event, if any.
    if clusters:
        top = clusters[0]
        dom = top["dominant_type"] or "medical"
        p = model.score(dom, priority=1, wind_mph=28, congestion_index=0.5)
        print(f"  P(escalation) for top cluster ({dom}, pri1, wind28): {p:.2f}")

    section("Demand forecast — next 6 hours (rows exceeding capacity)")
    fc = forecast.forecast(db, horizon=6)
    breaches = [f for f in fc if f["exceeds"]]
    print(f"  {len(fc)} forecast points; {len(breaches)} exceed capacity")
    for f in sorted(fc, key=lambda x: -x["predicted"])[:6]:
        flag = "  <-- EXCEEDS CAPACITY" if f["exceeds"] else ""
        print(f"     {f['district']:8s} {f['ts'][:16]}  pred={f['predicted']:.1f} "
              f"(cap {f['capacity']}, trend x{f['trend']}){flag}")

    db.close()
    print("\nPhase 2 validation complete.\n")


if __name__ == "__main__":
    main()
