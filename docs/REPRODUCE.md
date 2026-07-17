# Reproducing OpenEtruscan

Offline-first guide to rebuilding the data layer and re-deriving the
published numbers from a fresh clone. Every command below was verified
against this tree; the one exception (`rosetta-eval-v1` re-runs) is
explicitly marked as blocked.

## 1. Environment

Dependencies are locked in `uv.lock` (resolved against `pyproject.toml`,
Python ≥ 3.10). Torch and the other heavy ML packages enter the resolution
only through extras (`neural`, `rerank`, `transformers`); the core install
is lightweight.

```bash
uv sync                    # core package into .venv
uv sync --extra dev        # + test/lint toolchain (pulls [all], incl. torch)
```

Without uv: `python -m venv .venv && .venv/bin/pip install -e ".[dev]"`
(unlocked — versions may drift; `uv.lock` is the source of truth).

## 2. Fetch the corpus

The corpus is hosted on Zenodo (DOI
[10.5281/zenodo.20075836](https://doi.org/10.5281/zenodo.20075836), concept
DOI 10.5281/zenodo.20075835), not in git and not in DVC (the old
`gs://openetruscan-data-dvc` remote is gone).

```bash
python scripts/ops/fetch_data.py           # verify-and-skip if present
python scripts/ops/fetch_data.py --force   # re-download unconditionally
```

Downloads `research/data/openetruscan_clean.csv` and hard-fails unless its
SHA-256 is
`4fc09af94005655bfe26affeeb48295c88606ae23c8dbc33ff5436f9083f69f8`.
The silver labels (`research/data/openetruscan_labels.csv`) are tracked in
git and need no fetch.

## 3. Frozen classification split (Stream A)

The committed split is byte-reproducible from the corpus + silver labels:

```bash
python -m research.v2.pipelines.classify_split \
    --corpus research/data/openetruscan_clean.csv \
    --silver research/data/openetruscan_labels.csv \
    --out-train research/v2/data/classify_train_pool.jsonl \
    --out-test  research/v2/data/classify_test_v2.jsonl \
    --n-test 400 \
    --seed 42
```

(`make -C research/v2 classify-split` runs the same command.) Verify inputs
and outputs against `research/v2/data/SHA256SUMS` — the manifest mixes
repo-root-relative input paths with local output names, so check in two
steps from the repo root:

```bash
shasum -a 256 -c <(grep ' research/data/' research/v2/data/SHA256SUMS)
(cd research/v2/data && shasum -a 256 -c <(grep -v ' research/data/' SHA256SUMS))
```

## 4. Lacuna v2.0.3 metrics (Stream C)

The published lacuna numbers aggregate the committed jury output. Recompute:

```bash
python research/v2/eval/compute_lacuna_v2.py \
    --jury research/v2/results/lacuna/lacuna_jury_raw_v2_0_3_rerun.jsonl \
    --out /tmp/recheck.json
```

`/tmp/recheck.json` must be identical to
`research/v2/results/lacuna/lacuna_v2_0_3.json` (deterministic: bootstrap
seed defaults to 42), and the stdout digest must match the README /
`docs/INTELLIGENCE_V2.md` tables. Note: v2.0.2's Finding C was retracted as
a harness artifact; v2.0.3 is the corrected re-run.

## 5. Local API

`docker-compose.yml` is the production-VM stack; local dev uses
`docker-compose.dev.yml` (Postgres 16 + pgvector; no PostGIS, so spatial
endpoints are inert):

```bash
docker compose -f docker-compose.dev.yml up --build -d
docker compose -f docker-compose.dev.yml exec api alembic upgrade head
python scripts/ops/fetch_data.py
DATABASE_URL=postgresql://openetruscan:openetruscan@localhost:5432/openetruscan \
    openetruscan import research/data/openetruscan_clean.csv
```

API on `http://localhost:8000`.

## 6. rosetta-eval-v1

Reproducible from the repo:

- the committed eval result JSONs (`eval/rosetta-eval-v1-*.json`);
- the frozen 40/22 anchor split — regenerate with
  `eval/harness/_generate_eval_split.py` (`SEED = 20260510`, stratified by
  category × confidence);
- the eval protocol itself (`eval/harness/run_rosetta_eval.py`,
  `eval/harness/rosetta_eval_v1.sh`), which grades any model served behind
  `/neural/rosetta` via `--api-url`.

**Not reproducible:** re-running the benchmark against the historical model
column. That requires the retired embedding vectors from a GCS bucket in a
deleted GCP project; no public copy exists. The historical manifest (pinned
commits, schema state, run log) is in
[research/notes/reproduce-rosetta-eval-v1.md](../research/notes/reproduce-rosetta-eval-v1.md).
