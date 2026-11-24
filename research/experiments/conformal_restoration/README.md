# Conformal restoration sets: calibrated letter shortlists, no labels needed

## Question

Restoration models for Etruscan are weak: the best single-letter guess is right
about a third of the time. Can such a model still give an epigrapher something
honest: a set of letters that contains the missing one with a stated
probability? And how large is that set?

Split conformal prediction answers this with a finite-sample guarantee that
holds for any model. The labels are free: mask a known letter in an unseen
inscription and ask for it back. No human annotation is involved.

## Setup

- **Model:** the from-scratch character MLM of
  [`../hybrid_embed/`](../hybrid_embed/) (`train_charlm.py`, about 430K
  parameters). No pretrained weights.
- **Texts:** the 496 validation inscriptions that `train_charlm.py` held out
  at the `dup_group_id` level. They are reconstructed with the trainer's own
  seed; the reconstruction reproduces the trainer's logged validation accuracy
  exactly (0.39598), so no calibration or test text was seen in training.
- **Task:** one letter masked per inscription, chosen uniformly among letter
  positions; 55 letter classes (lowercase Latin transliteration, Etruscan
  specials such as θ χ φ ś, and Old Italic code points).
- **Protocol:** 100 repetitions. Each draws fresh mask positions and a fresh
  50/50 group-level calibration/test split. The tables report means over
  repetitions; the coverage SD across repetitions is about 0.03.

| Method | Score | Reference |
|---|---|---|
| top-k | fixed k: smallest k whose calibration coverage reaches 1 − α | baseline |
| LAC | 1 − p(true letter) | Sadinle, Lei & Wasserman 2019 |
| APS | probability mass ranked at or above the true letter (non-randomised) | Romano, Sesia & Candès 2020 |
| LAC-bucket | LAC with one threshold per letter-frequency bucket (Mondrian) | Vovk et al. 2005 |

Frequency buckets are thirds of total letter mass. In this corpus that splits
into {a, e, i}, {l, n, s, u}, and the remaining 48 letters.

## Results

Top-1 accuracy under this protocol: 0.358 (SD 0.020).

**Target coverage 90% (α = 0.1)**

| Method | Coverage | Mean set size | Coverage: other 48 / l n s u / a e i |
|---|---|---|---|
| top-k (k = 11 in most splits) | 0.908 | 10.5 | 0.78 / 0.97 / 0.97 |
| LAC | 0.907 | **8.7** | 0.78 / 0.97 / 0.97 |
| APS | 0.909 | 9.7 | 0.81 / 0.96 / 0.95 |
| LAC-bucket | 0.917 | 11.1 | **0.92 / 0.92 / 0.91** |

**Target coverage 80% (α = 0.2)**

| Method | Coverage | Mean set size | Coverage: other 48 / l n s u / a e i |
|---|---|---|---|
| top-k (k = 6 in most splits) | 0.817 | 6.5 | 0.60 / 0.91 / 0.94 |
| LAC | 0.811 | **5.4** | 0.60 / 0.90 / 0.93 |
| APS | 0.810 | 6.7 | 0.67 / 0.90 / 0.86 |
| LAC-bucket | 0.819 | 7.2 | **0.83 / 0.82 / 0.81** |

## Reading

1. **The guarantee holds.** Every method lands on its target marginal coverage
   across 100 resplits.
2. **LAC gives the smallest sets.** At 90% it returns 8.7 letters on average
   against top-k's 10.5 (k is re-chosen on each calibration split), with the
   same coverage: the model's confidence
   varies enough per position to be worth using.
3. **Marginal coverage hides who pays.** LAC and top-k reach 90% overall by
   covering a/e/i at 97% and every other letter at 78%. Those other letters
   carry most of an inscription's information (consonants, θ, χ, φ, ś), so a
   marginal 90% set is least reliable where a restoration matters most.
4. **Bucket-conditional LAC fixes the imbalance for 2.4 extra letters.**
   Coverage is 91 to 92% in every bucket. This is the variant to show a user.
5. **Word-initial letters are under-covered too.** Under every method they
   sit below medial letters: by 4 to 7 points at α = 0.1 and up to 10 points
   at α = 0.2 (`results.json`, `coverage_by_word_position`). At α = 0.2
   LAC-bucket keeps the gap to 2 points (0.81 vs 0.83) where APS leaves about 8;
   at α = 0.1 it is no better than APS. Calibrating per position as well as
   per bucket is the next step.

The practical output: for any masked letter, a shortlist of about 11 letters
out of 55 that contains the right one 9 times in 10, whatever the letter.
That is a modest narrowing from a weak model, and it is stated with a
guarantee rather than a softmax score.

## Limits

- One masked letter with full context is easier than a real lacuna, which
  spans several letters of unknown count. Extending to spans needs a set-valued
  score over strings; not done here.
- Exchangeability is assumed between calibration and test inscriptions. Both
  come from the same held-out groups, so it holds here; it would not hold for
  inscriptions from a different site, period, or script convention than the
  corpus. Recalibrate on in-domain texts before trusting coverage there.
- The model selected its best epoch on these validation groups. That treats
  calibration and test symmetrically, so coverage stays valid, but the top-1
  figure is mildly optimistic.

## Run

```bash
python scripts/ops/fetch_data.py
cd research/experiments/hybrid_embed && python prepare.py && python train_charlm.py
cd ../../.. && python research/experiments/conformal_restoration/conformal.py
```

About 45 s on a laptop CPU. Writes [`results.json`](results.json).
