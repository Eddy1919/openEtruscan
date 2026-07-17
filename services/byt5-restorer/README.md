# ByT5 Lacuna Restorer

Cloud Run microservice that restores lacunae in damaged Etruscan
inscriptions. `POST /restore` accepts Leiden-notation text
(`lar[---]al velinas`) and returns ranked character-level restorations.
The API proxies to it when `byt5_service_url` is configured (see
`src/openetruscan/api/server.py`); otherwise the API falls back to
in-process inference.

## Configuration

| Variable | Required | Meaning |
| --- | --- | --- |
| `MODEL_URI` | **yes** | HuggingFace repo id or local path of the checkpoint to serve. No default — see below. |
| `MODEL_VERSION` | no | Adapter name stamped on every response (default `byt5-lacunae-v1`). |
| `CACHE_PATH` | no | SQLite prediction-cache location (default `/tmp/byt5_cache.db`). |

`MODEL_URI` is deliberately mandatory. Every response advertises
`MODEL_VERSION` (`byt5-lacunae-v1`), so a built-in fallback to a base
checkpoint such as `google/byt5-small` would serve weights that were never
fine-tuned on lacunae under the adapter's name. A deployment that doesn't
set `MODEL_URI` fails at container startup with an error naming the
variable, rather than serving mislabelled predictions.

`GET /health` reports the resolved `model_uri` next to `model_version`, so
what a deployed instance actually serves is observable from outside:

```json
{"status": "ok", "model_loaded": false, "model_version": "byt5-lacunae-v1", "model_uri": "..."}
```

## Build and deploy

The Dockerfile pre-downloads a checkpoint into the image's HF cache
(`--build-arg PREBAKE_MODEL_URI=...`) so cold starts skip the download.
That is cache warming only, and only helps when it matches the runtime
`MODEL_URI`.

```sh
gcloud run deploy openetruscan-byt5 \
  --source services/byt5-restorer \
  --region europe-west4 \
  --project your-gcp-project-id \
  --set-env-vars MODEL_URI=<checkpoint implementing byt5-lacunae-v1> \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --cpu 1 \
  --memory 2Gi \
  --timeout 120s \
  --build-service-account=projects/.../serviceAccounts/cb-trigger-runner@...
```

## Tests

Startup/env behaviour is covered by `test_startup.py` (no model download,
not part of the root `pytest` run because `testpaths = ["tests"]`):

```sh
.venv/bin/pytest services/byt5-restorer/ -q
```
