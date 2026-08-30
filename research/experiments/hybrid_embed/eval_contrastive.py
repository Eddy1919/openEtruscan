#!/usr/bin/env python3
"""WP9 eval — what did contrastive alignment buy, measured three ways.

1. Held-out translation retrieval (test split, groups never seen):
   Eng→Etr and Etr→Eng over (a) the test pool only and (b) the full 5,569-row
   index as distractors. R@1 / R@10 / MRR. Chance R@10 reported alongside.
2. Rosetta glosses — the first *semantic* rosetta run: embed the Etruscan
   word with the aligned Etruscan tower, the English gloss with the English
   tower, p@10 over the gloss candidate pool (n=22 frozen test pairs).
   Compare: charLM surface p@10 0.455 (artifact), chance 10/58.
3. Search eval B, lexical + place categories, with a cross-lingual leg:
   English query → aligned Etruscan vectors; RRF with the WP6 router legs.

Output: out/contrastive_results.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from evaluate import BM25, OUT, REPO, K, l2, ndcg_at_k, rrf
from evaluate_v2 import S2SEncoder, load_token_states, maxsim
from model_scratch import Seq2Seq
from roles import parse_roles, tokenize
from tokenizer_scratch import BPETokenizer
from train_contrastive import DualEncoder, EngEncoder
from train_denoiser import pad_to

MAX_LEN = 48
ENG_MAX_LEN = 64
BATCH = 64


class Towers:
    def __init__(self, sfx: str = ""):
        ckpt = torch.load(OUT / f"contrastive_model{sfx}.pt", map_location="cpu",
                          weights_only=False)
        etr = Seq2Seq(vocab_size=ckpt["etr_vocab_size"], max_len=ckpt["etr_max_len"])
        self.model = DualEncoder(etr, EngEncoder(ckpt["eng_vocab_size"]))
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.eval()
        self.etr_tok = BPETokenizer.load(OUT / "bpe_tokenizer.json")
        self.eng_tok = BPETokenizer.load(OUT / f"eng_tokenizer{sfx}.json")

    @torch.no_grad()
    def etr(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), BATCH):
            x = torch.tensor([pad_to(self.etr_tok.encode(t)[:MAX_LEN], MAX_LEN)
                              for t in texts[i : i + BATCH]])
            out.append(self.model.encode_etr(x).numpy())
        return np.concatenate(out).astype(np.float32)

    @torch.no_grad()
    def eng(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), BATCH):
            x = torch.tensor([pad_to(self.eng_tok.encode(t)[:ENG_MAX_LEN], ENG_MAX_LEN)
                              for t in texts[i : i + BATCH]])
            out.append(self.model.encode_eng(x).numpy())
        return np.concatenate(out).astype(np.float32)


def retrieval_metrics(sims: np.ndarray, gold: np.ndarray) -> dict:
    """sims: [n_query, n_cand]; gold[i] = correct candidate index."""
    order = np.argsort(-sims, axis=1)
    ranks = np.array([int(np.where(order[i] == gold[i])[0][0]) + 1
                      for i in range(len(gold))])
    return {"r_at_1": float((ranks <= 1).mean()),
            "r_at_10": float((ranks <= 10).mean()),
            "mrr": float((1.0 / ranks).mean()),
            "median_rank": int(np.median(ranks)),
            "n": int(len(gold))}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--skip_search", action="store_true",
                    help="skip the search-router leg (proved harmful in v1)")
    args = ap.parse_args()
    sfx = "" if args.tag == "v1" else f"_{args.tag}"

    towers = Towers(sfx)
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    index_df["surface"] = index_df["surface"].fillna("")
    ids = index_df["id"].tolist()
    id_set = set(ids)
    aligned = np.load(OUT / f"aligned_etr_vectors{sfx}.npy")  # already normalized

    pairs = pd.read_csv(OUT / "contrastive_pairs.csv", dtype=str)
    test = pairs[pairs["part"] == "test"].reset_index(drop=True)
    print(f"test pairs: {len(test)}")

    ze = towers.etr(test["surface"].tolist())
    zg = towers.eng(test["translation"].tolist())
    gold = np.arange(len(test))

    results = {
        "test_pool_eng_to_etr": retrieval_metrics(zg @ ze.T, gold),
        "test_pool_etr_to_eng": retrieval_metrics(ze @ zg.T, gold),
        "chance_r_at_10_test_pool": 10 / len(test),
    }

    # full-index distractors: query = English translation, gold = its row
    id_to_pos = {r: i for i, r in enumerate(ids)}
    keep = test["id"].map(id_to_pos).notna()
    tq = test[keep]
    gold_full = tq["id"].map(id_to_pos).to_numpy(dtype=int)
    zg_full = towers.eng(tq["translation"].tolist())
    results["full_index_eng_to_etr"] = retrieval_metrics(zg_full @ aligned.T, gold_full)
    results["chance_r_at_10_full_index"] = 10 / len(ids)

    # --- rosetta glosses (semantic, both towers)
    sys.path.insert(0, str(REPO / "eval/harness"))
    from rosetta_eval_pairs import eval_pairs
    testp = eval_pairs(split="test")
    allp = eval_pairs(min_confidence="low", split=None)
    glosses = sorted({p.gloss.lower() for p in allp})
    zg_gloss = towers.eng(glosses)
    hits = 0
    for p in testp:
        ev = towers.etr([p.etr])[0]
        top = [glosses[i] for i in np.argsort(-(zg_gloss @ ev))[:K]]
        hits += int(p.gloss.lower() in top)
    results["rosetta_gloss"] = {"n": len(testp), "candidates": len(glosses),
                                "p_at_10": hits / len(testp),
                                "chance_p_at_10": K / len(glosses)}

    # --- search eval with cross-lingual leg in the router
    if args.skip_search:
        (OUT / f"contrastive_results{sfx}.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
        return
    s2s = S2SEncoder()
    doc_states = load_token_states()
    docs = [tokenize(s) for s in index_df["surface"]]
    bm25 = BM25(docs)
    queries = [json.loads(line) for line in
               (REPO / "eval/harness/search_eval_queries.jsonl").read_text().splitlines()]
    per_cat: dict[str, dict[str, list[float]]] = {}
    for q in queries:
        relevant = {r for r in q["relevant_ids"] if r in id_set}
        if not relevant:
            continue
        cat = q["category"]
        bm_rank = np.argsort(-bm25.scores(tokenize(q["query"])))
        _, q_toks = s2s.encode([q["query"]])
        li_rank = np.argsort(-maxsim(q_toks[0], doc_states))
        xl_rank = np.argsort(-(aligned @ towers.eng([q["query"]])[0]))
        systems = {
            "crosslingual_only": [xl_rank],
            "rrf_v2_legs": [bm_rank[:100], li_rank[:100]],
            "rrf_v2_plus_crosslingual": [bm_rank[:100], li_rank[:100], xl_rank[:100]],
        }
        for name, legs in systems.items():
            rank = legs[0] if len(legs) == 1 else np.argsort(-rrf(legs, len(ids)))
            ranked_ids = [ids[i] for i in rank[:K]]
            per_cat.setdefault(name, {}).setdefault(cat, []).append(
                ndcg_at_k(ranked_ids, relevant))
    search: dict = {}
    for name, cats in per_cat.items():
        cat_means = {c: float(np.mean(v)) for c, v in sorted(cats.items())}
        search[name] = {"per_category": cat_means,
                        "macro_mean": float(np.mean(list(cat_means.values())))}
    results["search_with_crosslingual"] = search

    (OUT / f"contrastive_results{sfx}.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
