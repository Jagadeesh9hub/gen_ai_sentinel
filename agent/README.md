# agent/

The ADK (Agent Development Kit) agent definition and its tools. *(Phase 4 — not yet implemented.)* Imported by `services/api`.

Planned contents:
- `agent.py` — the coordinator agent, system instructions, Gemini model config.
- `tools/` — one module per tool:
  - **Read:** `query_bigquery`, `search_protocols`, `forecast_demand`, `detect_anomalies`, `generate_recommendation`.
  - **Action (HITL-gated):** `draft_public_alert`, `create_dispatch_ticket`, `escalate_to_supervisor` — these emit a *proposed action*; they do not execute until a human approves via the API.
- `schemas.py` — the structured recommendation/evidence contract (see `ARCHITECTURE.md`).

Key rule: action tools never self-execute. The agent proposes; a human disposes.
