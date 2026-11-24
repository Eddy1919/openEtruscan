# OpenEtruscan v2: Gold Annotation & Frozen Benchmarks

Three parallel streams that close the audit gaps identified against v1. The streams sit at different protocol versions: Stream A is at v2.0.4 (2026-08-08), Stream C at v2.0.3 (2026-07-04), and Stream B has not produced a frozen set.

| Stream | Goal (pre-registered) | Status |
|---|---|---|
| **A: Classification gold** | Gold labels for a 400-row test pool over 7 inscription-type classes; Krippendorff α ≥ 0.80 between two human philologists on a 30-row spot-check | **v2.0.4.** A 3-rater jury (Claude Opus 4.8, Gemini 3.1 Pro, Gemini 3.5 Flash) rated the text-disjoint 427-row test pool: **167 candidate-gold**, a **59-row adjudication queue**, **201 all-unsure**. Krippendorff α = 0.8557 between the LLM raters, inflated because two of the three are Gemini. Macro F1 on the 167 rows: CharCNN 0.399 [0.353, 0.435], TF-IDF+NB 0.293 [0.255, 0.329] (the figure Deviation §D designates citable), MicroTransformer 0.252, EmbeddingMLP 0.210. CharCNN beats the other three in paired bootstrap (p ≤ 0.0025). `votive` and `commercial` have no gold rows, so macro F1 is capped at 5/7 ≈ 0.714. The gold is LLM-consensus silver until two philologists ratify it ([handoff bundle](handoff/v2.0.4-etr/)). |
| **B: Rosetta-eval-v2** | At least 100 bilingual pairs (target 120), train-lemma excluded, paired-bootstrap significance | **Not run.** `pipelines/rosetta_mine_pairs.py` and `pipelines/verify_lemma_exclusion.py` exist, but there is no mining `make` target, no `data/rosetta_eval_v2.jsonl`, and no committed result. The frozen semantic benchmark is still the 22-pair `rosetta-eval-v1` test split ([`eval/`](../../eval/) at the repo root). Candidates for a larger set sit in [`../anchors/gold_glosses/`](../anchors/gold_glosses/): 319 records, 0 human-verified. |
| **C: Lacunae gold** | At least 150 editor-restored inscriptions; char-level accuracy and hallucination rate | **v2.0.3 re-run** on 66 dedup clean-gold tasks (below the 150 target). Span-exact: Opus 4.8 0.288, Gemini 3.1 Pro 0.258, Gemini 3.5 Flash 0.258; no paired difference is significant. Hallucination: Flash 0.545, Pro 0.161 (Opus 0.000 by construction, not comparable). Retrieval-augmented prompting lifts Flash from 0.258 to 0.379 (paired p = 0.025), see [`../experiments/lacuna_restoration_rag/`](../experiments/lacuna_restoration_rag/). The v2.0.2 "Finding C" (Sonnet 0.949 hallucination rate) is **retracted**: empty completions were scored as hallucinations (CHANGELOG, v2.0.3 evaluation-protocol entry; PRE_REGISTRATION Deviation §B). |

Evidence for the Stream A and C numbers is committed under [`results/`](results/) with SHA256 manifests.

## Design principles (frozen)

1. **Pre-registration.** Every metric, every baseline, every significance test is declared in [`PRE_REGISTRATION.md`](PRE_REGISTRATION.md) *before* the eval runs. If you change a metric after seeing results, you must bump to v2.1 and disclose.
2. **Seeded determinism.** All splits use `seed=42` and are produced by a single script. The generated JSONL files are committed; the script reproduces them byte-for-byte. Stream A splits are also text-disjoint: `classify_split.py` exits non-zero if any normalized text appears in both pools (Deviation §D).
3. **LLM-jury, not LLM-oracle.** Multiple frontier models label independently. Unanimous agreement → candidate gold. Split decision → adjudication queue for a human philologist. No single model is treated as ground truth.
4. **Train-lemma exclusion (Stream B).** No inscription containing any test-set lemma may appear in the fine-tuning corpus. Verified by [`pipelines/verify_lemma_exclusion.py`](pipelines/verify_lemma_exclusion.py).
5. **Bootstrap CIs on every reported metric.** 10,000 resamples. Reported as a point estimate with its 95% interval. Paired bootstrap for model comparisons; p < 0.05 required for any "X > Y" claim.

## Directory layout

