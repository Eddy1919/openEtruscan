#!/usr/bin/env python3
"""Step 2 — train a from-scratch character MLM on the cleaned Etruscan corpus
and export mean-pooled inscription vectors.

Reuses ``openetruscan.ml.neural.CharMLM`` (~430K params at d=128/3 layers).
Validation split is on ``dup_group_id`` (10% of groups) so masked-accuracy is
measured on unseen texts, never on a duplicate of a training text. The final
vectors are produced for every row in index.csv (the retrieval index may
contain duplicates; that is correct for retrieval).

Output: out/charlm_vectors.npy  (float32, [n_index, d_model])
        out/charlm_ids.json
        out/charlm_model.pt
        out/charlm_train_log.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from openetruscan.ml.neural import CharMLM, CharVocab  # noqa: E402

OUT = HERE / "out"
MAX_LEN = 128
D_MODEL = 128
EPOCHS = 60
BATCH = 64
LR = 3e-4
MASK_P = 0.15
SEED = 20260830
PATIENCE = 6


def device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def mask_batch(x: torch.Tensor, vocab: CharVocab, g: torch.Generator):
    """BERT-style masking on non-pad positions. Returns (input, labels)."""
    mask_id = vocab.char_to_idx[vocab.MASK_TOKEN]
    labels = x.clone()
    nonpad = x != 0
    prob = torch.rand(x.shape, generator=g) < MASK_P
    selected = prob & nonpad
    labels[~selected] = -100
    inp = x.clone()
    roll = torch.rand(x.shape, generator=g)
    inp[selected & (roll < 0.8)] = mask_id
    random_ids = torch.randint(3, len(vocab), x.shape, generator=g)
    inp[selected & (roll >= 0.8) & (roll < 0.9)] = random_ids[
        selected & (roll >= 0.8) & (roll < 0.9)
    ]
    return inp, labels


@torch.no_grad()
def masked_accuracy(model, xs, vocab, g, dev) -> float:
    model.eval()
    correct = total = 0
    for i in range(0, len(xs), BATCH):
        x = xs[i : i + BATCH]
        inp, labels = mask_batch(x, vocab, g)
        logits = model(inp.to(dev)).cpu()
        sel = labels != -100
        if sel.any():
            pred = logits.argmax(-1)
            correct += int((pred[sel] == labels[sel]).sum())
            total += int(sel.sum())
    return correct / max(total, 1)


def main() -> None:
    torch.manual_seed(SEED)
    dev = device()
    train_df = pd.read_csv(OUT / "train.csv", dtype={"surface": str})
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    train_df = train_df[train_df["surface"].fillna("").str.len() > 0].reset_index(drop=True)
    index_df["surface"] = index_df["surface"].fillna("")

    texts = train_df["surface"].tolist()
    vocab = CharVocab.build(texts)
    print(f"vocab: {len(vocab)} chars | train texts: {len(texts)} | device: {dev}")

    groups = train_df["dup_group_id"].unique()
    rng = np.random.default_rng(SEED)
    rng.shuffle(groups)
    val_groups = set(groups[: len(groups) // 10])
    is_val = train_df["dup_group_id"].isin(val_groups).to_numpy()

    encoded = torch.tensor(
        [vocab.encode(t, max_len=MAX_LEN) for t in texts], dtype=torch.long
    )
    xs_train = encoded[~is_val]
    xs_val = encoded[is_val]
    print(f"split: {len(xs_train)} train / {len(xs_val)} val (group-level)")

    model = CharMLM(vocab_size=len(vocab), d_model=D_MODEL, num_layers=3).to(dev)
    n_params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    g = torch.Generator().manual_seed(SEED)
    g_val = torch.Generator().manual_seed(SEED + 1)

    log = {"n_params": n_params, "epochs": []}
    best_acc, best_state, bad = 0.0, None, 0
    for epoch in range(EPOCHS):
        model.train()
        perm = torch.randperm(len(xs_train), generator=g)
        losses = []
        for i in range(0, len(xs_train), BATCH):
            x = xs_train[perm[i : i + BATCH]]
            inp, labels = mask_batch(x, vocab, g)
            logits = model(inp.to(dev))
            loss = F.cross_entropy(
                logits.view(-1, len(vocab)), labels.view(-1).to(dev), ignore_index=-100
            )
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(float(loss))
        g_val.manual_seed(SEED + 1)  # same masks every eval
        acc = masked_accuracy(model, xs_val, vocab, g_val, dev)
        log["epochs"].append({"epoch": epoch, "loss": float(np.mean(losses)), "val_masked_acc": acc})
        print(f"epoch {epoch:02d} loss {np.mean(losses):.4f} val_masked_acc {acc:.4f}")
        if acc > best_acc:
            best_acc, bad = acc, 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= PATIENCE:
                print(f"early stop at epoch {epoch} (best {best_acc:.4f})")
                break

    model.load_state_dict(best_state)
    log["best_val_masked_acc"] = best_acc

    # mean-pooled encoder vectors for the full retrieval index
    model.eval()
    idx_encoded = torch.tensor(
        [vocab.encode(t, max_len=MAX_LEN) for t in index_df["surface"].tolist()],
        dtype=torch.long,
    )
    vecs = []
    with torch.no_grad():
        for i in range(0, len(idx_encoded), BATCH):
            x = idx_encoded[i : i + BATCH].to(dev)
            padding_mask = x == 0
            emb = model.pos_enc(model.embedding(x))
            out = model.transformer(emb, src_key_padding_mask=padding_mask)
            m = (~padding_mask).unsqueeze(-1).float()
            pooled = (out * m).sum(1) / m.sum(1).clamp(min=1)
            vecs.append(pooled.cpu().numpy())
    vectors = np.concatenate(vecs).astype(np.float32)

    np.save(OUT / "charlm_vectors.npy", vectors)
    (OUT / "charlm_ids.json").write_text(json.dumps(index_df["id"].tolist()))
    torch.save(
        {"state_dict": model.state_dict(), "char_to_idx": vocab.char_to_idx,
         "d_model": D_MODEL, "max_len": MAX_LEN},
        OUT / "charlm_model.pt",
    )
    (OUT / "charlm_train_log.json").write_text(json.dumps(log, indent=2))
    print(f"saved {vectors.shape} vectors | best val masked acc {best_acc:.4f}")


if __name__ == "__main__":
    main()
