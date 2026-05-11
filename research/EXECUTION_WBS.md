# Execution WBS — Defensible eval, v4 head-to-head, primary-source mining

End-to-end work-breakdown structure designed to be **executed one task
at a time by Gemini**, with each task verifiable from the project root
by a single command. Edoardo + Claude monitor results in the chat after
each task lands.

This is **operational** (one PR per task), not aspirational. If a task
gets reframed mid-execution, edit the row in place in the same PR.

> **Companion docs.** [`ROADMAP.md`](ROADMAP.md) is the strategic plan;
> [`WBS.md`](WBS.md) is the original task breakdown. This file is the
> *execution-ready* subset — the next ~3 weeks of work — with prompts
> tight enough that Gemini can run each task and a human can verify it
> in 60 seconds.

---

## How to use this document

a

1. Pick the **lowest-numbered task whose dependencies are met**.
2. Paste the entire task block (including "Steps", "Outputs",
   "Acceptance") into Gemini as a prompt. Add this fixed preamble:

   > You are a coding agent operating in the openEtruscan repo at
   > `/home/edoardo/Documents/openEtruscan`. Execute the task below.
   > Open a single PR titled `[<TASK-ID>] <task title>`. Run the
   > acceptance command and paste its output into the PR body. Don't
   > land work that fails the acceptance command.

3. After Gemini reports done, **run the acceptance command in the
   chat** — Claude pastes the result here, we eyeball it, mark the
   todo `completed`, and move to the next task.
4. If a task introduces a follow-up, file it as a new row in this
   document under the same phase, with the next free ID.

---

## Phase summary

| Phase | What it produces | Tasks | Est. effort | Cost |
|---|---|---|:---:|:---:|
| **P1** Defensible eval | Random / Levenshtein baselines, held-out 40/22 split, real cosine-coverage metric, frozen `rosetta-eval-v1` | T1.1 – T1.5 | 2.25 days | $0 |
| **P2** v4 head-to-head | Production vocab re-embedded through `etr-lora-v4`, ingested behind a feature flag, evaluated against LaBSE | T2.1 – T2.4 | 1.25 days | ~$0.50 Vertex |
| **P3** Findings refresh | Updated FINDINGS.md table, reproducibility manifest | T3.1 – T3.2 | 0.5 day | $0 |
| **P5** Cheap interventions | Cross-encoder rerank, cosine→confidence calibration, dual-track loanword/semantic API | T5.1 – T5.4 | 2.5 days | $0 |
| **P4** Primary-source mining (conditional) | LLM-extracted attested anchors, dedup vs. eval, optional contrastive LaBSE fine-tune | T4.1 – T4.4 | 3 days | ~$5 Anthropic + ~$0.30 Vertex |

**Critical path** (sequential): T1.3 → T1.5 → T2.1 → T2.2 → T2.3 → T2.4 → T3.1 → T5.1 → T5.4.
Everything else can be parallelised once T1.3 lands.

### Decision tree after each phase

```
P3 (FINDINGS table) → look at v4 vs LaBSE field@10 number
  ├── v4 closes the gap (≥0.18) → ship v4, skip P5+P4, go straight to publication
  └── gap remains → P5
P5 (cheap interventions) → re-run rosetta-eval-v1
  ├── reranker / calibration push field@10 to ≥0.20 → ship, publish, done
  └── gap remains → P4 (primary-source mining)
P4 → conditional contrastive fine-tune
  ├── yield ≥30 attested anchors AND fine-tune ≥1.5× field@5 → ship, publish
  ├── yield ≥30 but fine-tune <1.5× → publishable negative result
  └── yield <30 → documented data-limitation, hard-negative-mining last-resort experiment
```

**P5 is sequenced before P4 deliberately** — Tier-1 interventions are
cheaper and methodologically cleaner than primary-source mining, so we
should know how much of the gap they close before committing $5 + 3
days to LLM-extraction work.

---

## Phase 1 — Defensible eval

### T1.1 — Levenshtein retrieval baseline

**Goal:** add a `--baseline=levenshtein` mode to the eval harness that
ranks Latin candidates by edit distance to the Etruscan source word.

**Files to touch:**

- [`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py)
- [`tests/test_rosetta_eval.py`](../tests/test_rosetta_eval.py) (or create if absent)

**Steps:**

1. Add a new helper `_query_neighbours_levenshtein(api_url, word, from_lang, to_lang, k)`
   that pulls the full target-language vocab from a new endpoint
   `GET /neural/rosetta/vocab?lang=lat` (if it doesn't exist yet, add
   a thin endpoint in `src/openetruscan/api/server.py` that returns
   `{words: [...]}` from `language_word_embeddings`; cap at 50k rows;
   cache for 1 hour at the route level).
2. The helper computes Levenshtein distance via the standard library
   (no new dep — implement an O(mn) DP routine inline; the vocabs
   are ≤ 50k tokens × ≤ 20 chars, ~10⁷ ops per query, runs in <1s).
3. Add `--baseline {levenshtein, none}` CLI flag (default `none`,
   preserving current behaviour). When set to `levenshtein`,
   `evaluate()` swaps the neighbour function but emits the **same
   report shape** so downstream tooling is undisturbed.
4. Test: hit the test API with a dummy pair where `etr == lat`
   (e.g. `fanu`/`fanu`) — the baseline should rank `fanu` first
   (distance 0). Add `tests/test_rosetta_eval.py::test_levenshtein_baseline_self_match`.

**Output:**

- New CLI flag: `python evals/run_rosetta_eval.py --baseline=levenshtein --json`
  produces a complete report.
- Possibly: new endpoint `GET /neural/rosetta/vocab?lang=lat`.

**Acceptance command:**

```bash
python evals/run_rosetta_eval.py --baseline=levenshtein --json \
  --api-url https://api.openetruscan.com \
  | jq '.precision_at_k, .precision_at_k_semantic_field, .n_evaluated'
```

Must produce three populated objects (no nulls) and `n_evaluated > 30`.

**Effort:** 0.75 day.

**Dependencies:** none.

---

### T1.2 — Random retrieval baseline

**Goal:** report the analytical expected precision@k under uniform
random retrieval given the Latin vocab size.

**Files to touch:**

- [`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py)
- [`tests/test_rosetta_eval.py`](../tests/test_rosetta_eval.py)

