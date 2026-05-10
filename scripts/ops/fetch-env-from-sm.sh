#!/bin/bash
# Pull the OpenEtruscan API container's runtime secrets from Google Secret
# Manager into the on-disk .env that docker-compose's `env_file:` consumes.
#
# Designed to run on a Google Compute Engine VM that has a service account
# attached with roles/secretmanager.secretAccessor on the chosen project.
# COS notes: /home and /mnt/stateful_partition are mounted noexec, so the
# script must always be invoked via `sudo bash <path>`, never run directly.
#
# Configuration via environment variables (all have sensible defaults):
#
#   OE_PROJECT     GCP project that holds the secrets. Required if not the
#                  same project as the VM (default: read from metadata).
#   OE_ENV_PATH    Where to write the .env file
#                  (default: $PWD/.env, i.e. the docker-compose working dir).
#   OE_ENV_OWNER   chown target for the file (default: current user).
#   OE_SECRETS     space-separated list of "ENV_NAME=secret-name" pairs
#                  (default: the three OpenEtruscan production secrets).
#
# Intended hooks:
#   - Run before `docker compose up -d` in the deploy workflow.
#   - Run on boot via cloud-init or a systemd oneshot pointing at this path.
#
# The script never reads the existing .env, so it is the only writer.
# Secret Manager is the source of truth.

set -euo pipefail

# Default to the project the VM itself is in — derived from the metadata
# service so a public clone of this script works in any environment.
PROJECT="${OE_PROJECT:-$(curl -fsS -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/project/project-id 2>/dev/null || echo '')}"
if [ -z "$PROJECT" ]; then
  echo "OE_PROJECT must be set (could not infer from VM metadata)" >&2
  exit 1
fi

ENV_PATH="${OE_ENV_PATH:-$(pwd)/.env}"
ENV_OWNER="${OE_ENV_OWNER:-$(id -un):$(id -gn)}"

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
ADM=$(fetch oe-admin-token)

# Derive DB_HOST/PORT/USER/PASSWORD/NAME from DATABASE_URL so that services
# which don't speak URL-with-querystring (looking at you, edoburu/pgbouncer:
# its auto-config script writes the raw path component including
# `?ssl=require` as the [databases] section key, which pgbouncer then fails
# to parse with "syntax error at line 3"). Anyone adding such a service
# points it at DB_HOST/USER/etc, not DATABASE_URL. Single source of truth
# stays `oe-database-url` in Secret Manager — these are derived, not new
# secrets.
DB_COMPONENTS=$(DB_URL_VAL="$DB_URL" python3 - <<'PY'
import os
from urllib.parse import urlparse, unquote
u = urlparse(os.environ["DB_URL_VAL"])
print(f"DB_HOST={u.hostname or ''}")
print(f"DB_PORT={u.port or 5432}")
print(f"DB_USER={unquote(u.username or '')}")
print(f"DB_PASSWORD={unquote(u.password or '')}")
print(f"DB_NAME={(u.path or '/').lstrip('/')}")
PY
)

umask 077
tmp=$(mktemp)
{
  printf 'DATABASE_URL=%s\n' "$DB_URL"
  printf '%s\n' "$DB_COMPONENTS"
  printf 'HF_TOKEN=%s\n'     "$HF"
  printf 'GEMINI_API_KEY=%s\n' "$GEM"
  printf 'ADMIN_TOKEN=%s\n'  "$ADM"
  printf 'BYT5_SERVICE_URL=%s\n' "https://openetruscan-byt5-o2ja6yhqqq-ez.a.run.app"
} > "$tmp"
chmod 600 "$tmp"
chown "$ENV_OWNER" "$tmp" 2>/dev/null || true
mv "$tmp" "$ENV_PATH"

echo "$(date -Iseconds) wrote $ENV_PATH from Secret Manager"
