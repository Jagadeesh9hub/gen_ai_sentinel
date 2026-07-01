# services/api/

FastAPI service that hosts the ADK agent and exposes it to the dashboard. *(Phase 4 / 6 — not yet implemented.)* Deploys to Cloud Run.

Planned endpoints:
- `POST /ask` — natural-language question → grounded answer + evidence.
- `GET /overview` — KPIs, district status, live incident feed (Server-Sent Events).
- `GET /forecast?district=` — forecast series + capacity line.
- `GET /anomalies` — current anomaly flags + clusters.
- `GET /recommendations` — pending proposed actions.
- `POST /actions/{id}/approve` · `/deny` · `/edit` — the human-in-the-loop gate; on approval, executes the real tool and writes `audit_log`.
- `POST /replay/start` — kicks off the scripted demo scenario.

Service account: BigQuery + Vertex AI + Pub/Sub publish (least privilege).
