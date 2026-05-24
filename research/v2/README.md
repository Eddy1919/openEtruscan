# OpenEtruscan v2 — Gold Annotation & Frozen Benchmarks

Three parallel streams that close the audit gaps identified against v1:

| Stream | Goal | Status (v2.0.2, 2026-05-24) |
|---|---|---|
| **A — Classification gold** | 2,000 gold rows over 7 inscription-type classes with Krippendorff α ≥ 0.80 | **143 candidate-gold rows shipped** (3-rater jury, Krippendorff α = 0.7649); 99-row adjudication queue awaiting philologist α ≥ 0.80 spot-check |
| **B — Rosetta-eval-v2** | 100+ bilingual pairs, train-lemma excluded, paired-bootstrap significance | scaffolding ready; mining pipeline in `pipelines/rosetta_mine_pairs.py` |
| **C — Lacunae gold** | 100–200 editor-restored inscriptions with hallucination metric | **118-row 3-rater jury shipped** (Gemini 0.220 span-exact / Llama 0.170 / Sonnet 0.051); **Finding C** — Sonnet hallucinates at 0.949 (95 % CI 0.907–0.983), significantly worse than Gemini & Llama at *p* < 0.001 |

## Design principles (frozen)

1. **Pre-registration.** Every metric, every baseline, every significance test is declared in [`PRE_REGISTRATION.md`](PRE_REGISTRATION.md) *before* the eval runs. If you change a metric after seeing results, you must bump to v2.1 and disclose.
2. **Seeded determinism.** All splits use `seed=42` and are produced by a single script. The generated JSONL files are committed; the script reproduces them byte-for-byte.
3. **LLM-jury, not LLM-oracle.** Multiple frontier models label independently. Unanimous agreement → candidate gold. Split decision → adjudication queue for a human philologist. No single model is treated as ground truth.
4. **Train-lemma exclusion.** No inscription containing any test-set lemma may appear in the fine-tuning corpus. Verified by [`pipelines/verify_lemma_exclusion.py`](pipelines/verify_lemma_exclusion.py).
5. **Bootstrap CIs on every reported metric.** 10,000 resamples. Reported as `point ± half-CI (95%)`. Paired bootstrap for model comparisons; p < 0.05 required for any "X > Y" claim.

## Directory layout

```
research/v2/
├── README.md                    this file
├── PRE_REGISTRATION.md          frozen eval spec (metrics, baselines, sig tests)
├── codebooks/                   annotation protocols, ONE DIR PER LANGUAGE
│   ├── README.md                multi-language overview
│   ├── etr/                     Etruscan (v2.0 frozen)
│   │   ├── classification.md    7-class decision tree + edge cases
│   │   ├── rosetta.md           bilingual pair definition
│   │   └── lacunae.md           restoration evaluation protocol
│   ├── osc/  README.md          Oscan (scaffold; codebooks TODO)
│   ├── fal/  README.md          Faliscan (scaffold; codebooks TODO)
│   └── rae/  README.md          Raetian (scaffold; codebooks TODO)
├── configs/                     per-language pipeline configuration
│   ├── etr.yaml                 active; corpus paths + class set + jury defaults
│   ├── osc.yaml                 stub
│   ├── fal.yaml                 stub
│   └── rae.yaml                 stub
├── pipelines/                   language-agnostic; pass --language=<iso>
│   ├── classify_split.py        frozen stratified split
│   ├── classify_jury.py         multi-model labeling (--language)
│   ├── classify_adjudicate.py   Krippendorff α + queue builder
│   ├── rosetta_mine_pairs.py    bilingual pair extraction
│   ├── verify_lemma_exclusion.py  train/test contamination check
│   ├── lacuna_mine.py           extract editor-restored examples
│   ├── lacuna_jury.py           multi-model restoration (--language)
│   └── train_classifier.py      v2 classifier training + bootstrap-CI eval
├── eval/                        bootstrap-CI eval harness (language-agnostic)
│   ├── bootstrap.py             reusable resampling + paired tests
│   ├── classify_metrics.py      macro-F1, per-class P/R, confusion
│   ├── rosetta_metrics.py       P@k, semantic-field@k, paired delta
│   └── lacuna_metrics.py        char-acc, hallucination-rate, span coverage
├── data/                        produced artifacts (frozen splits, gold sets)
│   └── .gitkeep
└── docs/
    ├── ADJUDICATION_GUIDE.md    how a philologist works the queue
    └── RUNBOOK.md               step-by-step operator instructions
```

