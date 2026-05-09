#!/usr/bin/env bash
# Submit the ByT5 v3 LoRA fine-tune to Vertex AI.
#
# Replaces v2 (which diverged — see train_byt5_v3.py docstring). The
# corpus dump must already be in GCS:
#   gs://openetruscan-rosetta/corpus/etruscan-prod-rawtext-v1.jsonl
# (uploaded by the bootstrap pass — re-run the extract+upload step from
# /tmp/etruscan-prod-rawtext-v1.jsonl if it has been deleted).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
ADAPTER_TAG="${ADAPTER_TAG:-byt5-lacunae-v3}"
CORPUS_NAME="${CORPUS_NAME:-etruscan-prod-rawtext-v1.jsonl}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="byt5-lacunae-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_TRAIN_PY="${SCRIPT_DIR}/train_byt5_v3.py"
GCS_CODE_URI="gs://${BUCKET}/code/train_byt5_v3.py"

echo "Uploading training script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_TRAIN_PY}" "${GCS_CODE_URI}"

# T4 16 GB is plenty for ByT5-small + LoRA at batch=2/accum=16. bf16
# is supported on T4 (Turing-gen tensor cores). Keeping the same
# machine class as the prior LoRA work for cost predictability.
cat > /tmp/vertex_byt5_v3_config.yaml <<YAML
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
            --epochs=5 \\
            --batch_size=2 \\
            --accumulation_steps=16 \\
            --learning_rate=5e-5 \\
            --warmup_ratio=0.1 \\
            --weight_decay=0.01 \\
            --max_grad_norm=1.0
YAML

echo "Submitting ${JOB_NAME}"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_byt5_v3_config.yaml

echo
echo "Job submitted. Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName:${JOB_NAME}'"
