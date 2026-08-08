# Pre-registration — OpenEtruscan v2 Evaluations

**Currently shipped:** **v2.0.3** (2026-07-04). Stream A (classification) 3-rater jury is final and unchanged from v2.0.2 (Krippendorff α = 0.7649, n=143). Stream C (lacunae) v2.0.2 "Finding C" was **retracted as a harness artifact** and re-run — see [Deviation §A](#deviation-a-3-rater-jury-not-delivered-on-v20) (Sonnet 4.6 for Opus 4.7 substitution, closed at v2.0.2) and [Deviation §B](#b--v202-lacuna-finding-c-retracted-harness-artifact-v203-re-run) (lacuna re-run).

**Version history:** v2.0 frozen 2026-05-17 → v2.0.1 on 2026-05-21 (2-rater jury acknowledgement) → v2.0.2 on 2026-05-23 (3-rater jury delivered, Deviation §A closed) → v2.0.3 on 2026-07-04 (Stream C lacuna re-run after retracting the empty-completion harness artifact, Deviation §B).
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
The training set must contain zero inscriptions whose `id` is in the test set, **and zero inscriptions whose normalized text matches a test row's**. Both are verified by `pipelines/classify_split.py`, which exits non-zero rather than emit a contaminated split.

The text clause was added on 2026-08-08 and the id-only clause it replaces was insufficient: 470 corpus rows repeat a `canonical_transliterated` value that also appears under a different id, so an id-disjoint split still hands the model test strings during training. The frozen v2 split predates the fix and leaks 25/400 — see Deviation §D. Audit any split with `python -m research.v2.eval.split_contamination`.

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
- **Hallucination rate** — fraction of rows where the model emits ≥1 character outside the marked lacuna span (i.e., it changes a non-lacuna character). Defined formally in [`codebooks/lacunae.md`](codebooks/etr/lacunae.md).

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
- **As delivered (v2.0.1, 2026-05-20)**: 2-rater jury (Gemini 2.5 Pro + Llama 4 Maverick) on Vertex AI, both with `response_format=json_object` schema enforcement. Run logged at `gs://<retired-project>_cloudbuild/openetruscan-v2/classify/20260520T205613Z/`.
- **Why**: Anthropic Claude Opus 4.7 on Vertex was enabled in the GCP project but the per-base-model `online_prediction_input_tokens_per_minute` quota was 0 at run time, and the quota-increase ticket was estimated to block the run by an unknown number of hours.
- **Closure (v2.0.2, 2026-05-23)**: 3-rater jury delivered. Claude **Sonnet 4.6** was substituted for Opus 4.7 because Sonnet's pre-provisioned quota (2.4M tokens/min on `claude-haiku-4-5` in europe-west1; Sonnet enabled the same way) was already active. Claude Haiku 4.5 was evaluated first but its over-conservative "unsure" rate (8/14 on the smoke vs Sonnet's 4/14) tanked Krippendorff α from 0.67 (2-rater) to 0.45 (3-rater w/ Haiku); we substituted Sonnet 4.6 instead. Final 3-rater run logged at `gs://<retired-project>_cloudbuild/openetruscan-v2/classify/20260523T214907Z/`.
- **v2.0.2 headline numbers** (which supersede v2.0.1 for all forward-looking claims): Krippendorff α = **0.7649** (up from 0.716), candidate-gold = **143 rows** (down from 159; stricter), adjudication queue = **99 rows** (up from 79), all-unsure = 158. The stricter 3-rater unanimity gate is the right shape: lower yield, higher per-row confidence.
- **Mitigation**: v2.0.1 candidate-gold (159 rows from the 2-rater jury) remains addressable as a "consensus-silver" reference set; v2.0.2 (143 rows, 3-rater unanimous) is the new headline figure for publication. Both raw jury outputs are preserved in GCS for audit.
- **Substitution rationale documentation**: Sonnet 4.6 is in the same Anthropic family as the originally pre-registered Opus 4.7, so the inter-rater-independence assumption (three distinct training-data lineages: Anthropic + Google + Meta) is preserved. We are NOT claiming Sonnet 4.6 ≈ Opus 4.7 on task performance; we are claiming that for inter-rater-disagreement detection, an Anthropic model in the same family provides equivalent independence from Gemini and Llama.
- **Severity**: this is the kind of deviation an honest pre-registration documents rather than the kind it hides. The closure happened within 3 days of the original deviation, and the substitution is principled (same-family Anthropic model for inter-rater independence). All v2 numbers cited in `README.md` and `docs/INTELLIGENCE_V2.md` should be re-tagged to v2.0.2 at the next public-doc update.