**Steps:**

1. Add `_random_baseline_metrics(vocab_size: int, eval_pairs)` that
   computes:
   - **Strict-lexical p@k**: `k / vocab_size` (per pair the chance
     of hitting the exact lemma in a random sample of k).
   - **Semantic-field p@k**: `1 - C(V-F, k) / C(V, k)` where `V` is
     vocab size and `F = |LATIN_SEMANTIC_FIELDS[category]|`. Closed
     form via `math.comb`.
2. Add a `--baseline=random` mode. The report has the same shape;
   `n_evaluated` equals `len(pairs)` filtered by the same rules.
3. Document the math in a docstring on `_random_baseline_metrics`.
4. Test: with `vocab_size=1000`, `field_size=10`, `k=5` →
   strict ≈ 0.005, field ≈ 0.0489 (verify analytically).

**Output:**

- `python evals/run_rosetta_eval.py --baseline=random` runs in <1s
  and produces a complete report.

**Acceptance command:**

```bash
python evals/run_rosetta_eval.py --baseline=random --json \
  | jq '{strict: .precision_at_k, field: .precision_at_k_semantic_field}'
```

`strict.10` must be ≥ 0 and ≤ 0.001 (Latin vocab is ~10⁵, so 10/10⁵ = 1e-4).
`field.10` must be > `strict.10` (semantic field is broader).

**Effort:** 0.25 day.

**Dependencies:** none. (Independent of T1.1.)

---

### T1.3 — Held-out 40/22 anchor split

**Goal:** declare an explicit `EVAL_SPLIT` field on every `EvalPair`
with a stratified train/test split, and default the harness to test.

**Files to touch:**

- [`evals/rosetta_eval_pairs.py`](../evals/rosetta_eval_pairs.py)
- [`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py)
- [`tests/test_rosetta_eval_pairs.py`](../tests/test_rosetta_eval_pairs.py)

**Steps:**

1. Add `split: str = "test"` field to `EvalPair` (default test so any
   future row added without thought ends up in the held-out half —
   safer for accidental train-leakage than the other way around).
2. Generate the split deterministically in a one-shot script
   `evals/_generate_eval_split.py` (kept in repo for reproducibility):
   - Group pairs by `(category, confidence)` strata.
   - Within each stratum, take ~⌊n × 22/62⌋ to test, rest to train.
   - Use `random.Random(seed=20260510).shuffle` so the split is
     reproducible.
   - Run the script once, paste the resulting split list into
     `rosetta_eval_pairs.py`. Keep `_generate_eval_split.py` checked
     in but it should not run at import time.
3. Add `eval_pairs(split: str | None = "test", min_confidence=...)`
   helper. Existing callers without `split` get test (the safe default).
4. Add `--split {train, test, all}` CLI flag to the eval harness;
   default `test`. Print the split being used at the top of the report.
5. Tests:
   - `test_split_balance`: each category has ≥1 train AND ≥1 test
     example unless |category| < 2.
   - `test_no_overlap`: train ∩ test = ∅ on the `(etr, lat)` key.
   - `test_split_size`: `len(test) ∈ [20, 24]` and `len(train) ∈ [38, 42]`.

**Output:**

- 62 EvalPair rows now carry `split="train"` or `split="test"`.
- New flag `--split` on the eval harness.

**Acceptance command:**

```bash
python -c "
from evals.rosetta_eval_pairs import EVAL_PAIRS, eval_pairs
train = [p for p in EVAL_PAIRS if p.split == 'train']
test  = [p for p in EVAL_PAIRS if p.split == 'test']
overlap = {(p.etr,p.lat) for p in train} & {(p.etr,p.lat) for p in test}
print(f'train={len(train)} test={len(test)} overlap={len(overlap)}')
assert overlap == set()
assert 38 <= len(train) <= 42
assert 20 <= len(test) <= 24
print('OK')
"
```

Must print `OK` and the right counts.

**Effort:** 0.5 day.

**Dependencies:** none. **Blocks anything that trains on anchor pairs.**

---

### T1.4 — Threshold-aware coverage metric

**Goal:** replace the stale `coverage_any_hit` stub with the real
"fraction of source words whose top-1 cosine ≥ threshold" metric.

**Files to touch:**

- [`src/openetruscan/api/server.py`](../src/openetruscan/api/server.py) (verify cosines are returned — they already are, see line that emits `cosine` in the rosetta endpoint)
- [`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py)
- [`tests/test_rosetta_eval.py`](../tests/test_rosetta_eval.py)
- [`research/FINDINGS.md`](FINDINGS.md) — fix stale "stub" claim

