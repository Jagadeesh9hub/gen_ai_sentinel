# data-generator/

Synthetic public-safety data generator. *(Phase 1 / 7 — not yet implemented.)* Runs as a Cloud Run Job.

Two modes:
- **`seed`** — generate weeks of realistic historical data (diurnal patterns, per-district profiles, weather correlation, labeled past escalations) and load BigQuery. The training/grounding base.
- **`replay`** — publish the scripted "developing event" to Pub/Sub on a timeline so the live demo unfolds in real time.

Design principle: **realism knobs** (call rate per district, escalation probability, correlation strength) are config, not hardcoded.

Planned contents:
- `scenarios/north-gas-leak.yaml` — the scripted demo scenario (see `docs/demo-script.md`).
- generator modules per signal type (incidents, dispatch, weather, traffic, citizen reports).
