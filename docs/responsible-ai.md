# Responsible & explainable AI

Public-safety decisions are high-stakes. SENTINEL is designed so the AI **accelerates** human judgment without replacing it, and so every machine-made suggestion is inspectable.

## Principles in the design

| Principle | How it is enforced |
|---|---|
| **Human-in-the-loop on high-stakes actions** | Public alerts and dispatch tickets are *drafted/proposed*, never auto-sent. Execution requires a deliberate approval click. |
| **Confidence on every recommendation** | Each recommendation carries a 0–1 confidence score, rendered as a bar in the UI — not buried in logs. |
| **Evidence trail** | Each recommendation lists the anomaly, forecast, and protocol citation it rests on, each linking back to its source. |
| **Protocol grounding** | Recommendations cite the city's own SOPs retrieved via RAG, so the AI defers to policy rather than improvising. |
| **Immutable audit trail** | `audit_log` records who approved what, when, with a snapshot of the evidence at decision time. |
| **PII-free data** | All data is synthetic; no real personal information is ingested or stored. |
| **Alert-text guardrails** | Drafted alert copy is template-constrained and passes through Gemini safety settings before a human reviews it. |

## Confidence — how it is derived

Confidence is a transparent composite, not a black box:
- model probability (escalation classifier `P(escalation)`),
- signal strength (anomaly z-score magnitude),
- forecast margin (predicted demand vs. available capacity),
- protocol match quality (RAG retrieval score).

The composition is documented and shown in the evidence breakdown so a coordinator can see *which* factor drove the score.

## Known limitations (model card)

- **Synthetic data:** patterns reflect the generator's assumptions, not a specific real city. Forecasts and escalation scores should be re-validated on real data before any operational use.
- **Escalation classifier:** trained on a limited synthetic history; where signal is weak it falls back to a transparent weighted heuristic plus a Gemini rationale. This fallback is labeled as such in the evidence trail.
- **Geocoding/enrichment of citizen texts:** approximate; low-confidence extractions are flagged rather than trusted silently.
- **Not a system of record:** SENTINEL recommends and drafts; the authoritative CAD/dispatch system and a human coordinator remain in control.

## Bias & fairness considerations

- Resource recommendations are driven by incident signals and protocol thresholds, not demographic attributes (which are not collected).
- District baselines are normalized so a historically busier district does not perpetually suppress anomaly detection in quieter ones.
- The audit log enables after-action review of whether recommendations were equitable across districts.

## Failure modes & safeguards

- **Stream outage:** UI falls back to the last seeded snapshot; staleness is shown, not hidden.
- **Model unavailable:** read tools degrade to raw BigQuery aggregates; recommendations are suppressed rather than guessed.
- **Over-trust risk:** the approval step, confidence bar, and evidence trail are designed to keep the human evaluating, not rubber-stamping.
