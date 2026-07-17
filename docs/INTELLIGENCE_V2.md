# OpenEtruscan classification & restoration — methodology

This document describes the architectures and evaluation protocols behind the classifier and lacuna-restoration components shipped with this project. It is a methodology paper, not a marketing page.

**An earlier version of this document made claims that did not survive the v2 evaluation rebuild — specifically that the classifier achieved 99% macro F1 and that the lacuna restorer had "high philological safety". Both claims are retracted below. The numbers that replace them are computed under the pre-registered v2 protocol in [`research/v2/`](../research/v2/).**

## 1. What the v1 claims were and why they were wrong

| v1 claim | What was actually measured | Why it didn't hold up |
|---|---|---|
| "Macro F1 = 0.99" for the classifier | The MLP head on top of `text-embedding-004` reached ~0.99 on a self-labeled subset (training-set leakage). The same architecture's held-out performance on the 29-row v1 test set was 0.28 macro F1. | The 0.99 number was not on held-out data; it was an in-distribution fit. The README/HF card highlighted it without disclosing the eval setting. |
| "Phil. Safety: High (Sentinels)" for lacuna restoration | The ByT5 + LoRA path was upgraded to use sentinel tokens (`<extra_id_0>`) instead of free-form generation. "High" was a qualitative label with no quantitative definition or measurement. | "Phil. Safety" was never operationalized as a metric. The v1 doc did not specify what hallucination rate had dropped from, or to. |

The v2 protocol fixes both by pre-registering metrics, freezing splits, running a multi-rater jury for the labels themselves, and reporting bootstrap 95% CIs on every number.

## 2. v2 classifier

**Reference architecture.** TF-IDF (character 2–4-grams, max 3000 features, min_df=2) + Multinomial Naive Bayes (α=0.1). Identical to the v1 production architecture under `src/openetruscan/ml/classifier.py`. Reusing the v1 architecture deliberately so that the rigor delta between v1 and v2 is in the *evaluation*, not the *model*.

**Training data.** 282 silver-labeled inscriptions from the v1 reasoning-cascade output (`research/data/openetruscan_labels.csv`), filtered to those NOT in the v2 frozen test split.

**Evaluation data (v2.0.2).** 143 candidate-gold inscriptions, drawn from a 400-row stratified test split and labeled by a 3-model LLM jury (**Claude Sonnet 4.6 + Gemini 2.5 Pro + Llama 4 Maverick** on Vertex AI) under the codebook at [`research/v2/codebooks/etr/classification.md`](../research/v2/codebooks/etr/classification.md). A row enters candidate-gold only if all three raters independently agreed at confidence ≥ medium. **Krippendorff α = 0.7649 across raters** on the full pool. v2.0.1 (n=159, 2-rater jury) is superseded; see [Deviation §A in PRE_REGISTRATION.md](../research/v2/PRE_REGISTRATION.md) for the substitution rationale.

**Head-to-head: four architectures on the same v2.0.2 split** (10 000-resample bootstrap, seed=42):

| Architecture | Params | Macro F1 (95% CI) | Accuracy | Head-2 F1 | Tail-5 F1 |
|---|---|---|---|---|---|
| TF-IDF + NB | ~3K | **0.313** (0.273 – 0.348) | 0.776 | 0.838 | 0.103 |
| CharCNN | 28K | **0.369** (0.257 – 0.432) | 0.657 | 0.762 | 0.211 |
| MicroTransformer | 274K | **0.317** (0.202 – 0.404) | 0.483 | 0.530 | 0.232 |
| EmbeddingMLP (MiniLM-multilingual) | 58K + frozen 384-d encoder | **0.124** (0.099 – 0.149) | 0.469 | 0.434 | 0.000 |

**Two findings, both replicated between v2.0.1 (n=159) and v2.0.2 (n=143):**

*Finding A — architecture-invariance among local-feature models.* TF-IDF+NB / CharCNN / MicroTransformer cluster at 0.31–0.37 macro F1 with overlapping bootstrap CIs despite 100× parameter-count range. **Adding parameters does not move macro F1; the bottleneck is data, not architecture.**

*Finding B — out-of-distribution dense embeddings fail.* EmbeddingMLP with multilingual MiniLM as a frozen encoder lands at 0.124 — CI [0.099, 0.149] does **not** overlap with TF-IDF+NB's CI [0.273, 0.348]. **Significant at p<0.05** by the non-overlapping-CI heuristic. A pretrained encoder with no Etruscan in its training distribution discards exactly the surface-morphological features (`-uce`, `mi…al`, `tular spural`) that carry the typological signal; character n-grams capture them. This contradicts the conventional NLP intuition that dense pretrained embeddings always beat surface-feature baselines.

