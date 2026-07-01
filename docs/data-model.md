# Data model (BigQuery)

**Dataset:** `sentinel`

The model has four layers: **raw** (mirror the feeds), **curated** (unified + aggregated), **ML/analytics** (forecast, escalation, anomalies), and **governance** (actions + audit). Schemas below are indicative; final DDL lives in `bigquery/`.

## Raw layer

### `raw_incidents`
| column | type | notes |
|---|---|---|
| incident_id | STRING | PK |
| ts | TIMESTAMP | event time |
| district | STRING | one of 6 districts |
| lat, lng | FLOAT64 | location |
| type | STRING | medical \| fire \| police \| hazmat \| traffic |
| priority | INT64 | 1 (highest) – 3 |
| source | STRING | 911 \| dispatch |
| reported_text | STRING | free text |
| status | STRING | open \| dispatched \| on_scene \| cleared |

### `raw_dispatch`
`dispatch_id, incident_id, unit_id, unit_type, dispatched_ts, on_scene_ts, cleared_ts, district`

### `raw_weather`
`ts, district, temp_f, wind_mph, precip, condition`

### `raw_traffic`
`ts, district, congestion_index (0–1), road_closures`

### `raw_citizen_reports`
`report_id, ts, lat, lng, raw_text, channel`
→ enriched by the Cloud Function into **`citizen_reports_enriched`**: `+ type, severity_est, entities (ARRAY<STRING>), dedup_cluster_id`

## Curated layer (views / scheduled tables)

### `unified_incidents`
One row per incident joined with its dispatch timing and the nearest weather/traffic reading. This is the "unified view" the coordinator queries.
Key derived fields: `response_time_sec = on_scene_ts - dispatched_ts`, `weather_condition`, `congestion_index`.

### `district_hour_metrics`
Per district × hour aggregates: `incident_count, by_type counts, avg_response_time_sec, units_busy, units_available`. Powers Q&A, the overview, and forecasting.

### `event_clusters`
Spatial-temporal clusters of correlated signals: `cluster_id, district, first_ts, last_ts, member_incident_ids (ARRAY), member_count, growth_rate, dominant_type, centroid_lat, centroid_lng, gemini_correlation_summary`.

## ML / analytics layer

### `forecast_volume` (ARIMA_PLUS output)
`district, forecast_ts, predicted_count, prediction_interval_lower, prediction_interval_upper`.

### `escalation_scores`
`cluster_id, scored_ts, p_escalation, top_features (ARRAY<STRUCT<feature STRING, contribution FLOAT64>>)`. Feature contributions feed the evidence trail.

### `anomaly_flags`
`district, type, hour, observed_rate, baseline_rate, zscore, is_anomaly`.

## Governance layer

### `dispatch_tickets`
`ticket_id, created_ts, incident_id|cluster_id, recommended_units, status (proposed|approved|denied|executed), approved_by, approved_ts`.

### `public_alerts`
`alert_id, created_ts, cluster_id, draft_text, severity, channel, status (proposed|approved|denied), approved_by, approved_ts`.

### `audit_log`
`event_id, ts, actor (agent|human), action_type, target_id, confidence, evidence_snapshot (JSON), decision (proposed|approved|denied|edited|executed), notes`.
This table is the accountability backbone — every agent proposal and every human decision is recorded with the evidence as it stood at decision time.

## Lineage summary

```
raw_*  →  unified_incidents / district_hour_metrics  →  forecast_volume / escalation_scores / anomaly_flags / event_clusters
                                                          │
                                          agent reasoning → proposed actions → (human approval) → dispatch_tickets / public_alerts → audit_log
```
