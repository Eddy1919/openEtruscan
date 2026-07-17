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

> **Note.** `api.openetruscan.com` is **retired** and Rosetta retrieval is not on
> the current public API — run against a local research-API instance
> (`src/openetruscan/api` on :8000). The dated rows in the run-log table below
> record the host as it was at the time and are left unchanged as history.

```bash
bash eval/harness/rosetta_eval_v1.sh \
  --api-url http://localhost:8000 \
  --output auto
```

`--output auto` writes the JSON to
`eval/rosetta-eval-v1-<UTC-timestamp>.json` and prints the destination
to stderr. Anything else as `--output` is taken as a literal path; if
omitted, the JSON goes to stdout.

## What's pinned

| Component | Pinned value | Source of truth |
|---|---|---|
| Eval split | `test` (22 pairs) | [`eval/harness/rosetta_eval_pairs.py`](../../eval/harness/rosetta_eval_pairs.py) — `split="test"` rows |
| Min-confidence filter | `medium` (drops `low`-confidence pairs) | [`eval/harness/run_rosetta_eval.py`](../../eval/harness/run_rosetta_eval.py) `BENCHMARK_PRESETS["rosetta-eval-v1"]` |
| Semantic fields | committed in repo, no external dep | [`eval/harness/latin_semantic_fields.py`](../../eval/harness/latin_semantic_fields.py) |
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
  baselines will move slightly. Acceptable; since 2026-07-17 the harness
  records `vocab_size` inside each baseline column's JSON (the run-log
  column below is the cross-check, no longer the only record). A failed
  vocab fetch now aborts the random baseline instead of silently
  substituting a placeholder V.
- **API rate-limit pacing.** Default 2.05 s between requests; total
  wall-clock ~70 s for the 22-pair test split. `--no-pace` only for
  local APIs.

## Pinned benchmark definition (content hashes)

The July 2026 history squash destroyed the commit ids this section
originally pinned (`287f740`, `5e960b2`), so — as with the
pre-registration re-anchoring in the 1.1.0 release — the benchmark
definition is anchored in content hashes, not commit ids. The two files
below fully determine the eval set, split, and semantic fields:

| File | sha256 (2026-07-17) |
|---|---|
| `eval/harness/rosetta_eval_pairs.py` | `92e2abe1434df1b7d32f27bb161c763d64ad89ac9c99937f021f188d340ec610` |
| `eval/harness/latin_semantic_fields.py` | `f0a12f45bf3cc5c2188333d0c7e3add26e42946d99d6254209c7c7cc141283cc` |

`run_rosetta_eval.py` and `rosetta_eval_v1.sh` carry the metric
definitions; changes to them are only admissible under this label when
they leave every committed number unchanged (the 2026-07-17 changes are
additive: `vocab_size` recording and the hard-fail on vocab-fetch
errors). When you update the benchmark in a way that *changes the
numbers*, bump the label (`rosetta-eval-v2`) — never re-purpose an
existing label.

## Independent verification — 2026-07-17

What a from-scratch check of the committed
`eval/rosetta-eval-v1-20260511T080032Z.json` could and could not
confirm without a live API (`api.openetruscan.com` is retired):

- **Random column: fully replicated.** An independent implementation of
  the closed-form math (`k/V` strict; `1 − C(V−F,k)/C(V,k)` field) over
  the 22 test-split pairs with V=50,000 reproduces all eight committed
  values to full float precision.
- **Levenshtein column: internally consistent.** Recomputing strict and
  field hits from the column's own recorded `per_pair.top_predictions`
  confirms every metric value. The *ranking itself* (that these are
  truly the 10 edit-closest words in the 50,000-word vocab) is not
  re-checkable without the vocab endpoint; the DP implementation is
  unit-tested instead.
