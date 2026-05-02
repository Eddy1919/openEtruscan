# ByT5 Lacuna Restorer — Cloud Run service
# CPU-only, min-instances=0.  Autoscales to zero between calls.
# Expected cost: ~€0-3/mo at current traffic.
#
# Build:
#   docker build -t byt5-restorer .
#
# Deploy:
#   gcloud run deploy openetruscan-byt5 \
#     --source . \
#     --region europe-west4 \
#     --min-instances 0 \
#     --max-instances 2 \
#     --cpu 1 \
#     --memory 1Gi \
#     --timeout 60s \
#     --set-env-vars MODEL_URI=gs://openetruscan-models/byt5-lacunae/v1 \
#     --no-allow-unauthenticated

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Non-root
RUN groupadd --system svc && useradd --system --gid svc svc
USER svc

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
