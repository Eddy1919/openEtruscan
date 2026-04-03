#!/usr/bin/env python3
"""
Standalone training script — trains CharCNN and MicroTransformer on the corpus,
prints a comparison table, and exports models.

Usage:
    python scripts/train_neural.py --db-url $DATABASE_URL --output data/models/ --epochs 30
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    import os

    from dotenv import load_dotenv
    load_dotenv(".env")

    parser = argparse.ArgumentParser(description="Train neural inscription classifiers.")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL", "postgresql://corpus_reader:etruscan_secret@34.76.146.115/corpus"),
        help="Path to PostgreSQL database.",
    )
    parser.add_argument(
        "--output",
        default="data/models/",
        help="Output directory for models and metrics.",
    )
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs.")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size.")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate.")
    parser.add_argument("--patience", type=int, default=5, help="Early stopping patience.")
    parser.add_argument(
        "--arch",
        choices=["cnn", "transformer", "both"],
        default="both",
        help="Architecture to train.",
    )
    args = parser.parse_args()

    from openetruscan.neural import NeuralClassifier

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    all_metrics: dict[str, dict] = {}

    archs = ["cnn", "transformer"] if args.arch == "both" else [args.arch]

    for arch in archs:
        print(f"\n{'=' * 60}")
        print(f"  Training {arch.upper()}")
        print(f"{'=' * 60}\n")

        clf = NeuralClassifier(arch=arch)
        metrics = clf.train_from_corpus(
            db_url=args.db_url,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            patience=args.patience,
        )

        # Save model weights
        clf.save(out)
        print(f"  💾 Saved {arch} weights to {out}")

        # Export ONNX
        onnx_path = out / f"{arch}.onnx"
        clf.export_onnx(onnx_path)
        print(f"  💾 Exported ONNX to {onnx_path}")

        all_metrics[arch] = metrics

    # Print comparison table
    print(f"\n{'=' * 60}")
    print("  COMPARISON")
    print(f"{'=' * 60}\n")
    print(f"  {'Model':<22} {'Params':>8} {'Time':>8} {'F1 (macro)':>10}")
    print(f"  {'-' * 22} {'-' * 8} {'-' * 8} {'-' * 10}")
    for arch, m in all_metrics.items():
        time_str = f"{m['train_time_s']:.1f}s"
        print(f"  {arch.upper():<22} {m['params']:>8,} {time_str:>8} {m['val_f1_macro']:>10.4f}")

    # Per-class breakdown
    for arch, m in all_metrics.items():
        print(f"\n  {arch.upper()} per-class:")
        print(f"    {'Class':<15} {'Prec':>6} {'Recall':>6} {'F1':>6} {'N':>5}")
        print(f"    {'-' * 15} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 5}")
        for cls_name, cls_m in m["per_class"].items():
            print(
                f"    {cls_name:<15} "
                f"{cls_m['precision']:>6.3f} "
                f"{cls_m['recall']:>6.3f} "
                f"{cls_m['f1']:>6.3f} "
                f"{cls_m['support']:>5}"
            )

    # Save metrics
    metrics_path = out / "metrics.json"
    metrics_path.write_text(
        json.dumps(all_metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n  📊 Metrics saved to {metrics_path}")


if __name__ == "__main__":
    main()