**Steps:**

1. In `_query_neighbours`, return the full neighbour list including
   cosines (currently the function strips them — change to return
   `[(word, cosine), ...]` and update callers).
2. Update `evaluate()` to record `top1_cosine` per pair.
3. Replace `coverage_at_threshold` computation with the real one:
   `fraction of pairs where top1_cosine >= c` for `c ∈ {0.50, 0.70, 0.85}`.
4. Remove the "left as a follow-up" comment in
   `run_rosetta_eval.py:218-231`.
5. In [`research/FINDINGS.md`](FINDINGS.md) §"What's still missing"
   item 5, change "Coverage metric is a stub" to a one-line note that
   it's now computed, with a pointer to T1.4.
6. Test: feed `evaluate()` a fake API client returning known cosines,
   verify coverage_at_threshold[0.85] equals the expected fraction.

**Output:**

- `coverage_any_hit` is renamed to `coverage_at_threshold` in the
  report (breaking change for downstream consumers — should be safe,
  no current consumer reads this field).
- FINDINGS.md no longer claims the metric is a stub.

**Acceptance command:**

```bash
python evals/run_rosetta_eval.py --json \
  --api-url https://api.openetruscan.com \
  | jq '.coverage_at_threshold | to_entries | map({thr: .key, frac: .value})'
```

Must print a list of three objects with `thr` ∈ {"0.5","0.7","0.85"}
and `frac ∈ [0, 1]`. `frac@0.5` ≥ `frac@0.7` ≥ `frac@0.85`.

**Effort:** 0.5 day.

**Dependencies:** none.

---

### T1.5 — Frozen `rosetta-eval-v1` reference benchmark

**Goal:** a single command reproduces the headline numbers in
FINDINGS.md from a freshly-checked-out repo. Pinned model, vocab,
split, metric definitions.

**Files to touch:**

- New: `evals/rosetta_eval_v1.sh` (the entrypoint)
- New: [`research/notes/reproduce-rosetta-eval-v1.md`](notes/reproduce-rosetta-eval-v1.md)
- [`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py): add
  `--benchmark=rosetta-eval-v1` switch that locks all flags

**Steps:**

1. Define `rosetta-eval-v1` as the tuple:
   - eval split: `test` (T1.3)
   - min_confidence: `medium`
   - model under test: pulled from `--api-url` (so the benchmark is a
     *protocol*, not a model)
   - all 4 baselines: random, levenshtein, model under test
   - report fields: strict@k, field@k, coverage@thr, by_category, by_confidence
2. `evals/rosetta_eval_v1.sh` takes `--api-url` and produces a
   single JSON `eval/rosetta-eval-v1-<UTC-timestamp>.json` with all
   four runs concatenated under top-level keys
   `{random, levenshtein, model}`.
3. Reproducibility note documents:
   - Pinned eval split: commit hash of `rosetta_eval_pairs.py`.
   - Pinned vocab: GCS URI of the embeddings JSONL the API was
     populated from.
   - Pinned API URL.
   - Date of the benchmark run, who ran it.

**Output:**

- One-shot script `bash evals/rosetta_eval_v1.sh > /tmp/eval.json`.
- Reproducibility note in `research/notes/`.

**Acceptance command:**

```bash
bash evals/rosetta_eval_v1.sh --api-url https://api.openetruscan.com \
  > /tmp/rosetta-eval-v1.json
jq '{
  random_strict_at_10: .random.precision_at_k["10"],
  lev_strict_at_10:    .levenshtein.precision_at_k["10"],
  model_strict_at_10:  .model.precision_at_k["10"],
  model_field_at_10:   .model.precision_at_k_semantic_field["10"],
  coverage:            .model.coverage_at_threshold
}' /tmp/rosetta-eval-v1.json
```

Must print all five fields populated. `model_field_at_10` should
recover the FINDINGS.md headline of ≈ 0.119 (within ±0.01 due to the
new test split being smaller than the original 62).

**Effort:** 0.5 day.

**Dependencies:** T1.1, T1.2, T1.3, T1.4.

---

## Phase 2 — etr-lora-v4 head-to-head

### T2.1 — Parameterise the Etruscan embed script for v4

**Goal:** the existing
[`scripts/training/vertex/embed_etruscan.py`](../scripts/training/vertex/embed_etruscan.py)
must accept `--adapter-tag etr-lora-v4` and produce
`gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl`.

**Files to touch:**

- [`scripts/training/vertex/embed_etruscan.py`](../scripts/training/vertex/embed_etruscan.py)
- New: `scripts/training/vertex/submit_etruscan_embed_v4.sh`

**Steps:**

1. Read the existing script — verify it already takes `--adapter-uri`
   or equivalent. If it hardcodes `etr-lora-v3`, add a CLI flag.
2. Verify the divider-normalisation logic is unchanged from v4
   training (must match `train_etruscan_lora.py` exactly — see the
   docstring warning on line 11).
3. Submit-script copy + edit:
   - `submit_etruscan_embed.sh` → `submit_etruscan_embed_v4.sh`
   - `ADAPTER_TAG=etr-lora-v4`
   - `OUTPUT_NAME=etr-xlmr-lora-v4.jsonl`
4. Local dry-run on 50 vocab tokens (use `--limit=50`) to verify the
   pipeline before launching Vertex.

**Output:**

- Updated embed script.
- New submit script for v4.

**Acceptance command:**

```bash
# Local dry-run, no Vertex
python scripts/training/vertex/embed_etruscan.py \
  --adapter-uri gs://openetruscan-rosetta/adapters/etr-lora-v4 \
  --limit 50 \
  --output /tmp/etr-v4-dryrun.jsonl
