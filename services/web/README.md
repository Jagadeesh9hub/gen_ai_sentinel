# services/web/

Next.js situational-overview dashboard. *(Phase 5 — not yet implemented.)* Deploys to Cloud Run.

Planned screens:
1. **Situational Overview** — district map with live incident pins + anomaly clusters, KPI tiles (active incidents, avg response time, units available), live feed.
2. **Ask** — chat panel; answers render with evidence chips + protocol citations.
3. **Recommendations & Actions** — the HITL queue: recommendation cards with a confidence bar, expandable evidence, Approve / Edit / Deny buttons, and an alert-draft preview modal.
4. **Forecast & Audit** — demand-vs-capacity charts, escalation watchlist, and the immutable audit log.

Talks to `services/api` over REST + Server-Sent Events. Service account: invoke API only.
