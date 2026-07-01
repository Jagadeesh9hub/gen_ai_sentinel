# SENTINEL API — FastAPI + agent. Deploys to Cloud Run.
# Build context = repo root (needs sentinel/, services/, data-generator/, rag/).
FROM python:3.12-slim

WORKDIR /app

# libgomp1 is needed at runtime by scikit-learn / scipy.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY sentinel ./sentinel
COPY services ./services
COPY data-generator ./data-generator
COPY rag ./rag
RUN pip install --no-cache-dir -e ".[gemini]"

# /tmp is always writable on Cloud Run. Data (incl. the demo event) is generated
# at startup so the container is self-contained and needs no external DB yet.
ENV SENTINEL_DUCKDB=/tmp/sentinel.duckdb \
    LLM_PROVIDER=mock \
    PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "python data-generator/generate.py --days 14 --db \"$SENTINEL_DUCKDB\" && exec uvicorn services.api.main:app --host 0.0.0.0 --port \"$PORT\""]
