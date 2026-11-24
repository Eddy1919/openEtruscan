# OpenEtruscan Research

This directory holds the **research narrative and forward-looking
planning** for the Rosetta Vector Space initiative: cross-language
word-vector retrieval among Etruscan, Latin, and Greek (the only
populated languages); extension to other ancient Mediterranean
languages is planned but not yet built.

This directory covers the research strands; engineering-wide topics
(corpus, search, infrastructure) live in the top-level `docs/`.

## Navigation

| File | What's in it | When you need it |
|---|---|---|
| [`data/`](data/) | **Published research artifacts.** The label files, the held-out evaluation set, and the notes for the Zenodo corpus deposit (the large corpus CSVs are not tracked in git). Every paper that cites OpenEtruscan should reference these files. | When citing the dataset or running benchmarks. |
| [`experiments/`](experiments/) | Self-contained experiments (one subdir each) with `eval.py` + protocol README + headline results. | When reproducing or extending an evaluation. |
| [`anchors/`](anchors/) | Candidate bilingual anchors, all unverified: LLM-mined classical glosses (`attested.jsonl`, 17 pairs) and the gloss adjudication queue in [`anchors/gold_glosses/`](anchors/gold_glosses/) (319 records: 307 `llm_checked`, 12 `seeded`, 0 `verified`). | When looking for gloss pairs, or when verifying them. Read each README's provenance warning first. |
| [`results/`](results/) | Result write-ups and metrics that sit outside an experiment directory. Holds the T4.3 LaBSE hard-negative LoRA fine-tune, a documented negative result (p@5 = 0.0 in all 17 folds). | When checking why a fine-tune was closed. |
| [`FINDINGS.md`](FINDINGS.md) | Rosetta vector-space strand: what works, what doesn't, and *why* the Bonfante-anchor metric was wrong. Headline numbers from the LaBSE eval. | For the cross-language retrieval research. |
| [`CURATION_FINDINGS.md`](CURATION_FINDINGS.md) | Corpus-curation strand (May 7-9 2026): mirror-glyph cleaning, Old Italic regeneration, classifier data-bottleneck, ByT5 lacuna failure, etr-lora-v4 retrieval gains. | For the dataset-engineering and classifier work. |
| [`BIBLIOGRAPHY.md`](BIBLIOGRAPHY.md) | Consolidated references: Etruscan philology, ML architectures, datasets, conventions. | When citing or following primary sources. |
| [`ROADMAP.md`](ROADMAP.md) | Forward-looking research plan: priorities, hypotheses still worth testing, scope boundaries, what's *not* in scope. | When deciding what the next investment should be. |
| [`v2/`](v2/) | OpenEtruscan v2: gold annotation + frozen benchmarks (LLM-jury labelling, pre-registered evals). Has its own [README](v2/README.md) and [`PRE_REGISTRATION.md`](v2/PRE_REGISTRATION.md). | When working on gold sets or pre-registered v2 benchmarks. |
| [`notes/`](notes/) | Topic-specific deep-dives that don't yet warrant promotion to a top-level doc. | When you want to know what was tried for a sub-problem. |
| [`parked/`](parked/) | Strands on hold since 2026-07-17: `cv_pipeline/` (YOLO glyph detection) and `v2-multilang/` (Oscan, Faliscan and Raetian placeholders). The [README](parked/README.md) lists what un-parks each one. | When you wonder where a removed scaffold went. |

## Companion artefacts (not in this directory)

| Artefact | Location | Purpose |
|---|---|---|
| Eval harness + metric definitions | [`/eval/harness/run_rosetta_eval.py`](../eval/harness/run_rosetta_eval.py), [`/eval/harness/latin_semantic_fields.py`](../eval/harness/latin_semantic_fields.py), [`/eval/harness/rosetta_eval_pairs.py`](../eval/harness/rosetta_eval_pairs.py) | The reproducible benchmark. |
| Eval-pair corpus | [`/eval/harness/rosetta_eval_pairs.py`](../eval/harness/rosetta_eval_pairs.py) | The 61 curated Etruscan↔Latin anchor pairs (39 train, 22 test; Bonfante 2002, Wallace 2008, Pallottino 1968) used to grade retrieval quality. |
| Production embedding pipeline | [`/scripts/training/vertex/`](../scripts/training/vertex/) | LoRA training, vocabulary embedding (LaBSE, XLM-R), DB ingest. See the README in that directory. |
| Research extraction tools | [`/scripts/research/`](../scripts/research/) | Tools that mine the Perseus classical corpus for primary-source bilingual evidence. |
| Primary-source corpus | `data/classical_texts/` (gitignored, ~5 GB) | Perseus Digital Library `canonical-latinLit` and `canonical-greekLit` mirrors. |
| Extracted Etruscan-mention passages | `data/extracted/etruscan_passages.jsonl` (gitignored) | 1,795 paragraphs from Livy, Dionysius, Cicero, Plutarch, Strabo, Pliny, etc. that mention Etruscan/Tyrrhenian. |
| Embedding artefacts (intermediate JSONLs + LoRA adapters) | `gs://openetruscan-rosetta/` | All vector files + adapter checkpoints from the iteration history. |

## Context for newcomers

OpenEtruscan started as a corpus + search platform for Etruscan
inscriptions. The Rosetta strand is an experimental research direction
*on top of* that platform: can we use modern multilingual transformer
embeddings to align Etruscan with its known neighbours (Latin, Greek)
in a single vector space, and use that geometry to assist philological
work?

The honest answer after three iterations on the pretrained-encoder
stack (XLM-R, XLM-R + LoRA, LaBSE) is: **partially**.
[`FINDINGS.md`](FINDINGS.md) lays out what works (sub-word cognate
retrieval, semantic-field clustering, theonym alignment), what
doesn't (lexical equivalence between unrelated surface forms), and
why. The result is a research-assistant tool that does real things on
real data, with a smaller claim than the decipherment the original
framing imagined.

A later strand rebuilt the stack from scratch, with no pretrained model
anywhere in the pipeline
([`experiments/hybrid_embed/README.md`](experiments/hybrid_embed/README.md)),
and the pre-registered gold-label work in [`v2/`](v2/) ran alongside it.
Both ran into the same limit: semantic claims are blocked on
human-verified labels. The semantic eval is still 22 gloss pairs, the
gold-gloss queue has 0 verified records, and the classification gold set
awaits philologist ratification.

[`ROADMAP.md`](ROADMAP.md) describes the
**rigour-first** plan to take what we have to a publishable / shippable
state.