wc -l /tmp/etr-v4-dryrun.jsonl  # must print "50 /tmp/..."
jq -s 'length, (map(.vector | length) | unique)' /tmp/etr-v4-dryrun.jsonl
# must print 50, [768]
```

**Effort:** 0.25 day.

**Dependencies:** none.

---

### T2.2 — Embed prod vocab through etr-lora-v4 on Vertex

**Goal:** produce the full v4 embeddings JSONL on GCS.

**Files to touch:**

- None (just runs T2.1's submit script).

**Steps:**

1. `bash scripts/training/vertex/submit_etruscan_embed_v4.sh`
2. Wait for Vertex job to complete (~12 min, ~$0.07).
3. Verify the JSONL row count matches the expected vocab size
   (~8k Etruscan tokens — same order as the v3 file).

**Output:**

- `gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl`

**Acceptance command:**

```bash
gsutil ls -l gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl
gsutil cat gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl \
  | head -3 | jq '{lang: .language, word, dim: (.vector | length)}'
gsutil cat gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl \
  | wc -l
```

Must print: file exists, 3 rows with `dim=768` and `lang="ett"`,
total row count ≥ 5000.

**Effort:** 0.25 day (mostly waiting for Vertex).

**Dependencies:** T2.1.

---

### T2.3 — Ingest v4 vectors behind a feature flag

**Goal:** load v4 vectors into the prod DB *alongside* the LaBSE
vectors so we can A/B them at query time, **without breaking the
live `/neural/rosetta` traffic**.

**Files to touch:**

- [`scripts/training/vertex/ingest_embeddings.py`](../scripts/training/vertex/ingest_embeddings.py)
- [`src/openetruscan/api/server.py`](../src/openetruscan/api/server.py) — add `embedder` query param
- [`src/openetruscan/ml/multilingual.py`](../src/openetruscan/ml/multilingual.py) — `find_cross_language_neighbours(embedder=...)` filter

**Steps:**

1. **Schema check:** `language_word_embeddings.embedder` already
   exists (per multilingual.py:217). The PK is `(language, word)`,
   so we can't have both LaBSE and v4 vectors for the same `(ett, fanu)`
   without changing PK.
2. **Decision (document in PR):** add `embedder_revision` to the PK
   via a new alembic migration. PK becomes
   `(language, word, embedder, embedder_revision)`. Existing rows
   keep their current `embedder='LaBSE'` / `embedder_revision='v1'`.
3. Update `ingest_embeddings.py` to set
   `embedder='xlmr-lora'`, `embedder_revision='v4'` when ingesting
   the v4 JSONL.
4. Update `find_cross_language_neighbours()` to take an optional
   `embedder` filter (`"LaBSE"` default — preserves prod behaviour).
5. Add `?embedder=` query param to `GET /neural/rosetta`. Default to
   `LaBSE`. Accept `"xlmr-lora-v4"` to query the v4 partition.
6. Run ingest from the openetruscan-eu VM via IAP:

   ```bash
   python scripts/training/vertex/ingest_embeddings.py \
     --gcs-uri gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl \
     --embedder xlmr-lora --revision v4
   ```

7. Smoke test prod: `curl '/neural/rosetta?word=fanu&from=ett&to=lat&embedder=xlmr-lora-v4'`
   must return non-empty neighbours; default call (no `embedder=`)
   must still return LaBSE results.

**Output:**

- Alembic migration adding `embedder_revision` to the PK.
- `?embedder=` query param on `/neural/rosetta`.
- v4 vectors live in prod DB, segregated by `embedder` column.

**Acceptance command:**

```bash
# Default (LaBSE) — must still return fanum
curl -sf 'https://api.openetruscan.com/neural/rosetta?word=fanu&from=ett&to=lat&k=5' \
  | jq '.neighbours[0].word'   # expect "fanum"

# v4
curl -sf 'https://api.openetruscan.com/neural/rosetta?word=fanu&from=ett&to=lat&k=5&embedder=xlmr-lora-v4' \
  | jq '{first: .neighbours[0].word, n: (.neighbours | length)}'
# expect n >= 1; first word may differ from LaBSE
```

**Effort:** 0.75 day (the schema migration is the risky part).

**Dependencies:** T2.2.

---

### T2.4 — Run the head-to-head eval

**Goal:** produce a single JSON with eval results for *both* LaBSE
and v4 against `rosetta-eval-v1`.

**Files to touch:**

- [`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py) — pass
  `embedder` through to API calls
- `evals/rosetta_eval_v1.sh` — emit two model rows (`labse`, `v4`)
  in the JSON

**Steps:**

1. Add `--embedder` CLI flag to `run_rosetta_eval.py`. The harness
   passes it as a query param to `/neural/rosetta`.