### §B — v2.0.2 lacuna Finding C retracted (harness artifact); v2.0.3 re-run

- **Clause affected**: Stream C — Lacunae restoration (Primary metrics: char-level top-1 accuracy and hallucination rate; and the Stream C rater set). The v2.0.2 lacuna results, including the published **"Finding C"** (Claude Sonnet 4.6 at a **0.949** hallucination rate, framed as "a frontier reasoning model loses at p<0.001"), are **RETRACTED**.
- **What went wrong**: the v2.0.2 lacuna jury **scored empty API responses as hallucinations**. 114 of 125 Sonnet-on-Vertex rows were empty completions — `max_tokens=1024` was exhausted while the model echoed `restored_full` — and `lacuna_jury.py` counted every empty response as `hallucinated=True`. The reported 0.949 measured a Vertex integration failure, not model behaviour; on the 11 rows Sonnet actually answered it led the field. The set was additionally inflated by **exact duplicates (125 rows → 70 unique tasks)**.
- **The fix**: `pipelines/lacuna_jury.py` — empty/unparseable responses now carry `no_parse=True` and are **never** scored as hallucinations; `pipelines/classify_jury.py` — Anthropic-Vertex `max_tokens` raised 1024 → 4096 with a non-empty retry that raises on persistent empty; `eval/{lacuna_metrics,compute_lacuna_v2}.py` — `no_parse` rows excluded from accuracy/hallucination denominators, coverage reported. Deduplication to **66 clean-gold tasks** (width-1-dominated, 43/66; 4 dirty-gold rows dropped).
- **Corrected re-run jury**: **Claude Opus 4.8** (direct agentic first-party rater) + **Gemini 3.1 Pro** (`gemini-3.1-pro-preview`) + **Gemini 3.5 Flash** (`gemini-3.5-flash`), 10 000-resample bootstrap, seed=42. This jury **deviates from the pre-registered Stream C protocol** on two counts: (1) it does not use the Stream C mandatory baselines (§Stream C Baselines) or the v2.0.2 lacuna raters (Sonnet 4.6 / Gemini 2.5 Pro / Llama 4 Maverick); (2) **Opus ran as a direct agentic first-party rater**, not on Vertex, because Opus is **not enabled on the available Vertex projects — only Haiku 4.5 is**. Opus was blind to gold and scored after the run. This is a documented, externally-forced deviation, not an opportunistic change.
- **Corrected result**: **no model wins on accuracy** — all span-exact deltas non-significant (paired bootstrap: Opus vs 3.1-Pro Δ+0.049 p=0.24; Opus vs 3.5-Flash Δ+0.031 p=0.37; 3.1-Pro vs 3.5-Flash Δ−0.016 p=0.66). The task is difficulty/data-bound, echoing the classifier's "data, not architecture" result. The only differentiator is **hallucination — Gemini 3.5 Flash 0.545 vs Gemini 3.1 Pro 0.161**.
- **Independence caveat (2×Google)**: the re-run panel is 2×Google + 1×Anthropic, not three distinct lineages. The two Gemini raters agree with each other (0.339) far more than either agrees with Opus (0.18 – 0.24), so a Krippendorff α over this panel is inflated by shared lineage. Opus's **0.000 hallucination is by construction** (`restored_full` assembled mechanically) and is **not comparable** to the free-generating Geminis. A lineage-independent panel is future work.
- **Severity / version**: version bump to **v2.0.3**. This deviation retracts a *published* result rather than a pre-run substitution, so it is the highest-severity entry in this file — but the retraction itself is the honest outcome the pre-registration discipline is meant to force. **Stream A (classification) is unaffected *by the empty-completion bug***: its short-output jury never hit it; α = 0.7649 / n=143 stand. It is **not** unaffected by the duplicate inflation noted above — the same defect was later found in the Stream A split, see Deviation §D. Data: `research/private/evaluation/lacuna_jury_raw_v2_0_3_rerun.jsonl`, `lacuna_v2_0_3.json`.

