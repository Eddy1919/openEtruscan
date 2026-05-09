#!/usr/bin/env bash
# ByT5 v5 — trained on the V2 corpus dump (canonical_clean, cleaned
# via normalize_inscriptions.py + merge_larth_metadata.py).
#
# Changes from v4:
#   1. corpus:  etruscan-prod-rawtext-v1.jsonl → etruscan-prod-rawtext-v2.jsonl
#   2. adapter: byt5-lacunae-v4 → byt5-lacunae-v5
#   3. epochs:  12 → 15 (the v4 curve was still descending at epoch 12)
#
# The underlying training script (train_byt5_v3.py) is unchanged — the
# gains come entirely from cleaner data (has_latin_orthography guard,
# ț→t mojibake fix, and the broader canonical_clean column).
#
# Expected wall time: ~70-80 min train + 5 min provisioning. Cost:
# ~$0.50 on T4. Output: gs://openetruscan-rosetta/adapters/byt5-lacunae-v5/
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
ADAPTER_TAG="${ADAPTER_TAG:-byt5-lacunae-v5}"
CORPUS_NAME="${CORPUS_NAME:-etruscan-prod-rawtext-v2.jsonl}"
EPOCHS="${EPOCHS:-15}"
ACCUM="${ACCUM:-32}"
LR="${LR:-5e-5}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="byt5-lacunae-v5-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_TRAIN_PY="${SCRIPT_DIR}/train_byt5_v3.py"
GCS_CODE_URI="gs://${BUCKET}/code/train_byt5_v3.py"

echo "Uploading training script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_TRAIN_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_byt5_v5_config.yaml <<YAML
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
            --base_model=google/byt5-small \\
            --epochs=${EPOCHS} \\
            --batch_size=2 \\
            --accumulation_steps=${ACCUM} \\
            --learning_rate=${LR} \\
            --warmup_ratio=0.1 \\
            --weight_decay=0.01 \\
            --max_grad_norm=1.0
YAML

echo "Submitting ${JOB_NAME} (epochs=${EPOCHS}, accum=${ACCUM}, effective batch=$((2*ACCUM)), lr=${LR})"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_byt5_v5_config.yaml

echo
echo "Job submitted. Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName:${JOB_NAME}'"