**Honest interpretation.** The reference TF-IDF+NB architecture works for the two dominant classes (`funerary` F1 0.84, `ownership` F1 0.79) and fails on the rare classes. The path to better numbers runs through *more annotated data*, not better models — confirmed across four architectures spanning 3 K → 274 K parameters.

## 3. v2 lacuna restoration

> ⚠️ **RETRACTION (v2.0.3, 2026-07-04) — the v2.0.2 lacuna results below the fold were a harness artifact and are withdrawn.**
> The v2.0.2 lacuna jury **scored empty API responses as hallucinations**. 114 of 125 Claude Sonnet 4.6 rows were empty completions — `max_tokens=1024` was exhausted while the model echoed `restored_full` — and `lacuna_jury.py` counted every empty response as `hallucinated=True`. The reported **Sonnet 0.949 hallucination rate** and the "a frontier reasoning model is significantly worse at p<0.001" narrative (old Finding C) measured a **Vertex integration failure, not model behaviour**; on the 11 rows Sonnet actually answered it led the field. The set was additionally inflated by exact duplicates (125 rows → 70 unique tasks). The corrected v2.0.3 re-run replaces the table, significance test, and findings below.
>
> **Scope of the retraction:** this affects the lacuna stream (Stream C) **only**. The classifier stream in §2 (jury = Claude Sonnet 4.6 + Gemini 2.5 Pro + Llama 4 Maverick, Krippendorff α = 0.7649, n=143) uses short outputs, was never touched by the empty-completion bug, and **stands unchanged**. See [`CHANGELOG.md` §2.0.3](../CHANGELOG.md) and [PRE_REGISTRATION.md Deviation §B](../research/v2/PRE_REGISTRATION.md#b--v202-lacuna-finding-c-retracted-harness-artifact-v203-re-run).

**Task.** Given an inscription with a marked Leiden-notation lacuna of known character width, produce the character sequence most likely to have been there. Scored against the editor's published restoration.

**Eval set (v2.0.3).** The v2.0.2 set (118/125 rows) was deduplicated to **70 unique tasks** and further filtered to **66 clean-gold tasks** (4 dirty-gold rows dropped). The corrected set is **width-1-dominated (43/66 tasks are single-character gaps)**. Gold filtered to drop trailing dash markers (`reri---` = "more destroyed text continues here", unscoreable) and editorial digit annotations. Harness fixes: empty/unparseable responses now carry `no_parse=True` and are **never** scored as hallucinations; Anthropic-Vertex `max_tokens` raised 1024 → 4096; `no_parse` rows excluded from accuracy/hallucination denominators with coverage reported.

**Models compared (v2.0.3 — 3-rater re-run).** **Claude Opus 4.8** (direct agentic first-party rater), **Gemini 3.1 Pro** (`gemini-3.1-pro-preview`), **Gemini 3.5 Flash** (`gemini-3.5-flash`). This jury **differs** from the v2.0.2 lacuna raters (Sonnet 4.6 / Gemini 2.5 Pro / Llama 4 Maverick) — see the caveats below. ByT5+LoRA (the model the v1 doc highlighted) is not included; it will be re-evaluated under the same protocol when its checkpoint is re-exported.

**Headline results (bootstrap, 10 000 resamples, seed=42, n=66 clean-gold tasks):**

| Model | Span exact (95% CI) | Char acc top-1 (95% CI) | Hallucination (95% CI) | Coverage |
|---|---|---|---|---|
| Claude Opus 4.8 | **0.288** (0.182 – 0.394) | **0.341** (0.235 – 0.449) | 0.000 (by construction, not comparable) | 66/66 |
| Gemini 3.1 Pro | 0.258 (0.161 – 0.371) | 0.315 (0.210 – 0.426) | **0.161** (0.081 – 0.258) | 62/66 |
| Gemini 3.5 Flash | 0.258 (0.152 – 0.364) | 0.278 (0.178 – 0.389) | 0.545 (0.424 – 0.667) | 66/66 |

The corrected set is width-1-dominated, and accuracy still falls off with width (Opus w1 span-exact 0.326 → w4-6 0.000; same shape across all three models), replicating the earlier width-stratification observation.

**Hallucination definition (replaces the v1 "Phil. Safety" placeholder):** a row counts as hallucinated if the model's `restored_full` deviates from the masked input outside the marked lacuna span — i.e., the model "fixed" or changed a character it was supposed to leave alone. Implementation in [`research/v2/pipelines/lacuna_jury.py`](../research/v2/pipelines/lacuna_jury.py).

**Significance (paired bootstrap, 10 000 resamples, seed=42):**

| Comparison | Δ span-exact | Two-sided p | Significant at α=0.05? |
|---|---|---|---|
| Opus 4.8 − Gemini 3.1 Pro | +0.049 | 0.24 | no |
| Opus 4.8 − Gemini 3.5 Flash | +0.031 | 0.37 | no |
| Gemini 3.1 Pro − Gemini 3.5 Flash | −0.016 | 0.66 | no |

**Two findings (v2.0.3):**

*Finding C (corrected) — no model wins on accuracy; the task is data-bound, not architecture-bound.* All three span-exact deltas are non-significant (paired-bootstrap p = 0.24 / 0.37 / 0.66) and every model's accuracy CI overlaps every other's. No frontier model separates from the field on restoration accuracy — the same "data, not architecture" result the classifier gives in §2. The **only** dimension on which the models differ is hallucination: **Gemini 3.5 Flash alters context outside the span on 54.5 % of rows vs Gemini 3.1 Pro's 16.1 %** (non-overlapping CIs). The old "frontier reasoning model is significantly worse" claim is withdrawn — it was an artifact of empty completions being scored as hallucinations.

> **Independence caveat.** The v2.0.3 jury is 2×Google + 1×Anthropic, not three distinct lineages. The two Gemini raters agree with each other (0.339) far more than either agrees with Opus (0.18 – 0.24), so any Krippendorff α over this panel is **inflated by shared lineage** and should not be read as three-way independent agreement. Separately, **Opus ran as a direct agentic first-party rater** (blind to gold, scored after the run) because Opus is not enabled on the available Vertex projects — only Haiku 4.5 is; this is a documented deviation (PRE_REGISTRATION.md §B). Opus's **0.000 hallucination is by construction** — its `restored_full` is assembled mechanically — and is therefore **not comparable** to the free-generating Geminis.

*Finding D (corrected) — the three v2.0.3 models are indistinguishable on accuracy.* The old Gemini-vs-Llama non-finding no longer applies (those raters are not in the v2.0.3 panel). The current non-finding is stronger: **all three raters are statistically indistinguishable on span-exact** at n=66. A significant accuracy separation would require either a larger eval set (target n ≥ 200) or a genuinely larger effect.

## 4. Reproducibility

**What is reproducible from this repository today** (each step verified —
full guide in [`docs/REPRODUCE.md`](REPRODUCE.md)):

```bash
# Fetch the corpus from the Zenodo DOI (SHA256-verified):
python scripts/ops/fetch_data.py

# Re-derive the frozen split byte-identically (hashes in research/v2/data/SHA256SUMS):
python -m research.v2.pipelines.classify_split \
    --corpus research/data/openetruscan_clean.csv \
    --silver research/data/openetruscan_labels.csv \
    --out-train research/v2/data/classify_train_pool.jsonl \
    --out-test  research/v2/data/classify_test_v2.jsonl \
    --n-test 400 --seed 42

# Recompute the v2.0.3 lacuna metrics from the committed raw jury output:
python research/v2/eval/compute_lacuna_v2.py \
    --jury research/v2/results/lacuna/lacuna_jury_raw_v2_0_3_rerun.jsonl \
    --out /tmp/recheck.json   # diff-identical to research/v2/results/lacuna/lacuna_v2_0_3.json
```

**What is NOT re-runnable**: the jury API calls themselves. The Cloud Build
orchestration configs (`cloudbuild/v2-*.yaml`) were removed along with the
GCP project that hosted them — an earlier revision of this section presented
those as a working one-command reproduction path, which had been false since
the project's deletion. Re-running the jury requires a live Vertex project
and re-authoring the orchestration; the committed raw outputs + metrics under
[`research/v2/results/`](../research/v2/results/) are the audit trail. Seeds,
codebook version, model ids, and rater set are recorded inside each output
JSON.

## 5. Things that are NOT in this document

By design:
- No comparison against ByT5+LoRA until it is re-evaluated under the v2 protocol.
- No comparison against the v1 "0.99 macro F1" number, because that number was not produced on held-out data and is not a valid baseline.
- No claim that the v2 numbers are "good" or "state-of-the-art". They are honest numbers; whether they meet a particular bar is for downstream readers to decide.

Future v2.1 work (tracked in [`research/v2/README.md`](../research/v2/README.md)):
- ~~3-rater jury once Anthropic Vertex quota is granted.~~ **Done at v2.0.2** — Sonnet 4.6 was substituted for Opus per [`PRE_REGISTRATION.md`](../research/v2/PRE_REGISTRATION.md) Deviation §A; classifier Krippendorff α = 0.7649, full results in §2 and §3.
- Philologist adjudication of the queue rows, target Krippendorff α ≥ 0.80 between humans.
- Multi-language extension (Oscan, Faliscan, Raetian) using the same architecture.
- Lacuna eval set expansion to n ≥ 200 so the v2.0.3 raters (Opus 4.8 / Gemini 3.1 Pro / Gemini 3.5 Flash), currently indistinguishable on accuracy at n=66, can be tested for significance, and so a lineage-independent rater panel can replace the current 2×Google jury.
