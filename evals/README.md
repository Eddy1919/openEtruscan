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

## Known finding (May 2026)

The first run of v2 surfaced a real product gap:

```text
[place_pleiades]  n=20  mean=0.0000   ← all 20 Pelagios place queries: 0
[place_findspot]   n= 8  mean=0.0000   ← all 8 findspot queries: 0
[chronology]      n= 3  mean=0.0000   ← period names not in canonical text
[cross_corpus]    n= 1  mean=0.0000   ← "trismegistos" not in canonical text
[lexical]         n=40  mean=0.3382   ← substring baseline (only signal)
Macro mean: 0.0676
```

`/search/hybrid?q=Tarquinia` returns **zero rows** even though
`/search?findspot=Tarquinia` returns 47. The hybrid retrieval index searches
canonical inscription text only — it doesn't see the `findspot` /
`pleiades_id` / `geonames_id` columns. So users searching "Tarquinia" in the
public search box get nothing.

**Fix path** (not in the eval branch; tracked separately): widen the
`/search/hybrid` query to include findspot / source / cross-corpus columns
in the FTS document, OR cascade to a structured-filter fallback when the
hybrid index returns zero. Once the fix lands, add
`place_pleiades=0.30,place_findspot=0.30` to the default gate in
`run_search_eval.py` so this can't silently regress again.

This is exactly the kind of gap a real eval is supposed to find — the
substring baseline missed it entirely because place names rarely appear
inside the canonical text of the inscriptions found at those places.
