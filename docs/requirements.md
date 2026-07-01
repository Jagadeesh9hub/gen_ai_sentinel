# Requirements

This document maps each required capability to its design, and calls out how the three judged pillars (prediction, automation, responsible/explainable AI) are satisfied.

## Functional requirements

### 1. Ingest & analyze structured + unstructured data into a unified view
- **Sources (synthetic):** 911/emergency call logs, dispatch records, weather feed, traffic feed, citizen text reports.
- **Ingestion:** per-type Pub/Sub topics. Structured signals stream into BigQuery via a Pub/Sub→BigQuery subscription; citizen texts pass through a Cloud Function that uses Gemini to extract structured fields.
- **Unified view:** `unified_incidents` joins incidents + dispatch + nearest weather/traffic per incident; `district_hour_metrics` aggregates per district per hour.

### 2. Answer questions in natural language
- Gemini interprets the question, the agent selects parameterized BigQuery queries (and/or NL→SQL), and Gemini phrases the grounded answer.
- Example questions the system must handle:
  - "Which districts have rising incident volume this hour?" → delta vs. prior hours over `district_hour_metrics`.
  - "What's the average response time for medical calls in the north zone today?" → filtered aggregate over `unified_incidents`.
  - "Are any patterns suggesting a developing situation?" → reads `event_clusters` + `anomaly_flags` with a Gemini summary.

### 3. Detect patterns & anomalies
- **Statistical:** rolling z-score per district × type × hour vs. historical baseline → `anomaly_flags`.
- **Spatial-temporal clustering:** group incidents within a radius + time window → `event_clusters` (turns multiple calls into one developing event).
- **Correlation reasoning:** Gemini reads clustered raw texts + weather/traffic context and judges whether they describe the same underlying event, with a rationale.

### 4. Predict outcomes
- **Demand forecast:** BigQuery ML `ARIMA_PLUS` per district/hour with confidence intervals, refreshed on a schedule.
- **Escalation classifier:** BigQuery ML model on historical features (cluster growth rate, type mix, wind, traffic, time-of-day); returns `P(escalation)` plus feature attributions via `ML.EXPLAIN_PREDICT`.
- **Fallback:** if labeled-data lift is weak in the hackathon window, a transparent weighted heuristic + Gemini rationale, documented as a known limitation.

### 5. Generate explainable recommendations
- Each recommendation is a structured object carrying `confidence` (0–1) and an `evidence[]` trail (anomaly, forecast, protocol citation).
- Recommendations cover responder allocation, prioritization, and whether to issue a public alert.

### 6. Automate workflows with human-in-the-loop
- Action tools: `draft_public_alert`, `create_dispatch_ticket`, `escalate_to_supervisor`.
- The agent proposes; the coordinator approves/edits/denies in the UI; only on approval does the API execute the tool and write to the audit log.

## The three judged pillars

| Pillar | Where it lives | Evidence to a judge |
|---|---|---|
| **Prediction** | BQML forecast + escalation classifier | Demand-vs-capacity chart crosses the capacity line *before* the surge; escalation badge appears early |
| **Automation** | ADK action tools + approval API | One approval click creates a real dispatch ticket and an alert draft, logged |
| **Responsible / explainable AI** | Confidence + evidence contract, RAG grounding, HITL gate, audit log | Every card shows *why* and *how sure*; high-stakes actions require a human; the audit log proves accountability |

## Non-functional requirements

- **Near real-time:** ingestion → insight within seconds during replay.
- **Reproducible demo:** scripted scenario + seeded fallback (see [`demo-script.md`](demo-script.md)).
- **Explainability by default:** no recommendation surfaces without confidence + evidence.
- **Least privilege:** one service account per service; secrets in Secret Manager.
- **No PII:** synthetic data only.
- **Cost-bounded:** BQML + Gemini Flash + small Cloud Run instances; teardown script provided.

## Out of scope (hackathon)

- Real integrations with live 911/CAD systems.
- Actually transmitting public alerts to the public (alerts are *drafted*, not sent).
- Authentication/multi-tenant operator accounts beyond a single demo coordinator.
