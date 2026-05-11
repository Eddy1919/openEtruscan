# ByT5 Lacuna Restorer — Cloud Run service
# CPU-only, min-instances=0.  Autoscales to zero between calls.
# Expected cost: ~€0-3/mo at current traffic.
#
# Build:
#   docker build -t byt5-restorer .
#
# Deploy (see also services/byt5-restorer README + comment in terraform/main.tf):
#   gcloud run deploy openetruscan-byt5 \
#     --source services/byt5-restorer \
#     --region europe-west4 \
#     --project long-facet-427508-j2 \
#     --allow-unauthenticated \
#     --min-instances 0 \
#     --max-instances 2 \
#     --cpu 1 \
#     --memory 2Gi \
#     --timeout 120s \
#     --build-service-account=projects/.../serviceAccounts/cb-trigger-runner@...

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Point HuggingFace at a writable path. The previous default
    # (~/.cache/huggingface) lived under /home/svc, which `useradd --system`
    # does *not* create — the runtime then crashed with
    # `PermissionError at /home/svc when downloading google/byt5-small`.
    HF_HOME=/app/.hf-cache \
    TRANSFORMERS_OFFLINE=0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the model into the image so cold starts don't have to
# hit HuggingFace. byt5-small is ~300 MB; bakes deterministically.
ARG MODEL_URI=google/byt5-small
RUN mkdir -p ${HF_HOME} && \
    python -c "from transformers import AutoTokenizer, AutoModelForSeq2SeqLM; \
        AutoTokenizer.from_pretrained('${MODEL_URI}'); \
        AutoModelForSeq2SeqLM.from_pretrained('${MODEL_URI}')"

COPY main.py .

# Non-root, but with a real home so HF_HOME-style downloads (if a future
# MODEL_URI bypasses the pre-bake) still have somewhere to land.
RUN groupadd --system svc && useradd --system --gid svc -d /app svc && \
    chown -R svc:svc /app
USER svc

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
