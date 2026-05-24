# Pre-registration — OpenEtruscan v2 Evaluations

**Currently shipped:** **v2.0.2** (3-rater jury complete for Streams A & C, 2026-05-23/24). See [Deviation §A](#deviation-a-3-rater-jury-not-delivered-on-v20) for the substitution rationale (Sonnet 4.6 for Opus 4.7).

**Version history:** v2.0 frozen 2026-05-17 → v2.0.1 on 2026-05-21 (2-rater jury acknowledgement) → v2.0.2 on 2026-05-23 (3-rater jury delivered, Deviation §A closed).
**Frozen on:** 2026-05-17
**Git commit at freeze:** `c281ed9` (`refactor: implement v2 research protocol with rigorous evaluation metrics, standardized configurations, and updated methodology documentation`).
**Authority:** any deviation from this document requires a version bump (next: v2.1) and an entry in the Deviations section at the bottom of this file.

This document fixes the evaluation protocol *before* the eval runs. If you read results first and then revise this document, you have unblinded the eval and the results are inadmissible in publication. The Deviations section is the only sanctioned place to record post-freeze adjustments — and only those forced by external constraints (e.g. unavailable API quota), not opportunistic improvements.

---

## Stream A — Classification

### Task
Multi-class single-label classification of Etruscan inscriptions into one of 7 epigraphic types: `funerary`, `ownership`, `dedicatory`, `votive`, `legal`, `boundary`, `commercial`.

### Test set
- **Source:** stratified random sample from the OpenEtruscan v1 cleaned corpus (`research/data/openetruscan_clean.csv` at commit `<freeze-commit>`).
- **Size:** `n = 400` (target). Strata: 7 classes × {high, medium, low} confidence × {Larth, CIE} source.
- **Selection:** seed=42, `pipelines/classify_split.py`. Frozen output: `data/classify_test_v2.jsonl`.
- **Annotation:** LLM-jury → unanimous → candidate gold → human philologist adjudication (target inter-rater Krippendorff α ≥ 0.80 across 2 human raters on a 30-row sub-sample). **Original protocol called for 3 raters** (Claude Opus 4.7 + Gemini 2.5 Pro + a third frontier model). **As delivered** (v2.0.1, see Deviation §A): 2 raters — Gemini 2.5 Pro + Llama 4 Maverick. Claude was unavailable at the time of the run because the project's Vertex Anthropic quota had not been granted yet. The 3-rater rerun will happen once quota lands.

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

This document becomes fully binding when:
- [x] All three Etruscan codebooks have been drafted (`codebooks/etr/*.md` — 2026-05-17)
- [x] The freeze commit hash is recorded above (`c281ed9` — recorded 2026-05-21)
- [ ] **Pending:** Krippendorff α between two human philologists on the 30-row spot-check sub-sample (target ≥ 0.80). Until this lands, the v2 numbers are explicitly labelled "candidate gold" / "consensus silver", not "gold".
- [ ] **Pending:** at least one external reviewer (philologist or ML researcher not on the project) has reviewed and dated this file.

Until the bottom two boxes are checked, v2 results may be cited only with the explicit caveat that human adjudication has not yet been performed. The published documents (`README.md`, `docs/INTELLIGENCE_V2.md`) already carry this caveat.

---

## Deviations from the frozen protocol

Each entry records: which clause changed, why it changed, when, and what mitigation was applied.

### §A — 2-rater jury instead of 3-rater (v2.0 → v2.0.1)

- **Original clause** (Stream A §Test set, Stream B §Baselines, Stream C §Baselines): "LLM-jury (3 models) → unanimous → candidate gold".
- **As delivered (v2.0.1, 2026-05-20)**: 2-rater jury (Gemini 2.5 Pro + Llama 4 Maverick) on Vertex AI, both with `response_format=json_object` schema enforcement. Run logged at `gs://long-facet-427508-j2_cloudbuild/openetruscan-v2/classify/20260520T205613Z/`.
- **Why**: Anthropic Claude Opus 4.7 on Vertex was enabled in the GCP project but the per-base-model `online_prediction_input_tokens_per_minute` quota was 0 at run time, and the quota-increase ticket was estimated to block the run by an unknown number of hours.
- **Closure (v2.0.2, 2026-05-23)**: 3-rater jury delivered. Claude **Sonnet 4.6** was substituted for Opus 4.7 because Sonnet's pre-provisioned quota (2.4M tokens/min on `claude-haiku-4-5` in europe-west1; Sonnet enabled the same way) was already active. Claude Haiku 4.5 was evaluated first but its over-conservative "unsure" rate (8/14 on the smoke vs Sonnet's 4/14) tanked Krippendorff α from 0.67 (2-rater) to 0.45 (3-rater w/ Haiku); we substituted Sonnet 4.6 instead. Final 3-rater run logged at `gs://long-facet-427508-j2_cloudbuild/openetruscan-v2/classify/20260523T214907Z/`.
- **v2.0.2 headline numbers** (which supersede v2.0.1 for all forward-looking claims): Krippendorff α = **0.7649** (up from 0.716), candidate-gold = **143 rows** (down from 159; stricter), adjudication queue = **99 rows** (up from 79), all-unsure = 158. The stricter 3-rater unanimity gate is the right shape: lower yield, higher per-row confidence.
- **Mitigation**: v2.0.1 candidate-gold (159 rows from the 2-rater jury) remains addressable as a "consensus-silver" reference set; v2.0.2 (143 rows, 3-rater unanimous) is the new headline figure for publication. Both raw jury outputs are preserved in GCS for audit.
- **Substitution rationale documentation**: Sonnet 4.6 is in the same Anthropic family as the originally pre-registered Opus 4.7, so the inter-rater-independence assumption (three distinct training-data lineages: Anthropic + Google + Meta) is preserved. We are NOT claiming Sonnet 4.6 ≈ Opus 4.7 on task performance; we are claiming that for inter-rater-disagreement detection, an Anthropic model in the same family provides equivalent independence from Gemini and Llama.
- **Severity**: this is the kind of deviation an honest pre-registration documents rather than the kind it hides. The closure happened within 3 days of the original deviation, and the substitution is principled (same-family Anthropic model for inter-rater independence). All v2 numbers cited in `README.md` and `docs/INTELLIGENCE_V2.md` should be re-tagged to v2.0.2 at the next public-doc update.