2. Update `rosetta_eval_v1.sh` to run the model evaluation twice:
   `embedder=LaBSE` → key `labse`, `embedder=xlmr-lora-v4` → key `v4`.
3. Emit a single JSON `{random, levenshtein, labse, v4}`.

**Output:**

- A `rosetta-eval-v1-<timestamp>.json` with four rows in
  `eval/` directory.

**Acceptance command:**

```bash
bash evals/rosetta_eval_v1.sh --api-url https://api.openetruscan.com \
  > /tmp/v1-headtohead.json
jq '{
  random:      .random.precision_at_k_semantic_field["10"],
  lev:         .levenshtein.precision_at_k_semantic_field["10"],
  labse:       .labse.precision_at_k_semantic_field["10"],
  v4:          .v4.precision_at_k_semantic_field["10"],
  labse_strict: .labse.precision_at_k["10"],
  v4_strict:    .v4.precision_at_k["10"]
}' /tmp/v1-headtohead.json
```

All six fields populated. The full table goes into Phase 3 writeup.

**Effort:** 0.25 day.

**Dependencies:** T1.5, T2.3.

---

## Phase 3 — Findings refresh

### T3.1 — Update FINDINGS.md with the head-to-head table

**Goal:** the canonical narrative document reflects the new numbers,
with the random/Levenshtein columns that the original review demanded.

**Files to touch:**

- [`research/FINDINGS.md`](FINDINGS.md)
- [`research/CURATION_FINDINGS.md`](CURATION_FINDINGS.md) — Finding 5
  cross-link

**Steps:**

1. Replace the headline numbers section with a 5-column table:
   `metric | random | levenshtein | XLM-R | LaBSE | etr-lora-v4`.
2. Move the now-stale "What's still missing" §5 (coverage stub) to a
   one-line "addressed in T1.4" note.
3. Add a new §"v4-vs-LaBSE — what changed" section (~150 words)
   reading off the table.
4. Cross-link CURATION_FINDINGS §5 (qualitative wins) to this
   quantitative comparison.

**Output:**

- FINDINGS.md headline table is current.

**Acceptance command:**

```bash
# Sanity: the 5-column table contains all expected column headers
grep -A2 '| metric ' research/FINDINGS.md | head -5
# Must show all 5 column names: random, levenshtein, XLM-R, LaBSE, etr-lora-v4
```

**Effort:** 0.25 day.

**Dependencies:** T2.4.

---

### T3.2 — Reproducibility manifest

**Goal:** anyone with the repo + GCS read access can reproduce the
exact numbers in FINDINGS.md.

**Files to touch:**

- New: [`research/notes/reproduce-rosetta-eval-v1.md`](notes/reproduce-rosetta-eval-v1.md)

**Steps:**

1. The manifest names: pinned model checkpoints (with GCS URIs),
   pinned vocab files (with GCS URIs), pinned eval-pair commit hash,
   pinned API URL, the date of the run, who ran it, the
   `rosetta-eval-v1` JSON output (committed under `eval/`).
2. Include a "to update" checklist for the next quarterly refresh.

**Output:**

- One markdown doc.

**Acceptance command:**

```bash
test -f research/notes/reproduce-rosetta-eval-v1.md && \
  grep -c '^|' research/notes/reproduce-rosetta-eval-v1.md
# Must print > 5 (a real table, not a stub)
```

**Effort:** 0.25 day.

**Dependencies:** T3.1.

---

## Phase 4 — Primary-source attested-anchor mining (conditional on P1-P3)

> **Run this phase only if the P3 table shows a genuine gap between
> levenshtein and the best model.** If LaBSE or v4 already crushes
> Levenshtein, the eval is the win and we should pivot to M2
> (qualitative review) instead. Decision point lives in T3.1's PR
> review.

### T4.1 — LLM-as-parser script

**Goal:** extract bilingual gloss attestations from the 1,795
Etruscan-mention passages already on disk, *without* the LLM drawing
on outside knowledge.

**Files to touch:**

- New: `scripts/research/llm_extract_anchors.py`

**Steps:**

1. Iterate over `data/extracted/etruscan_passages.jsonl`.
2. Per passage, send to Claude (via the Anthropic SDK) with this
   strictly-bounded prompt:
   > You are extracting bilingual gloss equivalences **stated in the
   > passage**. Do not use outside knowledge. If the passage says
   > "the Etruscans called X what we call Y", emit
   > `{"etruscan_word":"X","equivalent":"Y","equivalent_language":"lat|grc","evidence_quote":"<verbatim>","source":"<author> <work> <locus>"}`.
   > If no such statement is present, emit `[]`. Do not infer; do not
   > paraphrase; the `evidence_quote` must be a verbatim substring of
   > the passage.
3. Use prompt caching (cache the system prompt + few-shot examples)
   to keep cost ≤ $5 for the full corpus.
4. Append-only output: `data/extracted/llm_anchors_raw.jsonl`.
5. Cost report at the end (token usage, total $).
6. Resumability: skip passages that already produced output (idempotent
   on rerun).

**Output:**

- New script, `~/data/extracted/llm_anchors_raw.jsonl` populated.

**Acceptance command:**

