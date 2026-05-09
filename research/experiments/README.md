# Research Experiments

Each subdirectory is one experiment with a self-contained `eval.py` (or
`README.md` describing the protocol if the experiment was run via
existing infrastructure). Headline numbers below; see each experiment's
own README for details and reproduction.

## Index

| Experiment | Question | Headline result |
|---|---|---|
| [`byt5_v4_vs_v5/`](byt5_v4_vs_v5/) | Did corpus cleaning improve ByT5 lacuna restoration? | TBD — script ready, run pending |
| [`etr_lora_v3_vs_v4_retrieval/`](etr_lora_v3_vs_v4_retrieval/) | Did corpus cleaning improve XLM-RoBERTa+LoRA embedding retrieval? | Qualitative wins on sibilant convergence, structural patterns, abbreviation handling |
| [`classifier_data_bottleneck/`](classifier_data_bottleneck/) | What is the labeled-data threshold for Etruscan inscription typology? | macro F1 0.16 (n=184) → 0.28 (n=712, CNN); embedding-head fails at 0.075 due to curse-of-dimensionality |

## Conventions

- **`eval.py`** — runnable from repo root; reads from prod DB or local artifacts; emits results to stdout and a per-run `results.json` if applicable.
- **`README.md` per experiment** — protocol, dataset, metrics, conclusion. Updated when the experiment is rerun.
- **Held-out evaluation set** — [`/research/data/eval_heldout_29.csv`](../data/eval_heldout_29.csv). Any classifier experiment must report on this set with the training set explicitly excluding overlap (`signal_source = gold` rows that appear here are demoted to `unknown` before training).

## Adding a new experiment

1. Create `research/experiments/<short_descriptive_name>/`
2. Add `eval.py` (self-contained — repo-root-relative paths via `Path(__file__).resolve().parent.parent.parent.parent`)
3. Add `README.md` with: question, dataset, protocol, metrics, conclusion.
4. Add a row to the index table above.
