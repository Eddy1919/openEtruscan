# Dataset deposit v1.2 — checklist

Goal: publish `openetruscan_clean_v12.csv` = the frozen v1.1 grouped rows
plus the metadata columns the export has never carried (findspot,
coordinates, object_type, medium, language, script_system, classification,
completeness, pleiades_id, trismegistos_id, source_code) and the confirmed
bilingual annotations.

Why v1.2 matters, measured: 28 of the 74 frozen search-eval queries
(place_pleiades, place_findspot, chronology) score 0 for every text-only
system because the published CSV carries no place or authority columns; the
graph and hyperbolic embedding blocks cannot be evaluated on real geography;
and 525 Latin-orthography rows are only separable today by an uppercase
heuristic because `language` is dropped at export.

## Steps

1. **Generate** (needs read-only prod access; not possible from a clone):

   ```bash
   DATABASE_URL=postgres://... python scripts/data_pipeline/export_v12_metadata.py \
       --grouped research/data/openetruscan_clean_grouped.csv \
       --bilinguals research/data/bilingual_annotations.csv \
       --output research/data/openetruscan_clean_v12.csv
   ```

   The script LEFT JOINs on `id` and asserts the v1.1 row count is
   preserved: v1.2 is a strict column superset, so every published split,
   dup_group, and citation of v1.0/v1.1 rows stays valid.

2. **Review the bilingual annotations.**
   `research/data/bilingual_annotations.csv` ships 3 `id_confirmed` rows
   (Pe 1.211 = the lautni/libertus bilingual TLE 606; Um 1.7 = the Pesaro
   haruspex bilingual TLE 697; Ar 1.3) and 16 `needs_review` text-similarity
   candidates. Only `id_confirmed` rows are joined into the export; promote
   or delete the needs_review rows first (source:
   `research/anchors/gold_glosses/crossref_report.csv`, Benelli corpus in
   `research/anchors/gold_glosses/bilinguals.jsonl`).

3. **Verify**: `language` column should isolate exactly the ~525 rows the
   uppercase heuristic finds today (compare against
   `research/experiments/hybrid_embed/prepare.py` output: 525 dropped rows);
   `pleiades_id` coverage should make the 20 place_pleiades eval queries
   answerable (check a couple by hand: Arretium 413032, Saena 413044).

4. **Checksum + manifest**: `shasum -a 256 openetruscan_clean_v12.csv`, add
   an entry to `scripts/ops/fetch_data.py` FILES (new record id after the
   Zenodo step), keep the v1.1 entries pinned unchanged.

5. **Zenodo**: new version of DOI 10.5281/zenodo.21854263 (v1.1.0 record),
   upload v12 csv alongside the byte-identical v1.1 files, update the
   deposit description (new columns + bilingual annotation provenance:
   Benelli 1994 corpus, per van Heems' appendix). Publishing mints the new
   version DOI — cite it in README.md and research/data/README.md.

6. **Docs**: extend the schema table in `research/data/README.md` with the
   new columns; delete the "Columns this export does not carry" caveats
   that stop being true; note that the attribution-split problem
   (per-row `source`) is resolved by `source_code`.

Steps 1–3 need prod access and a human review pass; 4–6 are mechanical
follow-through after them. Nothing in the repo is changed by v1.2 until
fetch_data.py gains the new manifest entry.