```bash
python scripts/research/llm_extract_anchors.py --limit 20 --dry-run
# must print: "Would process 20 passages, est. cost $X.XX"
python scripts/research/llm_extract_anchors.py --limit 20
wc -l data/extracted/llm_anchors_raw.jsonl
# expect at least a few rows (Suetonius-aesar passage in the first 20 = guaranteed hit)
jq '.evidence_quote' data/extracted/llm_anchors_raw.jsonl | head
# every quote should be non-empty
```

**Effort:** 1 day.

**Dependencies:** T1.3 (so we know what to dedup against), Anthropic
API access, $5 spend approval.

---

### T4.2 — Anchor review + dedup

**Goal:** human-curated `attested.jsonl` with provenance, dedup'd
against the test split.

**Files to touch:**

- New: `research/anchors/attested.jsonl`
- New: `scripts/research/review_anchors.py` (CLI for hand-review)

**Steps:**

1. CLI tool prints each candidate with the verbatim quote, asks
   `[k]eep / [s]kip / [e]dit-equivalent`. State persisted to a
   sidecar TSV so review can resume.
2. After review, the tool dedups against `eval_pairs(split='test')`
   on the `(etr_norm, lat_norm)` key. Hits land in a separate
   `attested_eval_overlap.jsonl` (these are NOT useful for training,
   but are useful as a sanity check that the LLM extraction is
   finding real attestations).
3. Yield report: how many candidates, how many kept, how many
   train-eligible after dedup, broken down by source author.

**Output:**

- `research/anchors/attested.jsonl` (training-eligible).
- `research/anchors/attested_eval_overlap.jsonl` (sanity-check).
- Yield report appended to FINDINGS.md.

**Acceptance command:**

```bash
test -f research/anchors/attested.jsonl
wc -l research/anchors/attested.jsonl  # >= 30 ideally; record actual yield
jq '.source' research/anchors/attested.jsonl | sort -u  # source diversity
```

**Effort:** 1 day (manual review).

**Dependencies:** T4.1.

---

### T4.3 — Conditional contrastive LaBSE fine-tune — ✅ CLOSED (negative)

> **Result (2026-05-11):** Closed with a documented negative result. T4.2
> yielded 17 anchors (below the 30-pair gate), so we ran the experiment
> in its "last-resort Option B" form anyway — offline hard-negative
> mining + 17-fold LOO LoRA fine-tune on Vertex T4. 17 / 17 folds
> finished with precision@5 = 0.0; the regression guard stayed quiet
> throughout. Spend ≈ $0.10. Full writeup +per-fold metrics:
> [research/results/labse_hardneg_t43_FINDINGS.md](results/labse_hardneg_t43_FINDINGS.md).
> Vertex job: `4733299958738845696`. Adapter on GCS at
> `gs://openetruscan-rosetta/adapters/labse-attested-v1/` as audit
> artefact, NOT promoted to a versioned vocab partition.

**Goal:** **only if** T4.2 yielded ≥ 30 train-eligible attested pairs,
fine-tune LaBSE with `MultipleNegativesRankingLoss` and re-embed prod
vocab.

**Files to touch:**

- New: `scripts/training/vertex/finetune_labse_contrastive.py`
- New: `scripts/training/vertex/submit_labse_contrastive.sh`

**Steps:**

1. **Gate check:** if `wc -l research/anchors/attested.jsonl < 30`,
   stop. Document the negative result in FINDINGS.md and skip T4.4.
2. Train LaBSE adapter via sentence-transformers'
   `MultipleNegativesRankingLoss` on the attested pairs. 5-10 epochs,
   batch size 16, lr 2e-5. ~30 min on T4.
3. Re-embed the full prod vocab through the adapted model
   (`labse-attested-v1.jsonl`).
4. Ingest into prod with `embedder='LaBSE'`,
   `embedder_revision='attested-v1'`.

**Output:**

- New LaBSE adapter on GCS, vectors ingested behind feature flag.

**Acceptance command:**

```bash
# Gate check first
[[ $(wc -l < research/anchors/attested.jsonl) -ge 30 ]] || \
  { echo "INSUFFICIENT YIELD - SKIP T4.3"; exit 0; }
# Then verify the new vectors are queryable
curl -sf 'https://api.openetruscan.com/neural/rosetta?word=aesar&from=ett&to=lat&k=5&embedder=labse-attested-v1' \
  | jq '.neighbours | length'
# Must be > 0
```

**Effort:** 1.5 days.

**Dependencies:** T4.2 yielded ≥ 30, T2.3 schema in place.

---

### T4.4 — Re-eval against `rosetta-eval-v1` — ✅ CLOSED (subsumed by T4.3)

> **Result (2026-05-11):** Because T4.3 produced no adapter worth
> promoting (LoRA was effectively a no-op against the 17-anchor /
> 24,576-trainable-param budget), there is no `labse-attested` column
> to add to the head-to-head. The negative is already recorded in
> T4.3's findings doc. The `rosetta_eval_v1.sh` harness is unchanged
> and remains the canonical comparison for future adapter candidates
> once the anchor corpus grows (e.g. after Option C community curation
> lands meaningful contributions).

**Goal:** add a fifth column (`labse-attested`) to the head-to-head
table; declare success or honest negative result.

**Files to touch:**

- `evals/rosetta_eval_v1.sh` — add the new model
- [`research/FINDINGS.md`](FINDINGS.md) — update the table

**Acceptance criterion** (from research/ROADMAP.md M3.3):

- **Success**: semantic-field@5 on the held-out *test* split improves
  by ≥ 1.5× over the LaBSE-baseline column. The adapter ships to prod
  by default.
