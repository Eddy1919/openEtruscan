#!/usr/bin/env bash
# Submit the Latin vocabulary re-embed job.
#
# Reads gs://${BUCKET}/embeddings/labse-v1.jsonl, filters to language=lat,
# embeds each Latin word through XLM-R-base (mean-pool + L2-normalise),
# and writes a new JSONL ready to be ingested as the
# (embedder='xlmr-lora', embedder_revision='v4') partition's Latin half.
#
# Output: gs://${BUCKET}/embeddings/lat-xlmr-lora-v4.jsonl
#
# Cost: ~$0.30 on a single T4 GPU, ~10-15 min wall clock.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
SOURCE_NAME="${SOURCE_NAME:-labse-v1.jsonl}"
OUTPUT_NAME="${OUTPUT_NAME:-lat-xlmr-lora-v4.jsonl}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="lat-xlmr-v4-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PY="${SCRIPT_DIR}/embed_lat_xlmr_v4.py"
GCS_CODE_URI="gs://${BUCKET}/code/embed_lat_xlmr_v4.py"

echo "Uploading embed script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_lat_xlmr_v4_config.yaml <<YAML
workerPoolSpecs:
  - machineSpec:
      machineType: n1-standard-8
      acceleratorType: NVIDIA_TESLA_T4
      acceleratorCount: 1
    replicaCount: 1
    diskSpec:
      bootDiskType: pd-ssd
      bootDiskSizeGb: 100
    containerSpec:
      imageUri: us-docker.pkg.dev/vertex-ai/training/pytorch-gpu.2-2.py310:latest
      env:
        - name: PYTHONUNBUFFERED
          value: "1"
      command:
        - bash
        - -c
        - |
          set -euo pipefail
          gcloud storage cp ${GCS_CODE_URI} /tmp/embed_lat_xlmr_v4.py
          python -u /tmp/embed_lat_xlmr_v4.py \\
            --source_uri=gs://${BUCKET}/embeddings/${SOURCE_NAME} \\
            --output_path=/gcs/${BUCKET}/embeddings/${OUTPUT_NAME}
YAML

echo "Submitting ${JOB_NAME}"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_lat_xlmr_v4_config.yaml

echo
echo "Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName:${JOB_NAME}'"
echo "Output will land at: gs://${BUCKET}/embeddings/${OUTPUT_NAME}"
