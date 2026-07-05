# HuggingFace deployment plan

> **Status: not yet active.** No artifacts are currently published under `Eddy1919/openetruscan-classifier`. This document describes the *plan* for what will go on the Hub once the v2 evaluation has been ratified by human philologists (see [`research/v2/handoff/v2.0-etr/`](../research/v2/handoff/v2.0-etr/)).
>
> An earlier version of this file presented placeholder numbers ("99% Macro F1", "state-of-the-art", "8,091 verified inscriptions") as if they were live. Those claims are retracted; see [`docs/INTELLIGENCE_V2.md`](INTELLIGENCE_V2.md) for the actual v2 numbers and the retraction record.

## What will ship to the Hub

Once the philologist adjudication on the v2.0 candidate-gold set lands (Krippendorff α between two human raters ≥ 0.80 on the 30-row spot-check sub-sample), the following artifacts will be published:

| Artifact | Source | Reported metric (current v2.0.2 numbers) |
|---|---|---|
| `classifier_v2/` | `src/openetruscan/ml/classifier.py` (TF-IDF + MultinomialNB) trained on the v2 train pool | TF-IDF + NB: **macro F1 0.313, 95 % CI 0.273 – 0.348** on n=143 candidate-gold rows. Three neural baselines on the same split: CharCNN 0.369 [0.257, 0.432]; MicroTransformer 0.317 [0.202, 0.404]; EmbeddingMLP (frozen MiniLM-multilingual) 0.124 [0.099, 0.149]. |
| `lacuna_restorer_v2/` | Pre-trained frontier models scored under the v2.0.3 protocol (66 dedup clean-gold tasks); the v1 ByT5+LoRA path is not yet re-evaluated | Opus 4.8 (direct rater): span-exact **0.288** [0.182, 0.394], hallucination 0.000 (by construction). Gemini 3.1 Pro: 0.258 / **0.161**. Gemini 3.5 Flash: 0.258 / 0.545. All span-exact deltas non-significant. ⚠️ The v2.0.2 table (Sonnet 0.949) was **RETRACTED** — empty completions scored as hallucinations; see [`INTELLIGENCE_V2.md`](INTELLIGENCE_V2.md) and CHANGELOG [2.0.3]. |

Both artifacts will carry a full model card following the [Mitchell et al. 2019](https://arxiv.org/abs/1810.03993) template: intended use, training data, limitations, bias analysis, and the bootstrap-CI'd headline numbers — NOT point estimates without uncertainty.

## What will NOT ship

- Point-estimate metrics without confidence intervals.
- Numbers measured on in-distribution training data labelled as "performance".
- The phrase "state-of-the-art" — there is no peer-reviewed Etruscan classification leaderboard to compare against.

## Deployment workflow (when artifacts exist)

```bash
huggingface-cli login

# Classifier
huggingface-cli upload Eddy1919/openetruscan-classifier \
    research/v2/data/classifier_v2/ classifier_v2/

# Lacuna restorer (once re-evaluated)
huggingface-cli upload Eddy1919/openetruscan-classifier \
    research/v2/data/lacuna_restorer_v2/ lacuna_restorer_v2/
```

## Model card template

The published model card will be generated from the v2 eval JSONs (`gs://your-gcp-project-id_cloudbuild/openetruscan-v2/training/...`), not handwritten. See [`scripts/research/build_model_card.py`](../scripts/research/) (TODO) for the generator.
