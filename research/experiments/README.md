# Research Experiments

Each subdirectory is one experiment with a self-contained `eval.py` (or
`README.md` describing the protocol if the experiment was run via
existing infrastructure). Headline numbers below; see each experiment's
own README for details and reproduction.

## Index

| Experiment | Question | Headline result |
|---|---|---|
| [`byt5_v4_vs_v5/`](byt5_v4_vs_v5/) | Did corpus cleaning improve ByT5 lacuna restoration? | Both fail to converge (sentinel-token learning collapse; negative baseline) |
| [`lacuna_restoration/`](lacuna_restoration/) | Which post-ByT5 architecture works for character-level lacuna restoration? | XLM-R + char head: **38.0% top-1 / 60.6% top-3**. Char-MLM-from-scratch: 10.0% top-1 (negative baseline). Historical figures from one 500-row run with no CI, not reproduced; see the README's reproducibility section. |
| [`etr_lora_v3_vs_v4_retrieval/`](etr_lora_v3_vs_v4_retrieval/) | Did corpus cleaning improve XLM-RoBERTa+LoRA embedding retrieval? | Qualitative wins on sibilant convergence, structural patterns, abbreviation handling |
| [`classifier_data_bottleneck/`](classifier_data_bottleneck/) | What is the labeled-data threshold for Etruscan inscription typology? | macro F1 0.16 (n=184) → 0.28 (n=712, CNN); embedding-head fails at 0.075 due to curse-of-dimensionality |
| [`hybrid_embed/`](hybrid_embed/) | How much retrieval, restoration and cross-lingual signal does a from-scratch stack (own tokenizer, transformer, node2vec, VSA, hyperbolic embeddings, contrastive towers; no pretrained model) get from 5,569 cleaned inscriptions? | Structural retrieval: VSA structure vector 0.981 structure similarity vs 0.839 for char-3-gram. Offline search (74 frozen queries, lexical NDCG@10): RRF(BM25 + dense + late interaction) 0.427 vs BM25 0.297. Damaged-token restoration: 0.048. Etruscan↔English contrastive towers: Etr→Eng R@10 0.251 in a 171-candidate pool (chance 0.058); rosetta-gloss p@10 0.23 to 0.41 across variants on n=22, too few pairs to rank them. Numbers come from the README (`out/` is gitignored). |
| [`lacuna_restoration_rag/`](lacuna_restoration_rag/) | Does retrieving parallel inscriptions lift lacuna restoration over single-shot prompting, and is the lift more than copying an attested answer? | On the 66 v2.0.3 clean-gold tasks, span-exact: Gemini 3.5 Flash 0.258 → 0.379 with retrieval (paired p = 0.025, n=66, the clean headline); Gemini 3.1 Pro 0.295 → 0.523 (p < 0.001, but only 44 rows answered). With answer-revealing parallels stripped, Flash scores 0.333. Source: `results.json`. |
| [`vsa_role_filler/`](vsa_role_filler/) | Can an inscription be encoded as bound role⊗filler vectors, with no training, so that structural parallels (same template, different words) are retrievable? | On same-template pairs sharing zero words, recall@10 is 0.918 for the VSA structure vector (by construction, since it encodes the template) against 0.085 for gemini-embedding-001, 0.095 for char-3-gram and a 0.107 random floor. Scope is parser-limited: 678 of 5,932 inscriptions (11.4%). Feeding VSA parallels to the lacuna restorer hurts: span-exact 0.167 vs 0.318 for char-3-gram retrieval (negative). |

## Conventions

- **`eval.py`**: runnable from repo root; reads from prod DB or local artifacts; emits results to stdout and a per-run `results.json` if applicable.
- **`README.md` per experiment**: protocol, dataset, metrics, conclusion. Updated when the experiment is rerun.
- **Held-out evaluation set**: [`/research/data/eval_heldout_29.csv`](../data/eval_heldout_29.csv). Any classifier experiment must report on this set with the training set explicitly excluding overlap (rows that appear here are demoted to `unknown` before training).

## Adding a new experiment

1. Create `research/experiments/<short_descriptive_name>/`
2. Add `eval.py` (self-contained; repo-root-relative paths via `Path(__file__).resolve().parent.parent.parent.parent`)
3. Add `README.md` with: question, dataset, protocol, metrics, conclusion.
4. Add a row to the index table above.
