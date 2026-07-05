# `data/` — local data artifacts (not tracked in git)

This directory holds working data for the CIE ingestion and research pipelines.
**Its contents are intentionally git-ignored** (see the `*.db`, `*.pkl`,
`data/models/`, `data/cie/*.pdf` rules in [`.gitignore`](../.gitignore)). Large
or derived data is versioned with [DVC](https://dvc.org) against the
`gs://openetruscan-data-dvc` remote, not committed as blobs.

## Layout

| Path | Contents | Produced by |
|------|----------|-------------|
| `cie/databases/cie_rescued.db` | Curated SQLite of recovered + geocoded CIE Vol. I records (576 records passing automated extraction/geocoding validation, ~1.5k `text-embedding-004` vectors) | `scripts/data_pipeline/ingest_cie_rescued.py`, `fix_rescued.py`, `geocode_rescued_batch.py` |
| `cie/*.pdf` | Source CIE Vol. I scans (git-ignored) | manual download |
| `cie/pages/`, `cie/progress_*.json` | Per-page VLM extraction state | `scripts/data_pipeline/ingest_cie_all.py` |
| `models/` | Local ML model artifacts | training scripts |

## Restoring `cie_rescued.db`

It is not in the working tree of fresh clones. To obtain it:

- **Regenerate** from the source CIE Vol. I PDFs via the `scripts/data_pipeline/`
  pipeline (`ingest_cie_rescued.py` → `fix_rescued.py` → `geocode_rescued_batch.py`).
  This is the only self-contained path.
- **DVC** (`dvc pull`) is configured against `gs://openetruscan-data-dvc`, but that
  GCS remote lived in a since-retired GCP project — treat it as unavailable until a
  live remote is reconfigured in [`.dvc/config`](../.dvc/config).

> **Note:** an earlier version of this file pointed at a specific commit in git
> history to recover the SQLite blob. Git history was squashed to a single root
> commit, so that path no longer exists — regenerate from the PDFs instead.
