#!/usr/bin/env bash
# Deploy the ByT5 lacuna restorer to Cloud Run and wire the api to it.
#
# Cost: ~€0–3/mo. min-instances=0 means cold-start on first call (~10 s on CPU)
# but zero idle cost. The API container's RAM drops by ~700 MB once we stop
# loading torch in-process, which leaves headroom for the rerank model.
#
# Prereqs: gcloud authed against long-facet-427508-j2; the AR repo `openetruscan`
# already exists (created by the WIF setup runbook).

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-long-facet-427508-j2}"
REGION="${REGION:-europe-west4}"
SERVICE_NAME="${SERVICE_NAME:-openetruscan-byt5}"
SOURCE_DIR="${SOURCE_DIR:-services/byt5-restorer}"

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
  --set-env-vars "MODEL_VERSION=byt5-lacunae-v1"

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format='value(status.url)')

echo
echo "==> Service deployed at:"
echo "    ${URL}"
echo
echo "==> Next steps (run on the api VM):"
echo "    1. Add to .env:    BYT5_SERVICE_URL=${URL}"
echo "    2. Restart:        docker compose restart api"
echo "    3. Verify:         curl -s -X POST https://api.openetruscan.com/neural/restore \\"
echo "                            -H 'Authorization: Bearer \$ADMIN_TOKEN' \\"
echo "                            -H 'Content-Type: application/json' \\"
echo "                            -d '{\"text\":\"lar[---]al\",\"top_k\":3}'"
echo
echo "==> If the api uses Workload Identity, also bind it to the byt5 invoker role:"
echo "    gcloud run services add-iam-policy-binding ${SERVICE_NAME} \\"
echo "      --region=${REGION} --project=${PROJECT_ID} \\"
echo "      --member=\"serviceAccount:openetruscan-vm@${PROJECT_ID}.iam.gserviceaccount.com\" \\"
echo "      --role=roles/run.invoker"
