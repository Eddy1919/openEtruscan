# Pod A — Corpus & Data

**Goal.** Raise the data ceiling: every artifact the pipelines consume is
provenanced, licensed, and regenerable from a fresh clone. The classifier,
restorer, and LM are all corpus-bound, so this pod gates Pod B.

**Owned paths.** `data/`, `scripts/data_pipeline/`, `tests/test_corpus.py`.

**Non-goals.** Model training or eval (Pod B). Ingesting any new source
before its license is cleared by the lead.

## Task queue

- [x] **Fresh-clone reproducibility check.** Execute `docs/REPRODUCE.md`
  from a clean checkout end to end (`scripts/ops/fetch_data.py`, checksum
  verification, eval re-derivation). It claims to be verified — verify the
  claim independently and fix or report anything that fails. Good first
  task: it teaches the data layer.
- [ ] **Provenance manifest.** Define a manifest (extend `data/README.md` or
  add `data/provenance.jsonl`) recording source, license, retrieval date,
  and transform chain for every artifact in the `data/` layout table and
  the Zenodo deposit. Every existing artifact gets an entry; unknown
  provenance is recorded as unknown, not guessed.
- [ ] **Data validation tests.** Add checks to `tests/test_corpus.py` that
  fail loudly on schema drift, row-count regressions, and geocodes outside
  plausible bounds for the corpus.
- [ ] **Recovered GCS buckets.** `gs://openetruscan-data-dvc` (365 MB,
  content-addressed DVC md5 store) and `gs://openetruscan-rosetta-vai`
  (16.7 GB: corpus exports incl. a prod SQL dump, embeddings, byt5-lacunae
  adapters, models, eval sets) survived in a live GCP project. Inventory
  both, add provenance entries for everything worth keeping, correct
  `data/README.md`'s retired-remote note, and propose which artifacts get
  a citable Zenodo copy. The DVC store has no pointer files left in-tree —
  treat it as salvage to identify by hash, not as a live remote.
- [ ] **Source expansion survey.** Inventory candidate corpora beyond CIE
  Vol. I (Rix ET, ETP, EDR, …) with license status and estimated record
  counts. Report only — ingestion starts after the lead clears licensing.

## Definition of done

A fresh clone can regenerate or citably fetch every data artifact; the
provenance manifest covers all of them; validation tests run in CI.

## Status & escalations

(pod-owned — append dated entries here)

### 2026-07-17 — Fresh-clone reproducibility check (task 1) — DONE, with escalations

Ran `docs/REPRODUCE.md` end to end in a clean worktree on
`poda/s1-reproduce-check` (macOS arm64, uv 0.11.16, Docker running). The
"verified" claim holds for §§1–4 and 6; **§5 fails at the import step**.
Fixes land in Pod C/D paths, so nothing was fixed — reported below.

**Verified as documented:**

- §1 `uv sync` and `uv sync --extra dev` both resolve and install cleanly
  (torch 2.13.0, transformers 5.14.1 via `[all]`). The pip fallback
  ("Without uv") was not exercised.
- §2 `scripts/ops/fetch_data.py` downloads `openetruscan_clean.csv` from
  Zenodo record 20075836; independent `shasum -a 256` matches the doc's
  `4fc09af9…69f8`. Verify-and-skip (2nd run) and `--force` re-download
  both work; exit 0 throughout.
- §3 `classify_split` (both the `python -m` command and
  `make -C research/v2 classify-split`) regenerates
  `classify_train_pool.jsonl` / `classify_test_v2.jsonl` **byte-identical**
  (git tree stays clean); both documented `SHA256SUMS` steps pass (4/4 OK).
- §4 `compute_lacuna_v2.py` on the v2.0.3 rerun file produces JSON
  **byte-identical** to `research/v2/results/lacuna/lacuna_v2_0_3.json`;
  the stdout digest matches the README.md and `docs/INTELLIGENCE_V2.md`
  tables (spot-checked all 3 models + significance rows); the lacuna
  `SHA256SUMS` passes (4/4 OK).
- §6 `_generate_eval_split.py` reproduces all 61 committed split
  assignments in `rosetta_eval_pairs.py` exactly (train=39, test=22,
  stratification matched per pair); the 3 committed eval JSONs are valid;
  harness scripts and the historical manifest exist.

**Escalation 1 (Pod C, blocking §5): `openetruscan import` fails in the
dev stack.** `docker-compose.dev.yml` ships `pgvector/pgvector:pg16`
(deliberately no PostGIS), and its header claims "Everything else (search,
pgvector similarity, CRUD, migrations) works". Not true for import:
`_ensure_db()` (`src/openetruscan/core/corpus.py:659-676`) wraps
`CREATE EXTENSION postgis` + the `geom` column ALTERs in one try/except
that silently rolls back when PostGIS is absent, so `geom` is never
created; `add()`/`add_batch()` (`corpus.py:755-760`, `804-815`) then
insert into `geom` unconditionally →
`psycopg2.errors.UndefinedColumn: column "geom" of relation "inscriptions"
does not exist`. No alembic migration creates `geom` either. Reproduced
100%: `alembic upgrade head` clean, import dies at first batch. Candidate
fixes (lead's call): make the `geom` insert conditional on the column
existing (Pod C), or move the dev image to one with PostGIS + pgvector
(Pod D), plus correct the compose header claim. Secondary symptom: the
API's `/health` returns 503 (`db.ok:false`) in this stack.

**Escalation 2 (Pod D, docs):** `docs/REPRODUCE.md:102` says "the frozen
40/22 anchor split" — the actual frozen split is **39/22** (61 pairs;
40+22=62 refers to a superseded pair count). Regeneration proves 39/22.
Same stale "40/22" in `research/FINDINGS.md:450` (Pod B). REPRODUCE.md
line should read 39/22.

**Escalation 3 (Pod B, cosmetic):** `compute_lacuna_v2.py`'s stdout header
prints `# v2.0.2 lacuna evaluation` regardless of input version — the
v2.0.3 re-derivation prints a v2.0.2 banner. Output JSON is correct;
only the label is stale.

**Environment notes:** §5's documented `docker compose … up` cannot bind
host port 5432 on machines already running a local postgres (this one
was); the stack was verified with a temporary port override
(15432/18000, removed afterwards) — worth a sentence in REPRODUCE.md §5.
All containers/volumes from the check were torn down. Worktree left
clean except this brief edit; nothing committed per escalation stop.
