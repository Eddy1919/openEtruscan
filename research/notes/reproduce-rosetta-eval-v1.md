# Reproducing `rosetta-eval-v1`

`rosetta-eval-v1` is the **frozen reference benchmark** for the Rosetta
multilingual encoder. A single command produces the JSON that the
headline FINDINGS.md numbers come from; this note captures everything
you'd need to make a fresh run land on the same numbers six months from
now.

The benchmark is a **protocol**, not a model. The model column is
parameterised via `--api-url`, so the same eval scaffolding grades v3,
v4, an `etr-lora-attested` variant, or anything else served behind
`/neural/rosetta` — and the random/Levenshtein columns stay identical
across runs, giving us an honest delta to compare against.

## One-line reproduction

```bash
bash evals/rosetta_eval_v1.sh \
  --api-url https://api.openetruscan.com \
  --output auto
```

`--output auto` writes the JSON to
`eval/rosetta-eval-v1-<UTC-timestamp>.json` and prints the destination
to stderr. Anything else as `--output` is taken as a literal path; if
omitted, the JSON goes to stdout.

## What's pinned

| Component | Pinned value | Source of truth |
|---|---|---|
| Eval split | `test` (22 pairs) | [`evals/rosetta_eval_pairs.py`](../../evals/rosetta_eval_pairs.py) — `split="test"` rows |
| Min-confidence filter | `medium` (drops `low`-confidence pairs) | [`evals/run_rosetta_eval.py`](../../evals/run_rosetta_eval.py) `BENCHMARK_PRESETS["rosetta-eval-v1"]` |
| Semantic fields | committed in repo, no external dep | [`evals/latin_semantic_fields.py`](../../evals/latin_semantic_fields.py) |
| Strict-lexical metric | "exact expected Latin lemma in top-k" | `evaluate()` in `run_rosetta_eval.py` |
| Semantic-field metric | "any Latin word from the right semantic field in top-k" | `evaluate()` in `run_rosetta_eval.py` |
| Coverage thresholds | `{0.50, 0.70, 0.85}` cosine | `evaluate()` in `run_rosetta_eval.py` |
| `k` values | `{1, 3, 5, 10}` | `DEFAULT_K_VALUES` in `run_rosetta_eval.py` |
| Random baseline math | `k / V` (strict), `1 − C(V−F,k)/C(V,k)` (field) | `_random_baseline_metrics()` |
| Levenshtein baseline | Standard O(mn) DP against full Latin vocab | `_query_neighbours_levenshtein()` |
| Latin vocab source | `/neural/rosetta/vocab?lang=lat` from the API under test | Fetched at run time, cached for the duration of the run |

## What varies between runs (and why)

- **The model column.** That's the whole point. `--api-url` decides
  which model gets graded. Document the API's serving config in the run
  log below.
- **The Latin vocab.** Levenshtein and the random analytical baseline
  both depend on `|V|`, which the API's `/neural/rosetta/vocab`
  endpoint reflects at query time. Ingest changes between runs ⇒ the
  baselines will move slightly. Acceptable; log the vocab size with each
  run.
- **API rate-limit pacing.** Default 2.05 s between requests; total
  wall-clock ~70 s for the 22-pair test split. `--no-pace` only for
  local APIs.

## Pinned commit hashes (last touched)

These are the commits to roll back to if you need to reproduce a
historical run bit-for-bit.

| File | Pinned hash (at v1 freeze) |
|---|---|
| `evals/rosetta_eval_pairs.py` | `2530765` ([T1.3] Held-out 40/22 anchor split) |
| `evals/latin_semantic_fields.py` | `5ff53d9` (chore: fix linting errors — semantic-field vocab) |
| `evals/run_rosetta_eval.py` | bumped per task; see `git log -- evals/run_rosetta_eval.py` |
| `evals/rosetta_eval_v1.sh` | bumped per task; see `git log -- evals/rosetta_eval_v1.sh` |

When you update the benchmark in a way that *changes the numbers*, bump
the label (`rosetta-eval-v2`) — never re-purpose an existing label.

## Pinned vocab / corpus (GCS)

The API under test reads from `language_word_embeddings` in the prod
Postgres. The current production population came from:

- `gs://openetruscan-rosetta/embeddings/labse-v1.jsonl` (the LaBSE
  baseline that the system currently serves by default).
- `gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v3.jsonl` (the
  Etruscan-side encoder; pre-v4).

Once T2.3 lands and v4 is queryable behind `embedder=xlmr-lora-v4`, the
benchmark gains a fourth column and the v4 JSONL URI gets pinned here
alongside the LaBSE one. See `research/EXECUTION_WBS.md` § T2.3.

## Run log

Append a row each time the benchmark is run against prod and the JSON
is committed to `eval/`.

| Date (UTC) | Operator | API URL | Latin vocab size | Output file | Notes |
|---|---|---|---|---|---|
| 2026-05-10T21:01:24Z | edoardo | <https://api.openetruscan.com> | 50,000 | [`eval/rosetta-eval-v1-20260510T210124Z.json`](../../eval/rosetta-eval-v1-20260510T210124Z.json) | First frozen run. v0.5.0 / LaBSE column only (v4 not yet ingested). model.field@10=0.1875 on 16/22 evaluated (6 OOV). Pre-flight: stamped prod `alembic_version j5e6f7a8b9c0→a6d56926ff21` to reconcile a phantom revision blocking redeploy. |
| 2026-05-11T07:15:32Z | edoardo | <https://api.openetruscan.com> | 50,000 | [`eval/rosetta-eval-v1-20260511T071620Z.json`](../../eval/rosetta-eval-v1-20260511T071620Z.json) | First **head-to-head** run (T2.4) after T2.3 ingest. Schema: 4 columns `{random, levenshtein, labse, v4}`. LaBSE column reproduces the prior run exactly (strict@10=0.0625, field@10=0.1875). **v4 column = all-zero**: 8,905 ett v4 vectors ingested but 0 lat v4 vectors (T2.2 was Etruscan-only). All 22 source words are skipped because the target partition is empty. v4 numbers become meaningful once Latin is re-embedded under `(xlmr-lora, v4)` — tracked in memory note `t2-3-latin-half-missing`. |

## Update checklist (per quarterly refresh)

1. Bump the relevant commit hashes in the table above (or copy this doc
   to `reproduce-rosetta-eval-v<N+1>.md` for a semantically-breaking
   change).
2. Re-run `bash evals/rosetta_eval_v1.sh --output auto`.
3. Append a row to the **Run log** above.
4. Commit the new `eval/rosetta-eval-v1-*.json` file alongside the doc
   update.
5. If headline numbers changed, update `research/FINDINGS.md` in the
   same PR.

## Why this is shaped the way it is

Pre-T1.5, the eval harness had four CLI flags that could each be
forgotten or accidentally flipped. "Did this run use the test split or
all 62 pairs? Was `min_confidence=medium` or `low`? Which baseline
columns did we compute?" — that kind of question is exactly how
benchmark numbers drift. The `--benchmark=rosetta-eval-v1` switch in
`run_rosetta_eval.py` collapses all those choices into a single label;
the shell orchestrator collapses the three required columns into a
single command; this doc collapses the reproducibility manifest into a
single file. Stop, look at the table, type one command.
