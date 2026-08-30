#!/usr/bin/env python3
"""WP9 — contrastive alignment on the 1,800 Etruscan↔English translation
pairs (the Larth-derived `translation` column): the only semantic signal in
the published data, untouched by WP0–WP8.

Dual encoder, both sides ours:
  * Etruscan side: the WP2 seq2seq encoder (warm start from s2s_model.pt),
    fine-tuned, + linear projection
  * English side: a fresh encoder-only transformer over a from-scratch BPE
    vocab trained on the gloss text, + linear projection
  * symmetric InfoNCE, learnable temperature, in-batch negatives

False-negative control: pairs whose gloss OR Etruscan text repeats another
row in the batch are masked out of the negative set (many glosses repeat —
"mi" rows all translate the same).

Split: by dup_group_id, 80/10/10 (train/val/test), pairs deduplicated on
(surface, translation). Early stop on val Eng→Etr MRR.

Output: out/contrastive_model.pt        (both towers + projections)
        out/eng_tokenizer.json
        out/aligned_etr_vectors.npy     ([n_index, 128], full index, L2-ready)
        out/contrastive_train_log.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

from model_scratch import EncoderBlock, Seq2Seq
from tokenizer_scratch import PAD, BPETokenizer
from train_denoiser import pad_to

HERE = Path(__file__).parent
OUT = HERE / "out"

MAX_LEN = 48
ENG_MAX_LEN = 64
D = 128
EPOCHS = 100
BATCH = 64
LR_ETR = 5e-5   # warm-started tower: gentle
LR_NEW = 3e-4   # english tower + projections: fresh
SEED = 20260830
PATIENCE = 10


class EngEncoder(nn.Module):
    def __init__(self, vocab_size: int, d_model: int = D, n_layers: int = 2,
                 max_len: int = ENG_MAX_LEN):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, d_model, padding_idx=PAD)
        nn.init.normal_(self.emb.weight, std=0.02)
        nn.init.zeros_(self.emb.weight[PAD])
        self.pos = nn.Parameter(torch.zeros(1, max_len, d_model))
        nn.init.normal_(self.pos, std=0.02)
        self.blocks = nn.ModuleList(
            [EncoderBlock(d_model, 4, 256, 0.15) for _ in range(n_layers)])
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x):
        pad_mask = x == PAD
        h = self.emb(x) + self.pos[:, : x.size(1)]
        for blk in self.blocks:
            h = blk(h, pad_mask)
        h = self.norm(h)
        m = (~pad_mask).unsqueeze(-1).float()
        return (h * m).sum(1) / m.sum(1).clamp(min=1)


class DualEncoder(nn.Module):
    def __init__(self, etr: Seq2Seq, eng: EngEncoder):
        super().__init__()
        self.etr = etr
        self.eng = eng
        self.proj_etr = nn.Linear(D, D, bias=False)
        self.proj_eng = nn.Linear(D, D, bias=False)
        self.log_temp = nn.Parameter(torch.tensor(np.log(1 / 0.07), dtype=torch.float32))

    def encode_etr(self, x):
        states, pad_mask = self.etr.encode(x)
        return F.normalize(self.proj_etr(self.etr.pool(states, pad_mask)), dim=-1)

    def encode_eng(self, x):
        return F.normalize(self.proj_eng(self.eng(x)), dim=-1)


def info_nce(ze, zg, dup_mask, temp):
    """ze: etr [B,D], zg: eng [B,D]; dup_mask [B,B] True = not a valid negative."""
    logits = ze @ zg.T * temp
    eye = torch.eye(len(ze), dtype=torch.bool, device=logits.device)
    logits = logits.masked_fill(dup_mask & ~eye, -1e9)
    labels = torch.arange(len(ze), device=logits.device)
    return (F.cross_entropy(logits, labels) + F.cross_entropy(logits.T, labels)) / 2


@torch.no_grad()
def mrr_eng_to_etr(model, etr_x, eng_x) -> float:
    model.eval()
    ze = torch.cat([model.encode_etr(etr_x[i : i + BATCH])
                    for i in range(0, len(etr_x), BATCH)])
    zg = torch.cat([model.encode_eng(eng_x[i : i + BATCH])
                    for i in range(0, len(eng_x), BATCH)])
    sims = zg @ ze.T
    ranks = (sims >= sims.diag().unsqueeze(1)).sum(1)
    return float((1.0 / ranks.float()).mean())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze_etr", action="store_true",
                    help="freeze the Etruscan tower; train projections + English tower only")
    ap.add_argument("--augment_csv", type=Path, default=None,
                    help="extra (surface, translation) TRAIN pairs from gloss augmentation")
    ap.add_argument("--mined_csv", type=Path, default=None,
                    help="extra word-level (etr, gloss) TRAIN pairs from mining")
    ap.add_argument("--tag", default="v1", help="suffix for all output files")
    args = ap.parse_args()
    sfx = "" if args.tag == "v1" else f"_{args.tag}"

    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)

    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str, "translation": str})
    index_df["surface"] = index_df["surface"].fillna("")
    pairs = index_df[(index_df["translation"].fillna("").str.strip() != "")
                     & (index_df["surface"] != "")].copy()
    pairs["translation"] = pairs["translation"].str.strip().str.lower()
    pairs = pairs.drop_duplicates(subset=["surface", "translation"])
    print(f"pairs: {len(pairs)}")

    groups = np.array(sorted(pairs["dup_group_id"].unique()), dtype=object)
    rng.shuffle(groups)
    n = len(groups)
    val_g = set(groups[: n // 10])
    test_g = set(groups[n // 10 : 2 * (n // 10)])
    part = np.where(pairs["dup_group_id"].isin(val_g), "val",
                    np.where(pairs["dup_group_id"].isin(test_g), "test", "train"))
    pairs["part"] = part
    print(pairs["part"].value_counts().to_dict())
    pairs[["id", "surface", "translation", "dup_group_id", "part"]].to_csv(
        OUT / "contrastive_pairs.csv", index=False)

    # extra TRAIN-only pairs (augmentation / mining); never touch val/test
    extra_frames = []
    for path in (args.augment_csv, args.mined_csv):
        if path is not None:
            ex = pd.read_csv(path, dtype=str)
            ex["translation"] = ex["translation"].str.strip().str.lower()
            ex = ex[(ex["surface"].fillna("") != "") & (ex["translation"].fillna("") != "")]
            extra_frames.append(ex[["surface", "translation"]])
            print(f"extra pairs from {path.name}: {len(ex)}")

    etr_tok = BPETokenizer.load(OUT / "bpe_tokenizer.json")
    eng_texts = pairs[pairs["part"] == "train"]["translation"].tolist()
    for ex in extra_frames:
        eng_texts += ex["translation"].tolist()
    eng_tok = BPETokenizer.train(eng_texts, vocab_size=2000)
    eng_tok.save(OUT / f"eng_tokenizer{sfx}.json")

    def etr_batchify(texts):
        return torch.tensor([pad_to(etr_tok.encode(t)[:MAX_LEN], MAX_LEN) for t in texts])

    def eng_batchify(texts):
        return torch.tensor([pad_to(eng_tok.encode(t)[:ENG_MAX_LEN], ENG_MAX_LEN)
                             for t in texts])

    ckpt = torch.load(OUT / "s2s_model.pt", map_location="cpu", weights_only=False)
    etr = Seq2Seq(vocab_size=ckpt["vocab_size"], max_len=ckpt["max_len"])
    etr.load_state_dict(ckpt["state_dict"])
    model = DualEncoder(etr, EngEncoder(len(eng_tok)))
    print(f"params: {sum(p.numel() for p in model.parameters()):,}")

    new_params = (list(model.eng.parameters()) + list(model.proj_etr.parameters())
                  + list(model.proj_eng.parameters()) + [model.log_temp])
    if args.freeze_etr:
        for p in model.etr.parameters():
            p.requires_grad_(False)
        opt = torch.optim.AdamW(new_params, lr=LR_NEW, weight_decay=0.01)
        n_train = sum(p.numel() for p in new_params)
        print(f"etr tower FROZEN; trainable params {n_train:,}")
    else:
        opt = torch.optim.AdamW([
            {"params": model.etr.parameters(), "lr": LR_ETR},
            {"params": new_params, "lr": LR_NEW},
        ], weight_decay=0.01)

    tr = pairs[pairs["part"] == "train"].reset_index(drop=True)
    if extra_frames:
        tr = pd.concat([tr[["surface", "translation"]]] + extra_frames,
                       ignore_index=True).drop_duplicates()
        tr = tr.reset_index(drop=True)
        print(f"train pairs incl. extras: {len(tr)}")
    va = pairs[pairs["part"] == "val"].reset_index(drop=True)
    va_etr = etr_batchify(va["surface"].tolist())
    va_eng = eng_batchify(va["translation"].tolist())

    log = {"epochs": []}
    best, best_state, bad = 0.0, None, 0
    for epoch in range(EPOCHS):
        model.train()
        order = rng.permutation(len(tr))
        losses = []
        for i in range(0, len(order), BATCH):
            b = tr.iloc[order[i : i + BATCH]]
            if len(b) < 4:
                continue
            xe = etr_batchify(b["surface"].tolist())
            xg = eng_batchify(b["translation"].tolist())
            surf, glos = b["surface"].tolist(), b["translation"].tolist()
            B = len(b)
            dup = torch.zeros(B, B, dtype=torch.bool)
            for r in range(B):
                for c in range(B):
                    if r != c and (surf[r] == surf[c] or glos[r] == glos[c]):
                        dup[r, c] = True
            ze = model.encode_etr(xe)
            zg = model.encode_eng(xg)
            loss = info_nce(ze, zg, dup, model.log_temp.exp().clamp(max=100.0))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            losses.append(float(loss.detach()))
        mrr = mrr_eng_to_etr(model, va_etr, va_eng)
        log["epochs"].append({"epoch": epoch, "loss": float(np.mean(losses)),
                              "val_mrr": mrr})
        print(f"epoch {epoch:03d} loss {np.mean(losses):.4f} val MRR {mrr:.4f} "
              f"temp {float(model.log_temp.exp()):.2f}")
        if mrr > best:
            best, bad = mrr, 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= PATIENCE:
                print(f"early stop at {epoch} (best val MRR {best:.4f})")
                break

    model.load_state_dict(best_state)
    log["best_val_mrr"] = best
    torch.save({"state_dict": model.state_dict(),
                "etr_vocab_size": ckpt["vocab_size"], "etr_max_len": ckpt["max_len"],
                "eng_vocab_size": len(eng_tok)}, OUT / f"contrastive_model{sfx}.pt")

    # aligned Etruscan vectors for the whole index
    model.eval()
    vecs = []
    with torch.no_grad():
        for i in range(0, len(index_df), BATCH):
            vecs.append(model.encode_etr(
                etr_batchify(index_df["surface"].iloc[i : i + BATCH].tolist())).numpy())
    np.save(OUT / f"aligned_etr_vectors{sfx}.npy", np.concatenate(vecs).astype(np.float32))
    (OUT / f"contrastive_train_log{sfx}.json").write_text(json.dumps(log, indent=2))
    print(f"saved aligned vectors | best val MRR {best:.4f}")


if __name__ == "__main__":
    main()
