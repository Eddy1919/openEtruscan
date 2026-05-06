#!/usr/bin/env bash
# Submit the Etruscan vocabulary embedding job.
#
# Reads the prod inscriptions corpus already in GCS, applies the same
# divider normalisation the LoRA training used, embeds every unique
# Etruscan token through XLM-R-base + the etr-lora-v3 adapter.
#
# Output: gs://${BUCKET}/embeddings/etr-xlmr-lora-v3.jsonl
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
ADAPTER_TAG="${ADAPTER_TAG:-etr-lora-v3}"
CORPUS_NAME="${CORPUS_NAME:-etruscan-prod-v2.jsonl}"
OUTPUT_NAME="${OUTPUT_NAME:-etr-xlmr-lora-v3.jsonl}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="xlmr-embed-ett-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PY="${SCRIPT_DIR}/embed_etruscan.py"
GCS_CODE_URI="gs://${BUCKET}/code/embed_etruscan.py"

echo "Uploading embed script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_etr_embed_config.yaml <<YAML
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
          gcloud storage cp ${GCS_CODE_URI} /tmp/embed_etruscan.py
          python -u /tmp/embed_etruscan.py \\
            --corpus_path=/gcs/${BUCKET}/corpus/${CORPUS_NAME} \\
            --adapter_path=/gcs/${BUCKET}/adapters/${ADAPTER_TAG} \\
            --output_path=/gcs/${BUCKET}/embeddings/${OUTPUT_NAME}
YAML

echo "Submitting ${JOB_NAME}"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_etr_embed_config.yaml

echo
echo "Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName:${JOB_NAME}'"
