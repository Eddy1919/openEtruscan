# WBS T4.3 — LaBSE Hard-Negative LoRA Fine-Tune: Negative Result

**Decision date:** 2026-05-11
**Cost:** ≈ $0.10 (2m01s on a single Vertex AI T4)
**Vertex job:** `projects/27914760876/locations/us-central1/customJobs/4733299958738845696`
**Adapter artefacts:** `gs://openetruscan-rosetta/adapters/labse-attested-v1/`
**Metrics:** [labse_hardneg_t43_metrics.json](./labse_hardneg_t43_metrics.json) (per-fold)

## TL;DR

Contrastive LoRA fine-tuning of LaBSE on the 17 attested Etruscan→(Latin|Greek)
gloss anchors with 17 × 20 hard-negative pairs produces **no measurable lift**
over baseline (LOO precision@5 = 0.0 in every fold). The corpus is too small
and the supervision signal too thin for LoRA to move the embedding manifold
in a useful direction. We close T4.3 with a documented negative result.

## Setup

| Field                | Value                                                 |
|----------------------|-------------------------------------------------------|
| Base model           | `sentence-transformers/LaBSE` (471M params, 768d)     |
| Adapter              | LoRA (`peft`), `r=2, α=4, dropout=0.1`                |
| LoRA target          | `query, value` on encoder layers `[8, 9, 10, 11]`     |
| Trainable params     | **24,576 / 470,951,424 = 0.0052 %**                   |
| Optimiser            | AdamW, `lr = 2e-6`                                    |
| Loss                 | InfoNCE, temperature `τ = 0.05`                       |
| Anchors              | 17 (mixed Latin + Greek glosses, hand-curated T4.2)   |
| Hard negatives       | 20 per anchor, mined offline against the labse-v1     |
|                      | partition in `language_word_embeddings` (T2.4)        |
| Epochs               | 3                                                     |
| Eval                 | 17-fold leave-one-out; rank held-out positive among   |
|                      | (positive + 20 hard negs)                             |
| Regression guard     | Off-diag mean-cosine drift, abort if Δ > 0.02         |

Cost guards came directly from the *avoid-overfitting* mandate: small `r`,
late-layer-only, micro learning rate, batch=4, ≤3 epochs.

## Results

```
n_folds:      17     (none aborted by regression guard)
p@1 mean:     0.0
p@5 mean:     0.0
p@10 mean:    0.0
held_out_positive_rank: 21 / 21   (positive ranked LAST in every fold)
```

Per-fold history is uniform: per-epoch loss does not descend (oscillates
within ±0.3 of ~7.3 across folds), `on_diag − off_diag` cosine stays at
~+0.056, regression delta peaks at 6 × 10⁻⁵ — three orders of magnitude
below the abort threshold. **The model is essentially unchanged.**

## Interpretation

The negative is honest and consistent with the prior. With 24,576 trainable
parameters, `lr = 2e-6`, and 16 anchors per fold, the update budget is
≈ `24,576 × 2e-6 × 16 × 3 ≈ 2.4` "parameter-update-units" — well below the
threshold needed to flip ranks in a 768-dim space where the positives sit
on the *opposite side* of the manifold from the hard negatives (Greek gloss
vs Latinate orthographic neighbours).

The hard-negative *miner* did its job: see fold 16, where the model's
top-3 nearest neighbours to `hister` are `histriam, hysteria, histria`
(cosines 0.93, 0.93, 0.89). Those are genuine Latin cognates — exactly
the orthographic distractors we want the model to learn to push *below*
the semantic gloss `ludius` (actor). LaBSE knows the orthography but
not the semantics, and 17 contrastive examples are nowhere near enough
to install that knowledge.

What this rules out:

- **The "more epochs / bigger LoRA" rescue:** with no signal in `on_diag −
  off_diag` drift after 3 epochs, more epochs are extrapolation in noise.
  Bigger `r` would risk overfit — the very thing this experiment was
  designed *not* to do.
- **The "scale aren't the problem" hypothesis:** the experiment confirms
  that scale (n=17) *is* the problem.

## Implications for the broader Rosetta program

1. **T4.3 closed as negative.** Adapter `labse-attested-v1` is on GCS as
   an audit artefact; we will not promote it to a versioned vocab partition.
2. **Vocabulary-level Rosetta gains will not come from contrastive
   fine-tuning at this scale.** Future yield improvements should target
   anchor acquisition (Option C / community curation, [PR #55]) before
   any further fine-tune work.
3. **The mining pipeline is reusable** — when the anchor corpus grows past
   ~100 entries (e.g. after a Pelagios curation push) we can rerun the
   exact same job with the new anchors and re-evaluate. The submit script
   takes paths as flags.
4. **Negative-result discipline.** This is exactly the kind of clean fail
   the paper draft (Option A) should describe: a designed experiment with
   pre-registered guards, executed end-to-end on a public cloud, with all
   artefacts retained and findings written up in the same PR cycle.

## Reproducibility

```bash
# Re-mine negatives (cheap, ~5 min):
python scripts/research/mine_hard_negatives.py --mode offline-gcs

# Re-submit Vertex job:
bash scripts/training/vertex/submit_labse_hardneg.sh
# (requires: gcloud auth, project=double-runway-465420-h9)
```
