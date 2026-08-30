#!/usr/bin/env python3
"""WP5/WP8 — associative-memory restoration: decoder-only vs decoder+episodic
memory (kNN-LM, which is one modern-Hopfield update over a stored key–value
memory: softmax(β·sim)·values).

Datastore (the "hippocampus"): every teacher-forced decoder hidden state on
the *training* split, keyed to the next gold token. ~30K (state, token)
entries — episodic, lossless, never trained.

Restoration protocol: corrupt each held-out val sequence exactly like
training (span→[MASK] + point masks), then predict the tokens at the damaged
positions, teacher-forced. Systems:
  * decoder-only:      p = softmax(logits)
  * +episodic memory:  p = λ·softmax(logits) + (1−λ)·Σ softmax(β·cos)·onehot
λ, β tuned on a dev slice of the training groups, reported on val.

Gate (WP5): damaged-position accuracy with memory ≥ decoder-only.

Output: out/hopfield_results.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from model_scratch import Seq2Seq
from tokenizer_scratch import BOS, EOS, BPETokenizer
from train_denoiser import corrupt_tracked, pad_to

HERE = Path(__file__).parent
OUT = HERE / "out"
MAX_LEN = 48
SEED = 20260830
TOPK = 32


@torch.no_grad()
def hidden_states(model, x, y_in):
    mem, mem_pad = model.encode(x)
    logits, h = model.decode(y_in, mem, mem_pad, return_hidden=True)
    return logits, h


def main() -> None:
    torch.manual_seed(SEED)
    tok = BPETokenizer.load(OUT / "bpe_tokenizer.json")
    ckpt = torch.load(OUT / "s2s_model.pt", map_location="cpu", weights_only=False)
    model = Seq2Seq(vocab_size=ckpt["vocab_size"], max_len=ckpt["max_len"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    train_df = pd.read_csv(OUT / "train.csv", dtype={"surface": str})
    train_df = train_df[train_df["surface"].fillna("").str.len() > 0].reset_index(drop=True)
    seqs = [tok.encode(t)[: MAX_LEN - 1] for t in train_df["surface"]]

    # same group split as train_denoiser (same seed, same op order)
    groups = np.array(list(train_df["dup_group_id"].unique()), dtype=object)
    g_rng = np.random.default_rng(SEED)
    g_rng.shuffle(groups)
    val_groups = set(groups[: len(groups) // 10])
    is_val = train_df["dup_group_id"].isin(val_groups).to_numpy()
    val_seqs = [s for s, v in zip(seqs, is_val) if v and s]

    # dev slice for tuning: last 10% of *training* groups
    train_groups = [g for g in groups if g not in val_groups]
    dev_groups = set(train_groups[-len(train_groups) // 10:])
    is_dev = train_df["dup_group_id"].isin(dev_groups).to_numpy()
    store_seqs = [s for s, v, d in zip(seqs, is_val, is_dev) if not v and not d and s]
    dev_seqs = [s for s, v, d in zip(seqs, is_val, is_dev) if not v and d and s]
    print(f"store {len(store_seqs)} | dev {len(dev_seqs)} | val {len(val_seqs)}")

    # ---------------- build episodic datastore from CLEAN store sequences
    keys, values = [], []
    B = 64
    for i in range(0, len(store_seqs), B):
        batch = store_seqs[i : i + B]
        x = torch.tensor([pad_to(s, MAX_LEN) for s in batch])
        y_in = torch.tensor([pad_to([BOS] + s, MAX_LEN) for s in batch])
        y_out = [s + [EOS] for s in batch]
        _, h = hidden_states(model, x, y_in)
        for b, targets in enumerate(y_out):
            for j, t in enumerate(targets[: MAX_LEN]):
                keys.append(h[b, j].numpy())
                values.append(t)
    keys = np.stack(keys).astype(np.float32)
    keys /= np.maximum(np.linalg.norm(keys, axis=1, keepdims=True), 1e-9)
    values = np.array(values)
    print(f"datastore: {len(values):,} entries")

    vocab_size = ckpt["vocab_size"]

    def knn_probs(h_vec: np.ndarray, beta: float) -> np.ndarray:
        q = h_vec / max(np.linalg.norm(h_vec), 1e-9)
        sims = keys @ q
        top = np.argpartition(-sims, TOPK)[:TOPK]
        w = np.exp(beta * (sims[top] - sims[top].max()))
        w /= w.sum()
        p = np.zeros(vocab_size)
        np.add.at(p, values[top], w)
        return p

    def damaged_accuracy(eval_seqs, lam: float, beta: float, rng_seed: int):
        rng = np.random.default_rng(rng_seed)
        model_only_c = mix_c = tot = 0
        for s in eval_seqs:
            corr, damaged = corrupt_tracked(s, rng)
            x = torch.tensor([pad_to(corr, MAX_LEN)])
            y_in = torch.tensor([pad_to([BOS] + s, MAX_LEN)])
            logits, h = hidden_states(model, x, y_in)
            pm = F.softmax(logits[0], dim=-1).numpy()
            for j in sorted(damaged):
                if j >= MAX_LEN:
                    continue
                gold = s[j]
                p_model = pm[j]
                pred_m = int(np.argmax(p_model))
                p_knn = knn_probs(h[0, j].numpy(), beta)
                p_mix = lam * p_model + (1 - lam) * p_knn
                pred_x = int(np.argmax(p_mix))
                tot += 1
                model_only_c += int(pred_m == gold)
                mix_c += int(pred_x == gold)
        return model_only_c / max(tot, 1), mix_c / max(tot, 1), tot

    # tune on dev
    best = None
    for lam in (0.3, 0.5, 0.7, 0.9):
        for beta in (5.0, 20.0):
            m0, mx, n = damaged_accuracy(dev_seqs, lam, beta, SEED + 1)
            print(f"dev lam={lam} beta={beta}: model {m0:.4f} mix {mx:.4f} (n={n})")
            if best is None or mx > best[2]:
                best = (lam, beta, mx)
    assert best is not None
    lam, beta, _ = best
    print(f"chosen lam={lam} beta={beta}")

    m0, mx, n = damaged_accuracy(val_seqs, lam, beta, SEED + 2)
    results = {"datastore_entries": int(len(values)), "topk": TOPK,
               "lambda": lam, "beta": beta,
               "val_damaged_positions": n,
               "decoder_only_acc": m0, "decoder_plus_memory_acc": mx}
    (OUT / "hopfield_results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
