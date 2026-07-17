# Data pipeline scripts

Reusable pipeline steps for building and maintaining the OpenEtruscan
corpus: CIE Vol. I ingestion, findspot geocoding, corpus seeding and
metadata joins, Pleiades linking, and exports. Each
script is a standalone entrypoint; most read `DATABASE_URL` and API keys
from `.env` at the repo root.

One-off corpus-surgery scripts that already ran (range splitting, Latin
sieving, duplicate quarantine, location salvage, the `enrich_cie_*`
pair, `postgres_migration_v2.sql`, …) have been moved to
[`../attic/`](../attic/README.md) as the build audit trail.

## CIE Vol. I ingestion chain

Typical order for turning the CIE PDFs into geocoded corpus rows. Steps
marked *(attic)* are the historical one-offs that ran between the live
steps and are kept in `../attic/` for reference only.

1. `ingest_cie_all.py` — VLM-extract every CIE PDF, page by page.
2. `export_cie_sqlite.py` (or `export_cie_csv.py`) — flatten page JSON into a reviewable table with a Latin/Etruscan language heuristic.
3. *(attic: `morphological_sieve.py`, `split_ranges.py`/`sieve_ranges.py`/`unpack_ranges.py`/`execute_range_split.py`, `enrich_cie_etruscan*.py`, `separate_unknowns.py`, `flag_duplicates.py`/`quarantine_duplicates.py` — the language/range/dedup surgery)*
4. `init_findspot_db.py` → `cluster_findspots_gemini.py` → `validate_findspots_mapbox.py` — build and geocode the unique-findspot table.
5. *(attic: `salvage_unknown_locations.py`, `process_salvaged.py`, `fix_rescued.py` — recover unknown-location outliers)*
6. `geocode_rescued_batch.py` — batch-geocode the rescued rows.
7. `export_to_postgres.py` → `ingest_cie_rescued.py` — emit and load the validated rows into Postgres.

## Live scripts

### CIE ingestion & geocoding

| Script | Purpose | Inputs | Outputs |
|---|---|---|---|
| `ingest_cie_all.py` | VLM-extract all CIE Vol. I PDFs page by page | `data/cie/*.pdf`, VLM key (`.env`) | `data/cie/pages/*.json`, `progress_*.json` |
| `export_cie_csv.py` | Flatten page JSON to a review CSV; heuristic language tag | CIE page JSON | `data/cie/cie_export_review.csv` |
| `export_cie_sqlite.py` | Same, into SQLite (avoids CSV newline pollution) | CIE page JSON | `data/cie/cie_export_review.db` |
| `export_to_postgres.py` | Emit INSERT SQL from `cie_review` | `data/cie/databases/cie_etruscan.db` | `data/cie/working/pg_ingest.sql` |
| `ingest_cie_rescued.py` | Normalize + load rescued rows into Postgres | `cie_rescued.db`, `DATABASE_URL` | rows in `inscriptions` |
| `init_findspot_db.py` | Build unique-findspot table for geocoding | `cie_etruscan.db` | `data/cie/findspots_geocoding.db` |
| `cluster_findspots_gemini.py` | Cluster raw findspot strings into canonical toponyms | findspot db, `GEMINI_API_KEY` | `cluster_name` updates |
| `validate_findspots_mapbox.py` | Cross-check Gemini coords vs Mapbox (haversine) | findspot db, `MAPBOX_SECRET_TOKEN` | mapbox coords + distance |
| `geocode_rescued_batch.py` | Batch-geocode rescued findspots via Gemini | `cie_rescued.db`, `GEMINI_API_KEY` | coords in `cie_rescued.db` |

### Corpus seeding, normalization & metadata

| Script | Purpose | Inputs | Outputs |
|---|---|---|---|
| `seed_larth.py` | Seed the corpus from the Larth dataset | Larth `Etruscan.csv` (auto-download) | corpus rows |
| `merge_larth_metadata.py` | Join Larth translation/date columns onto the normalized CSV | `research/data/openetruscan_normalized.csv`, Larth CSV | `research/data/openetruscan_clean.csv` |
| `normalize_inscriptions.py` | Deterministic canonical/old_italic normalization + `data_quality` tagging | corpus / prod dump | `canonical_clean` column / clean CSV |
| `update_db_from_clean.py` | Emit idempotent ALTER/UPDATE SQL applying the clean CSV | `openetruscan_clean.csv` | SQL on stdout |
| `claude_label_corpus.py` | Rule-cascade classifier producing category labels | `research/data/openetruscan_clean.csv`, `inscription_labels.csv` | `research/data/openetruscan_labels.csv` |
| `integrate_burman.py` | Merge Burman concordance (TM/CIE cross-refs) | corpus db, `burman_concordance.csv` | enriched corpus, `trismegistos_mapping.yaml` |
| `ingest_genetics.py` | Ingest AADR/Posth archaeogenetic samples | AADR `.tsv`/`.csv` | `genetic_samples` rows |

### Pleiades linking & gazetteer

| Script | Purpose | Inputs | Outputs |
|---|---|---|---|
| `build_pleiades_gazetteer.py` | Build a local places+names gazetteer for findspot matching | Pleiades dumps (network) | `data/pleiades_gazetteer.json` |
| `ingest_pleiades.py` | Download Pleiades places, filter to Etruria bbox | Pleiades dump (network) | `../openEtruscan-frontend/public/data/pleiades-network.geojson` |
| `propose_pleiades_links.py` | Fuzzy-match findspots to the gazetteer → review queue | gazetteer, findspots (db or file) | `data/pleiades_link_queue.jsonl` |
| `review_pleiades_links.py` | HITL review of the link queue | `pleiades_link_queue.jsonl` | `data/pleiades_mapping.yaml` |

### Review & exports

| Script | Purpose | Inputs | Outputs |
|---|---|---|---|
| `human_review.py` | HITL structural review of curated CIE items into the corpus | `data/cie/curated_pending.json` | corpus rows |
| `export_json.py` | Export `inscriptions` to frontend static JSON | `DATABASE_URL` | `frontend/public/data/corpus.json` |
| `export_rdf.py` | Export corpus as RDF/Turtle (Linked Open Data) | corpus db | `data/rdf/corpus.ttl` |

The OpenAPI spec is regenerated by `scripts/ops/generate_openapi.py`
(drift-gated in CI). `export_rejected.py` moved to `scripts/attic/` —
`provenance_status` stopped encoding editorial rejection with the
four-tier migration, so its query matches nothing by construction.

## Unclear

Left in place pending the owning persona's call — do not delete or move
without confirmation.

| Script | Why unclear |
|---|---|
| `auto_curate.py` | Auto-curation pass (coherency rules + a hardcoded city→coord map) that reads `data/cie/full_extraction.json` and writes `curated_pending.json` for `human_review.py`. The logic is generic, but the S1 audit flagged it as a one-off and it is bound to the `full_extraction.json` artifact. Data owner to decide whether it stays a live curation step. |

`generate_openapi.py` was previously listed here; it was a broken duplicate of
`export_openapi.py` (imported the nonexistent `openetruscan.server`) and has
been deleted in the S1 remediation. Use `export_openapi.py`.
