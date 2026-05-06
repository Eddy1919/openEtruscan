#!/usr/bin/env bash
# Single LaBSE embedding job for lat + grc + ett (combined, no LoRA).
#
# Output: gs://${BUCKET}/embeddings/labse-v1.jsonl
#
# Cost: ~$0.30 on T4 (~30-40 min: vocab extraction + embed 200k+ tokens).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
TOP_N="${TOP_N:-100000}"
OUTPUT_NAME="${OUTPUT_NAME:-labse-v1.jsonl}"
ETR_CORPUS_NAME="${ETR_CORPUS_NAME:-etruscan-prod-v2.jsonl}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="labse-embed-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PY="${SCRIPT_DIR}/embed_labse.py"
GCS_CODE_URI="gs://${BUCKET}/code/embed_labse.py"

echo "Uploading script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_labse_config.yaml <<YAML
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
          gcloud storage cp ${GCS_CODE_URI} /tmp/embed_labse.py
          python -u /tmp/embed_labse.py \\
            --output_path=/gcs/${BUCKET}/embeddings/${OUTPUT_NAME} \\
            --etruscan_corpus_path=/gcs/${BUCKET}/corpus/${ETR_CORPUS_NAME} \\
            --top_n_per_lang=${TOP_N} \\
            --model_name=sentence-transformers/LaBSE
YAML

echo "Submitting ${JOB_NAME}"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_labse_config.yaml

echo
echo "Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName:${JOB_NAME}'"
