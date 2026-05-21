# Codebooks

Each language directory contains the frozen annotation protocols used by the LLM-jury pipeline. Codebooks are versioned independently per language and are referenced by ISO-639-3 code:

| Code | Language | Status | Codebooks |
|---|---|---|---|
| `etr` | Etruscan | v2.0 frozen | classification, rosetta, lacunae |
| `osc` | Oscan | scaffold only | TODO |
| `fal` | Faliscan | scaffold only | TODO |
| `rae` | Raetian | scaffold only | TODO |

## What's in each language directory

Every language directory should contain (or grow to contain):

- `classification.md` — inscription-type decision tree + positive/negative examples per class. Class set is language-specific (Etruscan = 7 epigraphic types; Oscan/Faliscan likely overlap with Etruscan but differ in legal-text categories; Raetian is too sparse for fine-grained typology yet).
- `rosetta.md` — definition of valid bilingual equivalence pairs against the classical sources that mention this language. Source language list differs (Etruscan ↔ Greek/Latin; Oscan ↔ Latin; Faliscan ↔ Latin; Raetian ↔ very limited classical attestation).
- `lacunae.md` — Leiden notation conventions + width-stratification + hallucination metric. The Leiden conventions are shared across all four languages; only the corpus differs.

## Why per-language and not shared

Inscription-type taxonomies do not transfer cleanly:
- Etruscan: heavy `funerary` + `ownership`, almost no `commercial`.
- Oscan: more `legal` (the famous bronze tablets) and `civic`, fewer funerary urns.
- Faliscan: very Latin-like, mostly `funerary` + `ownership`.
- Raetian: too few inscriptions to support fine-grained classes; likely collapse to `funerary` / `dedicatory` / `unsure` only.

The pipelines (`research/v2/pipelines/*.py`) treat the codebook as a CLI parameter; switching languages is a config swap, not a code change.

## How to add a new language

1. Pick the ISO-639-3 code.
2. Create `codebooks/<code>/` with the three codebooks above.
3. Create `configs/<code>.yaml` declaring the corpus paths and the allowed class set.
4. Run `make classify-jury LANG=<code>` (or the Cloud Build equivalent).
5. The bootstrap eval harness and adjudication-queue builder work unchanged.
