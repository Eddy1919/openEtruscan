# OpenEtruscan — Research

This directory holds the **research narrative and forward-looking
planning** for the Rosetta Vector Space initiative: cross-language
word-vector retrieval among Etruscan, Latin, Greek and other ancient
Mediterranean languages.

This is *separate* from the top-level [`/ROADMAP.md`](../ROADMAP.md),
which covers OpenEtruscan engineering as a whole (corpus, search,
infrastructure). Anything specific to the multilingual-encoder
research strand lives here.

## Navigation

| File | What's in it | When you need it |
|---|---|---|
| [`data/`](data/) | **Published research artifacts.** The cleaned corpus CSV, label files, and held-out evaluation set. Every paper that cites OpenEtruscan should reference these files. | When citing the dataset or running benchmarks. |
| [`experiments/`](experiments/) | Self-contained experiments (one subdir each) with `eval.py` + protocol README + headline results. | When reproducing or extending an evaluation. |
| [`FINDINGS.md`](FINDINGS.md) | Rosetta vector-space strand: what works, what doesn't, and *why* the Bonfante-anchor metric was wrong. Headline numbers from the LaBSE eval. | For the cross-language retrieval research. |
| [`CURATION_FINDINGS.md`](CURATION_FINDINGS.md) | Corpus-curation strand (May 7-9 2026): mirror-glyph cleaning, Old Italic regeneration, classifier data-bottleneck, ByT5 lacuna failure, etr-lora-v4 retrieval gains. | For the dataset-engineering and classifier work. |
| [`BIBLIOGRAPHY.md`](BIBLIOGRAPHY.md) | Consolidated references: Etruscan philology, ML architectures, datasets, conventions. | When citing or following primary sources. |
| [`ROADMAP.md`](ROADMAP.md) | Forward-looking research plan: priorities, hypotheses still worth testing, scope boundaries, what's *not* in scope. | When deciding what the next investment should be. |
| [`WBS.md`](WBS.md) | Work-breakdown structure: every research deliverable broken down into discrete tasks with acceptance criteria, estimated effort, dependencies. | When picking up a task to actually execute. |
| [`notes/`](notes/) | Topic-specific deep-dives that don't yet warrant promotion to a top-level doc. | When you want to know what was tried for a sub-problem. |

## Companion artefacts (not in this directory)

| Artefact | Location | Purpose |
|---|---|---|
| Eval harness + metric definitions | [`/evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py), [`/evals/latin_semantic_fields.py`](../evals/latin_semantic_fields.py), [`/evals/rosetta_eval_pairs.py`](../evals/rosetta_eval_pairs.py) | The reproducible benchmark. |
| Eval-pair corpus | [`/evals/rosetta_eval_pairs.py`](../evals/rosetta_eval_pairs.py) | The 62 curated Etruscan↔Latin anchor pairs (Bonfante 2002, Wallace 2008, Pallottino 1968) used to grade retrieval quality. |
| Production embedding pipeline | [`/scripts/training/vertex/`](../scripts/training/vertex/) | LoRA training, vocabulary embedding (LaBSE, XLM-R), DB ingest. See the README in that directory. |
| Research extraction tools | [`/scripts/research/`](../scripts/research/) | Tools that mine the Perseus classical corpus for primary-source bilingual evidence. |
| Primary-source corpus | [`/data/classical_texts/`](../data/classical_texts/) (gitignored, ~5 GB) | Perseus Digital Library `canonical-latinLit` and `canonical-greekLit` mirrors. |
| Extracted Etruscan-mention passages | [`/data/extracted/etruscan_passages.jsonl`](../data/extracted/etruscan_passages.jsonl) (gitignored) | 1,795 paragraphs from Livy, Dionysius, Cicero, Plutarch, Strabo, Pliny, etc. that mention Etruscan/Tyrrhenian. |
| Embedding artefacts (intermediate JSONLs + LoRA adapters) | `gs://openetruscan-rosetta/` | All vector files + adapter checkpoints from the iteration history. |

## Context for newcomers

OpenEtruscan started as a corpus + search platform for Etruscan
inscriptions. The Rosetta strand is an experimental research direction
*on top of* that platform: can we use modern multilingual transformer
embeddings to align Etruscan with its known neighbours (Latin, Greek)
in a single vector space, and use that geometry to assist philological
work?

The honest answer after three iterations of work is: **partially**.
[`FINDINGS.md`](FINDINGS.md) lays out what works (sub-word cognate
retrieval, semantic-field clustering, theonym alignment), what
doesn't (lexical equivalence between unrelated surface forms), and
why. This is normal-quality applied-NLP research — not the holy-grail
breakthrough the original framing imagined, but a useful research-
assistant tool that's been demonstrated to do real things on real
data.

[`ROADMAP.md`](ROADMAP.md) and [`WBS.md`](WBS.md) describe the
**rigour-first** plan to take what we have to a publishable / shippable
state.
