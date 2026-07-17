# Pod A — Corpus & Data

**Goal.** Raise the data ceiling: every artifact the pipelines consume is
provenanced, licensed, and regenerable from a fresh clone. The classifier,
restorer, and LM are all corpus-bound, so this pod gates Pod B.

**Owned paths.** `data/`, `scripts/data_pipeline/`, `tests/test_corpus.py`.

**Non-goals.** Model training or eval (Pod B). Ingesting any new source
before its license is cleared by the lead.

## Task queue

- [ ] **Provenance manifest.** Define a manifest (extend `data/README.md` or
  add `data/provenance.jsonl`) recording source, license, retrieval date,
  and transform chain for every artifact in the `data/` layout table. Every
  existing artifact gets an entry; unknown provenance is recorded as
  unknown, not guessed.
- [ ] **Dead DVC remote.** `.dvc/config` points at a GCS bucket in a retired
  project. Propose to the lead: reconfigure a live remote, or retire DVC in
  favor of Zenodo archives. Do not pick unilaterally — this is an
  infrastructure decision (escalation trigger).
- [ ] **Fresh-clone reproducibility.** Run the CIE pipeline
  (`ingest_cie_rescued.py` → `fix_rescued.py` → `geocode_rescued_batch.py`)
  from a clean checkout; document every manual prerequisite it actually
  needs and fix anything that fails silently.
- [ ] **Data validation tests.** Add checks to `tests/test_corpus.py` that
  fail loudly on schema drift, row-count regressions, and geocodes outside
  plausible bounds for the corpus.
- [ ] **Source expansion survey.** Inventory candidate corpora beyond CIE
  Vol. I (Rix ET, ETP, EDR, …) with license status and estimated record
  counts. Report only — ingestion starts after the lead clears licensing.

## Definition of done

A fresh clone can regenerate or citably fetch every data artifact; the
provenance manifest covers all of them; validation tests run in CI.

## Status & escalations

(pod-owned — append dated entries here)
