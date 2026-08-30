# Hybrid Etruscan embedding — from-scratch stack

This experiment measures how much retrieval and restoration signal a fully
custom stack can extract from 5,569 cleaned Etruscan inscriptions, with no
pretrained model anywhere in the pipeline.

Every component is built in this directory: the tokenizer (BPE, our
implementation), the encoder/decoder transformer (our attention), the graph
embeddings (our node2vec), the hyperbolic embeddings (our Riemannian SGD),
the VSA codes (dense and block-sparse), BM25, late-interaction scoring, and
the kNN-LM/Hopfield memory. torch is used as a tensor/autograd library only.

## Pipeline

```
prepare.py            clean + dedup (Zenodo grouped CSV -> out/index.csv, out/train.csv)
tokenizer_scratch.py  BPE vocab 1000, end-of-word marker         (WP1)
train_charlm.py       char-MLM baseline block (repo CharMLM)     (WP0, interim)
train_denoiser.py     custom seq2seq denoiser, lacuna corruption (WP2)
graph_embed.py        node2vec over inscription–entity graph     (WP0)
vsa_vectors.py        dense HRR/MAP role-filler vectors          (WP0)
vsa_sparse.py         block-sparse VSA, unbind protocol          (WP4)
hyperbolic_embed.py   Poincaré clan→inscription hierarchy        (WP7)
hopfield_restore.py   episodic kNN-LM memory for restoration     (WP5)
evaluate.py           v1 eval (charLM blocks)
evaluate_v2.py        v2 eval (custom stack + late interaction + router)
train_contrastive.py  dual-encoder alignment on translation pairs   (WP9)
eval_contrastive.py   WP9 eval: retrieval, rosetta glosses, router leg
```

Data comes from `scripts/ops/fetch_data.py` (Zenodo, SHA256-pinned). Cleaning
drops non-`clean` rows and the 525 majority-uppercase rows (Latin epigraphy +
OCR junk); training dedups on `dup_group_id` (row-level splits leak — see
`research/data/README.md`).

## Results (2026-08-30, all seeds fixed)

### Structural retrieval (NS1.3 protocol, 120 queries, top-5)

| system | structure sim | lexical overlap |
|---|---|---|
| char-3gram | 0.839 | 0.141 |
| charLM (char MLM, pooled) | 0.853 | 0.132 |
| custom s2s encoder (pooled) | 0.880 | 0.171 |
| node2vec | 0.850 | 0.240 |
| VSA-S (structure hypervector) | 0.981 | 0.046 |
| fused v2 [s2s \| n2v \| VSA-S] | 0.951 | 0.207 |

VSA stays the structure champion; fusion trades 3 points of structure for
4.5× its lexical recall.

### Offline search eval (74 frozen queries, NDCG@10, lexical category)

| system | lexical NDCG@10 |
|---|---|
| BM25 (sparse) | 0.297 |
| late interaction (MaxSim, per-token states) | 0.335 |
| dense fused v2 (pooled) | 0.356 |
| **RRF(BM25 + dense + late interaction)** | **0.427** |

Macro means are dominated by place/chronology categories that need metadata
the published CSV does not carry (findspot, Pleiades ids, dates) — those sit
at ≈0 for every text-only system and are not comparable to the prod API
numbers in `eval/harness/run_search_eval.py`.

### Restoration (damaged-position token accuracy, group-held-out val)

| system | acc |
|---|---|
| decoder-only (custom seq2seq) | 0.048 |
| decoder + episodic kNN-LM memory | 0.048 (tuned λ=0.9; every λ<1 hurt on dev) |

The episodic memory's next-token votes never helped: damaged tokens are
mostly hapax name pieces. Full-sequence teacher-forced
accuracy is 0.624; the memory's right role is retrieving whole parallel
inscriptions (the router), not predicting tokens.

### VSA unbind (role-filler round trip, cleaned index)

| code | GENTILICIUM | PATRONYMIC | STATUS |
|---|---|---|---|
| dense bipolar D=4096 | 70.7% | 92.3% | 98.7% |
| sparse block K=64×M=64 (1.6% activity) | 71.1% | 92.1% | 100.0% |

Cleaning alone lifted dense GENTILICIUM from the published 64.1% to 70.7%;
sparsity adds exact unbinding, not a large margin — the residual errors are
role-parser ambiguity.

