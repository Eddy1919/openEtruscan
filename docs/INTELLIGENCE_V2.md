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

**Task.** Given an inscription with a marked Leiden-notation lacuna of known character width, produce the character sequence most likely to have been there. Scored against the editor's published restoration.

**Eval set.** 118 inscriptions mined from the corpus where the editor proposed a specific restoration (`[abc]`-style brackets). Gold filtered to drop trailing dash markers (`reri---` = "more destroyed text continues here", unscoreable) and editorial digit annotations.

**Models compared (v2.0.2 — 3-rater).** Claude Sonnet 4.6 (`claude-sonnet-4-6@vertex-anthropic`), Gemini 2.5 Pro (`gemini-2.5-pro`), Llama 4 Maverick (`llama-4-maverick-17b-128e-instruct-maas`), all on Vertex AI in `europe-west1` / MaaS region `us-east5`. ByT5+LoRA (the model the v1 doc highlighted) is not included in this comparison — it will be re-evaluated under the same protocol when its checkpoint is re-exported. v2.0.1 (Gemini + Llama only, 2-rater) is superseded; the v2.0.1 outputs remain in GCS for audit.

**Headline results (bootstrap, 10 000 resamples, seed=42, n=118 per model):**

| Model | Span exact-match (95% CI) | Char acc top-1 (95% CI) | Char acc top-3 (95% CI) | Hallucination rate (95% CI) |
|---|---|---|---|---|
| Gemini 2.5 Pro | **0.220** (0.144 – 0.297) | **0.245** (0.172 – 0.321) | **0.415** (0.330 – 0.501) | **0.271** (0.195 – 0.356) |
| Llama 4 Maverick | 0.170 (0.102 – 0.237) | 0.189 (0.123 – 0.259) | 0.304 (0.227 – 0.381) | 0.627 (0.542 – 0.712) |
| Claude Sonnet 4.6 | 0.051 (0.017 – 0.093) | 0.055 (0.017 – 0.098) | 0.066 (0.025 – 0.112) | **0.949** (0.907 – 0.983) |

**Width-stratified char accuracy (Gemini):**

| Width bucket | n | char_acc_top1 | span_exact | hallucination |
|---|---|---|---|---|
| w1 (1 character) | 75 | 0.293 | 0.293 | 0.293 |
| w2_3 | 35 | 0.190 | 0.114 | 0.286 |
| w4_6 | 8 | 0.031 | 0.000 | 0.000 |
| w7+ | 0 | n/a | n/a | n/a |

The task is mostly tractable for single-character gaps and falls off sharply with width. This replicates the v2.0.1 width-stratification finding.

**Hallucination definition (replaces the v1 "Phil. Safety" placeholder):** a row counts as hallucinated if the model's `restored_full` deviates from the masked input outside the marked lacuna span — i.e., the model "fixed" or changed a character it was supposed to leave alone. Implementation in [`research/v2/pipelines/lacuna_jury.py`](../research/v2/pipelines/lacuna_jury.py).

**Significance (paired-bootstrap, n=65 shared subset where all three raters' gold survived the filter):**

| Comparison | Δ span-exact | 95% CI | Two-sided p | Significant at α=0.05? |
|---|---|---|---|---|
| Gemini − Sonnet | **+0.169** | [+0.092, +0.262] | **< 0.001** | yes |
| Llama − Sonnet | **+0.123** | [+0.031, +0.215] | **≈ 0.002** | yes |
| Gemini − Llama | +0.046 | [−0.077, +0.185] | ≈ 0.57 | no |

**Two findings, both new at v2.0.2 or strengthened from v2.0.1:**

*Finding C — Sonnet's reasoning capacity does not transfer to lacuna restoration.* Sonnet's 0.949 hallucination rate (95% CI [0.907, 0.983]) means it changes at least one character outside the marked lacuna on 95 of every 100 inscriptions. It interprets the task as "fix this damaged Etruscan text" rather than "fill the masked span and leave the rest byte-identical", despite an explicit hard-rule in the prompt. The same prompt to Gemini and Llama yields 0.271 and 0.627 hallucination rates respectively. **This is the strongest model-capability finding in v2** — a frontier reasoning model is *significantly worse* than two general-purpose models on a structured-edit task, because the structured-edit constraint is exactly the kind of instruction-following that fine-grained "creative" reasoning erodes.

*Finding D — Gemini vs Llama is still not separable at n=118.* Δ span-exact = +0.046, two-sided p ≈ 0.57. A genuinely significant Gemini-vs-Llama claim would require either a larger eval set (target n ≥ 200) or a tighter difference. v2.0.1 reported the same non-finding.

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
- ~~3-rater jury once Anthropic Vertex quota is granted.~~ **Done at v2.0.2** — Sonnet 4.6 was substituted for Opus per [`PRE_REGISTRATION.md`](../research/v2/PRE_REGISTRATION.md) Deviation §A; classifier Krippendorff α = 0.7649, full results in §2 and §3.
- Philologist adjudication of the queue rows, target Krippendorff α ≥ 0.80 between humans.
- Multi-language extension (Oscan, Faliscan, Raetian) using the same architecture.
- Lacuna eval set expansion to n ≥ 200 so Gemini vs Llama can be tested for significance.
