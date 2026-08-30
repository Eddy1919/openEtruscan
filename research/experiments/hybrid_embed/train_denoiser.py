#!/usr/bin/env python3
"""WP2 — train the from-scratch encoder/decoder as a lacuna-style denoiser.

Corruption mimics real epigraphic damage on the token sequence:
  * span corruption: a contiguous span of 1–3 tokens collapses to one [MASK]
    (a lacuna of unknown length — matches the Leiden `---` convention)
  * random token masking (point damage)
Every training sample gets at least one corruption. Target is the original
sequence; loss is CE over all target positions.

Metrics (group-held-out val, dup_group_id split):
  * full-seq token accuracy (teacher-forced) — inflated by easy copies
  * corrupted-region accuracy — the honest number, gate vs charLM 0.396

Output: out/s2s_model.pt, out/s2s_train_log.json
        out/s2s_pooled.npy           [n_index, d]   (fusion block)
        out/s2s_token_states.npz     ragged per-token states (late interaction)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from model_scratch import Seq2Seq
from tokenizer_scratch import BOS, EOS, MASK, PAD, BPETokenizer

HERE = Path(__file__).parent
OUT = HERE / "out"

MAX_LEN = 48
EPOCHS = 120
BATCH = 64
LR = 3e-4
SEED = 20260830
PATIENCE = 10


def pad_to(ids: list[int], n: int) -> list[int]:
    return ids[:n] + [PAD] * (n - len(ids))


def corrupt_tracked(ids: list[int], rng: np.random.Generator) -> tuple[list[int], set[int]]:
    """ids: token ids without BOS/EOS. Returns (corrupted copy, damaged
    original positions). Span damage collapses to one [MASK] (lacuna of
    unknown length); point damage masks in place. Always >=1 corruption."""
    n = len(ids)
    damaged: set[int] = set()
    if n == 0:
        return list(ids), damaged
    if n >= 2 and rng.random() < 0.7:
        span = int(rng.integers(1, min(3, n) + 1))
        start = int(rng.integers(0, n - span + 1))
        damaged |= set(range(start, start + span))
    for i in range(n):
        if i not in damaged and rng.random() < 0.1:
            damaged.add(i)
    if not damaged:
        damaged.add(int(rng.integers(0, n)))
    out: list[int] = []
    i = 0
    while i < n:
        if i in damaged:
            while i < n and i in damaged:
                i += 1
            out.append(MASK)  # contiguous damaged run -> one MASK
        else:
            out.append(ids[i])
            i += 1
    return out, damaged


def make_batch(seqs: list[list[int]], rng):
    """Returns (x corrupted, y_in, y_out, damaged sets per sample)."""
    xs, yin, yout, dmg = [], [], [], []
    for ids in seqs:
        c, d = corrupt_tracked(ids, rng)
        xs.append(pad_to(c, MAX_LEN))
        yin.append(pad_to([BOS] + ids, MAX_LEN))
        yout.append(pad_to(ids + [EOS], MAX_LEN))
        dmg.append(d)
    return torch.tensor(xs), torch.tensor(yin), torch.tensor(yout), dmg


@torch.no_grad()
def evaluate_val(model, val_seqs, rng) -> tuple[float, float]:
    model.eval()
    full_c = full_t = corr_c = corr_t = 0
    for i in range(0, len(val_seqs), BATCH):
        batch = val_seqs[i : i + BATCH]
        x, y_in, y_out, dmg = make_batch(batch, rng)
        logits = model(x, y_in)
        pred = logits.argmax(-1)
        live = y_out != PAD
        full_c += int((pred[live] == y_out[live]).sum())
        full_t += int(live.sum())
        # damaged-position accuracy: y_out positions align with the original
        # sequence, so the tracked damage set indexes them directly
        for b, d in enumerate(dmg):
            for j in d:
                if j < MAX_LEN:
                    corr_t += 1
                    corr_c += int(pred[b, j] == y_out[b, j])
    return full_c / max(full_t, 1), corr_c / max(corr_t, 1)


def main() -> None:
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    tok = BPETokenizer.load(OUT / "bpe_tokenizer.json")

    train_df = pd.read_csv(OUT / "train.csv", dtype={"surface": str})
    train_df = train_df[train_df["surface"].fillna("").str.len() > 0].reset_index(drop=True)
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    index_df["surface"] = index_df["surface"].fillna("")

    seqs = [tok.encode(t)[: MAX_LEN - 1] for t in train_df["surface"]]

    groups = np.array(list(train_df["dup_group_id"].unique()), dtype=object)
    g_rng = np.random.default_rng(SEED)
    g_rng.shuffle(groups)
    val_groups = set(groups[: len(groups) // 10])
    is_val = train_df["dup_group_id"].isin(val_groups).to_numpy()
    train_seqs = [s for s, v in zip(seqs, is_val) if not v and s]
    val_seqs = [s for s, v in zip(seqs, is_val) if v and s]
    print(f"seqs: {len(train_seqs)} train / {len(val_seqs)} val")

    model = Seq2Seq(vocab_size=len(tok), max_len=MAX_LEN)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"params: {n_params:,}")
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)

    log = {"n_params": n_params, "epochs": []}
    best, best_state, bad = 0.0, None, 0
    val_rng_seed = SEED + 99
    for epoch in range(EPOCHS):
        model.train()
        order = rng.permutation(len(train_seqs))
        losses = []
        for i in range(0, len(order), BATCH):
            batch = [train_seqs[j] for j in order[i : i + BATCH]]
            x, y_in, y_out, _ = make_batch(batch, rng)
            logits = model(x, y_in)
            loss = F.cross_entropy(logits.view(-1, len(tok)), y_out.view(-1),
                                   ignore_index=PAD)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            losses.append(float(loss.detach()))
        full_acc, corr_acc = evaluate_val(model, val_seqs,
                                          np.random.default_rng(val_rng_seed))
        log["epochs"].append({"epoch": epoch, "loss": float(np.mean(losses)),
                              "val_full_acc": full_acc, "val_corrupted_acc": corr_acc})
        print(f"epoch {epoch:03d} loss {np.mean(losses):.4f} "
              f"val full {full_acc:.4f} corrupted {corr_acc:.4f}")
        # early-stop on full-seq accuracy: the damaged-position metric has
        # only ~900 val positions and is too noisy to select a model on
        if full_acc > best:
            best, bad = full_acc, 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= PATIENCE:
                print(f"early stop at {epoch} (best full acc {best:.4f})")
                break

    model.load_state_dict(best_state)
    log["best_val_full_acc"] = best
    torch.save({"state_dict": model.state_dict(), "vocab_size": len(tok),
                "max_len": MAX_LEN}, OUT / "s2s_model.pt")

    # export pooled vectors + ragged token states for the full index
    model.eval()
    pooled_all, states_flat, lengths = [], [], []
    with torch.no_grad():
        for i in range(0, len(index_df), BATCH):
            chunk = index_df["surface"].iloc[i : i + BATCH].tolist()
            enc = [pad_to(tok.encode(t)[:MAX_LEN], MAX_LEN) for t in chunk]
            x = torch.tensor(enc)
            states, pad_mask = model.encode(x)
            pooled_all.append(model.pool(states, pad_mask).numpy())
            for b in range(x.size(0)):
                live = (~pad_mask[b]).sum().item()
                lengths.append(live)
                if live:
                    states_flat.append(states[b, :live].numpy())
    pooled = np.concatenate(pooled_all).astype(np.float32)
    np.save(OUT / "s2s_pooled.npy", pooled)
    np.savez_compressed(
        OUT / "s2s_token_states.npz",
        states=np.concatenate(states_flat).astype(np.float32) if states_flat else np.zeros((0, 128), np.float32),
        lengths=np.array(lengths, dtype=np.int32),
    )
    (OUT / "s2s_train_log.json").write_text(json.dumps(log, indent=2))
    print(f"saved pooled {pooled.shape} | best val full acc {best:.4f}")


if __name__ == "__main__":
    main()
