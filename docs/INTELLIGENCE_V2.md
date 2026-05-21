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

**Architecture.** TF-IDF (character 2–4-grams, max 3000 features, min_df=2) + Multinomial Naive Bayes (α=0.1). Identical to the v1 production architecture under `src/openetruscan/ml/classifier.py`. Reusing the v1 architecture deliberately so that the rigor delta between v1 and v2 is in the *evaluation*, not the *model*.

**Training data.** 282 silver-labeled inscriptions from the v1 reasoning-cascade output (`research/data/openetruscan_labels.csv`), filtered to those NOT in the v2 frozen test split.

**Evaluation data.** 159 candidate-gold inscriptions, drawn from a 400-row stratified test split of the corpus and labeled by an LLM jury (Gemini 2.5 Pro + Llama 4 Maverick) under the codebook at [`research/v2/codebooks/classification.md`](../research/v2/codebooks/classification.md). A row enters candidate-gold only if both raters agreed at confidence ≥ medium.

**Headline results (10 000-resample bootstrap, seed=42):**

| Metric | Point | 95% CI |
|---|---|---|
| Macro F1 | 0.312 | [0.273, 0.344] |
| Accuracy | 0.767 | [0.698, 0.830] |
| Head-2 F1 (`funerary` + `ownership`) | 0.829 | [0.770, 0.880] |
| Tail-5 F1 (rare classes) | 0.105 | [0.061, 0.140] |

**Per-class:** `funerary` F1 0.87, `ownership` F1 0.79, `dedicatory` F1 0.53, `boundary`/`legal` F1 0.00 (both predict-zero failures), `votive`/`commercial` n=0 in the eval set.

**Honest interpretation.** The architecture works for the two dominant classes and fails on the rare classes. This matches the long-standing finding in `research/CURATION_FINDINGS.md` that the bottleneck is *data*, not *architecture* — three different architectures (CharCNN, MicroTransformer, linear head over embeddings) all produced macro F1 in the 0.25–0.32 band on truly held-out data. The path to better numbers runs through more annotated data, not better models.

## 3. v2 lacuna restoration

**Task.** Given an inscription with a marked Leiden-notation lacuna of known character width, produce the character sequence most likely to have been there. Scored against the editor's published restoration.

**Eval set.** 118 inscriptions mined from the corpus where the editor proposed a specific restoration (`[abc]`-style brackets). Gold filtered to drop trailing dash markers (`reri---` = "more destroyed text continues here", unscoreable) and editorial digit annotations.

**Models compared:** Gemini 2.5 Pro and Llama 4 Maverick, both via Vertex AI. ByT5+LoRA (the model the v1 doc highlighted) is not included in this comparison — it will be re-evaluated under the same protocol when its checkpoint is re-exported.

**Headline results (bootstrap, 10 000 resamples, seed=42):**

| Model | Span exact-match (95% CI) | Char acc top-1 (95% CI) | Hallucination rate (95% CI) |
|---|---|---|---|
| Gemini 2.5 Pro | 0.254 (0.178 – 0.339) | 0.278 (0.202 – 0.358) | 0.356 (0.271 – 0.441) |
| Llama 4 Maverick | 0.195 (0.127 – 0.263) | 0.215 (0.146 – 0.288) | 0.610 (0.525 – 0.695) |

**Width-stratified char accuracy (Gemini):**

| Width bucket | n | char_acc_top1 | span_exact |
|---|---|---|---|
| w1 (1 character) | 75 | 0.293 | 0.293 |
| w2_3 | 35 | 0.274 | 0.200 |
| w4_6 | 8 | 0.150 | 0.125 |
| w7+ | 0 | n/a | n/a |

The task is mostly tractable for single-character gaps and falls off sharply with width. This is a real finding.

**Hallucination definition (replaces the v1 "Phil. Safety" placeholder):** a row counts as hallucinated if the model's `restored_full` deviates from the masked input outside the marked lacuna span — i.e., the model "fixed" or changed a character it was supposed to leave alone. Implementation in [`research/v2/pipelines/lacuna_jury.py`](../research/v2/pipelines/lacuna_jury.py).

**Significance.** Paired-bootstrap test on the 65 inscriptions where both raters' gold survived the filter: Δ(Gemini − Llama) span-exact = +0.062, 95% CI [−0.062, +0.185], **p = 0.20**. We cannot claim Gemini outperforms Llama on this task at the current sample size. A genuinely significant claim would require either a larger eval set (target n ≥ 200) or a tighter difference.

## 4. Reproducibility

Everything in this document is reproducible from a single Cloud Build invocation:

```bash
# Re-derive the frozen split + jury + adjudicated outputs:
gcloud builds submit . \
  --project=long-facet-427508-j2 \
  --config=cloudbuild/v2-classify-jury.yaml

# Retrain the classifier and re-derive the metrics in this document:
gcloud builds submit . \
  --project=long-facet-427508-j2 \
  --config=cloudbuild/v2-train-classifier.yaml

# Same for lacunae:
gcloud builds submit . \
  --project=long-facet-427508-j2 \
  --config=cloudbuild/v2-lacuna-jury.yaml
```

Outputs land at `gs://long-facet-427508-j2_cloudbuild/openetruscan-v2/...` with UTC timestamp prefixes; the latest run's prefix is recorded in the README's "What's new" section. Seeds, codebook version, model ids, and rater set are recorded inside each output JSON.

## 5. Things that are NOT in this document

By design:
- No comparison against ByT5+LoRA until it is re-evaluated under the v2 protocol.
- No comparison against the v1 "0.99 macro F1" number, because that number was not produced on held-out data and is not a valid baseline.
- No claim that the v2 numbers are "good" or "state-of-the-art". They are honest numbers; whether they meet a particular bar is for downstream readers to decide.

Future v2.1 work (tracked in [`research/v2/README.md`](../research/v2/README.md)):
- 3-rater jury once Anthropic Vertex quota is granted.
- Philologist adjudication of the 79-row queue rows, target Krippendorff α ≥ 0.80 between humans.
- Multi-language extension (Oscan, Faliscan, Raetian) using the same architecture.
