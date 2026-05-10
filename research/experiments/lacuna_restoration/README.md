# Lacuna Restoration — XLM-R + char-head vs. char-MLM-from-scratch

## Question

After ByT5 v4/v5 failed (see [`../byt5_v4_vs_v5/`](../byt5_v4_vs_v5/)),
which of the two replacement architectures recommended in
[`CURATION_FINDINGS.md`](../../CURATION_FINDINGS.md) Finding 6.3
actually works on the cleaned 6,567-row Etruscan corpus?

* **Approach A** — character-level transformer trained from scratch
  on a custom ~50-class Etruscan vocabulary (no LoRA, no sentinels,
  full BERT-style masked-LM training).
* **Approach B** — `xlm-roberta-base` warm-started from the
  `etr-lora-v4` adapter (then `merge_and_unload`'d), with a small
  MLP classification head reading the hidden state at the native
  `<mask>` token.

Both consume the same training corpus, the same masking protocol,
and predict over the same Etruscan character vocabulary. The
comparison isolates the encoder prior.

## Dataset

* **Train**: ~5,000 inscriptions from the prod DB satisfying
  `intact_token_ratio = 1.0 ∧ length(canonical_clean) > 10`.
* **Eval**: 500 held-out inscriptions from the same filter,
  selected deterministically by `md5(id)` ordering with `seed=42`.
* **Per row**: one random valid character position is masked;
  the model must predict the masked character.

## Protocol

For each model:

1. Load checkpoint and metadata from
   `gs://openetruscan-rosetta/models/{char-mlm-v1,lora-char-head-v1}`.
2. Iterate the 500 held-out rows; for each, mask one randomly-chosen
   character position (seed=42).
3. Compute top-1 and top-3 character accuracy.
4. Stratify top-1 by position (start / mid / end of word) and by
   target character to surface failure modes.
5. Record the top-10 (target → predicted) confusion pairs.

CPU-runnable end-to-end. Approach B's encoder load + 500 inferences
takes ~5 minutes on CPU.

## Run

```bash
python research/experiments/lacuna_restoration/eval.py
```

Models will be downloaded from GCS to `data/models/` on first run.

## Results

| Model | Top-1 | Top-3 | Top-1 (start) | Top-1 (mid) | Top-1 (end) |
|---|---|---|---|---|---|
| Approach A — char-MLM from scratch | 10.0% | 25.9% | — | — | — |
| Approach B — XLM-R + char head     | **38.0%** | **60.6%** | 35.4% | 39.2% | 36.8% |

**Approach A failure mode**: collapses onto the word-divider `:`
and the vowel `e`. Below frequency-weighted random — the model
learned a marginal-character prior, not a context-conditional one.

**Approach B failure mode**: top-error pairs are *vowel ↔ vowel*
swaps (e↔a, e↔i, a↔i). These are linguistically plausible
restorations — the same class of substitution a human philologist
makes when restoring damaged inscriptions. The flat positional
profile (35 / 39 / 37%) shows the model is performing genuine
bidirectional context interpolation, not exploiting word-edge
regularities.

## Conclusion

The encoder prior is the load-bearing variable at this data
scale. Approach B is shipped to production at `/neural/restore`
and `/lacunae` in the public openEtruscan UI; Approach A is
preserved as a documented negative baseline alongside ByT5 v4/v5.

See Finding 9 in [`CURATION_FINDINGS.md`](../../CURATION_FINDINGS.md)
for the broader interpretation.
