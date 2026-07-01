"""Pluggable LLM layer.

Providers, selected via the LLM_PROVIDER env var:
  - "mock"   : deterministic, offline (default) — the whole app runs with no key
  - "gemini" : real Gemini via a Google AI Studio API key (GEMINI_API_KEY)
  - "vertex" : real Gemini via Vertex AI using the runtime service account (no key)

The real providers degrade gracefully: if a generation call fails (bad model,
quota, API not enabled, transient error), they fall back to the grounded answer
so the app never surfaces an error to the user.
"""
from __future__ import annotations

import os


class MockLLM:
    name = "mock"

    def answer(self, question: str, facts: str) -> str:
        # The Q&A layer already builds grounded, readable facts; return them.
        return facts

    def draft_alert(self, info: dict) -> str:
        return (
            f"PUBLIC SAFETY ALERT — {info['district']} District. "
            f"Authorities are responding to a developing {info['hazard']} near "
            f"{info['location']}. Residents in the area should {info['action']} "
            f"Please avoid the area so responders can work. Updates to follow."
        )

    def ask(self, question: str, context: str):
        return None  # mock has no free-form generation; caller uses keyword routing


_MOCK = MockLLM()


class GeminiLLM:
    def __init__(self, model: str = "gemini-2.0-flash"):
        from google import genai  # lazy import; only when a real provider is used

        provider = os.environ.get("LLM_PROVIDER", "").lower()
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        use_vertex = provider == "vertex" or os.environ.get(
            "GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")

        if use_vertex:
            project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
            location = (os.environ.get("GOOGLE_CLOUD_LOCATION")
                        or os.environ.get("GCP_REGION") or "us-central1")
            self._client = genai.Client(vertexai=True, project=project, location=location)
            self.name = "gemini-vertex"
        elif api_key:
            self._client = genai.Client(api_key=api_key)
            self.name = "gemini-api"
        else:
            raise RuntimeError("No Gemini credentials (set GEMINI_API_KEY or use Vertex)")

        self._model = os.environ.get("GEMINI_MODEL", model)

    def _gen(self, prompt: str) -> str:
        resp = self._client.models.generate_content(model=self._model, contents=prompt)
        return (resp.text or "").strip()

    def answer(self, question: str, facts: str) -> str:
        try:
            return self._gen(
                "You are SENTINEL, a public-safety operations assistant. Answer the "
                "coordinator's question in 2-3 sentences using ONLY the facts provided. "
                "Be precise and calm.\n\n"
                f"Question: {question}\n\nFacts:\n{facts}\n\nAnswer:") or facts
        except Exception as e:
            print(f"[llm] gemini answer failed ({self._model}): {e}", flush=True)
            return facts

    def draft_alert(self, info: dict) -> str:
        try:
            return self._gen(
                "Draft a short public safety alert (plain, calm, no speculation). State "
                "the hazard, area, and protective action, and that updates will follow.\n\n"
                f"Details: {info}\n\nAlert:") or _MOCK.draft_alert(info)
        except Exception as e:
            print(f"[llm] gemini draft_alert failed ({self._model}): {e}", flush=True)
            return _MOCK.draft_alert(info)

    def ask(self, question: str, context: str):
        import json
        import re
        prompt = (
            "You are SENTINEL, a public-safety operations assistant for an emergency coordinator. "
            "Answer the QUESTION using ONLY the CONTEXT (live operational data and protocols). "
            "Be concise and precise (2-4 sentences). If the answer is not in the context, briefly say "
            "you don't have that data. Always propose 3 short, relevant follow-up questions this data "
            "can answer.\n\n"
            f"QUESTION: {question}\n\nCONTEXT:\n{context}\n\n"
            'Respond ONLY as JSON: {"answer": "...", "suggestions": ["...", "...", "..."]}'
        )
        try:
            raw = self._gen(prompt)
            m = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(m.group(0)) if m else {}
            ans = (data.get("answer") or "").strip()
            if not ans:
                return None
            return {"answer": ans, "suggestions": data.get("suggestions", [])}
        except Exception as e:
            print(f"[llm] gemini ask failed ({self._model}): {e}", flush=True)
            return None


def get_llm():
    provider = os.environ.get("LLM_PROVIDER", "mock").lower()
    if provider in ("gemini", "vertex"):
        try:
            return GeminiLLM()
        except Exception as e:  # missing SDK/creds -> stay usable
            print(f"[llm] Gemini init failed ({e}); falling back to mock", flush=True)
            return MockLLM()
    return MockLLM()