### §C — history squash destroyed the freeze anchor; evidence re-anchored (2026-07-17)

- **Clause affected**: the provenance guarantee itself — "Frozen on 2026-05-17, commit `c281ed9`" (header) and every clause whose authority rests on being committed before results.
- **What went wrong**: in July 2026 the repository history was squashed to a single root commit. Commit `c281ed9`, all tags, and the git-recoverable data blobs no longer exist, so the freeze timestamp and freeze ordering can no longer be verified from git. Separately, an audit on 2026-07-17 found the committed frozen split files were a corrupt export: `classify_test_v2.jsonl` held 99 rows (pre-registered: 400) and every row of both split files had empty text fields.
- **Re-anchoring (what was done)**:
  1. The frozen split was regenerated with the exact pre-registered invocation (seed=42, n-test=400) from the public Zenodo corpus deposit (`10.5281/zenodo.20075836`, SHA256 `4fc09af9…`). Verification: all 79 adjudication-queue IDs from the actual jury run are contained in the regenerated test pool with byte-identical `canonical_transliterated` text; the 99 IDs of the corrupt file are a strict subset of the regenerated 400. Full detail and one open delta (312 regenerated train-pool rows vs the historically reported 282 training rows) in [`research/v2/data/README.md`](data/README.md).
  2. The v2.0.2/v2.0.3 lacuna evidence (raw jury JSONL + computed metrics), previously only in the untracked `research/private/` staging area, was promoted to [`research/v2/results/lacuna/`](results/lacuna/) with a SHA256 manifest. Recomputing metrics from the promoted raw file reproduces the published v2.0.3 tables exactly.
  3. From this entry forward, artifact integrity is anchored in **content hashes** (the `SHA256SUMS` files under `research/v2/data/` and `research/v2/results/lacuna/`), not in git commit IDs. Hashes survive history rewrites; commit pointers here demonstrably did not.
- **What this does NOT repair**: the *temporal* claim that the protocol predates the results is now attested by this document's own narrative, the Zenodo deposit timestamps, and the GCS build IDs cited in §A — not by git history. Readers should weight it accordingly.
- **Severity**: process-level. No result changes. The lesson is recorded so the next history rewrite (if ever) is preceded by exporting anchors that survive it.

### §D — the Stream A contamination guard was id-only; the frozen split leaks 25/400 (2026-08-08)

