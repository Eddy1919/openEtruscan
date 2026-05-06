#!/usr/bin/env bash
# Submit the Latin + Greek XLM-R embedding job to Vertex AI.
#
# Output: gs://${BUCKET}/embeddings/${OUTPUT_NAME}
# Default: 100k tokens per language → 200k rows total, ~250 MB JSONL.
#
# Sources:
#   * Wikipedia (`wikimedia/wikipedia` 20231101.la and .el) streamed via HF
#     datasets. Greek = MODERN Greek; XLM-R was trained on modern Greek so
#     this is the right matching corpus, with the proxy caveat that ancient
#     Greek lemmas not shared with modern will have weak vectors.
#
# Cost: ~30-50 min on T4 (~$0.30). Mostly Wikipedia stream + tokenisation.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
OUTPUT_NAME="${OUTPUT_NAME:-lat-grc-xlmr-v2.jsonl}"
TOP_N="${TOP_N:-100000}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="xlmr-embed-lat-grc-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PY="${SCRIPT_DIR}/embed_vocab.py"
GCS_CODE_URI="gs://${BUCKET}/code/embed_vocab.py"

echo "Uploading embed script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_embed_config.yaml <<YAML
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
          gcloud storage cp ${GCS_CODE_URI} /tmp/embed_vocab.py
          python -u /tmp/embed_vocab.py \\
            --output_path=/gcs/${BUCKET}/embeddings/${OUTPUT_NAME} \\
            --top_n=${TOP_N}
YAML

echo "Submitting ${JOB_NAME}"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_embed_config.yaml

echo
echo "Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --project=${PROJECT_ID} --filter='displayName:${JOB_NAME}'"
