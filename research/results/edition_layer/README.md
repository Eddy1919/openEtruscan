# Edition-layer dry run (2026-11-24)

Output of `scripts/data_pipeline/build_edition_layer.py --report-dir` run
against a snapshot of the 5,932 records the public site served on
2026-11-24. Nothing was written to the database. Re-run the script against
Neon before `--apply` and compare: the numbers move as curators edit.

| File | What it lists |
|---|---|
| `summary.json` | Counts behind every number below. |
| `shared_cie_numbers.csv` | 558 CIE numbers held by more than one record, with the best pairwise text similarity. 342 have similarity ≥ 0.6: probable duplicate records, mostly a bare CIEP row next to a `CIE n` row. Not merged; a curator decides. |
| `rix_vs_site_label.csv` | 99 records where the ET text class and the site's own `classification` point different ways. Some are vocabulary (ET class 3 is "donative/votive", the site says "dedicatory"), some are real disagreements. |
| `findspot_vs_et_region.csv` | 82 records whose findspot string and ET region code name different places. A bare city name yields to the region; an explicit find phrase keeps the string. |
| `ciep_fragments.csv` | 687 bare (CIEP) records whose Larth entry has several rows, of which the corpus holds one (`row_held`, e.g. record 4538 holds row 19 of 19 of the Cippus Perusinus). Built from the snapshot and Larth's `CIEP_pymupdf.csv`; IDs and counts only. |
| `unmapped_findspots.csv` | 34 records whose findspot names a place outside `reference/places.csv` (Africa, Rome, …). |

## Headline numbers

- Coordinates: 307 records today → 3,915 after the backfill
  (419 city, 3,148 territory, 41 region precision). 1,199 come from the
  findspot string, 2,409 from the ET region code; 1,774 of those rest on
  the CIEP→CIE numbering and carry `findspot_basis = et_region_probable`.
- ET text class: 3,484 records, 3,130 of them labelled `unknown` today.
  Source: own ET siglum 142, Burman concordance 1,566, CIEP numbering 1,776.
- Trismegistos IDs: 135 → 1,863, from direct concordance links only.
- Findspot strings that only name a custodian or describe the object:
  620. With `--clear-custody-findspots` they move to
  `inscription_edition.findspot_source_text`, and documented provenance
  drops from 2,203 to 1,583 records (each change audited).
- Aliases: 18,214 (own ID 5,623; concordance 4,808; CIEP numbering
  7,783). 262 records have their CIEP→CIE alias confirmed by text match.
- Coverage index: 11,124 concordance rows that match no record. 60 more
  rows are left out because they list a text a record already holds under
  another reference. A row with an ET siglum is left out only when a record
  holds that siglum, since one TM number can cover several ET texts
  (TM 145365 is Ve 3.1, 6.1, 9.1 and 9.2). A row without an ET siglum is
  left out when a record holds its TM number (the Tabula Cortonensis's
  TM-only row). CII, TLE and CIL numbers never count, as those group
  several inscriptions.
- Lexicon: 319 glosses loaded from the gold-gloss file.