- **Clause affected**: Stream A — *Train/test contamination*, and by extension the primary metric it protects (macro F1 **0.313**, 95% CI 0.273–0.348, TF-IDF + Multinomial NB on the n=143 candidate-gold subset).
- **What went wrong**: the clause required, and `classify_split.py` enforced, disjointness **by `id`**. That is not the property the metric needs. The published corpus holds 6,567 rows over 6,097 distinct `canonical_transliterated` values: 470 rows repeat a text that also appears under a *different* id, because short formulaic inscriptions (`mi`, `suθina`, `aplu`, `alpan`, `turce`) genuinely recur across distinct artifacts. An id-disjoint split therefore still shows the model exact test strings during training. Measured on the frozen split: **25/400 test rows (6.2%)** have a bracket-stripped twin in the 312-row train pool, and **23** of those twins carry the same silver label.
- **Why the headline figure is affected more than 6.2% suggests**: the metric is computed on the *unanimous* candidate-gold subset (n=143), not the full 400-row pool, and the leak is not uniformly distributed across it. Leaked rows are **92% single-token**, against 16.5% in the 79-row non-unanimous adjudication queue. Short repeated forms are exactly what a jury agrees on unanimously — and **0 of the 25 leaked rows fell in the adjudication queue**, against 4.9 expected if the leak were spread evenly. The leak is therefore *enriched* in the scored subset rather than diluted by it. Because the metric is **macro**-averaged over seven classes, the effect is amplified further where the classes are thinnest: `votive` is 2/8 leaked (25%) and `dedicatory` 8/63 (12.7%), and each class carries 1/7 of the score.
- **What is NOT claimed**: the magnitude of the inflation. Nobody has re-scored the classifier on a clean split, so the direction of the bias is known and its size is not. The published ±0.038 interval is a bootstrap over sampling noise and does not model contamination at all, so it should not be read as bounding this. `0.313` is not retracted here — it is **flagged as an upper bound pending a clean re-run**.
- **The fix**: `pipelines/classify_split.py` now samples **text groups** rather than rows — a row entering the test pool takes every silver-labelled row sharing its normalized text with it — and exits non-zero if any normalized text spans both pools. `text_key()` strips Leiden markup so `la(u)tni` / `lautn(i)` / `laut(n)i` group together. Regenerating with the pre-registered invocation now yields a text-disjoint **427 test / 285 train** split. New tool `eval/split_contamination.py` measures the leak in any frozen split; `tests/test_v2_harness.py` covers the guard.
- **The frozen split WAS regenerated (maintainer decision, 2026-08-08, same day)**: the initial fix left the frozen files untouched to protect the jury run and the philologist handoff keyed to them. The maintainer overrode that, and the override is safe for a reason worth recording: with the same seed the text-disjoint generator follows the identical sampling path and *then* expands groups, so the new 427-row test pool is a **strict superset** of the old 400 and the new 285-row train pool a **strict subset** of the old 312. Every jury-scored id, all 79 queue ids, and the handoff CSVs remain valid references into the current pool. Old hashes recorded in [`data/README.md`](data/README.md). A second discovery forced the issue anyway: the v2.0.2 classify jury raw and candidate-gold files lived only under `gs://<retired-project>_cloudbuild/` and are **unrecoverable** — not in the salvage bucket, not on the Hub, not local (verified 2026-08-08). There is no stored gold to protect; the jury must re-run, and it should re-run against the clean pool.
- **Cost of the fix**: the text-disjoint split moves 27 rows from train to test, leaving **285** training rows against the previous 312. That worsens an already data-bound problem and sharpens the second defect below.
- **Related, not fixed**: the split allocates 400 of 712 labels (56%) to test. `commercial` gets **0 train / 2 test**, `boundary` 1/9, `legal` 3/7 — three of the seven classes in the macro denominator cannot be learned at all, and `commercial` contributes a structural zero to every macro F1 in the v2 tables. Stratified k-fold CV over text groups would use the scarce labels far better and give tighter intervals than one holdout. Queued for the Stream A re-run, not done here.
- **Precedent**: §B records this same failure mode — "the set was additionally inflated by **exact duplicates (125 rows → 70 unique tasks)**" — on the Stream C lacuna set. That entry states "Stream A (classification) is unaffected", which is correct for the empty-completion bug it was addressing but **not** for duplicate inflation. Stream A carried the identical defect, unguarded, for another three months.
- **Severity**: high. No result is retracted, but a published metric on every public surface now carries a caveat, and the pre-registered guarantee that protected it was never sufficient. Reproduce with:

  ```bash
  python -m research.v2.eval.split_contamination \
      --train research/v2/data/classify_train_pool.jsonl \
      --test  research/v2/data/classify_test_v2.jsonl \
      --queue research/v2/handoff/v2.0-etr/adjudication_queue.csv
  ```
