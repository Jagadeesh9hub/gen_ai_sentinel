# infra/

GCP provisioning and CI/CD. *(Phase 0 — not yet implemented.)*

Planned contents:
- `terraform/` (or `setup.sh`) — create the project resources: enable APIs, BigQuery dataset, Pub/Sub topics + BigQuery subscriptions, GCS bucket for protocols, Artifact Registry, service accounts with least-privilege IAM, Secret Manager entries.
- `cloudbuild.yaml` — build the `api` and `web` images, push to Artifact Registry, deploy to Cloud Run.
- `teardown.sh` — tear everything down to control cost after the hackathon.

APIs to enable: Cloud Run, BigQuery, Vertex AI, Pub/Sub, Cloud Functions, Eventarc, Cloud Scheduler, Artifact Registry, Cloud Build, Secret Manager.
