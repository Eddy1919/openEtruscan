#!/usr/bin/env bash
# ByT5 v4 — same training script as v3 (train_byt5_v3.py, which is
# numerically stable) but with two changes that the v3 result curve
# (eval_loss 74 -> 57 -> 47 -> 41 -> 38 across 5 epochs, still
# monotonically decreasing) said were worth doing:
#
#   1. epochs:                5  -> 12   (curve was nowhere near plateau)
#   2. gradient accumulation: 16 -> 32   (effective batch 32 -> 64)
#
# Other hyperparams identical to v3. Adapter goes to a separate tag
# so v3 stays usable until v4 verifies; if v4 wins we promote.
#
# Expected wall time: ~50-60 min train + 5 min provisioning. Cost:
# ~$0.40 on T4. Output: gs://openetruscan-rosetta/adapters/byt5-lacunae-v4/
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
ADAPTER_TAG="${ADAPTER_TAG:-byt5-lacunae-v4}"
CORPUS_NAME="${CORPUS_NAME:-etruscan-prod-rawtext-v1.jsonl}"
EPOCHS="${EPOCHS:-12}"
ACCUM="${ACCUM:-32}"
LR="${LR:-5e-5}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="byt5-lacunae-v4-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_TRAIN_PY="${SCRIPT_DIR}/train_byt5_v3.py"
GCS_CODE_URI="gs://${BUCKET}/code/train_byt5_v3.py"

echo "Uploading training script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_TRAIN_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_byt5_v4_config.yaml <<YAML
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
  --config=/tmp/vertex_byt5_v4_config.yaml

echo
echo "Job submitted. Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName:${JOB_NAME}'"
