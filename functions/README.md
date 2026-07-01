# functions/

Cloud Functions (2nd gen) for enrichment and event-driven triggers. *(Phases 1 / 6 — not yet implemented.)*

Planned functions:
- **`enrich_citizen_report`** — triggered by the citizen-text Pub/Sub topic; uses Gemini Flash to extract structured fields (type, severity estimate, entities, location) and writes `citizen_reports_enriched` in BigQuery.
- **`on_high_severity_incident`** — Eventarc-triggered; when a high-severity incident lands, asks the agent to evaluate and, if escalation is predicted, creates a proposed action for the coordinator's queue.

Cloud Scheduler additionally drives periodic forecast and anomaly-sweep refreshes.