```
research/v2/
├── README.md                    this file
├── PRE_REGISTRATION.md          frozen eval spec (metrics, baselines, sig tests) and Deviations log
├── Makefile                     pipeline targets (runbook below)
├── codebooks/
│   ├── README.md                codebook layout, per language
│   └── etr/                     Etruscan (v2.0 frozen)
│       ├── classification.md    7-class decision tree + edge cases
│       ├── rosetta.md           bilingual pair definition
│       └── lacunae.md           restoration evaluation protocol
├── configs/
│   └── etr.yaml                 corpus paths, class set, jury defaults
├── pipelines/
│   ├── _secrets.py              Secret Manager helper for the Gemini API key
│   ├── classify_split.py        frozen text-disjoint split
│   ├── classify_kfold.py        group-atomic stratified k-fold assignment (v2.1 candidate, not adopted)
│   ├── classify_jury.py         multi-model labeling (--language)
│   ├── classify_adjudicate.py   Krippendorff α + candidate-gold and queue builder
│   ├── classify_handoff.py      rebuilds handoff/v2.0.4-etr/ from committed evidence
│   ├── train_classifier.py      TF-IDF + NB baseline, bootstrap-CI eval
│   ├── train_neural.py          CharCNN / MicroTransformer / EmbeddingMLP, same eval
│   ├── rosetta_mine_pairs.py    bilingual pair extraction
│   ├── verify_lemma_exclusion.py  train/test lemma contamination check
│   ├── lacuna_mine.py           extract editor-restored examples
│   └── lacuna_jury.py          multi-model restoration (--language)
├── eval/
│   ├── bootstrap.py             resampling, paired tests, Krippendorff α
│   ├── classify_metrics.py      macro-F1, per-class P/R, confusion
│   ├── rosetta_metrics.py       P@k, semantic-field@k, paired delta
│   ├── lacuna_metrics.py        char-acc, hallucination-rate, span coverage
│   ├── compute_lacuna_v2.py     lacuna jury output → per-model metrics
│   ├── split_contamination.py   train/test text-overlap audit for a frozen split
│   ├── spotcheck_power.py       how often an n-row spot-check decides α ≥ 0.80 correctly
│   └── semantic_fields.json     frozen semantic-field vocabularies
├── data/
│   ├── README.md                split provenance and repair history
│   ├── SHA256SUMS
│   ├── classify_test_v2.jsonl   427-row text-disjoint test pool
│   └── classify_train_pool.jsonl  285-row train pool
├── docs/
│   └── ADJUDICATION_GUIDE.md    how a philologist works the queue
├── handoff/
│   ├── v2.0-etr/                superseded bundle (2-rater jury, 79-row queue)
│   └── v2.0.4-etr/              current bundle (59-row queue, two 30-row spot-checks)
└── results/
    ├── classify/                v2.0.4 jury raw, candidate gold, queue, metrics, predictions, paired bootstrap
    └── lacuna/                  v2.0.2 (retracted) and v2.0.3 jury output and metrics
```

## Language scope

Only Etruscan (`etr`) is implemented: `configs/etr.yaml` and `codebooks/etr/`. The Oscan, Faliscan and Raetian config and codebook placeholders were moved to [`../parked/v2-multilang/`](../parked/v2-multilang/) on 2026-07-17 because no corpus is ingested for those languages. Un-parking waits for a non-Etruscan corpus ingestion and for the Etruscan protocol to reach human-ratified gold ([`../parked/README.md`](../parked/README.md)).

`classify_jury.py` and `lacuna_jury.py` take `--language <iso>`, which loads `codebooks/<iso>/classification.md` or `lacunae.md`. `etr` is the only code with a codebook in this tree, so it is the only value that runs. The Etruscan inputs are the 6,567-row published corpus and its 712 silver labels.

## Runbook (operator view)

Run from the repo root. Targets that read the corpus need `research/data/openetruscan_clean.csv` (`python scripts/ops/fetch_data.py`).

