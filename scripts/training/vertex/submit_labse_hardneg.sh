#!/usr/bin/env bash
# Submit the LaBSE hard-negative contrastive fine-tune to Vertex AI
# (WBS T4.3 Option B — overfitting-guarded last-resort experiment).
#
# Estimated wall time: ≤ 15 min on T4 (17 LOO folds × 3 epochs × ≤8 negatives/anchor).
# Estimated cost: < $0.50.
# Project: double-runway-465420-h9 (per the spending/training rule).

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="${JOB_NAME:-labse-hardneg-${TIMESTAMP}}"

ANCHORS="${ANCHORS:-gs://${BUCKET}/anchors/attested.jsonl}"
NEGATIVES="${NEGATIVES:-gs://${BUCKET}/anchors/hard_negatives.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-gs://${BUCKET}/adapters/labse-attested-v1}"
EPOCHS="${EPOCHS:-3}"
LR="${LR:-2e-6}"
LORA_R="${LORA_R:-2}"
BATCH="${BATCH:-4}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_TRAIN_PY="${SCRIPT_DIR}/finetune_labse_hardneg.py"
GCS_CODE_URI="gs://${BUCKET}/code/finetune_labse_hardneg.py"

echo "Uploading training script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_TRAIN_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_labse_hardneg_config.yaml <<YAML
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
        # Vertex's pytorch-gpu.2-2 image ships torch_xla preinstalled and
        # auto-imports it; without a PJRT device set, it segfaults the
        # process the moment training starts (SIGSEGV at runtime.cc:25).
        # We are pure-CUDA — point torch_xla at CPU so its init succeeds
        # and stays out of the way.
        - name: PJRT_DEVICE
          value: "CPU"
      command:
        - bash
        - -c
        - |
          set -euo pipefail
          # Belt-and-braces: also remove torch_xla so nothing tries to
          # touch the TPU runtime even if some library imports it.
          pip uninstall -y torch_xla 2>/dev/null || true
          gcloud storage cp ${GCS_CODE_URI} /tmp/finetune_labse_hardneg.py
          python -u /tmp/finetune_labse_hardneg.py \\
            --anchors_path=${ANCHORS} \\
            --negatives_path=${NEGATIVES} \\
            --output_dir=${OUTPUT_DIR} \\
            --epochs=${EPOCHS} \\
            --lr=${LR} \\
            --lora_r=${LORA_R} \\
            --batch_size=${BATCH}
YAML

echo "Submitting ${JOB_NAME} (epochs=${EPOCHS}, batch=${BATCH}, lr=${LR}, lora_r=${LORA_R})"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_labse_hardneg_config.yaml

echo
echo "Job submitted. Monitor with:"
echo "  gcloud ai custom-jobs list --project=${PROJECT_ID} --region=${REGION} --limit=3"
