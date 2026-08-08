---
language:
  - ett
license: apache-2.0
library_name: onnx
tags:
  - etruscan
  - epigraphy
  - text-classification
  - low-resource-nlp
  - ancient-languages
  - onnx
  - byt5
  - lacuna-restoration
datasets:
  - Eddy1919/openetruscan-corpus
metrics:
  - f1
# No model-index block, deliberately. The artifacts in this repository were
# deposited 2026-05-02 and predate the evaluation protocol that produced the
# numbers in the Evaluation section below. They have NOT been re-evaluated
# under it, so attributing those scores to these exact weights would be a
# second unverified claim replacing the first. The Evaluation section reports
# results per *architecture* and says so. A model-index with result rows goes
# here once these artifacts are re-run against the v2.0.4 frozen test split.
# (The Hub validator also rejects a model-index whose results carry no
# metrics, which is exactly the state this card is honest about.)
---

# OpenEtruscan Intelligence Suite

> ## ⚠️ Retraction notice
>
> **An earlier version of this model card claimed "Achieves 99% Macro F1".
> That claim is retracted.** It measured performance on data the model had
> been trained on, with labels the pipeline had assigned to itself. It was
> never a held-out result and it never described this classifier's accuracy
> on unseen inscriptions.
>
> Under the v2.0.2 evaluation protocol (a frozen test split, three-rater
> consensus labels, bootstrap confidence intervals), **macro F1 for this
> family of models is in the 0.12–0.37 band**, not 0.99. The full corrected
> table is below.
>
> If you have cited the 99% figure, please correct or withdraw the citation.
> The retraction is also recorded in the
> [repository README](https://github.com/Eddy1919/openEtruscan#classification--restoration-models)
> and in `release-manifest.json`, which is the project's source of truth for
> every public claim.
>
> `metrics.json` and `v2/metadata.json` in this repository are **historical
> artifacts of the retracted run** and are retained for provenance only. See
> *What the files in this repository actually contain*, below, before reading
> any number out of them.

This repository holds the small neural models that back the OpenEtruscan
platform: two ONNX inscription-type classifiers for in-browser inference, and
a ByT5 LoRA adapter for lacuna restoration.

They are small models trained on a genuinely low-resource ancient corpus. They
are research instruments and browser demos. They are not decipherment tools,
and none of them should be treated as an authority on what an Etruscan
inscription says or means.

## Included artifacts

| File | What it is | Params |
|---|---|---:|
| `cnn.onnx` | Character-level CNN, 7-class inscription type | ~31K |
| `transformer.onnx` | Micro-transformer, 7-class inscription type | ~274K |
| `byt5_v2_6gb/` | ByT5-small LoRA adapter for lacuna restoration | LoRA over `google/byt5-small` |
| `v2/*.onnx` | Superseded legacy exports of the two classifiers | n/a |
| `metrics.json`, `v2/metadata.json` | **Retracted-run artifacts.** Provenance only. | n/a |

Classes: `boundary`, `commercial`, `dedicatory`, `funerary`, `legal`,
`ownership`, `votive`.

## Evaluation

### Classification: v2.0.4 protocol (clean split, 2026-08-08)

Evaluated on the v2.0.4 frozen candidate-gold set, n=167: three-rater LLM
jury (Claude Opus 4.8 + Gemini 3.1 Pro + Gemini 3.5 Flash, all on Vertex AI),
unanimous rows at confidence ≥ medium, Krippendorff α = 0.8557 (α is
lineage-inflated, two of the three raters are Gemini). Training pool: 285
silver-labelled rows on a **text-disjoint** split. 95% bootstrap CIs,
10,000 resamples, seed=42. Raw evidence is committed and SHA256-pinned in
the repository under `research/v2/results/classify/`.

| Architecture | Params | Macro F1 (95% CI) | Accuracy |
|---|---:|---|---:|
| **CharCNN** | 28K | **0.399** (0.353 – 0.435) | 0.665 |
| TF-IDF + Multinomial NB | ~3K | **0.293** (0.255 – 0.329) | 0.755 |
| MicroTransformer | 274K | **0.252** (0.140 – 0.338) | 0.317 |
| EmbeddingMLP (multilingual MiniLM, 384-d) | 58K + frozen encoder | **0.210** (0.181 – 0.242) | 0.641 |

Macro F1 averages over all 7 codebook classes; `votive` and `commercial`
have zero gold rows at v2.0.4, so the metric's ceiling on this set is ~0.714.

> **These numbers supersede the v2.0.2 table** (TF-IDF+NB 0.313, CharCNN
> 0.369, MicroTransformer 0.317, EmbeddingMLP 0.124, n=143, α=0.7649). The
> v2.0.2 split was disjoint by `id` but not by text: 25 of its 400 test rows
> repeated a train-pool text under a different id, and the leak concentrated
> in the scored candidate-gold subset. Its raw jury outputs are also lost
> with a retired GCP project, so it can never be re-scored. Not a controlled
> before/after: the gold set, jury, and train pool all changed. Full record:
> `research/v2/PRE_REGISTRATION.md` Deviation §D.

**These are architecture-level results, not measurements of the exact weights
in this repository.** The artifacts here were deposited on 2026-05-02 and
predate this protocol. Re-running them against the v2.0.4 frozen split is
open work; until it lands, treat the band above as the honest expectation for
models of this class on this corpus, not as a certificate for these files.

Two findings, updated at v2.0.4 (paired bootstrap, same 167 rows, seed=42):

1. **Architecture now matters: the v2.0.2 invariance finding did not
   replicate.** CharCNN beats TF-IDF+NB (Δ +0.106, p = 0.0025) and
   MicroTransformer (Δ +0.147, p = 0.0023) on the clean split. Data remains
   the dominant constraint, but character-level convolution measurably
   extracts more from the same 285 labels; the shipped TF-IDF+NB is no
   longer the best available architecture.
2. **Out-of-distribution dense embeddings still underperform.** EmbeddingMLP
   stays last on macro F1, significantly below TF-IDF+NB (Δ +0.083,
   p < 0.0001), though the gap narrowed from v2.0.2. A frozen modern
   multilingual encoder discards the surface-morphological features
   (`mi…al/-as` possessives, the `tular spural` boundary formula, suffixal
   markers) that carry the typological signal here.

Per-class, the dominant classes are modelled adequately (`funerary` F1 0.88,
`ownership` F1 0.74 on TF-IDF+NB) and the rare classes (`boundary`, `legal`,
`votive`, `commercial`) are data-starved and score zero. **The low macro
F1 is that imbalance reported honestly**, since macro F1 weights every class
equally regardless of support.

### The labels are silver, not gold

The v2.0.4 "candidate-gold" set is **LLM-consensus silver**. Two-philologist
ratification (target human α ≥ 0.80) has not been performed; the handoff
bundle awaiting adjudicators regenerates from committed evidence with
`make -C research/v2 classify-handoff`. These numbers measure agreement with
a frontier-model consensus, not with expert epigraphic judgement. Cite them
with that caveat attached.

### Lacuna restoration: ByT5, v2.0.3 protocol

- Span-exact accuracy **≈ 0.26–0.29** across models on n=66 clean-gold rows.
- 43 of those 66 gaps are a **single character** wide, so the task as measured
  is much easier than general restoration.
- No model in the jury table is a statistically significant winner.
- A separate retrieval-augmented experiment lifts span-exact 0.258 → 0.379
  (p = 0.025). Its retriever excludes near-duplicates using the true answer,
  which is conservative for measurement but **is not a deployable retrieval
  procedure**; do not read 0.379 as production accuracy.

An earlier "Finding C" (Sonnet hallucination rate 0.949) was **retracted** as a
harness artifact and does not appear in the v2.0.3 re-run.

## What the files in this repository actually contain

`metrics.json` reports `val_f1_macro: 0.7427` for the CNN over a 1,497-train /
375-validation split, with per-class F1 of 0.87–0.90 on `commercial`,
`dedicatory`, `funerary`, and `ownership`.

**Do not use those numbers.** They are not comparable to the table above and
they are not corrected figures:

- The split is roughly 6× the size of the v2.0.2 pool and its class balance is
  entirely different: `commercial` has support 102 there and is data-starved
  under v2.0.2. That divergence is the signature of self-assigned labels, which
  is precisely what the retraction is about.
- The evaluation was not held out under a frozen protocol, had no inter-rater
  agreement measurement, and reports no confidence intervals.

`v2/metadata.json` carries `"baseline_milestone": "8,091_verified"`. **That
number corresponds to no OpenEtruscan corpus artifact.** The project's counts
are 6,633 archival, 6,567 published (Zenodo), and 5,932 in the live deployed
database. 8,091 is a stray figure from the retracted era; it is not a corpus
size and should not be cited as one.

Both files are kept rather than deleted so the retracted run stays auditable.

## Intended use

- In-browser first-pass triage of inscription type, with the probability
  treated as a suggestion to a human reader.
- Restoration *candidates* for short lacunae, for a philologist to accept or
  reject.
- Baseline comparison for other low-resource epigraphic work.

## Out of scope

- **Translation or decipherment.** These models do not read Etruscan.
- **Authoritative classification.** Rare classes score near zero; a confident
  softmax over a rare class is not evidence.
- **Unsupervised restoration.** The evaluated task is dominated by
  single-character gaps and tops out below 0.3 exact-match.
- **Any published claim that omits the caveats above.**

A per-inscription softmax probability is a statement about one input, not a
measurement of reliability. The site surfaces both together for this reason.

## Usage

```python
from openetruscan.ml.neural import LacunaeRestorer

restorer = LacunaeRestorer("Eddy1919/openetruscan-classifier")
print(restorer.predict("mi ali[2]s"))
```

The ONNX classifiers run client-side in the browser on
[openetruscan.com/classifier](https://www.openetruscan.com/classifier), which
displays the corrected macro F1 alongside every prediction.

> **Deployment note.** An earlier card described the ByT5 restorer as served
> from Google Cloud Run. The project has since migrated off GCP; the service
> definition lives at `services/byt5-restorer` in the repository and the
> hosted `api.openetruscan.com` endpoint is retired. Run it locally or behind
> your own infrastructure.

## Training data

Derived from the OpenEtruscan corpus, Zenodo DOI
[10.5281/zenodo.20075836](https://doi.org/10.5281/zenodo.20075836), the
cleaned, ML-ready 6,567-row dataset, itself a subset of the 6,633-record
archival corpus. Upstream: the *Larth Dataset* (Vico & Spanakis 2023, ~71%)
and *Corpus Inscriptionum Etruscarum* Vol. I extractions (~29%). Full
provenance chain in
[`research/BIBLIOGRAPHY.md`](https://github.com/Eddy1919/openEtruscan/blob/main/research/BIBLIOGRAPHY.md).

## Licence

**Apache-2.0**, matching the project's per-artifact licensing scheme: code
MIT, data CC BY 4.0 outbound (CC0 inbound for contributions), model weights
Apache-2.0, documentation CC BY 4.0. Declared in
[`release-manifest.json`](https://github.com/Eddy1919/openEtruscan/blob/main/release-manifest.json).

## Citation

```bibtex
@software{openetruscan_2026,
  author    = {Panichi, Edoardo},
  title     = {{OpenEtruscan: open-source digital corpus platform for Etruscan epigraphy}},
  year      = {2026},
  version   = {1.3.0},
  doi       = {10.5281/zenodo.20075835},
  url       = {https://doi.org/10.5281/zenodo.20075835},
  publisher = {Zenodo}
}
```

Cite the concept DOI above for the project. Cite
[10.5281/zenodo.20075836](https://doi.org/10.5281/zenodo.20075836) for the
dataset specifically.
