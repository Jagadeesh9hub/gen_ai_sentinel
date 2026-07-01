# rag/

Retrieval-augmented grounding over the city's response protocols. *(Phase 3 — not yet implemented.)*

Planned contents:
- `protocols/` — the response-protocol corpus (markdown/PDF): e.g. Hazmat Tier-2 SOP, Public Alert Issuance Criteria, Mutual Aid Thresholds, Medical Response Standards.
- `ingest.py` — upload the corpus to GCS and (re)build the Vertex AI Search datastore.

The agent's `search_protocols` tool queries this datastore so every recommendation can cite the specific protocol that justifies it.
