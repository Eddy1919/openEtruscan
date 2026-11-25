# Name Index dry run (2026-11-25)

Output of `scripts/data_pipeline/build_name_index.py --report-dir`, run
against a snapshot of the 5,932 records the public site served on
2026-11-24. Nothing was written to the database.

| File | What it lists |
|---|---|
| `summary.json` | Counts behind the numbers below. |
| `names.csv` | One row per headword: name type, gender (praenomina only), confidence, attestations, records, and the forms seen. |

## Headline numbers

- 2,247 names in 1,067 records, under 748 headwords; 162 headwords occur at least twice. The index this replaces (`entities`, filled by `scripts/attic/migrate_graph.py`) shows 26 entries at two or more, one of them a whole formula.
- Praenomina: 1,306. 1,064 are listed forms (`high`) under 32 headwords; 242 are abbreviations read inside a naming formula (`probable`), under 18 more.
- Family names: 941, each the word after a praenomen (`probable`), skipping kinship terms in any case form or with the enclitic `-c` (`clanc`, `papalserc`). A spot check of 60 found most to be real gentilicia (`cainei`, `tetina`, `tlesna`, `seiante`, `tarχnas`), and some noise: truncated readings (`petr`, `cltcu`) and words that are not names.

## Known limits

- Family names are listed by form. `vipi`, `vipina`, `vipinei` and `vipinal` are case and gender forms of one name, but grouping them needs a morphological analysis this script does not do.
- Cognomina, theonyms and place names are not extracted.
- A Latin name formula without interpuncts (`L CAECINA L F`) is not read: a single letter counts as an abbreviated praenomen only before an interpunct or a dot.
