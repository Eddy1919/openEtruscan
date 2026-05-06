#!/usr/bin/env bash
# Submit the Etruscan LoRA fine-tune as a Vertex AI custom training job.
#
# Prerequisites (run by Claude on 2026-05-04):
#   * Bucket: gs://openetruscan-rosetta (us-central1)
#   * Corpus: gs://openetruscan-rosetta/corpus/etruscan-cie-v1.jsonl
#   * Code:   gs://openetruscan-rosetta/code/train_etruscan_lora.py (uploaded by this script)
#
# This script is idempotent w.r.t. the upload; the submitted job has a
# timestamped display name so re-runs don't collide.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
ADAPTER_TAG="${ADAPTER_TAG:-etr-lora-v2}"
CORPUS_NAME="${CORPUS_NAME:-etruscan-prod-v2.jsonl}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="etruscan-lora-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_TRAIN_PY="${SCRIPT_DIR}/train_etruscan_lora.py"
GCS_CODE_URI="gs://${BUCKET}/code/train_etruscan_lora.py"

echo "Uploading training script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_TRAIN_PY}" "${GCS_CODE_URI}"

# Vertex AI custom-job config. NVIDIA_TESLA_T4 on n1-standard-8 is the
# cheapest GPU SKU sufficient for LoRA on this corpus size (~$0.35/hr,
# whole job <30 min). g2-standard-8 + L4 is 2x faster but 2x the cost;
# stick with T4 unless we need to iterate fast.
cat > /tmp/vertex_config.yaml <<YAML
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
        - name: TRANSFORMERS_VERBOSITY
          value: info
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
            --epochs=5 \\
            --batch_size=16 \\
            --learning_rate=5e-4
YAML

echo "Submitting job ${JOB_NAME}"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_config.yaml

echo
echo "Job submitted. Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName:${JOB_NAME}'"
echo "  gcloud ai custom-jobs stream-logs <job-id> --region=${REGION}"
