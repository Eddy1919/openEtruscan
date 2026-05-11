#!/usr/bin/env bash
# Set up the weekly Cloud Scheduler cron that fires the `openetruscan-security`
# Cloud Build trigger on Mondays at 07:00 UTC.
#
# Why a script and not just docs: this involves four IAM bindings + one
# service account + one scheduler job, and three of the bindings have
# non-obvious requirements (Scheduler service-agent token-creator on the
# caller SA; caller SA needs serviceAccountUser on the *trigger's* SA).
# Encoding the recipe in a re-runnable script means we don't lose the
# institutional memory of "why does this fail with code=7".
#
# Idempotent: every step uses create-or-skip / add-policy-binding. Safe
# to re-run after partial failures.
#
# Manual fire (for testing or one-off scans):
#   gcloud scheduler jobs run openetruscan-weekly-security \
#     --location=europe-west6 --project=long-facet-427508-j2
#
# Disable temporarily:
#   gcloud scheduler jobs pause openetruscan-weekly-security ...
#   gcloud scheduler jobs resume openetruscan-weekly-security ...
#
# Delete (full teardown):
#   gcloud scheduler jobs delete openetruscan-weekly-security \
#     --location=europe-west6 --project=long-facet-427508-j2
#   gcloud iam service-accounts delete \
#     cb-trigger-runner@long-facet-427508-j2.iam.gserviceaccount.com \
#     --project=long-facet-427508-j2

set -euo pipefail

PROJECT="${PROJECT:-long-facet-427508-j2}"
LOCATION="${LOCATION:-europe-west6}"
SA_NAME="${SA_NAME:-cb-trigger-runner}"
JOB_NAME="${JOB_NAME:-openetruscan-weekly-security}"
TRIGGER_NAME="${TRIGGER_NAME:-openetruscan-security}"
SCHEDULE="${SCHEDULE:-0 7 * * 1}"  # Mondays 07:00 UTC
TIME_ZONE="${TIME_ZONE:-Etc/UTC}"

SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SCHEDULER_AGENT="service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"

echo "== Resolving the openetruscan-security trigger id"
TRIGGER_ID="$(gcloud beta builds triggers describe "$TRIGGER_NAME" \
  --project="$PROJECT" --region=global --format='value(id)')"
echo "   trigger: $TRIGGER_NAME (id=$TRIGGER_ID)"

echo "== Resolving the SA the trigger runs as (we need to grant impersonation on it)"
TRIGGER_SA="$(gcloud beta builds triggers describe "$TRIGGER_NAME" \
  --project="$PROJECT" --region=global --format='value(serviceAccount)')"
# Some triggers store the SA as a full resource path; reduce to email.
TRIGGER_SA_EMAIL="${TRIGGER_SA##*/}"
if [[ -z "$TRIGGER_SA_EMAIL" || "$TRIGGER_SA_EMAIL" == "None" ]]; then
  echo "   trigger has no explicit SA — uses default Cloud Build SA (no extra binding needed)"
  TRIGGER_SA_EMAIL=""
else
  echo "   trigger runs as: $TRIGGER_SA_EMAIL"
fi

echo "== Step 1/5: create the caller service account (idempotent)"
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA_NAME" \
    --project="$PROJECT" \
    --display-name="Cloud Build trigger runner (Scheduler)" \
    --description="Used by Cloud Scheduler weekly-security cron to invoke the $TRIGGER_NAME build trigger"
else
  echo "   SA $SA_EMAIL already exists"
fi

echo "== Step 2/5: grant Cloud Build trigger-run permissions to the caller SA"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudbuild.builds.builder" \
  --condition=None \
  --quiet >/dev/null
# builds.editor is broader and includes some perms not in builds.builder;
# both are needed in practice for the run-trigger API path.
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudbuild.builds.editor" \
  --condition=None \
  --quiet >/dev/null
echo "   granted: cloudbuild.builds.{builder,editor}"

echo "== Step 3/5: ensure Cloud Scheduler service identity exists, grant token-creator on caller SA"
gcloud beta services identity create \
  --service=cloudscheduler.googleapis.com \
  --project="$PROJECT" >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --project="$PROJECT" \
  --member="serviceAccount:${SCHEDULER_AGENT}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --quiet >/dev/null
echo "   granted: ${SCHEDULER_AGENT} → roles/iam.serviceAccountTokenCreator on ${SA_EMAIL}"

echo "== Step 4/5: caller SA needs serviceAccountUser on the trigger's SA (if any)"
if [[ -n "$TRIGGER_SA_EMAIL" ]]; then
  gcloud iam service-accounts add-iam-policy-binding "$TRIGGER_SA_EMAIL" \
    --project="$PROJECT" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser" \
    --quiet >/dev/null
  echo "   granted: ${SA_EMAIL} → roles/iam.serviceAccountUser on ${TRIGGER_SA_EMAIL}"
else
  echo "   skipped (trigger uses default Cloud Build SA)"
fi

echo "== Step 5/5: create the scheduler job"
URI="https://cloudbuild.googleapis.com/v1/projects/${PROJECT}/triggers/${TRIGGER_ID}:run"
BODY='{"branchName":"main"}'
if gcloud scheduler jobs describe "$JOB_NAME" \
    --location="$LOCATION" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB_NAME" \
    --project="$PROJECT" \
    --location="$LOCATION" \
    --schedule="$SCHEDULE" \
    --time-zone="$TIME_ZONE" \
    --uri="$URI" \
    --http-method=POST \
    --update-headers="Content-Type=application/json" \
    --message-body="$BODY" \
    --oauth-service-account-email="$SA_EMAIL" >/dev/null
  echo "   updated existing job $JOB_NAME"
else
  gcloud scheduler jobs create http "$JOB_NAME" \
    --project="$PROJECT" \
    --location="$LOCATION" \
    --schedule="$SCHEDULE" \
    --time-zone="$TIME_ZONE" \
    --uri="$URI" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body="$BODY" \
    --oauth-service-account-email="$SA_EMAIL" \
    --description="Weekly Mon 07:00Z run of cloudbuild/security.yaml (Gitleaks). Set up by scripts/ops/setup_weekly_security_cron.sh."
  echo "   created $JOB_NAME"
fi

echo
echo "Done. Verify with:"
echo "  gcloud scheduler jobs run $JOB_NAME --location=$LOCATION --project=$PROJECT"
echo "  # then within ~30s:"
echo "  gcloud builds list --project=$PROJECT --filter='substitutions.TRIGGER_NAME=$TRIGGER_NAME' --limit=2"
