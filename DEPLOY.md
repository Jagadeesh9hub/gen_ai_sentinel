# Deploying SENTINEL to Google Cloud Run

Run these in **Google Cloud Shell**. They build two containers (the FastAPI agent
API and the Next.js dashboard) and deploy both to Cloud Run. For the first deploy
the app is self-contained: data (including the demo "developing event") is
generated inside the API container using DuckDB, and the LLM defaults to the
offline mock. See the end for switching to Gemini and BigQuery.

## 1. Clone the repo into a `sentinel` folder
```bash
git clone https://github.com/Jagadeesh9hub/gen_ai_sentinel.git sentinel
cd sentinel
```

## 2. Point gcloud at your project + region
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud config set run/region us-central1
```

## 3. Enable the required APIs
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

## 4. Deploy the API (builds the root Dockerfile)
```bash
gcloud run deploy sentinel-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi --cpu 1 \
  --min-instances 1 \
  --port 8080
```

## 5. Capture the API URL
```bash
API_URL=$(gcloud run services describe sentinel-api --region us-central1 --format='value(status.url)')
echo "API: $API_URL"
```

## 6. Deploy the dashboard (proxies to the API via API_URL)
```bash
gcloud run deploy sentinel-web \
  --source services/web \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --set-env-vars API_URL=$API_URL \
  --port 8080
```

## 7. Open the dashboard
```bash
gcloud run services describe sentinel-web --region us-central1 --format='value(status.url)'
```
Open that URL in your browser — that's the live SENTINEL dashboard.

---

## Optional: use real Gemini instead of the mock LLM
Store your Google AI Studio key in Secret Manager and point the API at it:
```bash
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create gemini-key --data-file=-
gcloud secrets add-iam-policy-binding gemini-key \
  --member="serviceAccount:$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
gcloud run services update sentinel-api --region us-central1 \
  --update-secrets GEMINI_API_KEY=gemini-key:latest \
  --set-env-vars LLM_PROVIDER=gemini
```
(Or use Vertex AI Gemini with the service account instead of an API key — swap `sentinel/llm.py` `GeminiLLM` to the Vertex client.)

## Redeploy after code changes
```bash
git pull
gcloud run deploy sentinel-api --source . --region us-central1
gcloud run deploy sentinel-web --source services/web --region us-central1 --set-env-vars API_URL=$API_URL
```

## Reset the demo (clear approvals/tickets/alerts)
```bash
curl -X POST "$API_URL/api/admin/reset"
```

---

## Notes & next steps
- **`--min-instances 1`** keeps a single warm instance so the in-container DuckDB
  (and the audit log) stay consistent during a demo. Data regenerates on cold start.
- If your org blocks `--allow-unauthenticated`, deploy privately and grant the web
  service account `roles/run.invoker` on the API (the proxy call is server-side).
- **Toward the full GCP architecture:** move the data layer to **BigQuery**
  (replace `sentinel/db.py`), grounding to **Vertex AI Search**, and forecasting to
  **BigQuery ML** — all behind the existing interfaces. This first deploy proves the
  pipeline end-to-end on Cloud Run.
