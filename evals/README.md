# Search-quality eval

This directory holds a reproducible evaluation harness for `/search/hybrid`
based on authority-controlled ground truth: Pleiades place IDs, Trismegistos
cross-corpus IDs, `date_approx` chronology buckets, and findspot vocabularies,
plus a lexical-substring baseline.

## Why this exists

The hybrid retrieval pipeline (BM25 ⊕ pgvector with optional cross-encoder
rerank) is the corpus's primary user-facing surface. Without an automated
quality measure, every retrieval-touching change has to be eyeballed against
spot-checked queries — fine for the first few PRs, intractable as the pipeline
grows. This eval gives us:

1. A **regression detector** (lexical category): if a refactor breaks
   substring recall, NDCG@10 drops measurably.
2. A **quality measure** (place / chronology / cross-corpus categories):
   tests semantic retrieval against linked-data authority, not just lexical
   overlap.
3. **Reproducibility**: every gold set is derived programmatically from the
   live corpus by `build_eval_set.py`, so re-running it against a different
   API instance (staging, a fork, a Cloud Run preview) gives a comparable
   number.

## Files

- `build_eval_set.py` — downloads the corpus from a target API and rewrites
  `search_eval_queries.jsonl` with category-aware gold sets. Run when the
  corpus changes shape (new ingest, new fields populated).
- `search_eval_queries.jsonl` — JSONL, one query per line. Schema:

  ```json
  {"query": "Tarquinia", "relevant_ids": ["AT 1.105", "..."],
   "category": "place_pleiades", "methodology": "shared pleiades_id=413332",
   "n_relevant": 74, "pleiades_id": "413332"}
  ```

- `run_search_eval.py` — calls `/search/hybrid?q=…&limit=10` for each query,
  computes NDCG@10 per query and per category, and exits non-zero on any
  failed `--gate` clause.

## Categories

| name | gold set definition | what it tests | n queries |
|---|---|---|---:|
| `place_pleiades` | rows sharing a Pleiades ID with the queried place | Pelagios-aligned semantic place retrieval (Caere ↔ Cerveteri) | 20 |
| `place_findspot` | rows whose findspot string equals the query | exact findspot retrieval for places without a Pleiades ID | 8 |
| `chronology` | rows whose `date_approx` falls in the period bucket | period-aware retrieval (archaic / classical / late) | 3 |
| `cross_corpus` | rows with any `trismegistos_id` | linked-data reachability via canonical search | 1 |
| `lexical` | rows whose canonical text contains the query as a substring | regression detector for the BM25 + dense recall pipeline | 40 |

## Running it

```bash
# rebuild the gold set against current prod (slow — pages the whole corpus)
python evals/build_eval_set.py

# evaluate prod, default gates
python evals/run_search_eval.py --api-url https://api.openetruscan.com

# get a structured report
python evals/run_search_eval.py --api-url https://api.openetruscan.com --json

# custom gates (fail if any threshold is missed)
python evals/run_search_eval.py --gate "lexical=0.40,place_pleiades=0.30"
```

In CI the harness runs as the `search-quality` job in `.github/workflows/ci.yml`,
gated behind `vars.ENABLE_SEARCH_EVAL == 'true'`. It paces requests at
1.05 s to respect the prod `60/min` rate limit, so a full run takes ~80 s.

## Methodology notes

**Substring relevance is binary.** Each query in the lexical category has
relevant IDs derived from "the query string appears in NFC-normalised
canonical text". This is a recall proxy, not a meaning-relevance measure, but
it is reproducible and bias-free.

**Pleiades relevance is identifier-equivalence.** Two inscriptions are
relevant to the same place query iff they share a Pleiades ID. The query
itself is the canonical modern name (e.g. "Tarquinia"), but the gold set
includes any row whose `findspot` field is "Ager Tarquiniensis", "Tarchna",
or any other surface form of the same place — that's the whole point of
LOD-aware retrieval. The Pleiades-ID → modern-name lookup is hardcoded in
`PLEIADES_QUERY_NAMES` in the builder; verify and extend as new places are
added to the corpus.