```bash
# Stream A: classification
make -C research/v2 classify-split         # → data/classify_train_pool.jsonl, data/classify_test_v2.jsonl
make -C research/v2 classify-jury PROVIDERS="claude-opus-4-8 gemini-3.1-pro gemini-3.5-flash"
                                            # → results/classify/classify_jury_raw_v2_0_4.jsonl
                                            # needs VERTEX_PROJECT_ID; about $15 in API.
                                            # Without PROVIDERS the Makefile runs its older default roster.
make -C research/v2 classify-adjudicate    # → results/classify/classify_candidate_gold_v2_0_4.jsonl,
                                            #   classify_queue_v2_0_4.jsonl, classify_jury_summary_v2_0_4.json
make -C research/v2 classify-handoff       # → handoff/v2.0.4-etr/
# Two philologists work the 59-row queue and the 30-row dual-blind spot-check
# (handoff/v2.0.4-etr/README.md). No script merges their CSVs into a gold file yet.

# Classifier training and eval are not make targets (results/classify/README.md has the full command)
python -m research.v2.pipelines.train_classifier \
    --train-pool research/v2/data/classify_train_pool.jsonl \
    --eval-gold research/v2/results/classify/classify_candidate_gold_v2_0_4.jsonl \
    --out-metrics <metrics.json> --out-predictions <preds.jsonl>
# train_neural takes the same four flags plus --arch {charcnn,microtransformer,embedding-mlp}

# Stream B: no frozen pair set exists, so rosetta-exclude has nothing to check yet
make -C research/v2 rosetta-exclude        # needs data/rosetta_eval_v2.jsonl

# Stream C: lacunae
make -C research/v2 lacuna-mine            # → data/lacuna_raw_pairs.jsonl
make -C research/v2 lacuna-jury            # → data/lacuna_jury_raw.jsonl (same older default PROVIDERS)
python -m research.v2.eval.compute_lacuna_v2 --jury <raw jsonl> --out <metrics json>
                                            # the v2.0.3 Opus ratings were collected outside this script (Deviation §B)

# Utility
make -C research/v2 check-compile
make -C research/v2 bootstrap-selftest
make -C research/v2 clean                  # deletes data/*.jsonl, including the committed frozen split
```

## What "candidate gold" means

A row is **candidate gold** iff, across the whole jury (`pipelines/classify_adjudicate.py`):
- every rater returns the same label, that label is not `unsure`, and no rater hit an API error;
- every rater's confidence is `high` or `medium` (the schema-enforced levels are `high`/`medium`/`low`).

The pre-registered jury is three frontier LLMs from distinct training lineages. The v2.0.4 jury (Claude Opus 4.8 + Gemini 3.1 Pro + Gemini 3.5 Flash, all on Vertex AI) is 2×Google + 1×Anthropic, so agreement and α run higher than a three-lineage panel would give. Llama-family raters were unavailable on the billing project. The earlier 2-rater (v2.0.1) and Sonnet 4.6 / Gemini 2.5 Pro / Llama 4 Maverick (v2.0.2) juries are superseded; see `PRE_REGISTRATION.md` Deviations §A and §D.

Rows where the jury disagrees, or agrees with a low-confidence rating, go to the adjudication queue. Rows where every rater says `unsure` are set aside as all-unsure and are not in the queue. A philologist's verdict on a queue row (`accept`, `relabel`, `unsure` or `defect`, per [`docs/ADJUDICATION_GUIDE.md`](docs/ADJUDICATION_GUIDE.md)) is what moves it into the gold set.

At v2.0.4 the jury produced candidate gold for 167 of 427 rows (39%), queued 59 (14%), and set 201 (47%) aside as all-unsure.

Krippendorff α between two human adjudicators must reach ≥ 0.80 on the 30-row spot-check before the gold set ships. That check has not been done. Thirty rows decide that gate loosely: if the true α is 0.85 the point estimate falls below 0.80 a quarter of the time, and if it is 0.75 it passes 29% of the time (`eval/spotcheck_power.py`). The pre-registered gate is unchanged; `compute_alpha.py` now prints a bootstrap interval next to the estimate so a near-threshold result is read as such.

## Honest limitations

- **This is not gold yet.** The candidate-gold set is a 100% LLM-derived artifact that has *passed an inter-rater consensus filter*. It is publishable only as "LLM-consensus silver" until human philologists ratify.
- **No tactile or autopsy data.** Restoration evaluation is against editor-published readings, which are themselves scholarly conjecture for many fragmentary stones.
- **Class imbalance is structural.** `commercial` has 2 rows among the 712 silver labels, and `votive` and `commercial` have no candidate-gold rows at v2.0.4. Report per-class metrics and macro-F1 honestly, remember the 5/7 ceiling, and do not over-weight the dominant funerary class.
