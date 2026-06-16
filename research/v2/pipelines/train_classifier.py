"""v2 classifier training — apples-to-apples replacement of the v1 0.28-F1 baseline.

What this does
--------------
1. Train a TF-IDF + Multinomial Naive Bayes classifier on the v2 frozen
   train pool (silver-labeled rows that are NOT in the held-out test split).
2. Predict on the v2 candidate-gold set (the 2-rater unanimous-agreement
   subset of the held-out test pool — our cleanest consensus-silver eval).
3. Score macro-F1, per-class P/R/F1, and accuracy with bootstrap 95% CIs.
4. Drop both the trained model artifact and the eval JSON to GCS.

Why this is the right gate
--------------------------
v1 reported `0.28 macro F1 on 29 held-out rows` (CURATION_FINDINGS.md). v2
trains on a similarly-sized silver pool but evaluates on a >5× larger,
multi-rater-validated set with bootstrap CIs. Same classifier
architecture (TF-IDF char n-grams + NB) makes the comparison apples-to-
apples; the rigor delta is in the *eval* not the *model*.

Honest framing
--------------
- Train labels are SILVER (v1 reasoning cascade). Not gold.
- Eval labels are CONSENSUS-SILVER (2-rater jury, unanimous, conf ≥ medium).
  Not human-gold. Will be re-run when philologist adjudication lands.
- Per-class metrics on the tail (votive, commercial) are NaN because the
  candidate-gold set has 0 examples for them; will populate with broader
  data.

This script is meant to be invoked from cloudbuild/v2-train-classifier.yaml.
Local invocation is also supported for debugging.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from research.v2.eval.bootstrap import bootstrap_ci, write_result  # noqa: E402
from research.v2.eval.classify_metrics import (  # noqa: E402
    accuracy,
    confusion_matrix,
    head2_f1,
    macro_f1,
    per_class_report,
    tail5_f1,
)


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _text_field(row: dict) -> str:
    """Pick the best available text field; fall back gracefully."""
    return (
        row.get("canonical_transliterated") or row.get("raw_text") or row.get("text") or ""
    ).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--train-pool",
        type=Path,
        required=True,
        help="JSONL of silver-labeled training rows (NOT in test split).",
    )
    ap.add_argument(
        "--eval-gold", type=Path, required=True, help="JSONL of candidate-gold rows for eval."
    )
    ap.add_argument(
        "--out-metrics", type=Path, required=True, help="Output JSON with bootstrap-CI'd metrics."
    )
    ap.add_argument(
        "--out-predictions", type=Path, required=True, help="Output JSONL with per-row predictions."
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--n-resamples", type=int, default=10_000, help="Bootstrap resample count for CIs."
    )
    args = ap.parse_args(argv)

    # ── Lazy imports so the module is importable without sklearn ──
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.naive_bayes import MultinomialNB
    except ImportError as e:
        print(f"ERROR: scikit-learn required: {e}", file=sys.stderr)
        return 1

    # ── Load splits ──
    train_rows = _load_jsonl(args.train_pool)
    eval_rows = _load_jsonl(args.eval_gold)
    if not train_rows or not eval_rows:
        print(
            f"ERROR: empty splits (train={len(train_rows)}, eval={len(eval_rows)})", file=sys.stderr
        )
        return 1

    # ── Contamination check: no train id may also be in eval ──
    train_ids = {r["id"] for r in train_rows}
    eval_ids = {r["id"] for r in eval_rows}
    overlap = train_ids & eval_ids
    if overlap:
        print(f"ABORT: train/eval contamination on ids: {sorted(overlap)[:5]}...", file=sys.stderr)
        return 2

    # Train labels are the silver labels. Eval labels are the consensus
    # candidate-gold labels (jury_summary.consensus_label or gold_label).
    train_texts = [_text_field(r) for r in train_rows]
    train_labels = [r["silver_label"] for r in train_rows]
    eval_texts = [_text_field(r) for r in eval_rows]
    eval_labels = [
        r.get("gold_label") or r.get("jury_summary", {}).get("consensus_label", "")
        for r in eval_rows
    ]

    # Drop rows with empty text or missing labels (defensive)
    train_pairs = [(t, lbl) for t, lbl in zip(train_texts, train_labels, strict=False) if t and lbl]
    eval_pairs = [
        (t, lbl, r["id"])
        for t, lbl, r in zip(eval_texts, eval_labels, eval_rows, strict=False)
        if t and lbl
    ]
    if not train_pairs or not eval_pairs:
        print(
            f"ABORT: after empty-text drop, train={len(train_pairs)} eval={len(eval_pairs)}",
            file=sys.stderr,
        )
        return 3

    print(
        f"Train: {len(train_pairs)} rows, labels = {Counter(p[1] for p in train_pairs)}",
        file=sys.stderr,
    )
    print(
        f"Eval:  {len(eval_pairs)} rows, labels = {Counter(p[1] for p in eval_pairs)}",
        file=sys.stderr,
    )

    # ── Train ──
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=3000,
        min_df=2,
    )
    x_train = vectorizer.fit_transform([t for t, _ in train_pairs])
    y_train = [lbl for _, lbl in train_pairs]
    model = MultinomialNB(alpha=0.1)
    model.fit(x_train, y_train)

    # ── Predict ──
    x_eval = vectorizer.transform([t for t, _, _ in eval_pairs])
    y_pred = model.predict(x_eval)
    y_true = [lbl for _, lbl, _ in eval_pairs]

    # ── Eval rows = list of (gold, predicted) tuples for bootstrap_ci wrappers ──
    pairs_for_metrics = list(zip(y_true, y_pred, strict=False))

    cb_macro = bootstrap_ci(
        pairs_for_metrics, macro_f1, n_resamples=args.n_resamples, seed=args.seed
    )
    cb_acc = bootstrap_ci(pairs_for_metrics, accuracy, n_resamples=args.n_resamples, seed=args.seed)
    cb_head = bootstrap_ci(
        pairs_for_metrics, head2_f1, n_resamples=args.n_resamples, seed=args.seed
    )
    cb_tail = bootstrap_ci(
        pairs_for_metrics, tail5_f1, n_resamples=args.n_resamples, seed=args.seed
    )

    payload: dict[str, Any] = {
        "n_train": len(train_pairs),
        "n_eval": len(eval_pairs),
        "classes_in_eval": sorted({lbl for lbl in y_true}),
        "seed": args.seed,
        "n_resamples": args.n_resamples,
        "model": "TF-IDF (char 2-4-gram) + MultinomialNB(alpha=0.1)",
        "metrics": {
            "macro_f1": cb_macro.to_dict(),
            "accuracy": cb_acc.to_dict(),
            "head2_f1_funerary_ownership": cb_head.to_dict(),
            "tail5_f1": cb_tail.to_dict(),
        },
        "per_class": per_class_report(pairs_for_metrics),
        "confusion_matrix": confusion_matrix(pairs_for_metrics),
    }

    args.out_metrics.parent.mkdir(parents=True, exist_ok=True)
    write_result(args.out_metrics, payload)

    with args.out_predictions.open("w") as f:
        for (text, gold, insc_id), pred in zip(eval_pairs, y_pred, strict=False):
            f.write(
                json.dumps(
                    {
                        "id": insc_id,
                        "text": text,
                        "gold_label": gold,
                        "predicted_label": pred,
                        "correct": gold == pred,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print("\n── v2 training result ──", file=sys.stderr)
    print(f"  macro_f1   : {cb_macro.fmt()}", file=sys.stderr)
    print(f"  accuracy   : {cb_acc.fmt()}", file=sys.stderr)
    print(f"  head-2 F1  : {cb_head.fmt()}", file=sys.stderr)
    print(f"  tail-5 F1  : {cb_tail.fmt()}", file=sys.stderr)
    print(f"  → {args.out_metrics}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