### Hyperbolic genealogy (clan-membership MAP, 193 clans)

Poincaré d=16: 0.737 vs node2vec d=128: 0.985 — but node2vec trained on
exactly these membership edges (ceiling by construction). Viable low-dim
block; not a replacement. Kept out of search fusion.

### Rosetta diagnostic (22 frozen Etruscan↔Latin pairs, 58 candidates)

charLM p@10 0.455, custom s2s p@10 0.273, chance 0.172. Both are surface-form
artifacts, not semantics — the drop under subword tokenization confirms it.
No monolingual from-scratch model gets cross-lingual meaning from 5.5k texts.

### Contrastive alignment (1,773 Etruscan↔English pairs, dual encoder)

Both towers ours (WP2 encoder warm-started + fresh English encoder, InfoNCE,
duplicate-gloss negatives masked; `train_contrastive.py` / `eval_contrastive.py`).

| eval | score | chance |
|---|---|---|
| test-pool Eng→Etr R@10 (171 cand.) | 0.234 | 0.058 |
| test-pool Etr→Eng R@10 | 0.251 | 0.058 |
| full-index Eng→Etr R@10 (5,569 cand.) | 0.018 | 0.0018 |
| rosetta gloss p@10 (n=22, 60 cand.) | 0.318 | 0.167 |

The rosetta-gloss run is the first *semantic* number in this stack — the two
towers share no surface features, so 7/22 hits cannot be a char artifact.
It is also underpowered (binomial p≈0.08 vs chance): suggestive, not
certified. Adding the cross-lingual leg to the search router hurt (lexical
0.371→0.313), because the frozen queries are Etruscan surface strings, not
English; it stays out of the router. The binding constraint is pair count
(1,422 train pairs overfit 1.7M params by epoch ~7), not architecture.

#### Frozen-tower / augmentation / mining ablation (5 runs)

`gloss_augment.py` (rule-based English paraphrases, 433 variants),
`mine_pairs.py` (IBM Model 1 EM both-directions-agree + rosetta TRAIN split +
curated lexicon = 80 silver word pairs; every rosetta-TEST Etruscan word
excluded from every source).

| variant | val MRR | En→Et R@10 | Et→En R@10 | full-idx R@10 | gloss p@10 |
|---|---|---|---|---|---|
| v1 full-finetune | 0.123 | 0.234 | 0.251 | 0.018 | 0.318 |
| frozen (561K trainable) | 0.123 | 0.216 | 0.246 | 0.018 | 0.318 |
| frozen + aug | 0.108 | 0.187 | 0.211 | 0.023 | 0.318 |
| frozen + mined | 0.087 | 0.228 | 0.246 | 0.012 | 0.227 |
| frozen + aug + mined | 0.101 | 0.181 | 0.193 | 0.029 | 0.409 |

Readings that survive the noise: freezing the Etruscan tower costs ~2 points
of in-pool retrieval and nothing else at 3× fewer trainable params — right
default. Everything else is inside the error bars: the gloss column swings
0.227–0.409 (5–9 hits of 22) across variants, and no single ingredient
moves it consistently. The mining infrastructure works (lautni→freedman,
θui→here, mulu→given surfaced unsupervised); what is missing is an
evaluation large enough to steer by — n=22 gloss pairs and 171 test
sentences cannot rank five systems. Grow the frozen gold set before growing
the silver set.

### Retraining on the gold-gloss queue (WP10)

`build_gloss_pairs.py` converts `research/anchors/gold_glosses/` (319
records, llm_checked tier) into 221 training pairs and an independent
71-item silver word-level eval (`eval_gloss_silver.py`; ~276-gloss candidate
pool, chance p@10 0.036). Rosetta-TEST words are excluded from training;
all rosetta words are excluded from the silver eval. The silver eval is
llm_checked data, not the frozen benchmark — labeled accordingly.

