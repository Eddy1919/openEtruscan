#!/usr/bin/env python3
"""Build a corpus-grounded eval set for the hybrid search NDCG@10 harness.

The seed set at ``evals/search_eval_queries.jsonl`` originally used placeholder
``TLE_*`` IDs that did not exist in the corpus, so the harness scored 0.0 on
every query. This script downloads the full corpus once and rewrites the seed
to use real inscription IDs, with relevance defined as objective substring
match in the canonical / raw_text columns.

Methodology notes:
  - Relevance is binary, derived from a *deterministic substring rule*: an
    inscription is "relevant" to query Q iff Q (case-insensitive, NFC-normalised)
    appears in either ``canonical`` or ``raw_text``. This is a recall-oriented
    proxy, not a ground-truth measure of scholarly relevance — but it has the
    crucial property of being reproducible and bias-free, so NDCG@10 changes
    are signal about the retrieval pipeline rather than about labelling drift.
  - Queries that match zero rows or every row are dropped (uninformative).
  - Queries that match more than 200 rows are dropped (the gold set is too
    fuzzy to score top-10 retrieval against). Those are typically very common
    bigrams ("la", "ar") that the seed should not have included.
  - Categories from the seed are preserved when present.

Run from repo root:
    python evals/build_eval_set.py [--api-url https://api.openetruscan.com]

Writes back to ``evals/search_eval_queries.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import httpx

EVAL_FILE = Path(__file__).parent / "search_eval_queries.jsonl"
PAGE_SIZE = 500
MAX_GOLD_PER_QUERY = 200


def fetch_corpus(api_url: str) -> list[dict]:
    """Page through /search and collect (id, canonical, raw_text) for every row."""
    rows: list[dict] = []
    offset = 0
    while True:
        resp = httpx.get(
            f"{api_url}/search",
            params={"limit": PAGE_SIZE, "offset": offset},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        chunk = data.get("results", [])
        if not chunk:
            break
        for r in chunk:
            rows.append(
                {
                    "id": str(r.get("id", "")),
                    "canonical": (r.get("canonical") or "").lower(),
                    "raw_text": (r.get("raw_text") or "").lower(),
                }
            )
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        print(f"  fetched {len(rows)}/{data.get('total', '?')}", file=sys.stderr)
    return rows


def normalise(s: str) -> str:
    return unicodedata.normalize("NFC", s).lower()


def gold_for(query: str, corpus: list[dict]) -> list[str]:
    q = normalise(query)
    if not q:
        return []
    return [
        row["id"]
        for row in corpus
        if q in row["canonical"] or q in row["raw_text"]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="https://api.openetruscan.com")
    args = parser.parse_args()

    print(f"Reading seed queries from {EVAL_FILE}", file=sys.stderr)
    seed = [json.loads(line) for line in EVAL_FILE.read_text().splitlines() if line.strip()]
    print(f"  {len(seed)} seed queries", file=sys.stderr)

    print(f"Downloading corpus from {args.api_url}", file=sys.stderr)
    corpus = fetch_corpus(args.api_url)
    print(f"  {len(corpus)} rows", file=sys.stderr)

    out: list[dict] = []
    dropped_zero = 0
    dropped_too_many = 0
    for q in seed:
        query = q["query"]
        # Strip search-modifier syntax — the eval is per-token, not per-phrase.
        # Multi-word queries like "funerary Cerveteri" stay multi-word; the
        # substring rule handles them naturally.
        gold = gold_for(query, corpus)
        if not gold:
            dropped_zero += 1
            continue
        if len(gold) > MAX_GOLD_PER_QUERY:
            dropped_too_many += 1
            continue
        out.append(
            {
                "query": query,
                "relevant_ids": sorted(gold)[:MAX_GOLD_PER_QUERY],
                "category": q.get("category", "uncategorised"),
                "n_relevant": len(gold),
            }
        )

    print(
        f"Kept {len(out)} queries; dropped {dropped_zero} (zero matches), "
        f"{dropped_too_many} (>{MAX_GOLD_PER_QUERY} matches)",
        file=sys.stderr,
    )

    with EVAL_FILE.open("w") as fh:
        for q in out:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")

    print(f"Wrote {EVAL_FILE}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
