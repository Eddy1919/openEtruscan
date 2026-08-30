# Reproducing OpenEtruscan

This guide details how to rebuild the local dataset, re-derive the frozen evaluation splits, verify benchmark results, and start the local API stack from a clean repository clone.

---

## 1. Environment Setup

Dependencies are pinned in `uv.lock` (compatible with Python 3.10+):

```bash
# Set up locked environment
uv sync --extra dev

# Or with standard pip:
pip install -e ".[dev]"
```

---

## 2. Fetch the Corpus

Corpus files are stored under Zenodo (DOI: [10.5281/zenodo.21854263](https://doi.org/10.5281/zenodo.21854263)):

```bash
# Download and verify SHA-256 checksums
python scripts/ops/fetch_data.py

# Force re-download
python scripts/ops/fetch_data.py --force
```

This verifies that `research/data/openetruscan_clean.csv` matches `4fc09af94005655bfe26affeeb48295c88606ae23c8dbc33ff5436f9083f69f8`.

---

## 3. Re-deriving the Classification Split (Stream A)

The v2.0.4 text-disjoint classification split (427 test / 285 train) is deterministically generated from the cleaned corpus and silver labels:

```bash
python -m research.v2.pipelines.classify_split \
    --corpus research/data/openetruscan_clean.csv \
    --silver research/data/openetruscan_labels.csv \
    --out-train research/v2/data/classify_train_pool.jsonl \
    --out-test  research/v2/data/classify_test_v2.jsonl \
    --n-test 400 \
    --seed 42
```

Verify output integrity against the checksum manifest. Its entries mix repo-root-relative and local paths, so check in two passes from the repo root:

```bash
shasum -a 256 -c <(grep ' research/data/' research/v2/data/SHA256SUMS)
(cd research/v2/data && shasum -a 256 -c <(grep -v ' research/data/' SHA256SUMS))
```

---

## 4. Recomputing Lacuna Metrics (Stream C)

Compute exact-match and hallucination metrics from the raw consensus jury outputs:

```bash
python research/v2/eval/compute_lacuna_v2.py \
    --jury research/v2/results/lacuna/lacuna_jury_raw_v2_0_3_rerun.jsonl \
    --out /tmp/lacuna_recheck.json
```

The output `/tmp/lacuna_recheck.json` will match `research/v2/results/lacuna/lacuna_v2_0_3.json` deterministically.

---

## 5. Running the Local API & Database

Stand up a local PostgreSQL + pgvector container and initialize the database:

```bash
# Start Postgres container and API
docker compose -f docker-compose.dev.yml up --build -d

# Run Alembic migrations
docker compose -f docker-compose.dev.yml exec api alembic upgrade head

# Ingest cleaned corpus
DATABASE_URL=postgresql://openetruscan:openetruscan@localhost:5432/openetruscan \
    openetruscan import research/data/openetruscan_clean.csv
```

The local API is accessible at `http://localhost:8000`.
