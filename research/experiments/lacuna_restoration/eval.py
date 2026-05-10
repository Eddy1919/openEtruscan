#!/usr/bin/env python3
"""Lacuna restoration eval — Approach A (char-MLM) vs Approach B (XLM-R + char head).

Runs both architectures over a fixed 500-row held-out sample drawn
deterministically from the prod DB (seed=42). See README.md for the
protocol and the headline numbers; Finding 9 in CURATION_FINDINGS.md
for the interpretation.

Usage:
    python research/experiments/lacuna_restoration/eval.py
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg2
import torch
from dotenv import load_dotenv
from psycopg2.extras import DictCursor

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(REPO_ROOT / "src"))

from openetruscan.ml.char_mlm import (  # noqa: E402
    ETRUSCAN_CHARS,
    MASK_TOKEN,
    CharMLMConfig,
    CharTokenizer,
    CharTransformerMLM,
)


def load_test_data(limit: int = 500, seed: int = 42) -> list[dict]:
    """Sample held-out (text, mask_pos, target) rows from the prod DB."""
    load_dotenv(REPO_ROOT / ".env")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            """
            SELECT id, canonical_clean
            FROM inscriptions
            WHERE language = 'etruscan'
              AND intact_token_ratio = 1.0
              AND length(canonical_clean) > 10
            ORDER BY md5(id::text)
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    conn.close()

    rng = random.Random(seed)
    char_set = set(ETRUSCAN_CHARS)
    samples: list[dict] = []
    for r in rows:
        text = r["canonical_clean"].lower()
        valid = [i for i, c in enumerate(text) if c in char_set]
        if not valid:
            continue
        pos = rng.choice(valid)
        samples.append(
            {"id": r["id"], "original": text, "target": text[pos], "mask_pos": pos}
        )
    return samples


def _empty_metrics() -> dict:
    return {
        "top1": 0,
        "top3": 0,
        "total": 0,
        "by_char": defaultdict(lambda: {"top1": 0, "total": 0}),
        "by_pos": {
            "start": {"top1": 0, "total": 0},
            "mid": {"top1": 0, "total": 0},
            "end": {"top1": 0, "total": 0},
        },
        "confusion": Counter(),
    }


def _record(metrics: dict, target: str, top: list[str], pos_cat: str) -> None:
    metrics["total"] += 1
    metrics["by_char"][target]["total"] += 1
    metrics["by_pos"][pos_cat]["total"] += 1
    if target == top[0]:
        metrics["top1"] += 1
        metrics["by_char"][target]["top1"] += 1
        metrics["by_pos"][pos_cat]["top1"] += 1
    else:
        metrics["confusion"][(target, top[0])] += 1
    if target in top:
        metrics["top3"] += 1


def _classify_position(text: str, pos: int) -> str:
    word_bounds = {" ", ".", "·", "|", ":", "-"}
    is_start = pos == 0 or text[pos - 1] in word_bounds
    is_end = pos == len(text) - 1 or text[pos + 1] in word_bounds
    return "start" if is_start else ("end" if is_end else "mid")


def _print_metrics(name: str, metrics: dict) -> tuple[float, float]:
    print(f"--- {name} ---")
    top1 = metrics["top1"] / max(metrics["total"], 1)
    top3 = metrics["top3"] / max(metrics["total"], 1)
    print(f"Top-1 Accuracy: {top1:.1%}")
    print(f"Top-3 Accuracy: {top3:.1%}")
    print("\nAccuracy by Position:")
    for cat, m in metrics["by_pos"].items():
        if m["total"]:
            print(f"  {cat:6s}: {m['top1']/m['total']:.1%} ({m['total']} samples)")
    print("\nTop Errors (Target -> Predicted):")
    for (t, p), count in metrics["confusion"].most_common(10):
        print(f"  {t} -> {p}: {count}")
    print()
    return top1, top3


