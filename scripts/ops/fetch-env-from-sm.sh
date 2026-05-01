#!/bin/bash
# Pull the OpenEtruscan API container's runtime secrets from Google Secret Manager
# into the on-disk .env that docker-compose's `env_file:` consumes.
#
# Designed to run on the production GCE VM, where the attached service account
# (openetruscan-vm@long-facet-427508-j2.iam.gserviceaccount.com) holds
# roles/secretmanager.secretAccessor on the project.
#
# Usage (on VM):
#   sudo /home/edoardo.panichi/openEtruscan/scripts/ops/fetch-env-from-sm.sh
#
# Intended hooks:
#   - Run before `docker compose up -d` in the deploy workflow.
#   - Run on boot (e.g. via cloud-init or a systemd oneshot pointing at this path).
#
# The script never reads the existing .env, so it is the only writer.
# Secret Manager is the source of truth.

set -euo pipefail

PROJECT="${OE_PROJECT:-long-facet-427508-j2}"
ENV_PATH="${OE_ENV_PATH:-/home/edoardo.panichi/openEtruscan/.env}"
ENV_OWNER="${OE_ENV_OWNER:-edoardo.panichi:edoardo.panichi}"

token=$(curl -fsS -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

fetch() {
  # $1 = secret name (e.g. oe-database-url)
  curl -fsS -H "Authorization: Bearer $token" \
    "https://secretmanager.googleapis.com/v1/projects/${PROJECT}/secrets/$1/versions/latest:access" \
    | python3 -c "import sys, json, base64; sys.stdout.write(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode())"
}

DB_URL=$(fetch oe-database-url)
HF=$(fetch oe-hf-token)
GEM=$(fetch oe-gemini-api-key)

umask 077
tmp=$(mktemp)
{
  printf 'DATABASE_URL=%s\n' "$DB_URL"
  printf 'HF_TOKEN=%s\n'     "$HF"
  printf 'GEMINI_API_KEY=%s\n' "$GEM"
} > "$tmp"
chmod 600 "$tmp"
chown "$ENV_OWNER" "$tmp" 2>/dev/null || true
mv "$tmp" "$ENV_PATH"

echo "$(date -Iseconds) wrote $ENV_PATH from Secret Manager"