- **FINDINGS.md table: matches the JSON** in all four columns.
- **Not verified here:** the LaBSE and v4 model columns need a live API
  with the embedding partitions loaded (a re-run is unblocked — see
  below — but out of this session's scope).
- **Embeddings recovered.** `gs://openetruscan-rosetta` (the bucket the
  table above cites) is gone, but the operator verified on 2026-07-17
  that byte-identical copies of `labse-v1.jsonl` and
  `etr-xlmr-lora-v4.jsonl` (MD5s matching this manifest) survive in
  `gs://openetruscan-rosetta-vai`. See `docs/REPRODUCE.md` for the
  corrected availability statement. A historical-column re-run against
  the recovered vectors is queued as a Pod B task.
- **Pair-count correction.** The anchor module contains **61** unique
  pairs, split **39/22** — prose elsewhere said "62" and "40/22". The
  pre-squash history that would explain the difference (a pair removed
  after the split was cut?) is gone; 61/39/22 is the source of truth.

Known analytic simplification, unchanged for label stability: the
random field baseline uses F = |field vocabulary|, not
|field ∩ Latin vocab|. If some field words are absent from the vocab
this *inflates* the random baseline — conservative for any
"model beats random" claim.

## Pinned schema state

Reproducing the numbers also requires the prod DB schema being on a
specific alembic head. Querying a different schema can return the
same vectors but with different filters applied — the eval will run
but the results aren't comparable.

| Component | Pinned value |
|---|---|
| `alembic_version` on prod DB | `b7e6f7a8b9c1` (T2.3 — `embedder_revision` in PK) |
| PK shape on `language_word_embeddings` | `(language, word, embedder, embedder_revision)` |
| Supporting index | `ix_lwe_lang_embedder_revision` on `(language, embedder, embedder_revision)` |

Confirm with:

```sql
SELECT version_num FROM alembic_version;
-- expect b7e6f7a8b9c1
SELECT conname, pg_get_constraintdef(oid)
  FROM pg_constraint
 WHERE conrelid = 'language_word_embeddings'::regclass AND contype = 'p';
-- expect (language, word, embedder, embedder_revision)
```

## Pinned vocab / corpus (GCS)

The API under test reads from `language_word_embeddings` in the prod
Postgres. Each JSONL below is pinned with its GCS-side hashes so a
re-download can be byte-verified against the snapshot that produced
the committed run-log rows.

| GCS URI | Partition (embedder, revision) | Languages | Hash (md5, base64) | Notes |
|---|---|---|---|---|
| `gs://openetruscan-rosetta/embeddings/labse-v1.jsonl` | `("sentence-transformers/LaBSE", "v1")` | ett + grc + lat | `Smh4Hgl5+YLKeMR2mPeqhA==` | Default partition; the LaBSE column queries this. |
| `gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl` | `("xlmr-lora", "v4")` | ett only | `8m44dg5cU7k6T8q4fUNlaA==` | T2.3 v4 ingest; Etruscan half of the v4 column. |
| `gs://openetruscan-rosetta/embeddings/lat-xlmr-lora-v4.jsonl` | `("xlmr-lora", "v4")` | lat only | `ntYyMujjEQFz41nRzqhzrg==` (recorded 2026-07-17 from the recovered copy — the original bucket died before a hash was logged; Vertex job `lat-xlmr-v4-20260511-072257`, custom-job id `2423313989711691776`) | Latin half of the v4 column. Re-embeds the `lat` subset of `labse-v1.jsonl` through XLM-R-base (no LoRA — Latin doesn't get one). |
| `gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v3.jsonl` | `("xlm-roberta-base+etr-lora-v3", "v3")` | ett only | *historical; superseded by v4* | Pre-v4 Etruscan vectors; still resident in the DB for rollback. |

The table's URIs are the historical provenance; the bucket is gone
(see the recovery note above). Byte-identical copies live under the
same filenames in `gs://openetruscan-rosetta-vai/embeddings/`, so
verify a fresh download against the surviving bucket:

```bash
gsutil hash -c gs://openetruscan-rosetta-vai/embeddings/<file>
# Compare the "Hash (md5)" line to the table above.
```

When the v4 partition is complete on both sides, the v4 column of
`rosetta-eval-v1` becomes meaningful and FINDINGS.md gains a real
head-to-head table (WBS T3.1).

## Run log

Append a row each time the benchmark is run against prod and the JSON
is committed to `eval/`.

| Date (UTC) | Operator | API URL | Latin vocab size | Output file | Notes |
|---|---|---|---|---|---|
| 2026-05-10T21:01:24Z | edoardo | <https://api.openetruscan.com> | 50,000 | [`eval/rosetta-eval-v1-20260510T210124Z.json`](../../eval/rosetta-eval-v1-20260510T210124Z.json) | First frozen run. v0.5.0 / LaBSE column only (v4 not yet ingested). model.field@10=0.1875 on 16/22 evaluated (6 OOV). Pre-flight: stamped prod `alembic_version j5e6f7a8b9c0→a6d56926ff21` to reconcile a phantom revision blocking redeploy. |
| 2026-05-11T07:15:32Z | edoardo | <https://api.openetruscan.com> | 50,000 | [`eval/rosetta-eval-v1-20260511T071620Z.json`](../../eval/rosetta-eval-v1-20260511T071620Z.json) | First **head-to-head** run (T2.4) after T2.3 ingest. Schema: 4 columns `{random, levenshtein, labse, v4}`. LaBSE column reproduces the prior run exactly (strict@10=0.0625, field@10=0.1875). **v4 column = all-zero**: 8,905 ett v4 vectors ingested but 0 lat v4 vectors (T2.2 was Etruscan-only). All 22 source words are skipped because the target partition is empty. v4 numbers become meaningful once Latin is re-embedded under `(xlmr-lora, v4)` — tracked in memory note `t2-3-latin-half-missing`. |
| 2026-05-11T08:00:32Z | edoardo | <https://api.openetruscan.com> | 50,000 | [`eval/rosetta-eval-v1-20260511T080032Z.json`](../../eval/rosetta-eval-v1-20260511T080032Z.json) | First **complete head-to-head**. Vertex job `2423313989711691776` produced `lat-xlmr-lora-v4.jsonl` (100k Latin tokens through XLM-R-base, no LoRA); ingested under `(xlm-roberta-base, v4)`. Route alias system extended to be language-aware so `?embedder=xlmr-lora-v4` resolves to `(xlmr-lora, v4)` for ett and `(xlm-roberta-base, v4)` for lat. **Result:** LaBSE wins on `field@10` decisively (0.1875 vs 0.0625, 3× v4). v4's high `coverage@0.85` (1.0) is anisotropy, not quality. Decision: gap remains; proceed to P5 per the WBS decision tree. See FINDINGS.md for the full table. |

## Update checklist (per quarterly refresh)

1. Bump the relevant commit hashes in the table above (or copy this doc
   to `reproduce-rosetta-eval-v<N+1>.md` for a semantically-breaking
   change).
2. Re-run `bash eval/harness/rosetta_eval_v1.sh --output auto`.
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
