# OpenEtruscan Development Guide

How to set up, test, and extend the `openetruscan` Python package. The web
app is a separate repository
([`openEtruscan-frontend`](https://github.com/Eddy1919/openEtruscan-frontend));
see its README for frontend development.

## Environment setup

```bash
git clone https://github.com/Eddy1919/openEtruscan.git
cd openEtruscan

# Locked environment (uv.lock is committed):
uv sync --extra dev

# Or plain pip:
pip install -e ".[dev]"

pre-commit install
pytest
```

The suite runs against three backends, best available first: an explicit
`DATABASE_URL` (Postgres), a `testcontainers` pgvector container (needs
Docker), or in-memory SQLite as the fallback. Postgres-only tests (pgvector
search, the Alembic migration chain) skip on SQLite — run them locally with:

```bash
docker compose -f docker-compose.dev.yml up -d db
DATABASE_URL=postgresql://openetruscan:openetruscan@localhost:5432/openetruscan pytest
```

## Data

Corpus data is not in git. `scripts/ops/fetch_data.py` downloads it from the
Zenodo deposit and verifies checksums; [`docs/REPRODUCE.md`](REPRODUCE.md) is
the end-to-end guide (data → frozen splits → metrics → local API).

## Database migrations

Alembic owns the schema (`src/openetruscan/db/versions/`).

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/openetruscan"
alembic revision --autogenerate -m "Add new column"
alembic upgrade head
```

Two rules, both enforced by `tests/test_migrations.py`:

1. The chain must apply cleanly to an **empty** database (`upgrade head`
   from nothing).
2. Every ORM-mapped table must exist after the chain runs — a model change
   without a migration fails the test.

## Classification training

The neural heads (CharCNN / MicroTransformer / EmbeddingMLP) train through
the CLI under the v2 protocol:

```bash
openetruscan train-neural --arch charcnn --output data/models/
openetruscan predict-neural --arch charcnn "mi aviles"
```

Evaluation methodology, frozen splits, and bootstrap-CI metrics live in
[`research/v2/`](../research/v2/); read
[`research/v2/PRE_REGISTRATION.md`](../research/v2/PRE_REGISTRATION.md)
before changing any evaluation code — its invariants are pinned by
`tests/test_v2_harness.py`.

## Local API (parity reference)

```bash
uvicorn openetruscan.api.server:app --reload
```

This FastAPI app is a development convenience and parity reference; the
production API is TypeScript in the frontend repo (see
[`ARCHITECTURE.md`](ARCHITECTURE.md)).

## CI

Every PR runs: ruff lint + format check, mypy (dependency-light, pinned to
the pre-commit version), and pytest on 3.12 with coverage floor 45% against
a pgvector-backed Postgres service. Pushes to main run the full 3.10–3.13
matrix. Gitleaks runs on push and weekly.
