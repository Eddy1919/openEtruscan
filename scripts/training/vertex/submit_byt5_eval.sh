#!/usr/bin/env bash
# Submit ByT5 v4-vs-v5 evaluation job to Vertex AI.
#
# Runs on the same pytorch-gpu image with the same pinned peft/transformers
# versions used during training, so LoRA weights load correctly.
#
# Output: gs://openetruscan-rosetta/eval/byt5_v4_v5_results.json
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="byt5-eval-v4v5-${TIMESTAMP}"

cat > /tmp/vertex_byt5_eval_config.yaml <<YAML
workerPoolSpecs:
  - machineSpec:
      machineType: n1-standard-4
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
          gcloud storage cp gs://${BUCKET}/code/eval_byt5_v4_v5.py /tmp/eval.py
          python -u /tmp/eval.py \\
            --test_data=/gcs/${BUCKET}/eval/byt5_eval_100.jsonl \\
            --v4_adapter=/gcs/${BUCKET}/adapters/byt5-lacunae-v4 \\
            --v5_adapter=/gcs/${BUCKET}/adapters/byt5-lacunae-v5 \\
            --output=/gcs/${BUCKET}/eval/byt5_v4_v5_results.json
YAML

echo "Submitting ${JOB_NAME}"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_byt5_eval_config.yaml

echo
echo "Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName~${JOB_NAME}'"
