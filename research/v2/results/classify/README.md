# Stream A evidence: v2.0.4 classification re-run (2026-08-08)

Committed raw evidence for the v2.0.4 clean re-run. Everything here is
reproducible from the frozen split + this jury raw file; nothing lives only
in cloud storage. (The v2.0.2 equivalents lived only in a retired project's
GCS bucket and are unrecoverable. That loss is why this directory exists.)

## Why v2.0.4 exists

The v2.0.2 numbers were measured on an id-disjoint but text-contaminated
split (PRE_REGISTRATION.md Deviation §D): 25/400 test rows repeated a
train-pool text under a different id, and the leak concentrated in the
unanimous candidate-gold subset the metric was scored on. v2.0.4 re-runs
Stream A end-to-end on the text-disjoint 427/285 split with a fresh jury.

## Provenance

| Component | v2.0.2 (superseded) | v2.0.4 (this directory) |
|---|---|---|
| Split | 400 test / 312 train, id-disjoint only, 25 leaked texts | 427 test / 285 train, text-disjoint (0 leaked) |
| Jury | Sonnet 4.6 + Gemini 2.5 Pro + Llama 4 Maverick | Opus 4.8 + Gemini 3.1 Pro + Gemini 3.5 Flash (Vertex, 2026-08-08, 1,281 ratings, 0 API errors) |
| Krippendorff α | 0.7649 | **0.8557** (lineage caveat: 2 of 3 raters are Gemini, and shared lineage inflates α; same caveat as the v2.0.3 lacuna panel) |
| Candidate-gold | n=143 (labels LOST with retired project) | **n=167** (committed here) |
| Queue / all-unsure | 79 / 178 | 59 / 201 |

Candidate-gold class support: funerary 77, ownership 55, dedicatory 25,
boundary 6, legal 4, **votive 0, commercial 0**. `macro_f1` averages over
all 7 codebook classes regardless of support (`eval/classify_metrics.py`),
so the two absent classes contribute structural zeros; the ceiling of the
metric on this gold set is 5/7 ≈ 0.714. The v2.0.2 numbers used the same
convention.

## Results (train = 285 clean rows; eval = 167 candidate-gold; 10,000-resample bootstrap, seed=42)

| Architecture | Macro F1 (95% CI) | Accuracy | v2.0.2 (contaminated split, lost gold) |
|---|---|---|---|
| **CharCNN** | **0.399** (0.353 – 0.435) | 0.665 | 0.369 (0.257 – 0.432) |
| TF-IDF + Multinomial NB | 0.293 (0.255 – 0.329) | 0.755 | 0.313 (0.273 – 0.348) |
| MicroTransformer | 0.252 (0.140 – 0.338) | 0.317 | 0.317 (0.202 – 0.404) |
| EmbeddingMLP (MiniLM) | 0.210 (0.181 – 0.242) | 0.641 | 0.124 (0.099 – 0.149) |

The v2.0.2 column is **not directly comparable**: different gold set (lost),
different jury, contaminated train pool. It is shown as the historical record
the new numbers replace, not as a controlled before/after.

Paired bootstrap on macro F1, same 167 rows (`paired_bootstrap_v2_0_4.json`;
one-sided p, seed=42):

| Comparison | Δ point | 95% CI | p |
|---|---|---|---|
| CharCNN vs TF-IDF+NB | +0.106 | [+0.055, +0.149] | **0.0025** |
| CharCNN vs MicroTransformer | +0.147 | [+0.050, +0.264] | **0.0023** |
| TF-IDF+NB vs EmbeddingMLP | +0.083 | [+0.044, +0.122] | **<0.0001** |
| TF-IDF+NB vs MicroTransformer | +0.041 | [−0.049, +0.157] | 0.172 (n.s.) |

**Finding A (v2.0.2, "architecture-invariance among local-feature models")
does not replicate at v2.0.4**: CharCNN now beats both TF-IDF+NB and
MicroTransformer at p < 0.005 (paired). **Finding B (out-of-distribution
dense embeddings underperform) replicates**: EmbeddingMLP is still last on
macro F1 and significantly below TF-IDF+NB, though the gap narrowed
(0.083 vs the ~0.19 marginal gap at v2.0.2).

## Files

| File | What |
|---|---|
| `classify_jury_raw_v2_0_4.jsonl` | 1,281 rows: every (rater, inscription) judgment with rationale |
| `classify_candidate_gold_v2_0_4.jsonl` | 167 unanimous rows with `gold_label` |
| `classify_queue_v2_0_4.jsonl` | 59 disagreement rows for the philologist queue |
| `classify_jury_summary_v2_0_4.json` | α, per-class α, disagreement pairs |
| `metrics_*_v2_0_4.json` | Bootstrap-CI'd metrics per architecture |
| `preds_*_v2_0_4.jsonl` | Per-row predictions per architecture |
| `paired_bootstrap_v2_0_4.json` | Pairwise Δ macro-F1 tests |
| `SHA256SUMS` | Pins for everything above |

Caveats that must travel with any citation of these numbers: candidate-gold
is **LLM-consensus silver, not philologist-ratified gold** (the human
ratification bundle is [`../../handoff/v2.0.4-etr/`](../../handoff/v2.0.4-etr/));
the jury panel is 2×Google + 1×Anthropic, so α is lineage-inflated; and
votive/commercial have zero gold support, so macro F1 is bounded at ~0.714.

## Reproduce

```bash
make -C research/v2 classify-adjudicate classify-handoff   # from committed jury raw
python -m research.v2.pipelines.train_classifier \
    --train-pool research/v2/data/classify_train_pool.jsonl \
    --eval-gold research/v2/results/classify/classify_candidate_gold_v2_0_4.jsonl \
    --out-metrics /tmp/m.json --out-predictions /tmp/p.jsonl
```

Re-running the jury itself costs ~$15 of API and requires Vertex access
(`make -C research/v2 classify-jury PROVIDERS="claude-opus-4-8 gemini-3.1-pro gemini-3.5-flash"`,
with `VERTEX_PROJECT_ID` set to a project with the models enabled).
