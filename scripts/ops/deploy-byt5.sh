#!/usr/bin/env bash
# Deploy the ByT5 lacuna restorer to Cloud Run and wire the api to it.
#
# NOTE: the "run on the api VM" wiring steps printed at the end predate the
# retirement of the self-hosted API stack (historical note in
# docs/ARCHITECTURE.md) and are kept as a record of that deployment.
#
# Cost: ~€0–3/mo. min-instances=0 means cold-start on first call (~10 s on CPU)
# but zero idle cost. The API container's RAM drops by ~700 MB once we stop
# loading torch in-process, which leaves headroom for the rerank model.
#
# Prereqs: gcloud authed against your-gcp-project-id; the AR repo `openetruscan`
# already exists (created by the WIF setup runbook).

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-gcp-project-id}"
REGION="${REGION:-europe-west4}"
SERVICE_NAME="${SERVICE_NAME:-openetruscan-byt5}"
SOURCE_DIR="${SOURCE_DIR:-services/byt5-restorer}"

# The service refuses to start without an explicit MODEL_URI (no silent
# fallback to a base checkpoint) — so the deploy demands it up front
# instead of shipping a revision that crashloops.
if [[ -z "${MODEL_URI:-}" ]]; then
  echo "error: MODEL_URI is required (the adapter the service advertises," >&2
  echo "e.g. a byt5-lacunae checkpoint path). Set MODEL_URI and re-run." >&2
  exit 1
fi

echo "==> Deploying ${SERVICE_NAME} to Cloud Run (${REGION})"
gcloud run deploy "${SERVICE_NAME}" \
  --source "${SOURCE_DIR}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --min-instances 0 \
  --max-instances 2 \
  --cpu 1 \
  --memory 1Gi \
  --timeout 60s \
  --no-allow-unauthenticated \
  --set-env-vars "MODEL_VERSION=byt5-lacunae-v1,MODEL_URI=${MODEL_URI}"

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format='value(status.url)')

echo
echo "==> Service deployed at:"
echo "    ${URL}"
echo
echo "==> Next steps:"
echo "    1. Point the API deployment at it: set BYT5_SERVICE_URL=${URL}"
echo "       in the environment of wherever the FastAPI app runs."
echo "    2. Verify provenance: curl -s ${URL}/health   # reports model_uri"
echo "    (The old 'run on the api VM' wiring predates the self-hosted"
echo "    stack's retirement — see docs/ARCHITECTURE.md for that history.)"
echo
echo "==> If the api uses Workload Identity, also bind it to the byt5 invoker role:"
echo "    gcloud run services add-iam-policy-binding ${SERVICE_NAME} \\"
echo "      --region=${REGION} --project=${PROJECT_ID} \\"
echo "      --member=\"serviceAccount:openetruscan-vm@${PROJECT_ID}.iam.gserviceaccount.com\" \\"
echo "      --role=roles/run.invoker"
