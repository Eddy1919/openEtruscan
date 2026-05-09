#!/usr/bin/env bash
# etr-lora-v4 — retrained on the polished V3 corpus (canonical_clean,
# after normalize_inscriptions.py removed Cyrillic/Latin-Ext-B mirror-glyph
# corruption, unified sibilant variants σ/ś/š/ς → SAN, and regenerated
# Old Italic glyphs consistently).
#
# Changes from v3:
#   1. corpus:  etruscan-prod-v2.jsonl → etruscan-prod-rawtext-v3.jsonl
#   2. adapter: etr-lora-v3 → etr-lora-v4
#   3. epochs:  5 → 5 (unchanged; v3 converged in 5)
#
# The training script (train_etruscan_lora.py) is unchanged — gains come
# entirely from cleaner data.
#
# Expected wall time: ~30-60 min on T4, ~$0.40.
# Output: gs://openetruscan-rosetta/adapters/etr-lora-v4/
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
ADAPTER_TAG="${ADAPTER_TAG:-etr-lora-v4}"
CORPUS_NAME="${CORPUS_NAME:-etruscan-prod-rawtext-v3.jsonl}"
EPOCHS="${EPOCHS:-5}"
LR="${LR:-5e-4}"
BATCH="${BATCH:-16}"
MAX_LEN="${MAX_LEN:-64}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="etr-lora-v4-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_TRAIN_PY="${SCRIPT_DIR}/train_etruscan_lora.py"
GCS_CODE_URI="gs://${BUCKET}/code/train_etruscan_lora.py"

echo "Uploading training script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_TRAIN_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_etr_lora_v4_config.yaml <<YAML
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
          gcloud storage cp ${GCS_CODE_URI} /tmp/train.py
          python -u /tmp/train.py \\
            --corpus_path=/gcs/${BUCKET}/corpus/${CORPUS_NAME} \\
            --output_dir=/gcs/${BUCKET}/adapters/${ADAPTER_TAG} \\
            --base_model=xlm-roberta-base \\
            --epochs=${EPOCHS} \\
            --batch_size=${BATCH} \\
            --learning_rate=${LR} \\
            --max_length=${MAX_LEN} \\
            --lora_r=8 \\
            --lora_alpha=16 \\
            --lora_dropout=0.1
YAML

echo "Submitting ${JOB_NAME} (epochs=${EPOCHS}, batch=${BATCH}, lr=${LR})"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_etr_lora_v4_config.yaml

echo
echo "Job submitted. Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName~${JOB_NAME}'"
