"""Aggregate lacuna_jury_raw.jsonl into v2.0.2 per-model metrics.

For each model in the jury output, computes the three headline metrics with
10 000-resample bootstrap 95% CIs (span_exact_match, char_acc_top1,
hallucination_rate), the per-width-bucket breakdown, and pairwise paired-
bootstrap deltas (one row per ordered pair, restricted to rows where BOTH
models scored a clean gold).

Writes a single JSON summary to --out. Stdout is a human-readable digest in
the same layout the README/INTELLIGENCE_V2.md tables use, so the diff into
those docs is mechanical.

Usage:
    python -m research.v2.eval.compute_lacuna_v2 \\
        --jury research/data/lacuna_jury_raw.jsonl \\
        --out research/private/evaluation/lacuna_v2_0_2.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import bootstrap_ci, paired_bootstrap  # noqa: E402
from lacuna_metrics import (  # noqa: E402
    char_acc_top1,
    char_acc_top3,
    filter_clean,
    hallucination_rate,
    per_bucket_breakdown,
    span_exact_match,
)


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def group_by_model(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[str(r.get("model", "unknown"))].append(r)
    return out


def shared_rows(a: list[dict], b: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (a_aligned, b_aligned) where both have rows for the same ids."""
    a_by_id = {r["id"]: r for r in a}
    b_by_id = {r["id"]: r for r in b}
    common = sorted(set(a_by_id) & set(b_by_id))
    return [a_by_id[i] for i in common], [b_by_id[i] for i in common]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jury", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n-resamples", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    rows = load_rows(args.jury)
    if not rows:
        print(f"ERROR: empty jury at {args.jury}", file=sys.stderr)
        return 1

    by_model = group_by_model(rows)
    summary: dict = {
        "n_total_rows": len(rows),
        "models": sorted(by_model),
        "per_model": {},
        "per_bucket": {},
        "pairs": {},
        "n_resamples": args.n_resamples,
        "seed": args.seed,
    }

    print(f"# v2.0.2 lacuna evaluation — total jury rows: {len(rows)}")
    print(f"# models: {sorted(by_model)}\n")

    for model, mrows in by_model.items():
        clean = filter_clean(mrows)
        n_dirty = len(mrows) - len(clean)
        if not clean:
            summary["per_model"][model] = {"n": 0, "n_dirty_dropped": n_dirty}
            continue
        span_ci = bootstrap_ci(
            clean, span_exact_match, n_resamples=args.n_resamples, seed=args.seed
        )
        char1_ci = bootstrap_ci(clean, char_acc_top1, n_resamples=args.n_resamples, seed=args.seed)
        char3_ci = bootstrap_ci(clean, char_acc_top3, n_resamples=args.n_resamples, seed=args.seed)
        halluc_ci = bootstrap_ci(
            clean, hallucination_rate, n_resamples=args.n_resamples, seed=args.seed
        )
        summary["per_model"][model] = {
            "n": len(clean),
            "n_dirty_dropped": n_dirty,
            "span_exact_match": span_ci.to_dict(),
            "char_acc_top1": char1_ci.to_dict(),
            "char_acc_top3": char3_ci.to_dict(),
            "hallucination_rate": halluc_ci.to_dict(),
        }
        summary["per_bucket"][model] = per_bucket_breakdown(clean)
        print(f"## {model}  (n={len(clean)}, dropped={n_dirty})")
        print(f"  span exact: {span_ci.fmt()}")
        print(f"  char top-1: {char1_ci.fmt()}")
        print(f"  char top-3: {char3_ci.fmt()}")
        print(f"  hallucination: {halluc_ci.fmt()}")
        print()

    models = sorted(by_model)
    for i, m_a in enumerate(models):
        for m_b in models[i + 1 :]:
            a_clean = filter_clean(by_model[m_a])
            b_clean = filter_clean(by_model[m_b])
            a_aligned, b_aligned = shared_rows(a_clean, b_clean)
            if not a_aligned:
                continue
            paired_rows = list(zip(a_aligned, b_aligned, strict=True))
            paired = paired_bootstrap(
                paired_rows,
                lambda rs: span_exact_match([a for a, _ in rs]),
                lambda rs: span_exact_match([b for _, b in rs]),
                n_resamples=args.n_resamples,
                seed=args.seed,
            )
            key = f"{m_a}__vs__{m_b}__span_exact"
            summary["pairs"][key] = {
                "n_shared": len(paired_rows),
                **paired.to_dict(),
            }
            print(f"## {m_a}  vs  {m_b}  (n_shared={len(paired_rows)}, metric=span_exact)")
            print(f"  {paired.fmt()}  significant={paired.is_significant()}")
            print()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"# wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
