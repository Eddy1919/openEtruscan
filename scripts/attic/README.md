# Attic — corpus-surgery scripts (audit trail)

These are one-off scripts that already ran while the corpus was being
built. They are retained as the audit trail of *how* the corpus reached
its current state — nothing here is maintained, several will not run
against the current schema, and none of them should ever be re-run
against a live database without review. Most encode one-time decisions
(hardcoded CIE ids, ad-hoc column swaps, dated backfills) that are wrong
for any state other than the exact one they were written for.

Almost all operate on the intermediate SQLite databases under
`data/cie/` (`cie_etruscan.db`, `cie_latin.db`, `cie_ranges.db`,
`cie_rescued.db`, `cie_etruscan_unknown.db`), which were the working
scratch space of the CIE Vol. I ingestion, not the live Postgres corpus.

| File | What it did | ~When / why | Artifact |
|---|---|---|---|
| `compare_cie_db.py` | Substring-matched CIE review rows against live Postgres `canonical` texts to estimate overlap before ingestion. | CIE integration, diagnostic. | console report only |
| `enrich_cie_etruscan.py` | Added provenance columns to `cie_etruscan.db` and filled `canonical`/`phonetic`/`old_italic` via `core.normalizer`. | One-time CIE enrichment. | enriched `cie_etruscan.db` |
| `enrich_cie_etruscan_safe.py` | Same enrichment, but stubs `numpy`/`scipy`/`sklearn` to dodge import-time failures. | Retry variant of the above when the stats stack wouldn't import. | enriched `cie_etruscan.db` |
| `execute_range_split.py` | Expanded CIE id ranges (`486 et 487`, `489-491`, comma lists) from `cie_ranges.db` into `cie_rescued.db`. | One-time range decomposition. | rows in `cie_rescued.db` |
| `fix_latin_db.py` | Swapped a mis-written column in `cie_latin.db` (`likely_latin_morphology` out of `original_script` into `language_hint`). | One-shot repair after a bad write. | fixed `cie_latin.db` |
| `fix_rescued.py` | Injected 4 specific CIE ids (3067, 509, 3968, 4734) with hardcoded coordinates into `cie_rescued.db`. | One-time patch of known-location outliers. | rows in `cie_rescued.db` |
| `flag_duplicates.py` | Clustered near-duplicate `cie_review` rows by normalized text + findspot. | One-time dedup analysis. | `data/cie/duplicate_flag_report.md` |
| `morphological_sieve.py` | Split Latin rows out of `cie_etruscan.db` into `cie_latin.db` by Latin morphology/vocab markers. | One-time language separation. | populated `cie_latin.db` |
| `nuke_placeholder_findspots.py` | Moved rows with placeholder/empty findspots out of `cie_review` into a separate db. | One-time cleanup. | separate placeholder db |
| `postgres_migration_v2.sql` | Added `source_code`/`source_detail`/`original_script_entry` and backfilled existing rows as `LARTH`. | Dated legacy migration (2024-2025), applied once to the prod `inscriptions` table. | schema change on prod |
| `process_salvaged.py` | Moved 4 hardcoded salvaged ids from `cie_etruscan_unknown.db` into `cie_rescued.db` with coordinates. | One-time salvage of known outliers. | rows in `cie_rescued.db` |
| `propose_latin_rescue.py` | Scanned `cie_latin.db` for Etruscan phoneme/punctuation markers to flag rows sorted as Latin by mistake. | One-time review pass. | `data/cie/latin_rescue_candidates.md` |
| `quarantine_duplicates.py` | Built a `cie_discarded` table in `cie_etruscan.db` from exact-dup + Larth-overlap detection. | One-time dedup/quarantine. | `cie_discarded` table |
| `rescue_etruscan_genitives.py` | Moved Etruscan u-stem genitives mis-sorted as Latin back to `cie_etruscan.db` (hardcoded safe-word list). | One-time recovery. | rows moved back |
| `rescue_etruscan_genitives_v2.py` | Second pass of the above with a corrected column index and adjusted safe-word list. | Superseded v1. | rows moved back |
| `salvage_unknown_locations.py` | Used Gemini to extract toponyms from commentary for rows in `cie_etruscan_unknown.db`. | One-time location salvage. | `data/cie/salvaged_locations_report.md` |
| `separate_unknowns.py` | Moved rows with unknown findspot strings into `cie_etruscan_unknown.db`. | One-time split. | `cie_etruscan_unknown.db` |
| `sieve_ranges.py` | Split Latin rows out of `cie_ranges.db` into `cie_range_latin.db`. | One-time language separation. | `cie_range_latin.db` |
| `split_ranges.py` | Moved range-form CIE ids (`1339-1341`, `486 et 487`) out of `cie_etruscan.db` into `cie_ranges.db`. | One-time. | `cie_ranges.db` |
| `unpack_ranges.py` | Expanded range-form ids in `cie_ranges.db` into individual entries. | One-time. | `data/cie/range_decomposition_report.md` |
