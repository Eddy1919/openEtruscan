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

# ── Frozen reference benchmarks ─────────────────────────────────────────
# A "benchmark" pins the eval parameters so that a single label
# ("rosetta-eval-v1") reproduces *exactly* one numeric table. The model
# under test is still pulled from --api-url, so the benchmark grades a
# *protocol*, not a specific model checkpoint — drop in a new API URL
# and the same benchmark spec produces a comparable number for that
# model. See research/notes/reproduce-rosetta-eval-v1.md.
BENCHMARK_PRESETS: dict[str, dict[str, Any]] = {
    "rosetta-eval-v1": {
        "split": "test",
        "min_confidence": "medium",
        "category": None,
    },
}


def _query_neighbours(
    api_url: str,
    word: str,
    from_lang: str,
    to_lang: str,
    k: int,
    *,
    timeout_s: float = 15.0,
) -> list[tuple[str, float]] | None:
    """Hit /neural/rosetta and return the top-k target-language words and cosines.

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
            return [(n["word"], n["cosine"]) for n in body.get("neighbours", [])]
        except Exception as exc:
            print(f"  SKIP  {word!r}: {exc}", file=sys.stderr)
            return None
    return None


_VOCAB_CACHE: dict[str, list[str]] = {}

def _get_vocab(api_url: str, lang: str) -> list[str]:
    if lang not in _VOCAB_CACHE:
        resp = httpx.get(f"{api_url.rstrip('/')}/neural/rosetta/vocab", params={"lang": lang}, timeout=30.0)
        resp.raise_for_status()
        _VOCAB_CACHE[lang] = resp.json().get("words", [])
    return _VOCAB_CACHE[lang]

def _query_neighbours_levenshtein(
    api_url: str,
    word: str,
    from_lang: str,
    to_lang: str,
    k: int,
    *,
    timeout_s: float = 15.0,
) -> list[tuple[str, float]] | None:
    try:
        vocab = _get_vocab(api_url, to_lang)
    except Exception as exc:
        print(f"  SKIP  {word!r}: {exc}", file=sys.stderr)
        return None
        
    if not vocab:
        return []
        
    def dist(v: str) -> int:
        m, n = len(word), len(v)
        dp = list(range(n + 1))
        for i in range(1, m + 1):
            prev = dp[0]
            dp[0] = i
            for j in range(1, n + 1):
                temp = dp[j]
                if word[i - 1] == v[j - 1]:
                    dp[j] = prev
                else:
                    dp[j] = 1 + min(dp[j], dp[j - 1], prev)
                prev = temp
        return dp[n]
        
    scored = [(dist(v), v) for v in vocab]
    scored.sort()
    
    out = []
    for distance, v in scored[:k]:
        max_len = max(len(word), len(v))
        sim = 1.0 - distance / max_len if max_len > 0 else 1.0
        out.append((v, sim))
    return out
import math

def _random_baseline_metrics(api_url: str, eval_pairs: list[EvalPair]) -> dict[str, Any]:
    """Compute the analytical expected precision@k under uniform random retrieval.
    
    For strict-lexical precision@k, the expected chance of finding the single expected 
    target lemma in a random sample of k items from V items is simply k / V.
    
    For semantic-field precision@k, the expected chance of finding AT LEAST ONE 
    member of the semantic field in a random sample of k items is:
    1 - (chance of finding ZERO members)
    = 1 - C(V-F, k) / C(V, k)
    where F is the size of the semantic field.
    """
    p_at_k: dict[int, float] = {}
    p_at_k_field: dict[int, float] = {}
    
    try:
        vocab_size = len(_get_vocab(api_url, "lat"))
    except Exception as exc:
        print(f"  SKIP random baseline vocab fetch: {exc}", file=sys.stderr)
        vocab_size = 100000

    if not eval_pairs or vocab_size <= 0:
        for k in DEFAULT_K_VALUES:
            p_at_k[k] = 0.0
            p_at_k_field[k] = 0.0
        return {"precision_at_k": p_at_k, "precision_at_k_semantic_field": p_at_k_field}
        
    for k in DEFAULT_K_VALUES:
        strict_sum = 0.0
        field_sum = 0.0
        
        for pair in eval_pairs:
            # Strict-lexical: exactly 1 target lemma
            strict_sum += min(1.0, k / vocab_size)
            
            # Semantic-field: F target lemmas
            F = len(LATIN_SEMANTIC_FIELDS.get(pair.category, set()))
            if vocab_size <= F or vocab_size < k:
                field_sum += 1.0
            elif vocab_size - F < k:
                field_sum += 1.0
            else:
                chance_zero = math.comb(vocab_size - F, k) / math.comb(vocab_size, k)
                field_sum += 1.0 - chance_zero
                
        p_at_k[k] = strict_sum / len(eval_pairs)
        p_at_k_field[k] = field_sum / len(eval_pairs)
        
    return {
        "precision_at_k": p_at_k,
        "precision_at_k_semantic_field": p_at_k_field,
    }


def evaluate(
    api_url: str,
    pairs: list[EvalPair],
    *,
    k_max: int = max(DEFAULT_K_VALUES),
    pace: bool = True,
    baseline: str = "none",
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

    if baseline == "random":
        metrics = _random_baseline_metrics(api_url, pairs)
        return {
            "n_pairs": len(pairs),
            "n_evaluated": len(pairs),
            "n_skipped": 0,
            "n_failed": 0,
            "precision_at_k": metrics["precision_at_k"],
            "precision_at_k_semantic_field": metrics["precision_at_k_semantic_field"],
            "coverage_at_threshold": {0.5: 0.0, 0.7: 0.0, 0.85: 0.0},
            "by_category": {},
            "by_confidence": {},
            "per_pair": [],
        }

    for pair in pairs:
        if baseline == "levenshtein":
            neighbours = _query_neighbours_levenshtein(api_url, pair.etr, "ett", "lat", k_max)
        else:
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
        top_words = [w for w, _ in neighbours]
        top1_cosine = neighbours[0][1] if neighbours else None
        hit_k = next(
            (rank + 1 for rank, n in enumerate(top_words) if n == pair.lat),
            None,
        )
        # Semantic-field hit: rank of FIRST top-k entry that's a member of the
        # expected category's Latin vocabulary. Captures "the encoder routed
        # the query into the right semantic neighbourhood, even if it picked
        # the wrong specific lemma".
        field_hit_k = next(
            (rank + 1 for rank, n in enumerate(top_words)
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
                "top_predictions": top_words,
                "top1_cosine": top1_cosine,
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

    # ── Coverage: what fraction of source words returned a top-1 Latin
    # neighbour above various cosine thresholds? Indicates whether the
    # encoder is producing usable distances at all. ─────────────────────
    coverage_at_threshold: dict[float, float] = {}
    for thr in (0.50, 0.70, 0.85):
        if n_evaluated == 0:
            coverage_at_threshold[thr] = 0.0
            continue
        with_thr = sum(1 for p in per_pair if p.get("top1_cosine") is not None and p["top1_cosine"] >= thr)
        coverage_at_threshold[thr] = with_thr / n_evaluated

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
        "coverage_at_threshold": coverage_at_threshold,
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
    parser.add_argument(
        "--baseline",
        choices=["none", "levenshtein", "random"],
        default="none",
        help="Use a baseline algorithm instead of cross-lingual word-vector retrieval",
    )
    parser.add_argument(
        "--benchmark",
        choices=sorted(BENCHMARK_PRESETS),
        help=(
            "Apply a frozen benchmark preset. Locks --split, --min-confidence, "
            "and --category to the pinned values. CLI overrides are ignored "
            "(with a warning) so the same benchmark label always grades the "
            "same protocol. See research/notes/reproduce-rosetta-eval-v1.md."
        ),
    )

    args = parser.parse_args(argv)

    # ── Benchmark preset locks eval parameters ──────────────────────────
    # The split/min_confidence/category combination defines the benchmark.
    # If the user passes a non-default value alongside --benchmark, warn
    # but keep the preset — the whole point is that "rosetta-eval-v1"
    # numbers from two runs are directly comparable. The model under test
    # is still parameterised via --api-url.
    if args.benchmark:
        preset = BENCHMARK_PRESETS[args.benchmark]
        overrides = []
        if args.split != "test":
            overrides.append(f"--split={args.split} → {preset['split']}")
        if args.min_confidence != "medium":
            overrides.append(
                f"--min-confidence={args.min_confidence} → {preset['min_confidence']}"
            )
        if args.category is not None and preset["category"] is None:
            overrides.append(f"--category={args.category} → (none)")
        if overrides:
            print(
                f"WARN  --benchmark={args.benchmark} locks: "
                + ", ".join(overrides),
                file=sys.stderr,
            )
        args.split = preset["split"]
        args.min_confidence = preset["min_confidence"]
        args.category = preset["category"]

    split_arg = None if args.split == "all" else args.split
    pairs = eval_pairs(min_confidence=args.min_confidence, split=split_arg)
    if args.category:
        pairs = [p for p in pairs if p.category == args.category]
    if not pairs:
        print("No eval pairs match the filters.", file=sys.stderr)
        return 2

    if args.benchmark:
        print(
            f"Benchmark: {args.benchmark} "
            f"(split={args.split}, min_confidence={args.min_confidence}, "
            f"baseline={args.baseline}, api={args.api_url})",
            file=sys.stderr,
        )
    print(f"Split: {args.split} ({len(pairs)} pairs)", file=sys.stderr)


    report = evaluate(args.api_url, pairs, pace=not args.no_pace, baseline=args.baseline)

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
__all__ = [
    "evaluate",
    "_query_neighbours",
    "_query_neighbours_levenshtein",
    "_evaluate_gates",
    "EVAL_PAIRS",
    "asdict",
    "_random_baseline_metrics",
    "BENCHMARK_PRESETS",
]


if __name__ == "__main__":
    sys.exit(main())
