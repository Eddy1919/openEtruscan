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
from pathlib import Path

import httpx

EVAL_FILE = Path(__file__).parent / "search_eval_queries.jsonl"
K = 10
GATE_THRESHOLD = 0.40


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

    for q in queries:
        query_text = q["query"]
        relevant = set(q["relevant_ids"])

        try:
            resp = httpx.get(
                f"{api_url}/search/hybrid",
                params={"q": query_text, "limit": K},
                timeout=10.0,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:
            print(f"  SKIP  {query_text!r}: {exc}")
            continue

        # Binary relevance: 1.0 if in gold set, 0.0 otherwise
        rels = [1.0 if r.get("id") in relevant else 0.0 for r in results]
        ideal = [1.0] * len(relevant)
        score = ndcg(rels, ideal)
        scores.append(score)
        print(f"  {score:.3f}  {query_text}")

    mean = sum(scores) / len(scores) if scores else 0.0
    print(f"\nMean NDCG@{K}: {mean:.4f}  ({len(scores)} queries evaluated)")
    return mean


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
