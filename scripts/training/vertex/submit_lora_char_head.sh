#!/usr/bin/env bash
# Submit lora_char_head training job to Vertex AI.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"

echo "=== Uploading training script ==="
gcloud storage cp \
  scripts/training/vertex/train_lora_char_head.py \
  gs://${BUCKET}/code/

# ─── Approach B: XLM-R + Character Head ──────────────────────────────
JOB_NAME="lora-char-head-v1-${TIMESTAMP}"
echo ""
echo "=== Submitting ${JOB_NAME} ==="

cat > /tmp/vertex_lora_char_head.yaml <<YAML
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
          gcloud storage cp gs://${BUCKET}/code/train_lora_char_head.py /tmp/train.py
          python -u /tmp/train.py \\
            --corpus_path=/gcs/${BUCKET}/corpus/etruscan-prod-rawtext-v3.jsonl \\
            --adapter_path=/gcs/${BUCKET}/adapters/etr-lora-v4 \\
            --output_dir=/gcs/${BUCKET}/models/lora-char-head-v1 \\
            --freeze_encoder \\
            --epochs=20 \\
            --batch_size=32 \\
            --learning_rate=1e-3 \\
            --max_length=64 \\
            --samples_per_text=3
YAML

gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_lora_char_head.yaml

echo ""
echo "=== Job submitted ==="
echo "Monitor:"
echo "  gcloud ai custom-jobs list --region=${REGION} --limit=5 --format='table(displayName,state,createTime)'"
