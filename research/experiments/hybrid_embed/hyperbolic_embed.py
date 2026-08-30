#!/usr/bin/env python3
"""WP7 — Poincaré-ball embeddings for the clan→inscription hierarchy,
vs the Euclidean node2vec block.

Method: Nickel & Kiela 2017. Distance math is ours; torch supplies autograd
for the Euclidean gradient, which is then rescaled by the inverse metric
((1-||x||²)/2)² and the points retracted into the ball — Riemannian SGD.
(The first hand-derived-gradient version diverged to nan; autograd on the
same loss is the honest fix, torch stays a tensor library.)

Edges: (clan, inscription) membership pairs from the shared role parser
(clans = GENTILICIUM fillers in ≥2 inscriptions).

Comparison deliberately unfair to us: Poincaré d=16 vs node2vec d=128. Note
node2vec trained on exactly these membership edges, so its MAP is near
ceiling by construction — the gate is "get close at 8× fewer dims", and any
win would be decisive.

Gate: clan-membership MAP (macro over clans with ≥3 members).

Output: out/hyperbolic_vectors.npy, out/hyperbolic_results.json
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from roles import parse_roles, tokenize

HERE = Path(__file__).parent
OUT = HERE / "out"

DIM = 16
EPOCHS = 100
BURN_IN = 10
LR = 0.5
NEG = 10
BATCH = 512
SEED = 20260830
EPS = 1e-6
MAX_NORM = 1 - 1e-4


def poincare_dist(u: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    """u,v: [...,d] -> [...] geodesic distance in the Poincaré ball."""
    uu = (u * u).sum(-1).clamp(max=1 - 1e-6)
    vv = (v * v).sum(-1).clamp(max=1 - 1e-6)
    duv = ((u - v) ** 2).sum(-1)
    x = 1 + 2 * duv / ((1 - uu) * (1 - vv)).clamp(min=EPS)
    return torch.acosh(x.clamp(min=1 + EPS))


def project_(theta: torch.Tensor) -> None:
    with torch.no_grad():
        norms = theta.norm(dim=-1, keepdim=True)
        theta.mul_(torch.where(norms >= MAX_NORM, MAX_NORM / norms.clamp(min=EPS),
                               torch.ones_like(norms)))


def main() -> None:
    rng = np.random.default_rng(SEED)
    torch.manual_seed(SEED)
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    index_df["surface"] = index_df["surface"].fillna("")

    clan_members: dict[str, set[int]] = defaultdict(set)
    for i, s in enumerate(index_df["surface"]):
        for r, f in parse_roles(tokenize(s)):
            if r == "GENTILICIUM":
                clan_members[f].add(i)
    clan_members = {c: m for c, m in clan_members.items() if len(m) >= 2}

    clans = sorted(clan_members)
    n_clan = len(clans)
    n_nodes = n_clan + len(index_df)
    edges = np.array([(ci, n_clan + i)
                      for ci, c in enumerate(clans) for i in clan_members[c]])
    print(f"clans {n_clan} | nodes {n_nodes} | edges {len(edges)}")

    theta = torch.empty(n_nodes, DIM).uniform_(-1e-3, 1e-3).requires_grad_(True)
    edges_t = torch.from_numpy(edges)

    for epoch in range(EPOCHS):
        lr = LR / 10 if epoch < BURN_IN else LR
        order = torch.from_numpy(rng.permutation(len(edges)))
        total, nb = 0.0, 0
        for i in range(0, len(order), BATCH):
            b = edges_t[order[i : i + BATCH]]
            negs = torch.from_numpy(
                rng.integers(0, n_nodes, size=(len(b), NEG)))
            cand = torch.cat([b[:, 1:2], negs], dim=1)          # [B, 1+NEG]
            u = theta[b[:, 0]].unsqueeze(1)                     # [B,1,d]
            v = theta[cand]                                     # [B,1+NEG,d]
            d = poincare_dist(u, v)                             # [B,1+NEG]
            loss = torch.nn.functional.cross_entropy(
                -d, torch.zeros(len(b), dtype=torch.long))
            if theta.grad is not None:
                theta.grad.zero_()
            loss.backward()
            with torch.no_grad():
                g = theta.grad
                assert g is not None
                riem = ((1 - (theta * theta).sum(-1, keepdim=True)) ** 2) / 4
                theta.add_(-lr * riem * g)
            project_(theta)
            total += float(loss.detach()) * len(b)
            nb += len(b)
        if epoch % 10 == 0 or epoch == EPOCHS - 1:
            print(f"epoch {epoch:03d} loss {total / nb:.4f}")

    theta_np = theta.detach().numpy()

    # ---------------- evaluation: clan-membership MAP
    eval_clans = {c: m for c, m in clan_members.items() if len(m) >= 3}

    def average_precision(ranked, relevant: set[int]) -> float:
        hits, s = 0, 0.0
        for rank, idx in enumerate(ranked, start=1):
            if int(idx) in relevant:
                hits += 1
                s += hits / rank
        return s / max(len(relevant), 1)

    insc = torch.from_numpy(theta_np[n_clan:])
    ap_h = []
    for ci, c in enumerate(clans):
        if c not in eval_clans:
            continue
        d = poincare_dist(torch.from_numpy(theta_np[ci]).unsqueeze(0), insc)
        ap_h.append(average_precision(torch.argsort(d).numpy(), clan_members[c]))
    map_hyp = float(np.mean(ap_h))

    n2v = np.load(OUT / "graph_vectors.npy")
    n2v_n = n2v / np.maximum(np.linalg.norm(n2v, axis=1, keepdims=True), 1e-9)
    ap_e = []
    for c, members in eval_clans.items():
        cv = n2v_n[list(members)].mean(axis=0)
        ap_e.append(average_precision(np.argsort(-(n2v_n @ cv)), members))
    map_n2v = float(np.mean(ap_e))

    np.save(OUT / "hyperbolic_vectors.npy", theta_np[n_clan:].astype(np.float32))
    results = {"clans_eval": len(eval_clans), "dim_hyperbolic": DIM,
               "dim_node2vec": int(n2v.shape[1]),
               "map_hyperbolic": map_hyp, "map_node2vec": map_n2v,
               "note": "node2vec trained on these same membership edges; its MAP is near ceiling by construction"}
    (OUT / "hyperbolic_results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
