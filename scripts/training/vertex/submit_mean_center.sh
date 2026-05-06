#!/usr/bin/env bash
# Submit the mean-centering pass to Vertex AI. CPU-only — pure linear algebra
# over JSONL streams. Runs both lat-grc and ett files in sequence.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-openetruscan-rosetta}"
PCA_REMOVE="${PCA_REMOVE:-0}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
JOB_NAME="embed-mean-center-${TIMESTAMP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PY="${SCRIPT_DIR}/mean_center_embeddings.py"
GCS_CODE_URI="gs://${BUCKET}/code/mean_center_embeddings.py"

echo "Uploading script to ${GCS_CODE_URI}"
gcloud storage cp "${LOCAL_PY}" "${GCS_CODE_URI}"

cat > /tmp/vertex_meancenter_config.yaml <<YAML
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
      # pytorch-gpu image requires an accelerator — attach a cheap T4 even
      # though we're CPU-only; the image bootstraps fastest from cache.
      imageUri: us-docker.pkg.dev/vertex-ai/training/pytorch-gpu.2-2.py310:latest
      env:
        - name: PYTHONUNBUFFERED
          value: "1"
      command:
        - bash
        - -c
        - |
          set -euo pipefail
          gcloud storage cp ${GCS_CODE_URI} /tmp/mean_center.py
          # Process lat-grc (3.5 GB)
          python -u /tmp/mean_center.py \\
            --input_path=/gcs/${BUCKET}/embeddings/lat-grc-xlmr-v3.jsonl \\
            --output_path=/gcs/${BUCKET}/embeddings/lat-grc-xlmr-v3-centered.jsonl \\
            --pca-remove=${PCA_REMOVE}
          # Process etr (158 MB)
          python -u /tmp/mean_center.py \\
            --input_path=/gcs/${BUCKET}/embeddings/etr-xlmr-lora-v3.jsonl \\
            --output_path=/gcs/${BUCKET}/embeddings/etr-xlmr-lora-v3-centered.jsonl \\
            --pca-remove=${PCA_REMOVE}
YAML

echo "Submitting ${JOB_NAME} (PCA_REMOVE=${PCA_REMOVE})"
gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${JOB_NAME}" \
  --config=/tmp/vertex_meancenter_config.yaml

echo
echo "Monitor with:"
echo "  gcloud ai custom-jobs list --region=${REGION} --filter='displayName:${JOB_NAME}'"