- **Negative**: documented in FINDINGS.md, adapter stays behind the
  flag for future researchers to reproduce.

**Acceptance command:**

```bash
bash evals/rosetta_eval_v1.sh --api-url https://api.openetruscan.com \
  > /tmp/v1-with-attested.json
jq '{
  baseline:    .labse.precision_at_k_semantic_field["5"],
  attested:    .labse_attested.precision_at_k_semantic_field["5"],
  improvement: (.labse_attested.precision_at_k_semantic_field["5"] / .labse.precision_at_k_semantic_field["5"])
}' /tmp/v1-with-attested.json
```

Must produce all three numbers. `improvement ≥ 1.5` is the success
gate but not a hard CI fail — the negative-result branch is also a
publishable outcome.

**Effort:** 0.25 day.

**Dependencies:** T4.3.

---

## Out of scope here (tracked elsewhere)

- M2 qualitative-review pipeline → reopened after Phase 3 if there's
  reviewer availability.
- M4 Phoenician + Oscan populate → tracked in [`WBS.md`](WBS.md);
  out of scope for this WBS unless P3 shows the system already
  generalises.
- Lacuna restorer scaling (XLM-R-large warm-start) → separate WBS;
  the lacuna restorer is in production and not in the rosetta strand.
- Infrastructure hardening / secret rotation → separate operational
  task; doesn't depend on this WBS.

---

## Status tracking

Live status is in the chat session via TodoWrite. The
**source-of-truth** for completed work is `git log --oneline` on the
PRs that close each task ID.

### Results (as of 2026-05-11)

Phase 1 → 5 are all landed except T4.2-T4.4 (anchor review + the
conditional fine-tune that hangs off the yield). The decision-tree
arms in `## Phase summary > Decision tree after each phase` resolved
as follows:

- **After P3 (T3.1):** v4 column produced `field@10 = 0.0625`, *worse*
  than LaBSE's `0.1875` — gap remains → proceed to P5.
- **After P5 (T5.1 + T5.2 + T5.3 + T5.4):** rerank made `field@10`
  *worse* (T5.1 negative result, documented in `FINDINGS.md`).
  Margin-calibrated retention gave a real precision lift at
  `margin ≥ 0.05` (T5.2), but unconditional `field@10` stayed at
  0.1875. Below the ≥ 0.20 publish gate → proceed to P4.

