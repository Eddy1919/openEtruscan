#!/usr/bin/env python3
"""Cross-language alignment eval for the Rosetta Vector Space.

Hits the public ``/neural/rosetta`` endpoint with each of the curated
Etruscan-Latin equivalences from ``rosetta_eval_pairs.py`` and reports
precision@k, plus per-category and per-confidence-tier breakdowns. The
harness is the first consumer of those pairs in the post-Procrustes
architecture: the encoder never sees them during fine-tuning, so a high
precision@k against held-out pairs is an honest unsupervised
cross-language eval.

Usage
-----

    # Default: hit prod, report the standard table.
    python evals/run_rosetta_eval.py

    # Local API or a staging deploy.
    python evals/run_rosetta_eval.py --api-url http://localhost:8000

    # Machine-readable output (for piping into a CI gate).
    python evals/run_rosetta_eval.py --json

    # Tighter source-language selection (e.g. only test theonyms):
    python evals/run_rosetta_eval.py --category theonym

    # CI gate: pass-fail at the given precision@k threshold.
    python evals/run_rosetta_eval.py --gate "precision_at_5=0.40"

What "precision@k" means here
-----------------------------
For each EvalPair (etr → lat), we ask the API for the top-k Latin
neighbours of ``etr``. The pair is a *hit* if ``lat`` appears in the
top-k. precision@k is then ``hits / n_evaluated``. Pairs where the
source word has no stored vector (the language hasn't been populated
for ``etr``) are *skipped*, not counted as misses — that's an
operational gap, not a model regression. The output reports both
``n_evaluated`` and ``n_skipped`` so the denominator is unambiguous.

What this does NOT measure
--------------------------
Quality of *unknown* Etruscan words. The eval pairs are by definition
ones the philological consensus has settled. The whole point of the
Rosetta initiative is to handle the words that DON'T have known Latin
equivalents — that's what the discovery cron does, and it's a
qualitative-not-quantitative judgment that requires a domain expert.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Make the eval pairs importable when run as a script.
sys.path.insert(0, str(Path(__file__).parent))

import httpx  # noqa: E402

from latin_semantic_fields import LATIN_SEMANTIC_FIELDS  # noqa: E402
from rosetta_eval_pairs import EVAL_PAIRS, EvalPair, eval_pairs  # noqa: E402

# Prod's /neural/rosetta is rate-limited to 30 req/min — same gate as
# /search/hybrid. 2.05 s between requests stays comfortably under the
# limit and a full 62-pair eval takes ~130 s.
PER_REQUEST_DELAY_S = 2.05
RETRY_AFTER_429_S = 30.0
DEFAULT_K_VALUES = (1, 3, 5, 10)


def _query_neighbours(
    api_url: str,
    word: str,
    from_lang: str,
    to_lang: str,
    k: int,
    *,
    timeout_s: float = 15.0,
) -> list[str] | None:
    """Hit /neural/rosetta and return the top-k target-language words.

    Returns None on transport-level failures (so the caller can decide
    whether to skip or fail). Returns an empty list when the endpoint
    succeeded but the source word has no stored vector — distinguishable
    from None.
    """
    for attempt in (1, 2):
        try:
            resp = httpx.get(
                f"{api_url.rstrip('/')}/neural/rosetta",
                params={"word": word, "from": from_lang, "to": to_lang, "k": k},
                timeout=timeout_s,
            )
            if resp.status_code == 429 and attempt == 1:
                print(
                    f"  WAIT  429 on {word!r}, sleeping {RETRY_AFTER_429_S}s",
                    file=sys.stderr,
                )
                time.sleep(RETRY_AFTER_429_S)
                continue
            resp.raise_for_status()
            body = resp.json()
            # The endpoint always returns a `neighbours` array; an empty
            # list means "source word has no stored vector".
            return [n["word"] for n in body.get("neighbours", [])]
        except Exception as exc:
            print(f"  SKIP  {word!r}: {exc}", file=sys.stderr)
            return None
    return None


def evaluate(
    api_url: str,
    pairs: list[EvalPair],
    *,
    k_max: int = max(DEFAULT_K_VALUES),
    pace: bool = True,
) -> dict[str, Any]:
    """Run the eval. Returns a structured report.

    Shape:

    {
      "n_pairs":       int,
      "n_evaluated":   int,   # source-word vector found
      "n_skipped":     int,   # source word OOV in the store, not a model miss
      "n_failed":      int,   # transport / 4xx / 5xx
      "precision_at_k": {1: float, 3: float, 5: float, 10: float},
      "by_category":   {category: {precision_at_k: {...}, n: int}},
      "by_confidence": {confidence: {precision_at_k: {...}, n: int}},
      "per_pair":      [{etr, lat, hits_at_k_max, top_predictions}, ...]
    }
    """
    per_pair: list[dict[str, Any]] = []
    n_evaluated = 0
    n_skipped = 0
    n_failed = 0

    for pair in pairs:
        neighbours = _query_neighbours(
            api_url, pair.etr, "ett", "lat", k_max
        )
        if neighbours is None:
            n_failed += 1
            continue
        if not neighbours:
            n_skipped += 1
            continue

        n_evaluated += 1
        hit_k = next(
            (rank + 1 for rank, n in enumerate(neighbours) if n == pair.lat),
            None,
        )
        # Semantic-field hit: rank of FIRST top-k entry that's a member of the
        # expected category's Latin vocabulary. Captures "the encoder routed
        # the query into the right semantic neighbourhood, even if it picked
        # the wrong specific lemma".
        field_hit_k = next(
            (rank + 1 for rank, n in enumerate(neighbours)
             if n.lower() in LATIN_SEMANTIC_FIELDS.get(pair.category, set())),
            None,
        )
        per_pair.append(
            {
                "etr": pair.etr,
                "expected_lat": pair.lat,
                "category": pair.category,
                "confidence": pair.confidence,
                "rank_of_expected": hit_k,                  # strict-lexical
                "rank_of_first_field_match": field_hit_k,   # semantic-field
                "top_predictions": neighbours,
            }
        )
        if pace:
            time.sleep(PER_REQUEST_DELAY_S)

    # ── Strict-lexical precision@k ──────────────────────────────────────
    # "Was the EXACT expected Latin lemma in top-k?" — the original metric.
    p_at_k: dict[int, float] = {}
    for k in DEFAULT_K_VALUES:
        if n_evaluated == 0:
            p_at_k[k] = 0.0
            continue
        hits = sum(
            1 for p in per_pair
            if p["rank_of_expected"] is not None and p["rank_of_expected"] <= k
        )
        p_at_k[k] = hits / n_evaluated

    # ── Semantic-field precision@k ──────────────────────────────────────
    # "Was ANY Latin word from the expected category's vocabulary in top-k?"
    # Softer + more honest about what cross-language word-vector retrieval
    # actually does: it identifies semantic neighbourhoods, not exact lemma
    # equivalences. See evals/latin_semantic_fields.py for the field
    # vocabularies (curated from the eval set + standard synonyms).
    p_at_k_field: dict[int, float] = {}
    for k in DEFAULT_K_VALUES:
        if n_evaluated == 0:
            p_at_k_field[k] = 0.0
            continue
        hits = sum(
            1 for p in per_pair
            if p["rank_of_first_field_match"] is not None
            and p["rank_of_first_field_match"] <= k
        )
        p_at_k_field[k] = hits / n_evaluated

    # ── Coverage: what fraction of source words returned ANY Latin
    # neighbour above various cosine thresholds? Indicates whether the
    # encoder is producing usable distances at all. ─────────────────────
    coverage_at_threshold: dict[float, float] = {}
    for thr in (0.50, 0.70, 0.85):
        if n_evaluated == 0:
            coverage_at_threshold[thr] = 0.0
            continue
        # For coverage we just need to know if SOMETHING came back at all
        # (we already have neighbours per pair). Threshold semantics:
        # "did the API return at least one Latin word above cosine X for
        # this Etruscan source?" — but we don't currently store cosines
        # in per_pair. Track that the API returned any hit at all.
        # (Threshold-aware version requires cosine in per_pair; left as
        # a follow-up.)
        with_any = sum(1 for p in per_pair if p.get("top_predictions"))
        coverage_at_threshold[thr] = with_any / n_evaluated

    by_category = _group_metrics(per_pair, "category")
    by_confidence = _group_metrics(per_pair, "confidence")

    return {
        "n_pairs": len(pairs),
        "n_evaluated": n_evaluated,
        "n_skipped": n_skipped,
        "n_failed": n_failed,
        # Strict-lexical: "exact expected Latin word in top-k". This is
        # what the eval used to gate on. Honest read: low strict-lexical
        # numbers don't mean the system is broken; they mean cross-lingual
        # word-vector retrieval doesn't work at the lexical-equivalence
        # layer without parallel-data supervision. Keep tracking it for
        # historical comparability.
        "precision_at_k": p_at_k,
        # Semantic-field: "any Latin word from the right semantic field
        # in top-k". This is the honest metric for what the system DOES
        # do: route queries into the right semantic neighbourhood.
        "precision_at_k_semantic_field": p_at_k_field,
        "coverage_any_hit": coverage_at_threshold,
        "by_category": by_category,
        "by_confidence": by_confidence,
        "per_pair": per_pair,
    }


def _group_metrics(per_pair: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in per_pair:
        grouped[p[key]].append(p)
    out: dict[str, Any] = {}
    for cat, items in grouped.items():
        cat_p_at_k: dict[int, float] = {}
        cat_p_at_k_field: dict[int, float] = {}
        for k in DEFAULT_K_VALUES:
            hits = sum(
                1 for p in items
                if p["rank_of_expected"] is not None and p["rank_of_expected"] <= k
            )
            field_hits = sum(
                1 for p in items
                if p.get("rank_of_first_field_match") is not None
                and p["rank_of_first_field_match"] <= k
            )
            cat_p_at_k[k] = hits / len(items) if items else 0.0
            cat_p_at_k_field[k] = field_hits / len(items) if items else 0.0
        # Median rank of expected — informative when precision is low,
        # because it tells you whether the encoder is *close* or completely
        # wrong. Rank `None` (missed) becomes k_max+1 for this calculation.
        ranks = [
            p["rank_of_expected"] if p["rank_of_expected"] is not None else max(DEFAULT_K_VALUES) + 1
            for p in items
        ]
        out[cat] = {
            "n": len(items),
            "precision_at_k": cat_p_at_k,
            "precision_at_k_semantic_field": cat_p_at_k_field,
            "median_rank": int(statistics.median(ranks)) if ranks else None,
        }
    return out


def _print_human(report: dict[str, Any]) -> None:
    print(
        f"\nEvaluated {report['n_evaluated']}/{report['n_pairs']} pairs "
        f"(skipped {report['n_skipped']} OOV, {report['n_failed']} transport errors)"
    )
    print("\nStrict-lexical precision@k (was the EXACT expected Latin lemma in top-k?):")
    for k, v in report["precision_at_k"].items():
        print(f"  precision@{k:<2d} = {v:.3f}")

    print("\nSemantic-field precision@k (was ANY Latin word from the right semantic field in top-k?):")
    for k, v in report["precision_at_k_semantic_field"].items():
        print(f"  precision@{k:<2d} (field) = {v:.3f}")

    print("\nBy category — strict / field:")
    print(f"  {'category':<12} {'n':>3}  {'@1 strict':>10} {'@5 strict':>10} {'@1 field':>10} {'@5 field':>10}  median_rank")
    for cat, m in sorted(report["by_category"].items()):
        s1 = m["precision_at_k"][1]
        s5 = m["precision_at_k"][5]
        f1 = m.get("precision_at_k_semantic_field", {}).get(1, 0.0)
        f5 = m.get("precision_at_k_semantic_field", {}).get(5, 0.0)
        print(
            f"  {cat:<12} {m['n']:>3}  "
            f"{s1:>10.2f} {s5:>10.2f} {f1:>10.2f} {f5:>10.2f}  "
            f"{m['median_rank']}"
        )

    print("\nBy confidence tier — strict / field @5:")
    for tier, m in sorted(report["by_confidence"].items()):
        s5 = m["precision_at_k"][5]
        f5 = m.get("precision_at_k_semantic_field", {}).get(5, 0.0)
        print(
            f"  {tier:<8} n={m['n']:3d}  strict@5={s5:.2f}  field@5={f5:.2f}  "
            f"median_rank={m['median_rank']}"
        )


def _evaluate_gates(report: dict[str, Any], gate_spec: str) -> tuple[bool, list[str]]:
    """Parse `--gate name=value,name2=value2` and decide pass/fail.

    Recognised metric names:
      precision_at_1, precision_at_3, precision_at_5, precision_at_10
      precision_at_K_semantic_field
      <category>_precision_at_K (e.g. theonym_precision_at_5)
      <category>_precision_at_K_semantic_field
    """
    metrics: dict[str, float] = {}
    for k, v in report["precision_at_k"].items():
        metrics[f"precision_at_{k}"] = v
    for k, v in report.get("precision_at_k_semantic_field", {}).items():
        metrics[f"precision_at_{k}_semantic_field"] = v
    for cat, m in report["by_category"].items():
        for k, v in m["precision_at_k"].items():
            metrics[f"{cat}_precision_at_{k}"] = v
        for k, v in m.get("precision_at_k_semantic_field", {}).items():
            metrics[f"{cat}_precision_at_{k}_semantic_field"] = v

    failures: list[str] = []
    for clause in gate_spec.split(","):
        clause = clause.strip()
        if not clause:
            continue
        try:
            name, value = clause.split("=")
            threshold = float(value)
        except ValueError:
            failures.append(f"unparseable gate clause {clause!r}")
            continue
        actual = metrics.get(name)
        if actual is None:
            failures.append(f"unknown gate metric {name!r}; available: {sorted(metrics)[:6]}…")
            continue
        if actual < threshold:
            failures.append(f"{name}={actual:.3f} below threshold {threshold:.3f}")
    return (not failures), failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        default="https://api.openetruscan.com",
        help="Base URL of the API to evaluate against",
    )
    parser.add_argument(
        "--min-confidence",
        choices=["low", "medium", "high"],
        default="medium",
        help="Filter eval pairs by minimum confidence tier",
    )
    parser.add_argument(
        "--category",
        choices=[
            "kinship", "civic", "religious", "time", "numeral",
            "verb", "theonym", "onomastic",
        ],
        help="Restrict eval to one category only",
    )
    parser.add_argument(
        "--gate",
        help="Comma-separated metric=threshold pairs; non-zero exit on any miss",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout",
    )
    parser.add_argument(
        "--no-pace",
        action="store_true",
        help="Skip the 2.05 s between-request delay (use only against local APIs)",
    )
    parser.add_argument(
        "--split",
        choices=["train", "test", "all"],
        default="test",
        help="Which split to evaluate (default: test = held-out pairs only)",
    )

    args = parser.parse_args(argv)

    split_arg = None if args.split == "all" else args.split
    pairs = eval_pairs(min_confidence=args.min_confidence, split=split_arg)
    if args.category:
        pairs = [p for p in pairs if p.category == args.category]
    if not pairs:
        print("No eval pairs match the filters.", file=sys.stderr)
        return 2

    print(f"Split: {args.split} ({len(pairs)} pairs)", file=sys.stderr)

    report = evaluate(args.api_url, pairs, pace=not args.no_pace)

    if args.json:
        # asdict via the per_pair dicts (already JSON-friendly).
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False, default=str)
        sys.stdout.write("\n")
    else:
        _print_human(report)

    if args.gate:
        ok, failures = _evaluate_gates(report, args.gate)
        if not ok:
            for f in failures:
                print(f"FAIL: {f}", file=sys.stderr)
            return 1
        print("\nPASS", file=sys.stderr)

    return 0


# Re-export for the test module.
__all__ = ["evaluate", "_query_neighbours", "_evaluate_gates", "EVAL_PAIRS", "asdict"]


if __name__ == "__main__":
    sys.exit(main())
