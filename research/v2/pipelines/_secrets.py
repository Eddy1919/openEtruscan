"""Tiny GCP Secret Manager helper for v2 pipelines.

Only one secret is currently routed through here — GOOGLE_API_KEY for the
Gemini Generative Language API. The Anthropic side uses AnthropicVertex
with Application Default Credentials, so no Anthropic secret is needed.

Usage
-----
    from research.v2.pipelines._secrets import get_secret
    key = get_secret("GOOGLE_API_KEY")

Resolution order
----------------
1. If the secret is already present in `os.environ`, return it (lets local
   dev override without touching the cloud).
2. Otherwise fetch from Secret Manager in GCP project
   `double-runway-465420-h9`, version `latest`.
3. Cache in process memory so repeated calls don't hammer the API.

The script does not write to os.environ — callers that need the value as
an env var (e.g. `google.generativeai`) should set it themselves after
fetching.
"""
from __future__ import annotations

import functools
import os
import sys

DEFAULT_PROJECT_ID = os.environ.get(
    "SECRET_MANAGER_PROJECT_ID", "long-facet-427508-j2"
)

# Logical-name → actual Secret Manager secret name mapping.
# Lets pipeline code ask for "GOOGLE_API_KEY" without knowing whether the
# secret is published as oe-gemini-api-key, gemini-flash-key, etc.
SECRET_NAME_ALIASES: dict[str, str] = {
    "GOOGLE_API_KEY": os.environ.get("GEMINI_SECRET_NAME", "oe-gemini-api-key"),
}


@functools.lru_cache(maxsize=32)
def get_secret(name: str, project_id: str = DEFAULT_PROJECT_ID, version: str = "latest") -> str:
    """Return the value of `name` from env or Secret Manager. Cached.

    Name resolution:
      1. If `name` is in os.environ, return it (lets local dev override).
      2. Otherwise look up `name` in SECRET_NAME_ALIASES to get the real
         Secret Manager secret id, then fetch it.
    """
    env_val = os.environ.get(name)
    if env_val:
        return env_val
    secret_id = SECRET_NAME_ALIASES.get(name, name)
    try:
        from google.cloud import secretmanager  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            f"Secret {name!r} is not in os.environ and "
            "google-cloud-secret-manager is not installed. "
            "Install with: pip install google-cloud-secret-manager"
        ) from e
    client = secretmanager.SecretManagerServiceClient()
    resource = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
    try:
        response = client.access_secret_version(request={"name": resource})
    except Exception as e:  # noqa: BLE001 — surface auth errors clearly
        raise RuntimeError(
            f"Failed to read secret {secret_id!r} (alias for {name!r}) "
            f"from project {project_id!r}. "
            "Run `gcloud auth application-default login` to set up ADC, or "
            "set the value directly in os.environ to bypass Secret Manager."
        ) from e
    return response.payload.data.decode("utf-8")


if __name__ == "__main__":
    # Smoke test: try reading GOOGLE_API_KEY but don't print it.
    try:
        val = get_secret("GOOGLE_API_KEY")
        print(f"GOOGLE_API_KEY resolved (length {len(val)} chars)")
    except Exception as e:  # noqa: BLE001
        print(f"Could not resolve GOOGLE_API_KEY: {e}", file=sys.stderr)
        sys.exit(1)
