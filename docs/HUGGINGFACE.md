# HuggingFace deployment plan

> **Status: not yet active.** No artifacts are currently published under `Eddy1919/openetruscan-classifier`. This document describes the *plan* for what will go on the Hub once the v2 evaluation has been ratified by human philologists (see [`research/v2/handoff/v2.0-etr/`](../research/v2/handoff/v2.0-etr/)).
>
> An earlier version of this file presented placeholder numbers ("99% Macro F1", "state-of-the-art", "8,091 verified inscriptions") as if they were live. Those claims are retracted; see [`docs/INTELLIGENCE_V2.md`](INTELLIGENCE_V2.md) for the actual v2 numbers and the retraction record.

## What will ship to the Hub

Once the philologist adjudication on the v2.0 candidate-gold set lands (Krippendorff α between two human raters ≥ 0.80 on the 30-row spot-check sub-sample), the following artifacts will be published:

| Artifact | Source | Reported metric |
|---|---|---|
| `classifier_v2/` | `src/openetruscan/ml/classifier.py` (TF-IDF + MultinomialNB) trained on the v2 train pool | Macro F1 with bootstrap 95% CI on the human-ratified gold subset of the 400-row frozen test split |
| `lacuna_restorer_v2/` | TBD — the v1 ByT5+LoRA path has not yet been re-evaluated under the v2 protocol | Span-exact-match, char-acc top-1, and hallucination rate, each with bootstrap 95% CI |

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

The published model card will be generated from the v2 eval JSONs (`gs://long-facet-427508-j2_cloudbuild/openetruscan-v2/training/...`), not handwritten. See [`scripts/research/build_model_card.py`](../scripts/research/) (TODO) for the generator.
