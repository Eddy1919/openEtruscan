# OpenEtruscan Machine Learning: Methodology & Benchmarks

This document details the architectures, evaluation methodology, and benchmark results for epigraphic classification and lacuna restoration in OpenEtruscan. All protocols, frozen stratified splits, and metrics follow the pre-registered benchmark specification in [`research/v2/PRE_REGISTRATION.md`](../research/v2/PRE_REGISTRATION.md).

---

## 1. Evaluation Methodology

To ensure reproducibility and prevent data contamination, all evaluation adheres to three core principles:

1. **Text-Disjoint Frozen Splits**: Test partitions are sampled strictly across unique text groups rather than record IDs, guaranteeing zero lexical leakage between training and evaluation splits.
2. **Multi-Rater Consensus Annotation**: Ground-truth labels for low-resource epigraphic typology are generated through a multi-model consensus jury (Claude Opus 4.8, Gemini 3.1 Pro, Gemini 3.5 Flash) operating under a formalized philological codebook ([`research/v2/codebooks/etr/classification.md`](../research/v2/codebooks/etr/classification.md)). A record enters the candidate-gold set only upon unanimous agreement across independent raters (Krippendorff α = 0.8557).
3. **Statistical Significance via Bootstrap Resampling**: All reported metrics (Macro F1, accuracy, span exact-match) include empirical 95% bootstrap confidence intervals computed over 10,000 resamples (seed 42). Pairwise architecture comparisons report two-sided paired bootstrap p-values.

---

## 2. Inscription Typology Classification (7-Class Task)

### 2.1 Task & Dataset Setup

- **Task Definition**: Predict the functional and thematic typology of an Etruscan inscription among 7 standardized classes: `funerary`, `ownership`, `dedicatory`, `boundary`, `legal`, `votive`, and `commercial`.
- **Training Set**: 285 silver-labeled inscriptions from the text-disjoint training pool ([`research/v2/data/classify_train_pool.jsonl`](../research/v2/data/classify_train_pool.jsonl)).
- **Candidate-Gold Test Set**: 167 held-out inscriptions from the text-disjoint 427-row stratified test split ([`research/v2/data/classify_test_v2.jsonl`](../research/v2/data/classify_test_v2.jsonl)), validated by unanimous consensus among three independent raters.
- **Class Distribution (Gold)**: `funerary` (77), `ownership` (55), `dedicatory` (25), `boundary` (6), `legal` (4), `votive` (0), `commercial` (0). *Note: Macro F1 averages across all 7 classes; zero support in the tail classes caps the achievable macro F1 on this set at ~0.714.*

### 2.2 Model Architectures

1. **CharCNN (28K parameters)**: 1D character-level convolutional neural network with multi-width filters (kernel sizes 2, 3, 4, 5) and max-pooling, designed to detect morpho-phonotactic affixes (e.g., `-al`, `-as`, `-ce`, `mi...`).
2. **TF-IDF + Multinomial Naive Bayes (~3K features)**: Character 2–4-gram TF-IDF vectorizer (max 3,000 features, α=0.1) shipped in `src/openetruscan/ml/classifier.py`.
3. **MicroTransformer (274K parameters)**: 2-layer character-level transformer encoder with learned positional encodings.
4. **EmbeddingMLP (58K parameters + encoder)**: Frozen multilingual MiniLM (384-d) dense embeddings feeding a 2-layer MLP head.

### 2.3 Benchmark Results

Evaluated on the 167-row candidate-gold test split (10,000-resample bootstrap, seed 42):

| Architecture | Parameters | Macro F1 (95% CI) | Accuracy | Head-2 F1 | Tail-5 F1 |
|---|---|---|---|---|---|
| **CharCNN** | 28K | **0.399** (0.353 – 0.435) | 0.665 | 0.737 | 0.264 |
| **TF-IDF + Naive Bayes** | ~3K | **0.293** (0.255 – 0.329) | 0.755 | 0.810 | 0.087 |
| **MicroTransformer** | 274K | **0.252** (0.140 – 0.338) | 0.317 | 0.384 | 0.200 |
| **EmbeddingMLP** (MiniLM) | 58K + encoder | **0.210** (0.181 – 0.242) | 0.641 | 0.696 | 0.015 |

### 2.4 Key Findings

