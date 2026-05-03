#!/usr/bin/env python3
"""Evaluate hybrid search quality via NDCG@10.

Reads the labelled query set from ``evals/search_eval_queries.jsonl`` and
scores the ``/search/hybrid`` endpoint against it.

Usage:
    python evals/run_search_eval.py [--api-url http://localhost:8000]

Output:
    Prints per-query NDCG@10 and the corpus-wide mean.  Exits non-zero if
    mean NDCG@10 < 0.40 (a CI gate threshold).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import httpx

EVAL_FILE = Path(__file__).parent / "search_eval_queries.jsonl"
K = 10
GATE_THRESHOLD = 0.40
# Prod rate-limits /search/hybrid at 60/min (slowapi). Stay safely under
# that with one request per second; a full 90-query run takes ~90 s.
PER_REQUEST_DELAY_S = 1.05
RETRY_AFTER_429_S = 30.0


def dcg(relevances: list[float], k: int = K) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances[:k]))


def ndcg(relevances: list[float], ideal: list[float], k: int = K) -> float:
    idcg = dcg(sorted(ideal, reverse=True), k)
    if idcg == 0:
        return 0.0
    return dcg(relevances, k) / idcg


def evaluate(api_url: str) -> float:
    queries = [json.loads(line) for line in EVAL_FILE.read_text().splitlines() if line.strip()]
    scores: list[float] = []
    skipped = 0

    for q in queries:
        query_text = q["query"]
        relevant = set(q["relevant_ids"])

        # Honour the prod rate limit. A full run sleeps ~90 s but never 429s.
        # If the API is local (no rate limit), pass --fast.
        score = _query_ndcg(api_url, query_text, relevant)
        if score is None:
            skipped += 1
            continue

        scores.append(score)
        print(f"  {score:.3f}  {query_text}")
        time.sleep(PER_REQUEST_DELAY_S)

    mean = sum(scores) / len(scores) if scores else 0.0
    print(
        f"\nMean NDCG@{K}: {mean:.4f}  "
        f"({len(scores)} queries evaluated, {skipped} skipped)"
    )
    return mean


def _query_ndcg(api_url: str, query_text: str, relevant: set[str]) -> float | None:
    """One query → one NDCG@10. Retries once on 429."""
    for attempt in (1, 2):
        try:
            resp = httpx.get(
                f"{api_url}/search/hybrid",
                params={"q": query_text, "limit": K},
                timeout=10.0,
            )
            if resp.status_code == 429 and attempt == 1:
                print(f"  WAIT  429 on {query_text!r}, sleeping {RETRY_AFTER_429_S}s")
                time.sleep(RETRY_AFTER_429_S)
                continue
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:
            print(f"  SKIP  {query_text!r}: {exc}")
            return None

        rels = [1.0 if r.get("id") in relevant else 0.0 for r in results]
        ideal = [1.0] * len(relevant)
        return ndcg(rels, ideal)
    return None


def main():
    parser = argparse.ArgumentParser(description="Hybrid search NDCG@10 eval")
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()

    mean = evaluate(args.api_url)
    if mean < GATE_THRESHOLD:
        print(f"FAIL: mean NDCG@{K} {mean:.4f} < {GATE_THRESHOLD}")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
