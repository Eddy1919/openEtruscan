#!/usr/bin/env bash
# Submit the LaBSE hard-negative contrastive fine-tune to Vertex AI
# (WBS T4.3 Option B — overfitting-guarded last-resort experiment).
#
# NB: This is a scaffold. The training script itself
# (`finetune_labse_hardneg.py` in this directory) raises
# NotImplementedError until the implementation gate is opened —
# see its module docstring.
#
# Estimated wall time when complete: ≤ 15 min.
# Estimated cost: < $0.50 on a T4.
# Project: double-runway-465420-h9 (per the spending/training rule).

set -euo pipefail

PROJECT="${PROJECT:-double-runway-465420-h9}"
REGION="${REGION:-us-central1}"
JOB_NAME="${JOB_NAME:-labse-hardneg-$(date +%Y%m%d-%H%M%S)}"

ANCHORS="${ANCHORS:-gs://openetruscan-rosetta/anchors/attested.jsonl}"
NEGATIVES="${NEGATIVES:-gs://openetruscan-rosetta/anchors/hard_negatives.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-gs://openetruscan-rosetta/adapters/labse-attested-v1}"

echo "== Submitting $JOB_NAME to $PROJECT/$REGION"

gcloud ai custom-jobs create \
  --project="$PROJECT" \
  --region="$REGION" \
  --display-name="$JOB_NAME" \
  --worker-pool-spec="\
machine-type=n1-standard-8,\
accelerator-type=NVIDIA_TESLA_T4,\
accelerator-count=1,\
replica-count=1,\
container-image-uri=us-docker.pkg.dev/vertex-ai/training/pytorch-gpu.2-2.py310:latest,\
local-package-path=scripts/training/vertex,\
script=finetune_labse_hardneg.py,\
arguments=--anchors_path=$ANCHORS --negatives_path=$NEGATIVES --output_dir=$OUTPUT_DIR --lora_r=2 --lr=2e-6 --epochs=3 --batch_size=4 --leave_one_out"
