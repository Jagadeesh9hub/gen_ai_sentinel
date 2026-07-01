"""Exercise the local SENTINEL API end-to-end (no browser needed).

Start the server first:
    uvicorn services.api.main:app --port 8000
Then:
    python scripts/validate_api.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")  # render σ etc. on Windows consoles

BASE = "http://127.0.0.1:8000"


def call(path, data=None):
    url = BASE + path
    if data is not None:
        req = urllib.request.Request(
            url, data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def line(t):
    print("\n" + "-" * 70 + f"\n{t}\n" + "-" * 70)


def main():
    for _ in range(60):
        try:
            h = call("/api/health")
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise SystemExit("API did not come up on :8000")

    line("HEALTH")
    print(h)

    line("OVERVIEW — KPIs")
    ov = call("/api/overview")
    print(json.dumps(ov["kpis"], indent=2))
    print("district status:")
    for d in ov["districts"]:
        flag = "  ANOMALY" if d["is_anomaly"] else ""
        ex = "  EXCEEDS" if d["exceeds"] else ""
        print(f"  {d['district']:8s} now={d['latest_count']:>2} z={d['zscore']:>5} "
              f"next_pred={d['next_pred']} cap={d['capacity']}{flag}{ex}")

    line("RECOMMENDATIONS")
    recs = call("/api/recommendations")["recommendations"]
    for r in recs:
        print(f"  [{r['confidence']:.2f}] {r['title']}  ({r['status']})")
        print(f"         protocol: {r['protocol']}")
        for e in r["evidence"][:3]:
            print(f"         - {e['source']}: {e['detail']}")

    line("ASK")
    for q in ["Which districts have rising incident volume this hour?",
              "What's the average response time for medical calls in the north zone today?",
              "Are any patterns suggesting a developing situation?",
              "What's the demand forecast — will any district exceed capacity?"]:
        a = call("/api/ask", {"question": q})
        print(f"  Q: {q}\n  A: {a['answer']}\n")

    if recs:
        line("HUMAN-IN-THE-LOOP: approve top recommendation")
        top = recs[0]
        print(f"  approving: {top['title']}")
        print("  result:", call(f"/api/recommendations/{top['id']}/approve", {}))
        acts = call("/api/actions")
        print(f"  audit entries: {len(acts['audit'])}, tickets: {len(acts['tickets'])}, "
              f"alerts: {len(acts['alerts'])}")

    print("\nAPI validation complete.\n")


if __name__ == "__main__":
    main()
