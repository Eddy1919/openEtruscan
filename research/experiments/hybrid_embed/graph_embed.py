#!/usr/bin/env python3
"""Step 3 — relational graph vectors via node2vec (DeepWalk special case,
p=q=1) over the inscription–entity graph.

Graph construction (no external metadata needed — the published CSV carries
no findspot/pleiades columns):
  * one node per inscription id
  * one node per (ROLE, filler) entity extracted by the shared heuristic
    role parser (roles.py) — praenomina, gentilicia, patronymics, theonyms,
    verbs, status words
  * undirected edge inscription ↔ entity for every extracted role

Random walks over this bipartite graph put inscriptions that share clans,
name formulas, or dedication verbs — or that are linked through multi-hop
chains (same gentilicium via different praenomina) — near each other.

Trained with a skip-gram + negative-sampling objective in plain torch
(gensim is not a project dependency).

Output: out/graph_vectors.npy  (float32, [n_index, DIM]; zero row = no entities)
        out/graph_stats.json
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from roles import parse_roles, tokenize

HERE = Path(__file__).parent
OUT = HERE / "out"

DIM = 128
WALKS_PER_NODE = 10
WALK_LEN = 40
WINDOW = 5
NEG = 5
EPOCHS = 3
BATCH = 4096
LR = 1e-2
SEED = 20260830
MIN_ENTITY_DEGREE = 2  # singleton entities create no cross-inscription signal


def build_graph(index_df: pd.DataFrame):
    adj: dict[str, list[str]] = defaultdict(list)
    entity_degree: dict[str, int] = defaultdict(int)
    insc_entities: dict[str, list[str]] = {}
    for _, row in index_df.iterrows():
        ents = {f"{role}:{fill}" for role, fill in parse_roles(tokenize(row["surface"]))}
        insc_entities[row["id"]] = sorted(ents)
        for e in ents:
            entity_degree[e] += 1
    kept = {e for e, d in entity_degree.items() if d >= MIN_ENTITY_DEGREE}
    for insc, ents in insc_entities.items():
        for e in ents:
            if e in kept:
                adj[insc].append(e)
                adj[e].append(insc)
    return adj, kept


def random_walks(adj, rng) -> list[list[str]]:
    nodes = sorted(adj)
    walks = []
    for _ in range(WALKS_PER_NODE):
        order = rng.permutation(len(nodes))
        for i in order:
            node = nodes[i]
            walk = [node]
            for _ in range(WALK_LEN - 1):
                nbrs = adj[walk[-1]]
                if not nbrs:
                    break
                walk.append(nbrs[rng.integers(len(nbrs))])
            walks.append(walk)
    return walks


def skipgram_pairs(walks, node_id, rng):
    src, dst = [], []
    for walk in walks:
        ids = [node_id[n] for n in walk]
        for i, center in enumerate(ids):
            lo = max(0, i - WINDOW)
            for j in range(lo, min(len(ids), i + WINDOW + 1)):
                if j != i:
                    src.append(center)
                    dst.append(ids[j])
    pairs = np.stack([np.array(src), np.array(dst)], axis=1)
    rng.shuffle(pairs)
    return pairs


def main() -> None:
    rng = np.random.default_rng(SEED)
    torch.manual_seed(SEED)
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    index_df["surface"] = index_df["surface"].fillna("")

    adj, kept = build_graph(index_df)
    nodes = sorted(adj)
    node_id = {n: i for i, n in enumerate(nodes)}
    n_insc_in_graph = sum(1 for n in nodes if not any(n.startswith(r + ":") for r in
                          ("EGO", "VERB", "OBJECT", "STATUS", "THEONYM",
                           "PRAENOMEN", "GENTILICIUM", "PATRONYMIC")))
    print(f"graph: {len(nodes)} nodes ({n_insc_in_graph} inscriptions, "
          f"{len(kept)} entities), building walks...")

    walks = random_walks(adj, rng)
    pairs = skipgram_pairs(walks, node_id, rng)
    print(f"walks: {len(walks)} | skip-gram pairs: {len(pairs):,}")

    # degree^0.75 negative-sampling distribution
    deg = np.zeros(len(nodes))
    for n, nbrs in adj.items():
        deg[node_id[n]] = len(nbrs)
    neg_p = deg**0.75
    neg_p /= neg_p.sum()

    emb_in = nn.Embedding(len(nodes), DIM)
    emb_out = nn.Embedding(len(nodes), DIM)
    nn.init.normal_(emb_in.weight, std=0.05)
    nn.init.zeros_(emb_out.weight)
    opt = torch.optim.Adam(list(emb_in.parameters()) + list(emb_out.parameters()), lr=LR)

    pairs_t = torch.from_numpy(pairs.astype(np.int64))
    for epoch in range(EPOCHS):
        losses = []
        perm = torch.randperm(len(pairs_t))
        for i in range(0, len(pairs_t), BATCH):
            b = pairs_t[perm[i : i + BATCH]]
            center, ctx = emb_in(b[:, 0]), emb_out(b[:, 1])
            neg_ids = torch.from_numpy(
                rng.choice(len(nodes), size=(len(b), NEG), p=neg_p).astype(np.int64)
            )
            neg = emb_out(neg_ids)
            pos_score = torch.nn.functional.logsigmoid((center * ctx).sum(-1))
            neg_score = torch.nn.functional.logsigmoid(
                -(neg * center.unsqueeze(1)).sum(-1)
            ).sum(-1)
            loss = -(pos_score + neg_score).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(float(loss))
        print(f"epoch {epoch} loss {np.mean(losses):.4f}")

    weights = emb_in.weight.detach().numpy().astype(np.float32)
    vectors = np.zeros((len(index_df), DIM), dtype=np.float32)
    hit = 0
    for i, insc in enumerate(index_df["id"]):
        j = node_id.get(insc)
        if j is not None:
            vectors[i] = weights[j]
            hit += 1
    np.save(OUT / "graph_vectors.npy", vectors)
    stats = {
        "nodes": len(nodes),
        "entities_kept": len(kept),
        "inscriptions_in_graph": hit,
        "inscriptions_total": len(index_df),
        "skipgram_pairs": int(len(pairs)),
    }
    (OUT / "graph_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