| variant | val MRR | En→Et R@10 | Et→En R@10 | full-idx R@10 | rosetta 22 | silver 71 p@10 |
|---|---|---|---|---|---|---|
| v1 full-finetune | 0.123 | 0.234 | 0.251 | 0.018 | 0.318 | 0.028 |
| frozen + aug + mined | 0.101 | 0.181 | 0.193 | 0.029 | 0.409 | 0.028 |
| frozen + gold-gloss | 0.114 | 0.240 | 0.234 | 0.035 | 0.409 | 0.042 |
| frozen + aug + mined + gold-gloss | 0.108 | 0.222 | 0.263 | 0.026 | 0.364 | 0.085 |

The gold-gloss pairs are the first ingredient that helps without a
trade-off: frozen+gold-gloss matches v1 on sentence retrieval while
doubling full-index R@10 and holding rosetta at 0.409. The combined variant
posts the best silver score and the best Et→En retrieval. Absolute
word-level numbers remain small — 221 word pairs is a lexicon seed, not a
dictionary — and every silver label still awaits human verification.

#### Seed variance + bootstrap CIs (statistical hygiene pass)

frozen+gold-gloss retrained with three extra model seeds (init/batch order
only; the split stays fixed), 95% percentile-bootstrap CIs over items:

| run | silver p@10 (CI95) | rosetta p@10 (CI95) |
|---|---|---|
| v1 baseline | 0.028 [0.000, 0.070] | 0.318 [0.136, 0.500] |
| frozen+gg (seed 20260830) | 0.042 [0.000, 0.099] | 0.409 [0.227, 0.636] |
| frozen+gg seed 101 | 0.070 [0.014, 0.141] | 0.318 [0.136, 0.500] |
| frozen+gg seed 202 | 0.056 [0.014, 0.113] | 0.273 [0.091, 0.455] |
| frozen+gg seed 303 | 0.056 [0.014, 0.113] | 0.364 [0.182, 0.591] |
| frozen+aug+mined+gg | 0.085 [0.028, 0.155] | 0.364 [0.182, 0.591] |

Two readings. The direction is seed-stable: every gold-gloss run beats the
baseline's 0.028 on the silver eval (seed mean 0.056 ± 0.012, chance
0.036). And no single run clears chance at the 95% level — every CI still
contains 0.036, and the rosetta CIs span half the unit interval, which is
the n=22 problem stated as an interval. Conclusion unchanged, now with
error bars: the effect is real-looking but small, and certifying it needs
the verified gold eval, not another training run.

#### Cross-lingual router leg, retested with the frozen+gg towers

Still hurts: lexical NDCG@10 0.371 (BM25 + late-interaction) vs 0.331 with
the cross-lingual leg added; the leg alone scores 0.008. Structural, not a
tower-quality problem: the frozen queries are Etruscan surface strings, so
an English-side encoder cannot help on this benchmark by construction.
English-query search needs its own labeled query set before it can be
evaluated at all.

## Limits

- Semantics is capped by data: 27.4% of rows have translations. WP9 uses
  them and measures how far they go — 4× chance in-pool, 10× chance against
  the full index, one underpowered semantic rosetta signal. More
  architecture will not move this; more pairs will.
- The search eval reuses `eval/harness/search_eval_queries.jsonl` offline on
  a different index than prod; numbers are internally comparable only.
- The role parser (roles.py, lifted from vsa_role_filler) is heuristic; its
  errors propagate into the graph, VSA, and hyperbolic blocks.

## Reproduce

```bash
python scripts/ops/fetch_data.py
cd research/experiments/hybrid_embed
python prepare.py && python tokenizer_scratch.py
python train_charlm.py            # PYTORCH_ENABLE_MPS_FALLBACK=1 on Apple Silicon
python train_denoiser.py
python graph_embed.py && python vsa_vectors.py && python vsa_sparse.py
python hyperbolic_embed.py && python hopfield_restore.py
python evaluate.py && python evaluate_v2.py
python train_contrastive.py && python eval_contrastive.py
# ablations
python gloss_augment.py && python mine_pairs.py
python train_contrastive.py --freeze_etr --augment_csv out/gloss_augmented.csv \
    --mined_csv out/mined_pairs.csv --tag frozen_aug_mined
python eval_contrastive.py --tag frozen_aug_mined --skip_search
```

All outputs land in `out/` (gitignored). Results JSONs: `out/results.json`
(v1), `out/results_v2.json`, `out/vsa_sparse_results.json`,
`out/hyperbolic_results.json`, `out/hopfield_results.json`.
