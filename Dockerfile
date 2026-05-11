# ── Stage 1: Builder ────────────────────────────────────────────────────────
# Install build-only dependencies (gcc, libpq-dev) here. They never ship.
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

# Install only the runtime extras needed for the API container.
# neural-inference (onnxruntime) is lightweight; neural (torch) is NOT included.
# telemetry pulls in opentelemetry SDK (~30 MB on disk, no torch/transformers).
RUN pip install --no-cache-dir --prefix=/install \
    ".[server,postgres,prosopography,stats,lod,neural-inference,telemetry]"


# ── Stage 2: Runtime ───────────────────────────────────────────────────────
# Clean image: no gcc, no libpq-dev, no pip cache, no source tree.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Only the compiled .so for libpq is needed at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source (no tests, scripts, frontend) and the alembic
# config so the same image can run `alembic upgrade head` during deploys.
COPY src/ src/
COPY alembic.ini ./

# Ship ONLY the canonical attested-anchors JSONL — not the whole
# research/anchors/ directory. server.py's _load_attested_jsonl() looks
# at /app/research/anchors/attested.jsonl as a fallback path; without
# this COPY the /anchors/attested endpoint returns {"items": [], "count": 0}
# in prod and the frontend ProposeCard can't render its "attested" status
# ticks. The sibling files (hard_negatives.jsonl from offline mining,
# llm_anchors_raw* from the T4.2 LLM extraction, agent_decisions.tsv,
# README.md) are training-time artefacts; they have no runtime consumer
# and stay out of the image to keep the layer small.
COPY research/anchors/attested.jsonl research/anchors/attested.jsonl

# Create non-root user
RUN groupadd --system appuser && useradd --system --gid appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "openetruscan.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
