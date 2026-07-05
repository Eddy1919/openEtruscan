# Retrieval-Augmented Lacuna Restoration (Aeneas-style)

## Question

Does retrieving parallel inscriptions as in-context evidence lift Etruscan
lacuna restoration over single-shot prompting — the way Ithaca/Aeneas
(Assael et al. 2022; DeepMind 2025) use parallels for Greek/Latin? And is the
lift genuine generalization or just copying an attested answer?

## Motivation

The v2.0.3 lacuna re-run (see CHANGELOG `[2.0.3]` and `../../v2/README.md`) found
its three raters — Claude Opus 4.8 (0.288), Gemini 3.1 Pro (0.258), and Gemini
3.5 Flash (0.258) — tied at ~0.26–0.29 span-exact single-shot (all differences
non-significant); the task is data/difficulty-bound. The RAG A/B below is run on
the two Gemini models (Opus served as a manual direct rater in the jury re-run,
not through this scripted RAG harness).
Etruscan is highly **formulaic** (`mi mlaχ mlakas`, `lautn`/`lautni`,
onomastic + funerary templates), so the missing signal for a single-shot model
is often *attested elsewhere in the corpus*. This tests whether automated
retrieval of that attestation closes the gap.

## Method

- **Test set:** the frozen 66 clean-gold tasks from v2.0.3 (deduplicated,
  width-1-dominated: 43/66 are single-character gaps). Gold is the editor's
  published restoration.
- **Retriever:** char-3-gram cosine over the full public corpus
  (5,932 canonical inscriptions, pulled from `www.openetruscan.com/api/search`),
  top-k=8. **Leakage-excluded:** the target inscription and any near-duplicate
  whose normalized text contains (or is contained by) the gold-filled target
  are dropped before ranking.
- **Restorer:** the same models scored single-shot in v2.0.3 (Gemini 3.1 Pro,
  Gemini 3.5 Flash), model held constant so any lift is attributable to
  retrieval alone. The RAG prompt adds a "Parallel inscriptions" block; the
  single-shot prompt is identical minus that block.
- **Significance:** paired bootstrap, 10 000 resamples, seed=42, on the rows
  each model answered under both conditions.

## Results

Span-exact, same 66-task gold, model held constant:

| Model            | Single-shot | +RAG (k=8) | Δ (paired bootstrap) |
|------------------|------------:|-----------:|----------------------|
| Gemini 3.1 Pro   | 0.295       | **0.523**  | +0.227, **p < 0.001** (n=44 answered) |
| Gemini 3.5 Flash | 0.258       | **0.379**  | +0.121, **p = 0.025** (n=66, full coverage) |

The lift concentrates on formulaic short gaps, as the mechanism predicts
(Flash: w1 0.302→0.419, w2-3 0.211→0.316, w4-6 0.000→0.250).

### Confidence is calibrated → a restore-or-abstain tool

Self-reported confidence tracks accuracy tightly, especially with RAG:

| Confidence | Gemini 3.5 Flash +RAG | Gemini 3.1 Pro +RAG |
|------------|----------------------:|--------------------:|
| high       | 0.545                 | **0.808**           |
| medium     | 0.056                 | 0.222               |
| low        | 0.000                 | 0.083               |

When Pro+RAG reports "high," it is right 81% of the time — enough for a
deployable *restore-at-high-confidence, abstain-otherwise* product.

### Leakage ablation — the lift survives

Only **11 of 66** tasks had an answer-revealing parallel in their top-8.
Re-running with those parallels stripped (Gemini 3.5 Flash):

| Condition                         | Span-exact |
|-----------------------------------|-----------:|
| single-shot                       | 0.258      |
| +RAG (full)                       | 0.379      |
| +RAG, answer-revealing stripped   | **0.333**  |

On the **pure-generalization subset** (55 tasks with no revealing parallel):
single-shot 0.236 → RAG **0.309**. RAG helps even where there is nothing to
copy — the gain is genuine formula/structure transfer, not answer leakage. On
the 11 answer-revealed tasks it doubles (0.364 → 0.727), as expected for
attestation-grounded restoration.

## Conclusion

Retrieval-augmented restoration transfers from Latin/Greek (Aeneas/Ithaca) to
Etruscan, a low-resource language isolate. The gain is **significant**,
**formula-driven**, **survives a leakage ablation**, and comes with a
**calibrated confidence signal**. This is the first positive significant
result in the lacuna strand and the basis for the frontend restorer.

## Caveats

- **Pro coverage bug:** 19/70 Pro rows returned empty (`thinking_budget=0` +
  longer RAG prompts); Pro's Δ is on the answered subset. **Flash (n=66, full
  coverage) is the clean headline.** A production run must fix Pro's empties.
- Char-3-gram is a deliberately simple retriever; a learned-embedding retriever
  (etr-lora-v4 / pgvector) is the obvious next ablation.
- 66 tasks, width-1-dominated, editor-conjecture gold (inherited v2.0.3 limits).

## Reproduction

```bash
# 1. corpus.json — pull canonical texts from the public API (paginated /search)
# 2. blind_pool.jsonl + gold_map.json — derived from
#    research/private/evaluation/lacuna_jury_raw_v2_0_3_rerun.jsonl
#    (unique (id,masked) tasks, gold held separately)
# 3. run (Vertex ADC; tripcreator-prod has Gemini, not Opus):
python rag_restore.py single gemini-3.5-flash
python eval_ablation.py gemini-3.5-flash
```

Raw per-row outputs and the corpus dump live in the gitignored
`research/private/evaluation/` (local-only, like the rest of that dir).