## Multi-language scope

The architecture supports four ancient Italic languages out of the same harness:

| Language | ISO | Status | Approx corpus |
|---|---|---|---|
| Etruscan | `etr` | **v2.0 frozen**; 400-row test set; classifier macro F1 = 0.31 ± 0.04 | ~6,500 inscriptions |
| Oscan | `osc` | scaffold (config + README); codebooks TODO | ~600 inscriptions (Crawford 2011) |
| Faliscan | `fal` | scaffold; codebooks TODO | ~400 inscriptions (Bakkum 2009) |
| Raetian | `rae` | scaffold; codebooks TODO | ~400 inscriptions (Schumacher 2004) |

The eval harness (bootstrap, classify_metrics, lacuna_metrics) is language-agnostic. Adding Oscan etc. is: draft codebook → fill out config YAML → stage corpus in `gs://openetruscan-rosetta/corpus/` → re-run the same Cloud Build with `--substitutions=_LANGUAGE=osc`. Zero pipeline changes.

## End-to-end runbook (operator view)

```bash
# Stream A — Classification
make -C research/v2 classify-split         # → data/classify_train.jsonl, classify_test.jsonl
make -C research/v2 classify-jury          # → data/classify_jury_raw.jsonl  (~$15 in API at 2-rater jury)
make -C research/v2 classify-adjudicate    # → data/classify_candidate_gold.jsonl
                                            # + data/classify_adjudication_queue.jsonl
# Philologists work the queue (~79 disagreement rows + 30-row dual-blind spot-check; ≈5-7 hours per philologist)
make -C research/v2 classify-merge         # → data/classify_gold_v2.jsonl
make -C research/v2 classify-eval BASELINE=charcnn EXPERIMENTAL=embedding_mlp

# Stream B — Rosetta-eval-v2
make -C research/v2 rosetta-mine           # → data/rosetta_pairs_raw.jsonl
make -C research/v2 rosetta-exclude        # → data/rosetta_eval_v2.jsonl (lemma-clean)
make -C research/v2 rosetta-eval BASELINE=labse EXPERIMENTAL=etr_lora_v4

# Stream C — Lacunae
make -C research/v2 lacuna-mine            # → data/lacuna_raw_pairs.jsonl
make -C research/v2 lacuna-jury            # → data/lacuna_jury_raw.jsonl
make -C research/v2 lacuna-adjudicate      # → data/lacuna_candidate_gold.jsonl
make -C research/v2 lacuna-eval MODEL=byt5
```

## What "candidate gold" means

A row is **candidate gold** iff:
- All raters in the active jury independently produce the same label (target jury: 3 frontier LLMs from distinct training lineages; **v2.0.1 deviation**: shipped with 2 raters, Gemini 2.5 Pro + Llama 4 Maverick, because Claude Vertex quota was unavailable at run time — see `PRE_REGISTRATION.md` §Deviations §A).
- Every rater returns confidence ≥ medium (the schema-enforced confidence levels are `high`/`medium`/`low`).
- The row's text passes the "non-trivial signal" check (length > 5 chars, not pure name-only fragment unless context disambiguates).

Everything else lands in the adjudication queue, stratified by class so philologists see a balanced sample. Once a human signs off on a queue row (`accept`, `reject`, `relabel`), it joins the gold set with `signal_source = gold:human_adjudicated`.

This is the standard pattern used at frontier labs (Anthropic's Constitutional AI rubric work, DeepMind's medical-imaging annotation pipelines): models do the easy 60–80%, humans do the hard 20–40%. Krippendorff α between human adjudicators must reach ≥ 0.80 before the gold set ships.

## Honest limitations

- **This is not gold yet.** The candidate-gold set is a 100% LLM-derived artifact that has *passed an inter-rater consensus filter*. It is publishable only as "LLM-consensus silver" until human philologists ratify.
- **No tactile or autopsy data.** Restoration evaluation is against editor-published readings, which are themselves scholarly conjecture for many fragmentary stones.
- **Class imbalance is structural.** With ~2 commercial inscriptions known in the entire corpus, no amount of annotation will produce a balanced 7-class problem. Report per-class metrics and macro-F1 honestly; do not over-weight the dominant funerary class.
