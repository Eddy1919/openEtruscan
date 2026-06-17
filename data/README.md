# `data/` — local data artifacts (not tracked in git)

This directory holds working data for the CIE ingestion and research pipelines.
**Its contents are intentionally git-ignored** (see the `*.db`, `*.pkl`,
`data/models/`, `data/cie/*.pdf` rules in [`.gitignore`](../.gitignore)). Large
or derived data is versioned with [DVC](https://dvc.org) against the
`gs://openetruscan-data-dvc` remote, not committed as blobs.

## Layout

| Path | Contents | Produced by |
|------|----------|-------------|
| `cie/databases/cie_rescued.db` | Curated SQLite of recovered + geocoded CIE Vol. I records (576 verified records, ~1.5k `text-embedding-004` vectors) | `scripts/data_pipeline/ingest_cie_rescued.py`, `fix_rescued.py`, `geocode_rescued_batch.py` |
| `cie/*.pdf` | Source CIE Vol. I scans (git-ignored) | manual download |
| `cie/pages/`, `cie/progress_*.json` | Per-page VLM extraction state | `scripts/data_pipeline/ingest_cie_all.py` |
| `models/` | Local ML model artifacts | training scripts |

## Restoring `cie_rescued.db`

It is not in the working tree of fresh clones. To obtain it:

- **From git history** (it lived here until it was untracked):
  `git show 8cfd216:data/cie/databases/cie_rescued.db > data/cie/databases/cie_rescued.db`
- **Or regenerate** from the source PDFs via the `scripts/data_pipeline/` pipeline.
- **Or, once tracked in DVC:** `dvc pull`.
