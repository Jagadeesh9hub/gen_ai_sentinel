# Build roadmap

A deliberately **demo-first** sequence: something is showable at the end of every phase, and the deploy pipeline is proven before there is anything to lose.

| Phase | Deliverable | Why this order |
|---|---|---|
| **0 · Scaffold** | Repo + GCP project + APIs enabled + a "hello world" service deployed to Cloud Run + Cloud Build trigger | Prove the deploy pipeline first |
| **1 · Data** | BigQuery schema + synthetic `seed` generator → loaded tables + `unified_incidents` view | Everything downstream needs data |
| **2 · Predict / detect** | BQML `ARIMA_PLUS` forecast + escalation model + anomaly views + clustering | The prediction & detection muscle |
| **3 · Grounding** | Protocol corpus in GCS → Vertex AI Search datastore | Needed before recommendations can cite |
| **4 · Agent + API** | ADK agent + tools + FastAPI on Cloud Run; `/ask` works end-to-end | The brain |
| **5 · Dashboard** | Next.js overview + Ask + Recommendations on Cloud Run | Now it's a product |
| **6 · Automate** | HITL approve → execute + audit log | The "agent acts" pillar |
| **7 · Replay + polish** | Scripted scenario, demo script rehearsed, README + demo GIF | Make the 4-minute story bulletproof |

## Time-box guidance

- If time runs short, **phases 0–6 still demo fully on seeded data**; phase 7 is what makes it sing for judges.
- Keep each Cloud Run service tiny (min instances 0, small CPU/mem) to stay within hackathon credits.
- Defer Looker Studio, real traffic/weather APIs, and auth — they are explicitly out of scope.

## Definition of done (per phase)

- **0:** `gcloud run deploy` succeeds and returns a live URL; pushing to `main` redeploys.
- **1:** `SELECT COUNT(*) FROM sentinel.unified_incidents` returns realistic seeded rows.
- **2:** forecast and anomaly queries return non-trivial results on seeded data.
- **3:** `search_protocols("hazmat tier 2")` returns the right SOP passage.
- **4:** `POST /ask` answers the three sample questions with grounded evidence.
- **5:** the overview renders live KPIs + the incident feed; Ask works in the browser.
- **6:** approving a recommendation creates a `dispatch_tickets` row and an `audit_log` entry.
- **7:** a full replay runs the demo script start-to-finish without manual intervention.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Vertex AI / ADK region or quota gaps | Pick a region with Gemini + Vertex AI Search up front; Flash fallback |
| Live replay flakiness in judging | Pre-seeded static fallback + recorded backup video |
| Escalation model has too little signal | Transparent heuristic + Gemini rationale, labeled as fallback |
| Cost overrun | BQML + Flash + scale-to-zero Cloud Run; teardown script |
