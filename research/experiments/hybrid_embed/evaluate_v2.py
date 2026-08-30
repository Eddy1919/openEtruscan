#!/usr/bin/env python3
"""WP3/WP6/WP8 — end-to-end evaluation of the from-scratch stack.

Systems on eval B (offline NDCG@10, 74 frozen queries):
  * bm25                — sparse leg (ours)
  * dense_fused_v2      — pooled [s2s | node2vec | VSA-S], per-block L2
  * late_interaction    — MaxSim over per-token encoder states (WP3; nothing
                          pooled away)
  * rrf_all             — RRF(bm25, dense, late-interaction): the WP8 router;
                          every ranked id is a corpus row, answers resolve to
                          lossless stores by construction

Eval A (structural protocol) reruns with the s2s pooled block and fusion v2.
Eval C (rosetta n=22) reruns with the s2s encoder.

The hyperbolic block has its own gate (hyperbolic_results.json) and does not
join search fusion: its geometry is distance-from-clan-point, defined only
for genealogical queries.

Output: out/results_v2.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from evaluate import (BM25, OUT, REPO, K, l2, ndcg_at_k, rrf,
                      eval_structural, vsa_codebook, vsa_encode_S)
from model_scratch import Seq2Seq
from roles import parse_roles, tokenize
from tokenizer_scratch import BPETokenizer
from train_denoiser import pad_to

MAX_LEN = 48


class S2SEncoder:
    def __init__(self):
        self.tok = BPETokenizer.load(OUT / "bpe_tokenizer.json")
        ckpt = torch.load(OUT / "s2s_model.pt", map_location="cpu", weights_only=False)
        self.model = Seq2Seq(vocab_size=ckpt["vocab_size"], max_len=ckpt["max_len"])
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.eval()

    @torch.no_grad()
    def encode(self, texts: list[str]):
        """-> (pooled [n,d], token_states list of [t_i,d])"""
        x = torch.tensor([pad_to(self.tok.encode(t)[:MAX_LEN], MAX_LEN) for t in texts])
        states, pad_mask = self.model.encode(x)
        pooled = self.model.pool(states, pad_mask).numpy().astype(np.float32)
        toks = []
        for b in range(x.size(0)):
            live = int((~pad_mask[b]).sum())
            toks.append(states[b, :max(live, 0)].numpy().astype(np.float32))
        return pooled, toks


def load_token_states():
    z = np.load(OUT / "s2s_token_states.npz")
    states, lengths = z["states"], z["lengths"]
    out, off = [], 0
    for n in lengths:
        seg = states[off : off + n]
        norm = np.linalg.norm(seg, axis=1, keepdims=True)
        out.append(seg / np.maximum(norm, 1e-9))
        off += n
    return out


def maxsim(q_states: np.ndarray, doc_states: list[np.ndarray]) -> np.ndarray:
    qn = q_states / np.maximum(np.linalg.norm(q_states, axis=1, keepdims=True), 1e-9)
    scores = np.zeros(len(doc_states), dtype=np.float32)
    for i, d in enumerate(doc_states):
        if len(d) and len(qn):
            scores[i] = float((qn @ d.T).max(axis=1).mean())
    return scores


def main() -> None:
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    index_df["surface"] = index_df["surface"].fillna("")
    ids = index_df["id"].tolist()
    id_set = set(ids)

    s2s_pooled = np.load(OUT / "s2s_pooled.npy")
    graph = np.load(OUT / "graph_vectors.npy")
    vsa_S = np.load(OUT / "vsa_S.npy")
    fused_v2 = np.concatenate([l2(s2s_pooled), l2(graph), l2(vsa_S)], axis=1)

    print("=== A. structural protocol (v2 blocks) ===")
    structural = eval_structural(index_df, {"s2s_pooled": s2s_pooled,
                                            "fused_v2": fused_v2})
    print(json.dumps(structural, indent=2))

    enc = S2SEncoder()
    doc_states = load_token_states()
    role_vec, pos, _ = vsa_codebook(index_df["surface"].tolist())

    ent_rows: dict[str, list[int]] = {}
    for i, s in enumerate(index_df["surface"]):
        for r, f in parse_roles(tokenize(s)):
            ent_rows.setdefault(f"{r}:{f}", []).append(i)
    graph_entity_vec = {e: graph[rows].mean(axis=0)
                        for e, rows in ent_rows.items() if len(rows) >= 2}
    g_dim = graph.shape[1]

    def query_vec(q: str) -> np.ndarray:
        pooled, _ = enc.encode([q])
        cv = l2(pooled)[0]
        gvecs = [graph_entity_vec[f"{r}:{f}"] for r, f in parse_roles(tokenize(q))
                 if f"{r}:{f}" in graph_entity_vec]
        gv = np.mean(gvecs, axis=0) if gvecs else np.zeros(g_dim, dtype=np.float32)
        gv = gv / max(float(np.linalg.norm(gv)), 1e-9)
        sv = vsa_encode_S(q, role_vec, pos)
        sv = sv / max(float(np.linalg.norm(sv)), 1e-9)
        return np.concatenate([cv, gv.astype(np.float32), sv.astype(np.float32)])

    docs = [tokenize(s) for s in index_df["surface"]]
    bm25 = BM25(docs)
    queries = [json.loads(line) for line in
               (REPO / "eval/harness/search_eval_queries.jsonl").read_text().splitlines()]

    per_cat: dict[str, dict[str, list[float]]] = {}
    skipped = 0
    for q in queries:
        relevant = {r for r in q["relevant_ids"] if r in id_set}
        if not relevant:
            skipped += 1
            continue
        cat = q["category"]
        bm_rank = np.argsort(-bm25.scores(tokenize(q["query"])))
        dense_rank = np.argsort(-(fused_v2 @ query_vec(q["query"])))
        _, q_toks = enc.encode([q["query"]])
        li_rank = np.argsort(-maxsim(q_toks[0], doc_states))
        rrf_rank = np.argsort(-rrf([bm_rank[:100], dense_rank[:100], li_rank[:100]],
                                   len(ids)))
        systems = {"bm25": bm_rank, "dense_fused_v2": dense_rank,
                   "late_interaction": li_rank, "rrf_all": rrf_rank}
        for name, rank in systems.items():
            ranked_ids = [ids[i] for i in rank[:K]]
            per_cat.setdefault(name, {}).setdefault(cat, []).append(
                ndcg_at_k(ranked_ids, relevant))

    search: dict = {"skipped_queries_no_relevant_in_index": skipped}
    for name, cats in per_cat.items():
        cat_means = {c: float(np.mean(v)) for c, v in sorted(cats.items())}
        search[name] = {"per_category": cat_means,
                        "macro_mean": float(np.mean(list(cat_means.values())))}
    print("=== B. offline search eval v2 (NDCG@10) ===")
    print(json.dumps(search, indent=2))

    # --- C. rosetta with s2s encoder
    import sys
    sys.path.insert(0, str(REPO / "eval/harness"))
    from rosetta_eval_pairs import eval_pairs
    test = eval_pairs(split="test")
    allp = eval_pairs(min_confidence="low", split=None)
    latin_vocab = sorted({p.lat for p in allp})
    lat_pooled, _ = enc.encode(latin_vocab)
    lat_n = l2(lat_pooled)
    hits = 0
    for p in test:
        ev, _ = enc.encode([p.etr])
        top = [latin_vocab[i] for i in np.argsort(-(lat_n @ l2(ev)[0]))[:K]]
        hits += int(p.lat in top)
    rosetta = {"n": len(test), "candidates": len(latin_vocab),
               "p_at_10": hits / len(test), "chance_p_at_10": K / len(latin_vocab)}
    print("=== C. rosetta (s2s) ===")
    print(json.dumps(rosetta, indent=2))

    (OUT / "results_v2.json").write_text(json.dumps(
        {"structural_v2": structural, "search_ndcg10_v2": search,
         "rosetta_s2s": rosetta}, indent=2))
    print("saved out/results_v2.json")


if __name__ == "__main__":
    main()