| Task | What it produced | Lands as | Status |
| --- | --- | :---: | :---: |
| **P1 — Defensible eval** | | | |
| T1.1 Levenshtein retrieval baseline | `--baseline=levenshtein` mode + `/neural/rosetta/vocab` endpoint. Strict@10 = 0, field@10 = 0; coverage@0.5 = 0.955 (anchored to surface form) | [#14](https://github.com/Eddy1919/openEtruscan/pull/14) | ✅ |
| T1.2 Random retrieval baseline | `--baseline=random` + analytical `k/V` and `1−C(V−F,k)/C(V,k)` arms | [#15](https://github.com/Eddy1919/openEtruscan/pull/15) | ✅ |
| T1.3 Held-out 40/22 anchor split | `evals/rosetta_eval_pairs.py` with `split` of `train` or `test`; `min_confidence` filter | [#16](https://github.com/Eddy1919/openEtruscan/pull/16) | ✅ |
| T1.4 Threshold-aware coverage | `coverage@{0.50, 0.70, 0.85}` cosine; correctly anchored to *target-side surface form* | [#17](https://github.com/Eddy1919/openEtruscan/pull/17) | ✅ |
| T1.4b Integration glue | All 4 baseline columns side-by-side in one report shape | [#19](https://github.com/Eddy1919/openEtruscan/pull/19) | ✅ |
| T1.5 Frozen `rosetta-eval-v1` | `--benchmark=rosetta-eval-v1` switch + `evals/rosetta_eval_v1.sh` orchestrator. **First frozen run:** model field@10 = 0.1875 | [#20](https://github.com/Eddy1919/openEtruscan/pull/20) | ✅ |
| **P2 — etr-lora-v4 head-to-head** | | | |
| T2.1 Parameterise embed script | `--embedder` + `--revision` flags; `--corpus` accepts local paths | inside [#30](https://github.com/Eddy1919/openEtruscan/pull/30) | ✅ |
| T2.2 Embed prod vocab through v4 | 8,905 ett vectors at `(xlmr-lora, v4)`; Vertex job `xlmr-embed-ett-20260510-200031` | inside [#30](https://github.com/Eddy1919/openEtruscan/pull/30) | ✅ |
| T2.3 Ingest v4 vectors behind a feature flag | Alembic `b7e6f7a8b9c1`: PK extended to `(language, word, embedder, embedder_revision)`; `?embedder=` query param; language-aware alias resolution in [#38](https://github.com/Eddy1919/openEtruscan/pull/38) | [#30](https://github.com/Eddy1919/openEtruscan/pull/30), [#38](https://github.com/Eddy1919/openEtruscan/pull/38) | ✅ |
| T2.4 Run the head-to-head eval | 4-column eval `{random, levenshtein, labse, v4}`; first complete head-to-head 2026-05-11T08:00:32Z; v4 column = `field@10 = 0.0625` (loses to LaBSE) | [#35](https://github.com/Eddy1919/openEtruscan/pull/35) | ✅ |
| Latin v4 re-embed | 100k Latin tokens through XLM-R-base, ingested under `(xlm-roberta-base, v4)` | [#36](https://github.com/Eddy1919/openEtruscan/pull/36) | ✅ |
| **P3 — Findings refresh** | | | |
| T3.1 FINDINGS.md head-to-head table | 4-column table + decision-tree verdict; gap remains → P5 | [#39](https://github.com/Eddy1919/openEtruscan/pull/39) | ✅ |
| T3.2 Reproducibility manifest | Audit-grade `reproduce-rosetta-eval-v1.md` — alembic head pinned, GCS md5 hashes, run-log table | [#37](https://github.com/Eddy1919/openEtruscan/pull/37) | ✅ |
| **P5 — Cheap interventions (sequenced before P4)** | | | |
| T5.1 Cross-encoder rerank | BGE rerank-v2-m3 wired into the harness via `--rerank`. **Negative result:** field@10 0.1875 → 0.1250 (worse). Documented as publishable. | [#40](https://github.com/Eddy1919/openEtruscan/pull/40), [#41](https://github.com/Eddy1919/openEtruscan/pull/41) | ✅ |
| T5.2 Calibration curve | Per-pair `top1_margin` + `calibration_curve` block; at `τ ≥ 0.05` precision@5 lifts 2.7× | [#42](https://github.com/Eddy1919/openEtruscan/pull/42) | ✅ |
| T5.3 `min_margin` query param | `/neural/rosetta?min_margin=…` empties when margin < τ | [#42](https://github.com/Eddy1919/openEtruscan/pull/42) | ✅ |
| T5.4 Dual-track API | `?track=` accepting `semantic`, `loanword`, or `all`; semantic drops the `apa→apa` loanword leak | [#42](https://github.com/Eddy1919/openEtruscan/pull/42) | ✅ |
| **P4 — Primary-source mining (proceeding because gap remains)** | | | |
| T4.1 LLM-as-parser | `scripts/research/llm_extract_anchors.py` using Gemini 2.5 Pro on Vertex (`double-runway`). **Result:** 27 raw glosses from 1,795 passages, 9 hallucination-drops, $4.46 (under $5 gate). Substituted Gemini for Claude because Anthropic-on-Vertex isn't enabled in the project. | [#45](https://github.com/Eddy1919/openEtruscan/pull/45) | ✅ |
| **T4.2 Anchor review + dedup** | Hand-curated `attested.jsonl` from the 27 raw rows (rough triage suggests ~13 solid + ~5 plausible + ~9 reject) | TBD | 🟡 **NEXT** |
| T4.3 Conditional contrastive LaBSE fine-tune | Ran as "Option B last-resort" with 17 anchors + offline-mined hard negs; 17/17 LOO folds p@5=0.0; adapter on GCS as audit artefact only | ~$0.10 (T4, 2m01s) | ✅ closed-negative (2026-05-11) |
| T4.4 Re-eval against rosetta-eval-v1 | Subsumed by T4.3 — no adapter worth promoting; harness unchanged for future adapter candidates | n/a | ✅ closed-negative (2026-05-11) |

### Infrastructure side-quests (completed during this WBS)

These weren't in the WBS but were unblockers / quality-of-life lifts
that landed alongside the research tasks:

| Side-quest | Why it mattered | PR |
| --- | --- | :---: |
| Migrate CI/CD from GitHub Actions to Cloud Build | Removed WIF gymnastics, single billing surface, native Secret-Manager access | [#21](https://github.com/Eddy1919/openEtruscan/pull/21) onwards |
| Phantom alembic-revision recovery (`j5e6f7a8b9c0`) | Unblocked prod deploys that were stuck mid-T2.3 | inside [#30](https://github.com/Eddy1919/openEtruscan/pull/30) |
| Zenodo concept-DOI `10.5281/zenodo.20075836` backfill | Made the corpus citeable; surfaced in `/cite` page | (multiple) |
| HF Hub push of `etr-lora-v4` | Adapter live at <https://huggingface.co/Eddy1919/etr-lora-v4> | [#43](https://github.com/Eddy1919/openEtruscan/pull/43) |
| Weekly security-scan Cloud Scheduler | Reproducible setup script with the three non-obvious IAM bindings encoded | [#44](https://github.com/Eddy1919/openEtruscan/pull/44) |
| `openetruscan-ci-pr` trigger fix | `commentControl: COMMENTS_ENABLED → COMMENTS_ENABLED_FOR_EXTERNAL_CONTRIBUTORS_ONLY` so maintainer PRs auto-build | (gcloud, no PR) |
| `openetruscan-ci-matrix` shared-DB-race fix | Per-Python-version isolated test databases | [#46](https://github.com/Eddy1919/openEtruscan/pull/46) |
| Repo hygiene (`yolo*.pt`, `bandit.json` untracked) | ~11.5 MB off the working tree | [#47](https://github.com/Eddy1919/openEtruscan/pull/47) |
| Pelagios Network metadata + manifesto surfacing | Machine-readable membership in CITATION.cff / .zenodo.json / codemeta.json + 6th principle on the frontend manifesto | [#48](https://github.com/Eddy1919/openEtruscan/pull/48) + frontend [#3](https://github.com/Eddy1919/openEtruscan-frontend/pull/3) |