- CharCNN outperforms both TF-IDF+NB (Δ = +0.106, p = 0.0025) and MicroTransformer (Δ = +0.147, p = 0.0023). Its 1D convolutions pick up the prefixal and suffixal markers (`mi...al`, `tular`, `-ce`) that carry epigraphic formula structure.
- The frozen multilingual MiniLM embeddings score lowest of the four architectures (Δ = −0.083 vs TF-IDF+NB, p < 0.0001): a modern multilingual encoder does not represent fragmented ancient Italic morphology well.
- Dominant classes are well-modeled (`funerary` F1 0.88, `ownership` F1 0.74); the tail categories (`boundary`, `legal`, `votive`, `commercial`) stay data-starved regardless of architecture.

---

## 3. Lacuna Restoration

### 3.1 Task & Benchmark Setup

- **Task Definition**: Given an inscription with a marked Leiden-convention lacuna of known character width (e.g., `larθ[a]l`), restore the most probable missing characters.
- **Evaluation Set**: 66 clean-gold restoration tasks from the deduplicated corpus, filtered to exclude unconstrained continuation markers (`---`). 43 of 66 tasks represent single-character lacunae (width-1).
- **Metric Definitions**:
  - **Span Exact-Match**: Complete sequence match over the lacuna span.
  - **Top-1 Character Accuracy**: Character-level accuracy within the restored span.
  - **Hallucination Rate**: Percentage of instances where the model modifies or corrupts characters *outside* the designated lacuna span.

### 3.2 Benchmark Results

Evaluated across 66 clean-gold tasks (10,000-resample bootstrap, seed 42):

| Model | Span Exact-Match (95% CI) | Top-1 Char Acc (95% CI) | Hallucination Rate (95% CI) | Coverage |
|---|---|---|---|---|
| **Claude Opus 4.8** | **0.288** (0.182 – 0.394) | **0.341** (0.235 – 0.449) | 0.0% (constrained assembly) | 66/66 |
| **Gemini 3.1 Pro** | 0.258 (0.161 – 0.371) | 0.315 (0.210 – 0.426) | **16.1%** (0.081 – 0.258) | 62/66 |
| **Gemini 3.5 Flash** | 0.258 (0.152 – 0.364) | 0.278 (0.178 – 0.389) | 54.5% (0.424 – 0.667) | 66/66 |

### 3.3 Statistical Comparisons & Observations

| Pairwise Comparison | Δ Span Exact-Match | Two-Sided p-value | Significant (α = 0.05)? |
|---|---|---|---|
| Claude Opus 4.8 vs Gemini 3.1 Pro | +0.049 | 0.24 | No |
| Claude Opus 4.8 vs Gemini 3.5 Flash | +0.031 | 0.37 | No |
| Gemini 3.1 Pro vs Gemini 3.5 Flash | −0.016 | 0.66 | No |

- No pair of models separates on span exact-match at this sample size (n=66); all three pairwise CIs overlap.
- Hallucination rate is where the models actually differ: Gemini 3.5 Flash alters text outside the marked lacuna on 54.5% of rows against Gemini 3.1 Pro's 16.1%, and the two confidence intervals (0.424–0.667 vs 0.081–0.258) do not overlap.

---

## 4. Reproducing Results

All splits, raw model outputs, and calculation scripts are tracked in git with SHA-256 integrity verification:

```bash
# 1. Fetch corpus data from Zenodo
python scripts/ops/fetch_data.py

# 2. Re-derive the text-disjoint classification split (seed 42)
python -m research.v2.pipelines.classify_split \
    --corpus research/data/openetruscan_clean.csv \
    --silver research/data/openetruscan_labels.csv \
    --out-train research/v2/data/classify_train_pool.jsonl \
    --out-test  research/v2/data/classify_test_v2.jsonl \
    --n-test 400 --seed 42

# 3. Verify SHA-256 manifests (entries mix repo-root-relative and local paths)
shasum -a 256 -c <(grep ' research/data/' research/v2/data/SHA256SUMS)
(cd research/v2/data && shasum -a 256 -c <(grep -v ' research/data/' SHA256SUMS))

# 4. Recompute lacuna metrics from committed raw outputs
python research/v2/eval/compute_lacuna_v2.py \
    --jury research/v2/results/lacuna/lacuna_jury_raw_v2_0_3_rerun.jsonl \
    --out /tmp/lacuna_eval.json
```

For complete step-by-step reproduction instructions, refer to [`docs/REPRODUCE.md`](REPRODUCE.md).
