# Pre-registration — OpenEtruscan v2 Evaluations

**Frozen on:** 2026-05-17
**Git commit at freeze:** TBD (record `git rev-parse HEAD` when this file is signed off)
**Authority:** any deviation from this document requires a v2.1 release and an entry in [`docs/DEVIATIONS.md`](docs/DEVIATIONS.md).

This document fixes the evaluation protocol *before* the eval runs. If you read results first and then revise this document, you have unblinded the eval and the results are inadmissible in publication.

---

## Stream A — Classification

### Task
Multi-class single-label classification of Etruscan inscriptions into one of 7 epigraphic types: `funerary`, `ownership`, `dedicatory`, `votive`, `legal`, `boundary`, `commercial`.

### Test set
- **Source:** stratified random sample from the OpenEtruscan v1 cleaned corpus (`research/data/openetruscan_clean.csv` at commit `<freeze-commit>`).
- **Size:** `n = 400` (target). Strata: 7 classes × {high, medium, low} confidence × {Larth, CIE} source.
- **Selection:** seed=42, `pipelines/classify_split.py`. Frozen output: `data/classify_test_v2.jsonl`.
- **Annotation:** LLM-jury (3 models) → unanimous → candidate gold → human philologist adjudication (target inter-rater Krippendorff α ≥ 0.80 across 2 human raters on a 50-row sub-sample).

### Primary metric
**Macro-F1 over the 7 classes**, computed with `sklearn.metrics.f1_score(average='macro', zero_division=0)`.

### Secondary metrics (all reported)
- Per-class precision, recall, F1
- Confusion matrix (with normalisation by true class)
- Accuracy weighted by `data_quality=clean` rows only
- F1 on the head-2 classes (funerary + ownership) and the tail-5 classes separately

### Significance test
For any "model A > model B" claim:
- Paired bootstrap, 10,000 resamples of the test set (same indices for both models), Macro-F1 delta per resample.
- Report: `delta_macro_f1 = +X.XX (95% CI: [a, b]), p = pp.pp` where p is the fraction of resamples where delta ≤ 0.
- **Claim is admissible iff p < 0.05.**

### Baselines (mandatory)
1. **Majority-class** (always predict `funerary`)
2. **TF-IDF + Logistic Regression** (character n-grams, n ∈ {2,3,4}, fit on train, evaluated on test)
3. **CharCNN** (v1 production model)
4. **XLM-R-base** (frozen embeddings + linear head)
5. The new model under evaluation

A new model must beat baseline 4 with p < 0.05 to be reported as an improvement. Beating 1–3 is necessary but not sufficient.

### Train/test contamination
The training set must contain zero inscriptions whose `id` is in the test set. Verified by `pipelines/classify_split.py` which raises if any test ID appears in train.

---

## Stream B — Rosetta-eval-v2

### Task
Given an Etruscan query word, retrieve its bilingual equivalent (Latin or Greek) from a held-out set of attested pairs.

### Test set
- **Source:** primary classical sources (Greek + Latin authors discussing Etruscan vocabulary). Mined via `pipelines/rosetta_mine_pairs.py`, hand-verified subset.
- **Size:** `n ≥ 100` pairs (target 120, to allow 20 rejections during human verification).
- **Strata:** {kinship, theonym, civic/place, funerary, cognate, gloss-only}.
- **Selection:** all verified pairs from `attested.jsonl` after expansion, deduplicated by `(etruscan_word, equivalent)`.
- **Train-lemma exclusion:** any inscription in the fine-tuning corpus containing *any* test-pair Etruscan lemma is removed from training. Verified by `pipelines/verify_lemma_exclusion.py`. Reproduced in eval logs.

### Primary metric
**Precision@10 (P@10)** — does the top-10 retrieval contain the gold equivalent?

