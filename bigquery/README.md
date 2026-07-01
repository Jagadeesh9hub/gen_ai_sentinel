# bigquery/

BigQuery schema, curated views, and BigQuery ML models. *(Phases 1–2 — not yet implemented.)*

Planned contents:
- `ddl/` — `CREATE TABLE` for raw tables and governance tables (see `docs/data-model.md`).
- `views/` — `unified_incidents`, `district_hour_metrics`, `event_clusters`, `anomaly_flags`.
- `ml/` — `CREATE MODEL` for `ARIMA_PLUS` demand forecasting and the escalation classifier; scoring queries using `ML.FORECAST` and `ML.EXPLAIN_PREDICT`.
- `scheduled/` — queries refreshed by Cloud Scheduler (forecast + anomaly sweeps).
