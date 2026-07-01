# 🛡️ SENTINEL — Public Safety Decision Intelligence Platform

> **Situational Event iNTELligence.** SENTINEL fuses fragmented 911, dispatch, weather, traffic, and citizen-report signals into a single live picture, **predicts** where demand and escalation are heading, and **acts** — drafting alerts, opening dispatch tickets, escalating to supervisors — with a confidence score, an evidence trail, and a human approving every high-stakes move.

Built for the GenAI hackathon on **Google Cloud** (Gemini · BigQuery · Vertex AI Search · Agent Development Kit · Cloud Run).

> **Status:** 📐 Design & planning. This repository currently contains the architecture and requirements design. Implementation follows the phased [roadmap](docs/roadmap.md).

---

## The problem

A city emergency operations coordinator monitors incoming signals from many sources — 911/emergency call logs, dispatch records, weather feeds, traffic conditions, and citizen reports — but the data arrives **fragmented across systems and faster than any human can synthesize**. The coordinator must decide, in near real time:

- Where to allocate limited responders
- Which incidents are escalating
- When to issue public alerts

Today this depends on manual cross-referencing and gut instinct under time pressure. SENTINEL turns that fragmented stream into faster, better-informed, **explainable** decisions.

---

## What it does (the six capabilities)

| # | Capability | How SENTINEL delivers it |
|---|------------|--------------------------|
| 1 | **Unify** structured + unstructured data | Pub/Sub → BigQuery; citizen texts enriched by Gemini into a single `unified_incidents` view |
| 2 | **Answer** in natural language | Gemini + RAG over the city's own protocols, grounded in live BigQuery data |
| 3 | **Detect** patterns & anomalies | Statistical baselines + spatial-temporal clustering + Gemini correlation → "one developing event," not five unrelated calls |
| 4 | **Predict** outcomes | BigQuery ML `ARIMA_PLUS` demand forecast + an escalation classifier with feature attributions |
| 5 | **Recommend**, explainably | Every recommendation carries a **confidence score** and an **evidence trail** citing the protocol that justifies it |
| 6 | **Automate** with a human in the loop | The agent *proposes* actions (alert draft, dispatch ticket, supervisor escalation); a human approves before anything executes |

The three judged pillars — **prediction**, **automation**, and **responsible/explainable AI** — are first-class, not afterthoughts. See [`docs/requirements.md`](docs/requirements.md) for the full mapping.

---

## Architecture at a glance

```
SOURCES (synthetic)  →  Pub/Sub  →  BigQuery (warehouse + BQML)
                                         │
        Vertex AI Search (RAG) ──────────┤
                                         ▼
                 ADK Agent (Gemini)  →  FastAPI (Cloud Run)  →  Next.js dashboard (Cloud Run)
                                         │
                          Audit log · dispatch tickets · alert drafts (BigQuery)
```

Full diagram, service mapping, and data flow: [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Repository layout

```
sentinel/
├── docs/                 # requirements, demo script, data model, responsible AI, roadmap
├── infra/                # GCP setup (Terraform / gcloud), Cloud Build CI/CD
├── data-generator/       # synthetic seed + scripted "replay" engine
├── bigquery/             # schema DDL, curated views, BQML model SQL
├── rag/                  # response-protocol corpus + Vertex AI Search ingestion
├── agent/                # ADK agent definition + tools (shared library)
├── services/
│   ├── api/              # FastAPI service hosting the agent  → Cloud Run
│   └── web/              # Next.js situational-overview dashboard → Cloud Run
└── functions/            # Cloud Functions: citizen-text enrichment, event triggers
```

---

## The demo in 4 minutes

A scripted "developing event" (a North-District gas-leak cluster) replays live: SENTINEL **detects** the cluster, **forecasts** demand exceeding capacity, **recommends** pre-positioning + a public alert + supervisor escalation — each with confidence and evidence — and the coordinator **approves**, triggering a dispatch ticket and an alert draft. Full walkthrough and fallback plan: [`docs/demo-script.md`](docs/demo-script.md).

---

## Technology

| Layer | Choice |
|-------|--------|
| Reasoning / NL | **Gemini 2.5 Pro / Flash** via Vertex AI |
| Data warehouse | **BigQuery** (+ BigQuery ML for forecasting & escalation) |
| Grounding / RAG | **Vertex AI Search** over protocol docs in Cloud Storage |
| Agent orchestration | **Agent Development Kit (ADK)**, Python |
| Ingestion / events | **Pub/Sub**, **Cloud Functions**, **Eventarc**, **Cloud Scheduler** |
| Serving | **Cloud Run** (API + web), **Cloud Run Jobs** (data generator) |
| Frontend | **Next.js** (React) |
| CI/CD | **Cloud Build** + **Artifact Registry**, triggered from GitHub |

---

## Build roadmap

A demo-first, phased plan (something showable at the end of each phase):
**0** Scaffold & deploy pipeline → **1** Data → **2** Predict/detect → **3** RAG → **4** Agent + API → **5** Dashboard → **6** Automate + audit → **7** Replay + polish.
Details: [`docs/roadmap.md`](docs/roadmap.md).

---

## Prerequisites (for implementation phases)

- A **Google Cloud project** with billing/credits and these APIs enabled: Cloud Run, BigQuery, Vertex AI, Pub/Sub, Cloud Functions, Eventarc, Cloud Scheduler, Artifact Registry, Cloud Build, Secret Manager.
- Local tooling: **Python 3.11+**, **Node.js 20+**, **gcloud CLI**, **git**.

> Local check at design time: `git` ✅, `node` ✅. **Python** and **gcloud** still need to be installed before Phase 0.

---

## Responsible AI

Human-in-the-loop on every high-stakes action, confidence + evidence on every recommendation, protocol grounding via RAG, an immutable audit trail, and PII-free synthetic data. See [`docs/responsible-ai.md`](docs/responsible-ai.md).

---

## License

[MIT](LICENSE)