**Date buckets are loose.** `archaic = year ≤ -500`, `classical = -500 < year ≤ -300`,
`late = -300 < year ≤ -50`. These are conventional but porous; the category
is intentionally not gated by default.

**Categories not yet covered.**

- *Person/clan retrieval* — the prosopography graph extracted from canonical
  text is currently dominated by parsing artefacts (`:`, `•`, `|` showing up
  as "clans"). Once entity extraction is cleaned up, add a category that
  uses the `entities` and `relationships` tables.
- *Object type / medium / classification* — only 16 rows have these populated;
  not enough signal yet.
- *EAGLE / TEI gold* — the `eagle_id` column is empty across the corpus.
  When the EAGLE ingest lands, add a `cross_corpus_eagle` category.

## What the eval has caught and how it was fixed

**May 2026 — FTS widening.** First run of v2 found that
`/search/hybrid?q=Tarquinia` returned 0 rows even though
`/search?findspot=Tarquinia` returned 47. The `fts_canonical` tsvector
indexed canonical text only; it didn't see findspot, pleiades_id,
trismegistos_id, or any other structured column. Every category that
depended on structured metadata scored 0.0.

Migration `e7c8d9e0f1a2_widen_fts_canonical` rebuilt the tsvector with
weighted ranks: weight A for canonical (primary signal), B for
findspot + cross-corpus IDs, C for source / notes / bibliography.

**May 2026 — structured-query parsing.** With the FTS widened, the two
remaining at-zero categories were `chronology` and `cross_corpus`,
where the queries are *conceptual* ("archaic", "trismegistos") and
those literal strings never appear in any indexed column. Solved by
adding a token-level parser to `/search/hybrid` that maps recognised
words to structured `repo.search` filters:

  | token                 | becomes                        |
  |-----------------------|--------------------------------|
  | `archaic`             | `date_min=-700, date_max=-500` |
  | `classical`           | `date_min=-499, date_max=-300` |
  | `late`                | `date_min=-299, date_max=-50`  |
  | `trismegistos` / `tm` | `has_trismegistos=True`        |
  | `pleiades`            | `has_pleiades=True`            |
  | `eagle`               | `has_eagle=True`               |

Mixed queries split cleanly: `q="archaic larthal"` runs the FTS+dense
pipeline on `larthal` with the date range as a structured WHERE.
`q="archaic late"` widens the date range to span both periods.

```text
              first eval   post FTS    post parser    n
chronology        0.0000   →  0.0000   →   1.0000     3
cross_corpus      0.0000   →  0.0000   →   1.0000     1
place_pleiades    0.0000   →  0.8042   →   0.7939     19
place_findspot    0.0000   →  0.3912   →   0.3912     8
lexical           0.3382   →  0.3242   →   0.3242     40
Macro mean        0.0676   →  0.3039   →   0.7019
```

The default gate now enforces every category that has signal:

```text
lexical=0.25,place_pleiades=0.50,place_findspot=0.20,
chronology=0.80,cross_corpus=0.80,macro_mean=0.50
```

Each threshold is set well below the current baseline so noise doesn't
false-fail, but a real regression in any category will trip the gate.

## Known gaps still to close

- `place_findspot` mean=0.39 is dragged down by full Latin-phrase
  findspots like "Clusii in agro" — those are not normal search
  queries. Could be addressed by canonicalising findspot strings or
  by including the most common bigram of each findspot in the gold set
  generator.
- More period vocabulary: "orientalising", "hellenistic" don't yet
  parse. Add them to `_PERIOD_RANGES` when the corpus has dated rows
  in those windows.
- Person/clan retrieval (deferred): the prosopography graph is
  currently dominated by parsing artefacts (see ROADMAP). Once the
  entity extractor is cleaned up, add a `prosopography` category that
  tests retrieval by clan name.
