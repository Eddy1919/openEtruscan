#!/usr/bin/env python3
"""Conformal prediction sets for single-character restoration.

Question: can a weak restorer still give an epigrapher something honest, a
set of letters that contains the missing one with a stated probability, and
how large is that set?

Labels are free: we mask a known letter in an unseen inscription and ask the
model for it. No human annotation is involved.

Model: the from-scratch character MLM of hybrid_embed (train_charlm.py,
~430K params, val masked accuracy 0.396). Calibration and test texts both
come from its held-out validation groups (dup_group_id level, never seen in
training), reconstructed with the trainer's own seed.

Methods, all split-conformal at miscoverage alpha:
  * top-k      fixed-size sets, k = smallest with calibration coverage >= 1-alpha
  * LAC        score 1 - p(true)                       (Sadinle et al. 2019)
  * APS        score = probability mass ranked at or above the true letter
               (non-randomised; Romano et al. 2020)
  * LAC-bucket class-conditional LAC with letters pooled into frequency
               buckets, so low-frequency letters get their own threshold (Mondrian CP)

Each repetition draws fresh mask positions and a fresh 50/50 group-level
calibration/test split; numbers are means and SDs over repetitions.

Usage (after hybrid_embed/prepare.py and train_charlm.py):
    python research/experiments/conformal_restoration/conformal.py
Output: research/experiments/conformal_restoration/results.json
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from openetruscan.ml.neural import CharMLM, CharVocab

HERE = Path(__file__).parent
HYB = HERE.parent / "hybrid_embed" / "out"

TRAIN_SEED = 20260830  # train_charlm.py SEED: reproduces its validation split
SEED = 20261124
REPS = 100
ALPHAS = (0.1, 0.2)
N_BUCKETS = 3
BUCKET_NAMES = ["low_mass", "mid_mass", "high_mass"]


def load_model() -> tuple[CharMLM, CharVocab, int]:
    ckpt = torch.load(HYB / "charlm_model.pt", map_location="cpu", weights_only=False)
    c2i = ckpt["char_to_idx"]
    vocab = CharVocab(char_to_idx=c2i, idx_to_char={v: k for k, v in c2i.items()})
    model = CharMLM(vocab_size=len(c2i), d_model=ckpt["d_model"], num_layers=3)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, vocab, ckpt["max_len"]


def validation_texts(vocab: CharVocab) -> pd.DataFrame:
    """The exact validation groups train_charlm.py held out."""
    df = pd.read_csv(HYB / "train.csv", dtype={"surface": str})
    df = df[df["surface"].fillna("").str.len() > 0].reset_index(drop=True)
    rebuilt = CharVocab.build(df["surface"].tolist())
    if rebuilt.char_to_idx != vocab.char_to_idx:
        raise SystemExit("train.csv does not match the checkpoint vocabulary; rerun prepare.py")
    # object array: same order as the trainer's shuffle (checked: the
    # reconstructed split reproduces its logged val accuracy, 0.39598)
    groups = np.array(df["dup_group_id"].unique(), dtype=object)
    rng = np.random.default_rng(TRAIN_SEED)
    rng.shuffle(groups)
    val_groups = set(groups[: len(groups) // 10])
    return df[df["dup_group_id"].isin(val_groups)].reset_index(drop=True)


def is_letter(ch: str) -> bool:
    return ch.isalpha() and not ch.isupper()


def word_position(text: str, i: int) -> str:
    start = i == 0 or not text[i - 1].isalpha()
    end = i == len(text) - 1 or not text[i + 1].isalpha()
    if start and end:
        return "single"
    return "initial" if start else "final" if end else "medial"


@torch.no_grad()
def letter_probs(
    model: CharMLM, vocab: CharVocab, texts: list[str], pos: list[int], max_len: int, letters
) -> np.ndarray:
    """P(letter | context with one [MASK]) restricted to the letter classes."""
    mask_id = vocab.char_to_idx[vocab.MASK_TOKEN]
    letter_ids = torch.tensor([vocab.char_to_idx[c] for c in letters])
    x = torch.tensor([vocab.encode(t, max_len=max_len) for t in texts])
    x[torch.arange(len(texts)), torch.tensor(pos)] = mask_id
    out = []
    for i in range(0, len(texts), 256):
        logits = model(x[i : i + 256])[torch.arange(min(256, len(texts) - i)), pos[i : i + 256]]
        out.append(torch.softmax(logits[:, letter_ids], dim=-1).numpy())
    return np.concatenate(out)


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    n = len(scores)
    level = math.ceil((n + 1) * (1 - alpha)) / n
    return float(np.quantile(scores, min(level, 1.0), method="higher"))


def aps_scores(probs: np.ndarray) -> np.ndarray:
    """Per-class APS score: mass of every class ranked at or above it."""
    order = np.argsort(-probs, axis=1)
    sorted_p = np.take_along_axis(probs, order, axis=1)
    cum = np.cumsum(sorted_p, axis=1)
    scores = np.empty_like(probs)
    np.put_along_axis(scores, order, cum, axis=1)
    return scores


def evaluate(sets: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    covered = sets[np.arange(len(y)), y]
    return covered, sets.sum(axis=1)


def one_rep(probs, y, groups, buckets, rng, alpha) -> dict:
    ug = np.unique(groups)
    cal_groups = set(rng.permutation(ug)[: len(ug) // 2])
    cal = np.array([g in cal_groups for g in groups])
    te = ~cal
    pc, yc, pt, yt = probs[cal], y[cal], probs[te], y[te]
    res = {}

    # top-k
    ranks_c = (pc > pc[np.arange(len(yc)), yc][:, None]).sum(1) + 1
    k = next(k for k in range(1, probs.shape[1] + 1) if (ranks_c <= k).mean() >= 1 - alpha)
    ranks_t = (pt > pt[np.arange(len(yt)), yt][:, None]).sum(1) + 1
    res["top_k"] = ((ranks_t <= k), np.full(len(yt), k), {"k": k})

    # LAC
    q = conformal_quantile(1 - pc[np.arange(len(yc)), yc], alpha)
    res["lac"] = (*evaluate(1 - pt <= q, yt), {})

    # APS
    ac, at = aps_scores(pc), aps_scores(pt)
    q = conformal_quantile(ac[np.arange(len(yc)), yc], alpha)
    res["aps"] = (*evaluate(at <= q, yt), {})

    # class-conditional LAC over frequency buckets
    qb = {}
    for b in np.unique(buckets):
        sel = buckets[yc] == b
        qb[b] = conformal_quantile(1 - pc[np.arange(len(yc)), yc][sel], alpha) if sel.any() else 1
    thresh = np.array([qb[buckets[c]] for c in range(probs.shape[1])])
    res["lac_bucket"] = (*evaluate(1 - pt <= thresh[None, :], yt), {})
    return res, te


def main() -> None:
    model, vocab, max_len = load_model()
    letters = sorted(c for c in vocab.char_to_idx if len(c) == 1 and is_letter(c))
    lidx = {c: i for i, c in enumerate(letters)}
    val = validation_texts(vocab)
    texts = val["surface"].tolist()
    groups = val["dup_group_id"].to_numpy()

    # buckets: thirds of total letter mass, lowest first. With this corpus
    # that is {everything else} / {l n s u} / {a e i}.
    freq = Counter(ch for t in texts for ch in t if ch in lidx)
    order = sorted(letters, key=lambda c: freq.get(c, 0))
    cum = np.cumsum([freq.get(c, 0) for c in order]) / max(sum(freq.values()), 1)
    bucket_of = {c: min(int(f * N_BUCKETS), N_BUCKETS - 1) for c, f in zip(order, cum, strict=True)}
    buckets = np.array([bucket_of[c] for c in letters])

    rng = np.random.default_rng(SEED)
    summary: dict = {
        "model": "hybrid_embed charLM (train_charlm.py)",
        "n_letters": len(letters),
        "n_val_texts": len(texts),
        "n_val_groups": int(len(np.unique(groups))),
        "reps": REPS,
        "bucket_letters": {
            name: [c for c in letters if bucket_of[c] == b] for b, name in enumerate(BUCKET_NAMES)
        },
        "alphas": {},
    }
    acc1 = []
    agg: dict = {a: {} for a in ALPHAS}
    for _ in range(REPS):
        pos, keep = [], []
        for i, t in enumerate(texts):
            cand = [j for j, ch in enumerate(t[:max_len]) if ch in lidx]
            if cand:
                pos.append(int(rng.choice(cand)))
                keep.append(i)
        tx = [texts[i] for i in keep]
        gr = groups[keep]
        y = np.array([lidx[tx[k][p]] for k, p in enumerate(pos)])
        wpos = np.array([word_position(tx[k], p) for k, p in enumerate(pos)])
        probs = letter_probs(model, vocab, tx, pos, max_len, letters)
        acc1.append(float((probs.argmax(1) == y).mean()))
        for a in ALPHAS:
            res, te = one_rep(probs, y, gr, buckets, rng, a)
            for name, (covered, size, extra) in res.items():
                d = agg[a].setdefault(
                    name,
                    {"cov": [], "size": [], "single": [], "k": [], "by_bucket": {}, "by_pos": {}},
                )
                d["cov"].append(covered.mean())
                d["size"].append(size.mean())
                d["single"].append((size == 1).mean())
                if "k" in extra:
                    d["k"].append(extra["k"])
                for b in range(N_BUCKETS):
                    sel = buckets[y[te]] == b
                    if sel.any():
                        d["by_bucket"].setdefault(b, []).append(covered[sel].mean())
                for p in ("initial", "medial", "final"):
                    sel = wpos[te] == p
                    if sel.any():
                        d["by_pos"].setdefault(p, []).append(covered[sel].mean())

    summary["top1_acc"] = {"mean": float(np.mean(acc1)), "sd": float(np.std(acc1))}
    names = BUCKET_NAMES
    for a in ALPHAS:
        block = {}
        for name, d in agg[a].items():
            block[name] = {
                "coverage": {"mean": float(np.mean(d["cov"])), "sd": float(np.std(d["cov"]))},
                "mean_set_size": {
                    "mean": float(np.mean(d["size"])),
                    "sd": float(np.std(d["size"])),
                },
                "singleton_rate": float(np.mean(d["single"])),
                "coverage_by_bucket": {
                    names[b]: float(np.mean(v)) for b, v in d["by_bucket"].items()
                },
                "coverage_by_word_position": {p: float(np.mean(v)) for p, v in d["by_pos"].items()},
            }
            if d["k"]:
                block[name]["k_mode"] = int(Counter(d["k"]).most_common(1)[0][0])
        summary["alphas"][str(a)] = block

    (HERE / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(
        f"{len(letters)} letter classes | {len(texts)} val texts | "
        f"top-1 {summary['top1_acc']['mean']:.3f}"
    )
    for a, block in summary["alphas"].items():
        print(f"\nalpha={a} (target coverage {1 - float(a):.0%})")
        print(
            f"  {'method':11} {'cover':>6} {'size':>6} {'single':>7}    low   mid  high | init  med  final"
        )
        for name, r in block.items():
            bb, bp = r["coverage_by_bucket"], r["coverage_by_word_position"]
            print(
                f"  {name:11} {r['coverage']['mean']:6.3f} {r['mean_set_size']['mean']:6.2f} "
                f"{r['singleton_rate']:7.2f}   {bb.get('low_mass', float('nan')):.2f}  "
                f"{bb.get('mid_mass', float('nan')):.2f}  {bb.get('high_mass', float('nan')):.2f} | "
                f"{bp.get('initial', float('nan')):.2f} {bp.get('medial', float('nan')):.2f}  "
                f"{bp.get('final', float('nan')):.2f}"
            )


if __name__ == "__main__":
    main()
