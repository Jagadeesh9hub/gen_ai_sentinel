# Demo script — the 4-minute "developing event"

The entire platform is built to make this story land reliably during judging. A scripted scenario (`data-generator/scenarios/north-gas-leak.yaml`) replays to Pub/Sub on a timeline so SENTINEL detects → predicts → recommends → acts on cue.

## Scenario: North-District gas leak

| Time | What streams in | What SENTINEL does | What the judge sees |
|------|-----------------|--------------------|---------------------|
| 0:00 | Baseline trickle across 6 districts | Calm situational overview | Map + KPI tiles, green status |
| 0:30 | 3 citizen texts ("smell of gas", "smoke near 5th & Oak") + 2 nearby medical 911 calls; wind 28 mph | Anomaly + clustering flag **one developing event** | Red cluster pulses on the map; "Possible developing event" banner |
| 1:30 | Volume keeps climbing | Forecast predicts North medical+fire demand exceeding free units in ~40 min; escalation classifier scores 0.82 | Demand-vs-capacity chart spikes above the capacity line; escalation badge |
| 2:30 | Coordinator asks: *"What's happening in the north zone and what should I do?"* | Gemini + RAG answer, grounded in the city's protocol, with citations | Chat answer with protocol citation + evidence chips |
| 3:00 | — | Three recommendations appear, each with confidence + evidence: (1) pre-position 2 units, (2) draft public alert, (3) escalate to fire supervisor | Recommendation cards, expandable to "why" |
| 3:30 | Coordinator clicks **Approve** on the alert + ticket | Dispatch ticket created, alert text drafted (not sent), supervisor notified — all logged | Toast confirmations; alert-draft modal; new audit-log entry |

## Talking points (tie to judged pillars)

- **Prediction:** "Notice the forecast crossed the capacity line *before* the surge actually hit — that's the 40-minute head start."
- **Automation:** "One approval turned a recommendation into a real dispatch ticket and a drafted alert — the agent acted, it didn't just advise."
- **Responsible AI:** "Every card shows its confidence and the evidence behind it, cites the city's own protocol, and the alert was *drafted* — a human stays in the loop for anything public-facing. The audit log records who approved what."

## Reliability / fallback plan

- **Primary:** live replay via `POST /replay/start`.
- **Fallback:** the same scenario is pre-seeded into BigQuery so every screen (overview, forecast, anomalies, recommendations) renders fully from static data even if the live stream hiccups. The Q&A and approval flows work identically against the seeded snapshot.
- **Network-free option:** record a 90-second screen capture of a clean run as a last-resort backup to embed in the submission.

## "What if it's worse?" (judge interaction)

Realism knobs (call rate, escalation probability, correlation strength) are config in the scenario YAML — bump them live to show the forecast and recommendations adapt.
