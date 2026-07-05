"""v2 neural classifier retrain — head-to-head against TF-IDF+NB baseline.

Trains and evaluates each neural architecture the project ships against the
SAME v2 frozen splits used by `train_classifier.py` (the TF-IDF+NB baseline):

  --arch charcnn           character-level CNN     (~50K params)
  --arch microtransformer  2-layer 4-head xfmr    (~500K params)
  --arch embedding-mlp     MLP on sentence-transformer embeddings (~50K params + frozen encoder)

All run with the same train pool (silver labels NOT in test split) and eval
on the same 159-row candidate-gold set. Bootstrap 95% CIs on every metric so
results are directly comparable to the TF-IDF+NB baseline at macro F1 = 0.312
± 0.036. Paired-bootstrap p-values are computed offline by a separate
comparison script once each arch's predictions are uploaded to GCS.

Honest framing
--------------
- Train labels remain SILVER (v1 reasoning cascade). Eval labels are
  CONSENSUS-SILVER (2-rater LLM-jury, unanimous, conf ≥ medium).
- The point of this retrain is to confirm or refute the audit hypothesis
  that "the bottleneck is data, not architecture" — i.e., that none of the
  3 neural architectures dramatically beat the TF-IDF+NB baseline on this
  amount of data.
- Per-class metrics for the rare tail (votive, commercial) will be NaN
  because the candidate-gold eval has no examples of those classes. Same
  caveat as in `train_classifier.py`.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
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

SEED = 42


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _text_field(row: dict) -> str:
    return (
        row.get("canonical_transliterated") or row.get("raw_text") or row.get("text") or ""
    ).strip()


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


# ───────────────────────────────────────────────────────────────────────────
# Architectures
# ───────────────────────────────────────────────────────────────────────────


def train_torch_arch(
    arch: str,
    train_texts: list[str],
    train_labels: list[str],
    eval_texts: list[str],
    eval_labels: list[str],
    epochs: int = 30,
    batch_size: int = 32,
    lr: float = 1e-3,
    patience: int = 5,
    max_len: int = 128,
) -> tuple[list[str], dict[str, Any]]:
    """Train CharCNN or MicroTransformer; return (predictions, train_metrics)."""
    import torch
    from openetruscan.ml.neural import (
        AlphaFocalLoss,
        CharCNN,
        CharVocab,
        MicroTransformer,
    )

    _seed_everything(SEED)

    # Build vocab from train texts only (eval is held out).
    vocab = CharVocab.build(train_texts)
    labels_present = sorted(set(train_labels) | set(eval_labels))
    label_to_idx = {lbl: i for i, lbl in enumerate(labels_present)}
    idx_to_label = {i: lbl for lbl, i in label_to_idx.items()}
    num_classes = len(labels_present)

    def encode(texts: list[str], labels: list[str]):
        x = torch.tensor([vocab.encode(t, max_len) for t in texts], dtype=torch.long)
        y = torch.tensor([label_to_idx[lbl] for lbl in labels], dtype=torch.long)
        return x, y

    x_train, y_train = encode(train_texts, train_labels)
    x_eval, y_eval = encode(eval_texts, eval_labels)

    # Inside-train val (10%) for early stopping. Eval is HELD OUT.
    n_train = len(train_texts)
    rng = random.Random(SEED)
    indices = list(range(n_train))
    rng.shuffle(indices)
    n_val = max(1, n_train // 10)
    val_idx = indices[:n_val]
    tr_idx = indices[n_val:]
    x_tr, y_tr = x_train[tr_idx], y_train[tr_idx]
    x_vl, y_vl = x_train[val_idx], y_train[val_idx]

    if arch == "charcnn":
        model = CharCNN(vocab_size=len(vocab), num_classes=num_classes)
    elif arch == "microtransformer":
        model = MicroTransformer(vocab_size=len(vocab), num_classes=num_classes, max_len=max_len)
    else:
        raise ValueError(f"Unknown torch arch: {arch}")

    n_params = sum(p.numel() for p in model.parameters())
    print(f"  {arch}: {n_params:,} parameters", file=sys.stderr)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    class_counts = torch.bincount(y_tr, minlength=num_classes).float()
    alpha = len(y_tr) / (num_classes * class_counts.clamp(min=1))
    criterion = AlphaFocalLoss(alpha=alpha, gamma=2.0)

    best_val_f1 = 0.0
    best_state: dict[str, Any] | None = None
    no_improve = 0
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(len(x_tr))
        for start in range(0, len(x_tr), batch_size):
            batch = perm[start : start + batch_size]
            xb, yb = x_tr[batch], y_tr[batch]
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
        # Val
        model.eval()
        with torch.no_grad():
            val_preds = model(x_vl).argmax(dim=1).cpu().numpy()
        from sklearn.metrics import f1_score

        val_f1 = f1_score(y_vl.numpy(), val_preds, average="macro", zero_division=0)
        if val_f1 > best_val_f1:
            best_val_f1 = float(val_f1)
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                print(
                    f"  early stop at epoch {epoch} (best val F1 {best_val_f1:.3f})",
                    file=sys.stderr,
                )
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        eval_logits = model(x_eval)
        eval_preds = eval_logits.argmax(dim=1).cpu().numpy()
    preds = [idx_to_label[int(i)] for i in eval_preds]

    return preds, {
        "n_params": n_params,
        "best_val_f1": best_val_f1,
        "train_time_s": round(time.time() - t0, 2),
        "vocab_size": len(vocab),
        "max_len": max_len,
        "epochs_run": epoch,
        "labels_present": labels_present,
    }


def train_embedding_mlp(
    train_texts: list[str],
    train_labels: list[str],
    eval_texts: list[str],
    embedder_id: str,
    hidden_layer_sizes: tuple[int, ...] = (128, 64),
) -> tuple[list[str], dict[str, Any]]:
    """Embed texts via a frozen sentence-transformer, train an sklearn MLP.

    Note on label encoding: sklearn>=1.5 with `early_stopping=True` calls
    `np.isnan(y_pred)` during inner-validation scoring, which TypeErrors on
    string class labels. We work around it by integer-encoding labels via
    LabelEncoder for `fit`, then decoding predictions back to strings.
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import LabelEncoder

    _seed_everything(SEED)
    print(f"  loading embedder {embedder_id!r} ...", file=sys.stderr)
    encoder = SentenceTransformer(embedder_id)
    print(
        f"  embedding {len(train_texts)} train + {len(eval_texts)} eval texts ...", file=sys.stderr
    )
    t0 = time.time()
    x_train = np.asarray(
        encoder.encode(train_texts, normalize_embeddings=True, show_progress_bar=False),
        dtype=np.float32,
    )
    x_eval = np.asarray(
        encoder.encode(eval_texts, normalize_embeddings=True, show_progress_bar=False),
        dtype=np.float32,
    )
    embed_time = time.time() - t0

    label_encoder = LabelEncoder()
    y_train = label_encoder.fit_transform(train_labels)

    mlp = MLPClassifier(
        hidden_layer_sizes=hidden_layer_sizes,
        activation="relu",
        solver="adam",
        max_iter=500,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=SEED,
    )
    t1 = time.time()
    mlp.fit(x_train, y_train)
    train_time = time.time() - t1
    pred_idx = mlp.predict(x_eval)
    preds = label_encoder.inverse_transform(pred_idx).tolist()
    return preds, {
        "n_params": sum(c.size for c in mlp.coefs_) + sum(b.size for b in mlp.intercepts_),
        "best_val_f1": float(getattr(mlp, "best_validation_score_", 0.0) or 0.0),
        "embedder": embedder_id,
        "embed_dim": int(x_train.shape[1]),
        "embed_time_s": round(embed_time, 2),
        "train_time_s": round(train_time, 2),
        "hidden_layer_sizes": list(hidden_layer_sizes),
        "labels_present": sorted(set(train_labels)),
    }


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--arch", required=True, choices=["charcnn", "microtransformer", "embedding-mlp"]
    )
    ap.add_argument("--train-pool", type=Path, required=True)
    ap.add_argument("--eval-gold", type=Path, required=True)
    ap.add_argument("--out-metrics", type=Path, required=True)
    ap.add_argument("--out-predictions", type=Path, required=True)
    ap.add_argument(
        "--embedder",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="Sentence-transformer model id for --arch embedding-mlp.",
    )
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--n-resamples", type=int, default=10_000)
    args = ap.parse_args(argv)

    train_rows = _load_jsonl(args.train_pool)
    eval_rows = _load_jsonl(args.eval_gold)
    train_ids = {r["id"] for r in train_rows}
    eval_ids = {r["id"] for r in eval_rows}
    if train_ids & eval_ids:
        print(f"ABORT: train/eval contamination ({len(train_ids & eval_ids)} ids)", file=sys.stderr)
        return 2

    train_pairs = [(_text_field(r), r["silver_label"]) for r in train_rows]
    train_pairs = [(t, lbl) for t, lbl in train_pairs if t and lbl]
    eval_pairs = []
    for r in eval_rows:
        text = _text_field(r)
        label = r.get("gold_label") or r.get("jury_summary", {}).get("consensus_label", "")
        if text and label:
            eval_pairs.append((text, label, r["id"]))

    train_texts = [t for t, _ in train_pairs]
    train_labels = [lbl for _, lbl in train_pairs]
    eval_texts = [t for t, _, _ in eval_pairs]
    eval_labels = [lbl for _, lbl, _ in eval_pairs]
    # eval ids are read off `eval_pairs` directly where written below;
    # no separate list needed.

    print(f"arch={args.arch}", file=sys.stderr)
    print(f"  n_train={len(train_pairs)}  classes={dict(Counter(train_labels))}", file=sys.stderr)
    print(f"  n_eval ={len(eval_pairs)}  classes={dict(Counter(eval_labels))}", file=sys.stderr)

    if args.arch in ("charcnn", "microtransformer"):
        preds, train_meta = train_torch_arch(
            args.arch,
            train_texts,
            train_labels,
            eval_texts,
            eval_labels,
            epochs=args.epochs,
        )
    else:  # embedding-mlp
        preds, train_meta = train_embedding_mlp(
            train_texts,
            train_labels,
            eval_texts,
            args.embedder,
        )

    # Build (gold, pred) pairs for bootstrap
    rows_for_metrics = list(zip(eval_labels, preds, strict=False))

    cb_macro = bootstrap_ci(rows_for_metrics, macro_f1, n_resamples=args.n_resamples, seed=SEED)
    cb_acc = bootstrap_ci(rows_for_metrics, accuracy, n_resamples=args.n_resamples, seed=SEED)
    cb_head = bootstrap_ci(rows_for_metrics, head2_f1, n_resamples=args.n_resamples, seed=SEED)
    cb_tail = bootstrap_ci(rows_for_metrics, tail5_f1, n_resamples=args.n_resamples, seed=SEED)

    payload: dict[str, Any] = {
        "arch": args.arch,
        "n_train": len(train_pairs),
        "n_eval": len(eval_pairs),
        "seed": SEED,
        "n_resamples": args.n_resamples,
        "train_meta": train_meta,
        "metrics": {
            "macro_f1": cb_macro.to_dict(),
            "accuracy": cb_acc.to_dict(),
            "head2_f1_funerary_ownership": cb_head.to_dict(),
            "tail5_f1": cb_tail.to_dict(),
        },
        "per_class": per_class_report(rows_for_metrics),
        "confusion_matrix": confusion_matrix(rows_for_metrics),
    }

    args.out_metrics.parent.mkdir(parents=True, exist_ok=True)
    write_result(args.out_metrics, payload)

    with args.out_predictions.open("w") as f:
        for (gold, _, insc_id), pred in zip(eval_pairs, preds, strict=False):
            f.write(
                json.dumps(
                    {
                        "id": insc_id,
                        "arch": args.arch,
                        "gold_label": gold,
                        "predicted_label": pred,
                        "correct": gold == pred,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"\n── {args.arch} ──", file=sys.stderr)
    print(f"  macro_f1   : {cb_macro.fmt()}", file=sys.stderr)
    print(f"  accuracy   : {cb_acc.fmt()}", file=sys.stderr)
    print(f"  head-2 F1  : {cb_head.fmt()}", file=sys.stderr)
    print(f"  tail-5 F1  : {cb_tail.fmt()}", file=sys.stderr)
    print(f"  → {args.out_metrics}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