def eval_char_mlm(samples: list[dict], model_dir: str | Path) -> tuple[float, float]:
    """Approach A — character transformer MLM trained from scratch."""
    model_dir = Path(model_dir)
    meta = json.loads((model_dir / "metadata.json").read_text())

    config = CharMLMConfig(
        vocab_size=meta["vocab_size"],
        d_model=meta["d_model"],
        n_layers=meta["n_layers"],
        n_heads=meta["n_heads"],
        max_length=meta["max_length"],
    )
    model = CharTransformerMLM(config)
    model.load_state_dict(
        torch.load(model_dir / "char_mlm_best.pt", map_location="cpu", weights_only=True)
    )
    model.eval()
    tokenizer = CharTokenizer()

    metrics = _empty_metrics()
    for s in samples:
        text, pos, target = s["original"], s["mask_pos"], s["target"]
        masked = text[:pos] + MASK_TOKEN + text[pos + 1 :]
        ids = tokenizer.encode(masked, max_length=config.max_length)
        mask_idx = pos + 1  # +1 for BOS
        if mask_idx >= config.max_length:
            continue
        preds = model.predict_at_mask(
            torch.tensor([ids]), torch.tensor([mask_idx]), top_k=3
        )[0]
        chars = [tokenizer.id_to_char.get(cid, "?") for cid, _ in preds]
        _record(metrics, target, chars, _classify_position(text, pos))

    return _print_metrics("Approach A — Char-MLM from scratch", metrics)


def eval_xlmr_head(samples: list[dict], model_dir: str | Path) -> tuple[float, float]:
    """Approach B — XLM-R + etr-lora-v4 + char prediction head."""
    import torch.nn as nn
    from peft import PeftModel
    from transformers import AutoModel, AutoTokenizer

    model_dir = Path(model_dir)
    meta = json.loads((model_dir / "metadata.json").read_text())

    class CharPredictionHead(nn.Module):
        def __init__(self, hidden_dim: int, num_classes: int) -> None:
            super().__init__()
            self.head = nn.Sequential(
                nn.Dropout(0.1),
                nn.Linear(hidden_dim, 256),
                nn.GELU(),
                nn.LayerNorm(256),
                nn.Linear(256, num_classes),
            )

        def forward(self, hidden_states, mask_positions):
            batch_idx = torch.arange(
                hidden_states.size(0), device=hidden_states.device
            )
            return self.head(hidden_states[batch_idx, mask_positions])

    head = CharPredictionHead(meta["hidden_dim"], meta["num_classes"])
    head.load_state_dict(
        torch.load(model_dir / "char_head_best.pt", map_location="cpu", weights_only=True)
    )
    head.eval()

    tokenizer = AutoTokenizer.from_pretrained(meta["encoder"])
    base_model = AutoModel.from_pretrained(meta["encoder"])
    encoder = PeftModel.from_pretrained(base_model, meta["adapter"])
    encoder = encoder.merge_and_unload()
    encoder.eval()

    id_to_char = {i: c for i, c in enumerate(meta["char_set"])}

    metrics = _empty_metrics()
    for s in samples:
        text, pos, target = s["original"], s["mask_pos"], s["target"]
        masked = text[:pos] + "<mask>" + text[pos + 1 :]
        encoded = tokenizer(masked, return_tensors="pt")
        positions = (encoded.input_ids[0] == tokenizer.mask_token_id).nonzero(as_tuple=True)[0]
        if len(positions) == 0:
            continue
        mask_pos = positions[0].item()

        with torch.no_grad():
            enc_out = encoder(**encoded)
            logits = head(enc_out.last_hidden_state, torch.tensor([mask_pos]))
        probs = torch.nn.functional.softmax(logits[0], dim=-1)
        _, topk_ids = torch.topk(probs, 3)
        chars = [id_to_char[int(i)] for i in topk_ids]
        _record(metrics, target, chars, _classify_position(text, pos))

    return _print_metrics("Approach B — XLM-R + char head", metrics)


def main() -> int:
    samples = load_test_data(limit=500)
    print(f"Loaded {len(samples)} evaluation samples\n")

    # Pull both checkpoints from GCS into data/models/ if not already local.
    for name in ("char-mlm-v1", "lora-char-head-v1"):
        local = REPO_ROOT / "data" / "models" / name
        if not local.exists():
            subprocess.run(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    "-r",
                    f"gs://openetruscan-rosetta/models/{name}",
                    str(REPO_ROOT / "data" / "models"),
                ],
                check=True,
            )

    eval_char_mlm(samples, REPO_ROOT / "data" / "models" / "char-mlm-v1")
    eval_xlmr_head(samples, REPO_ROOT / "data" / "models" / "lora-char-head-v1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
