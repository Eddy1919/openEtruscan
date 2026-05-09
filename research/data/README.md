# OpenEtruscan — Research Data

Published research artifacts that accompany the OpenEtruscan corpus.
Files in this directory are the canonical reference for any paper,
benchmark, or downstream model that wants to cite the dataset. They
are reproducible from the production database via the scripts in
[`scripts/data_pipeline/`](../../scripts/data_pipeline/).

## Files

### Tracked in this repository (small reference artifacts)

| File | Rows | Cols | Purpose |
|---|---|---|---|
| [`openetruscan_labels.csv`](openetruscan_labels.csv) | 712 | 4 | Inscription-type labels derived by reasoning cascade. Auditable signal trail per row. |
| [`inscription_labels.csv`](inscription_labels.csv) | 184 | 4 | Hand-labels (gold) — Claude-reasoned from full English translations only. Subset of `openetruscan_labels.csv` with `signal_source = gold`. |
| [`eval_heldout_29.csv`](eval_heldout_29.csv) | 29 | 4 | Independent held-out evaluation set (zero training overlap). Use for any classifier benchmark. |

### Published via Zenodo (large; gitignored, not in this repo)

| File | Rows | Cols | Purpose |
|---|---|---|---|
| `openetruscan_clean.csv` | 6,567 | 10 | **The published v1 dataset.** ML-ready; cleaned, tagged, labeled, joined with Larth metadata. **Download via Zenodo DOI** — see citation section below. |
| `openetruscan_normalized.csv` | 6,567 | 7 | Intermediate before the Larth merge. Reproducible from `openetruscan_clean.csv` minus the `translation` / `year_from` / `year_to` columns. |

To regenerate the large CSVs locally from the prod DB:

```bash
# requires DATABASE_URL pointing at the OpenEtruscan prod instance
python scripts/data_pipeline/normalize_inscriptions.py \
    --input /tmp/etruscan-prod-rawtext-v1.jsonl \
    --csv research/data/openetruscan_normalized.csv

python scripts/data_pipeline/merge_larth_metadata.py \
    --normalized research/data/openetruscan_normalized.csv \
    --output research/data/openetruscan_clean.csv
```

For the published version (with frozen DOI for citation), download from Zenodo (URL in the Zenodo deposit metadata).

## Schema — `openetruscan_clean.csv`

```
id                          text   inscription identifier (CIE / ETP / Pallottino-Rix)
raw_text                    text   carved glyph stream (Old Italic where original)
canonical_transliterated    text   scholarly transliteration; Cyrillic / Latin-Ext-B
                                   mirror-glyph corruption deterministically mapped;
                                   Greek-block sibilants (θ χ σ φ ξ ς) preserved
canonical_italic            text   regenerated Old Italic glyph stream (U+10300–U+1032F).
                                   NULL for Latin-orthography rows, retrograde-OCR
                                   garbage, and rows containing letters with no Old
                                   Italic correspondent (g, y).
canonical_words_only        text   intact tokens only — no editorial brackets, no
                                   uncertainty markers, no lacuna dashes. For
                                   word-embedding training where the model should
                                   learn from attested whole forms.
translation                 text   English gloss from the Larth dataset (when present)
year_from                   int    earliest plausible date (BCE convention; positive
                                   integer = BCE; e.g. 650 = 650 BCE)
year_to                     int    latest plausible date (BCE)
intact_token_ratio          float  fraction of canonical tokens that are complete (0–1).
                                   Filtering knob for ML pipelines. Set to 0.0 for
                                   non-clean rows.
data_quality                text   three-class tag: clean / needs_review / ocr_failed.
```

## Quality breakdown

```
clean         6,094  (92.8%)  — ML-ready
needs_review    154  ( 2.3%)  — residual non-standard characters
ocr_failed      319  ( 4.9%)  — digit-substitution OCR junk; diagnostic only
```

## ML usability tiers

| Tier | Filter | Rows | Use case |
|---|---|---|---|
| **1** (gold) | `data_quality=clean ∧ intact_token_ratio=1 ∧ canonical_italic IS NOT NULL` | 3,528 | Old Italic glyph models, highest-quality embeddings |
| **2** (clean ∧ intact) | `data_quality=clean ∧ intact_token_ratio=1` | 4,058 | Word-embedding training |
| **3** (any clean) | `data_quality=clean` | 6,094 | Sequence / lacuna-restoration training (partial words and editorial markup are useful here) |
| **4** (full) | `*` | 6,567 | Diagnostic / error analysis |

## Provenance

- **~71% from the Larth dataset** (Vico, G. & Spanakis, G., 2023. "Larth: Dataset and Machine Translation for Etruscan." Ancient Language Processing Workshop, EMNLP 2023). Source: https://github.com/GianlucaVico/Larth-Etruscan-NLP
- **~29% from the Corpus Inscriptionum Etruscarum (CIE) Vol. I**, ingested via scripts under [`/scripts/data_pipeline/`](../../scripts/data_pipeline/) (1,855 rows that are not in Larth).

## Reproducibility

The pipeline that generated these files:

```bash
# 1. Normalize the prod-DB extract
python scripts/data_pipeline/normalize_inscriptions.py \
    --input /tmp/etruscan-prod-rawtext-v1.jsonl \
    --csv research/data/openetruscan_normalized.csv

# 2. Merge in Larth's translation / year columns
python scripts/data_pipeline/merge_larth_metadata.py \
    --normalized research/data/openetruscan_normalized.csv \
    --output research/data/openetruscan_clean.csv

# 3. Generate the inscription-type labels via the reasoning cascade
python scripts/data_pipeline/claude_label_corpus.py
# → research/data/openetruscan_labels.csv (712 labels)
```

## Editorial conventions (Leiden)

Editorial markup in `canonical_transliterated` and `raw_text` follows the Leiden conventions used in classical epigraphy:

| Symbol | Meaning |
|---|---|
| `[ ]` | editorial restoration of a damaged passage |
| `< >` | editorial addition (omitted by ancient scribe) |
| `{ }` | editorial deletion (mistake by ancient scribe) |
| `( )` | expansion of an abbreviation |
| `?` | uncertain reading |
| `---` | lacuna of unknown length |
| `•` `·` | word separator |

## License & citation

The cleaning pipeline, normalized columns, Old Italic regeneration, words-only column, and quality / labeling tags are released under CC-BY-4.0. The `translation` / `year_from` / `year_to` columns are derived from the Larth dataset (Vico & Spanakis, 2023) — please cite the original Larth paper for any use of those columns.

When citing this dataset, please also cite the foundational philological references:

- Bonfante, G. & Bonfante, L. (2002). *The Etruscan Language: An Introduction.* Manchester University Press.
- Wallace, R. E. (2008). *Zikh Rasna: A Manual of the Etruscan Language and Inscriptions.* Beech Stave Press.
- Pallottino, M. (1968). *Testimonia Linguae Etruscae* (2nd ed.). La Nuova Italia.