### Secondary metrics (all reported)
- P@1, P@5, P@50
- Recall@10
- **Semantic-field P@10** — looser metric that scores a hit if *any* word from the gold-pair's semantic field appears in top-10. The semantic-field vocabularies are frozen in `eval/semantic_fields.json` at the freeze commit and may not be edited after results are seen.
- Mean reciprocal rank (MRR)

### Significance test
- Paired bootstrap, 10,000 resamples over the 100+ pairs (same pair indices for both models).
- Report `delta_P@10 = +X.XX (95% CI: [a, b]), p = pp.pp`.
- **Claim admissible iff p < 0.05.**

### Baselines (mandatory)
1. **Random retrieval** (sample 10 Latin/Greek lemmas at random from the candidate vocabulary)
2. **Levenshtein** (rank Latin/Greek candidates by edit distance to the Etruscan query)
3. **LaBSE** (off-the-shelf multilingual sentence embeddings)
4. **XLM-R-base mean-pool** (no fine-tuning)
5. The new model under evaluation

A new model must beat baseline 3 (LaBSE) with p < 0.05 to be reported as an improvement on the multilingual-embedding frontier.

---

## Stream C — Lacunae restoration

### Task
Given an Etruscan inscription with a marked lacuna (Leiden `[...]` or dotted-bracket `[..]` notation), produce the most likely character sequence to fill it. Evaluated against the editor's published restoration.

### Test set
- **Source:** OpenEtruscan v1 cleaned corpus, filtered to rows where `raw_text` contains Leiden restoration markup of known length.
- **Size:** `n ≥ 150` editor-restored inscriptions.
- **Strata:** lacuna width in characters {1, 2–3, 4–6, 7+}.
- **Curation:** 3-model LLM-jury removes inscriptions where the restoration is obviously over-determined (e.g., the lacuna is in the middle of a stock formula like `mi cana ___ as`). Final set requires 1 philologist's accept on each row.

### Primary metrics
- **Char-level top-1 accuracy** on the lacuna span (mean across rows)
- **Hallucination rate** — fraction of rows where the model emits ≥1 character outside the marked lacuna span (i.e., it changes a non-lacuna character). Defined formally in [`codebooks/lacunae.md`](codebooks/lacunae.md).

### Secondary metrics
- Char-level top-3 accuracy
- Span-exact-match rate (entire lacuna correct)
- Per-width-stratum breakdown of all metrics

### Significance test
- Paired bootstrap, 10,000 resamples. Two metrics, two tests, **Bonferroni correction**: claim admissible iff p < 0.025 (= 0.05 / 2).

### Baselines (mandatory)
1. **Most-frequent-character** (always predict `a` per position)
2. **Char-bigram LM** trained on the v1 corpus (excluding test inscriptions)
3. **ByT5-small** off-the-shelf (no fine-tune)
4. **ByT5-small + LoRA** (the v1 production model)
5. The new model under evaluation

---

## What this pre-registration prohibits

- Looking at the test set before the model is trained ("inadvertent inspection").
- Reporting any metric not declared above ("metric mining").
- Changing class definitions, semantic-field vocabularies, or lacuna-width bins after the eval has run.
- Reporting "X is better than Y" without the paired-bootstrap p-value.
- Cherry-picking high-confidence subsets and reporting the metric on that subset as the headline.
- Re-using a test set across training rounds. Once a model has been evaluated on `data/classify_test_v2.jsonl`, that model's tuning is frozen.

## What it requires

- Every result table cites the commit hash, the seed, the model checkpoint hash, and the bootstrap CI.
- Every "improvement" claim cites a paired-bootstrap p-value.
- Negative results are reported with the same prominence as positive ones.
- Hallucination metrics are reported alongside accuracy metrics; you do not get to report one and hide the other.

## Sign-off

This document becomes binding when:
- [ ] All three codebooks are signed off (`codebooks/*.md`)
- [ ] The freeze commit hash is recorded above
- [ ] At least one external reviewer (philologist or ML researcher not on the project) has reviewed and dated the bottom of this file
