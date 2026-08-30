#!/usr/bin/env python3
"""WP4 — sparse block-code VSA vs dense bipolar VSA, unbind protocol.

Dense MAP binding superposes with crosstalk that grows with the number of
bound pairs — that is why GENTILICIUM unbind sat at 64.1%. Sparse block codes
(Frady/Kleyko style) fix it at the representation level:

  * D units split into K blocks of m units; an atom is one active unit per
    block (sparsity 1/m ≈ cortical activity levels)
  * binding  = per-block modular index addition (blockwise circular shift)
  * unbind   = per-block index subtraction — exact inverse
  * superposition = per-block count vectors; two summed role–filler pairs
    only collide when both blocks agree, so crosstalk decays like 1/m per
    block instead of 1/sqrt(D) overall

Both codes get the same memory budget: 4096 units.
Protocol: identical to vsa_role_filler round-trip — encode I = Σ role⊗filler,
unbind each role, cleanup against the filler codebook, accuracy per role.

Output: out/vsa_sparse_results.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from roles import ROLES, parse_roles, tokenize

HERE = Path(__file__).parent
OUT = HERE / "out"
D = 4096
K = 64          # blocks
M = D // K      # units per block
SEED = 7


def main() -> None:
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    parsed = [parse_roles(tokenize(s)) for s in index_df["surface"].fillna("")]
    fillers = sorted({f for roles in parsed for _, f in roles})
    n_fill = len(fillers)
    fill_id = {f: i for i, f in enumerate(fillers)}

    results = {}

    # ---------------- dense bipolar baseline (same protocol, cleaned index)
    rng = np.random.default_rng(SEED)
    role_vec = {r: rng.choice([-1.0, 1.0], size=D) for r in ROLES}
    fill_mat = rng.choice([-1.0, 1.0], size=(n_fill, D))

    dense = {}
    for target in ["GENTILICIUM", "PATRONYMIC", "STATUS"]:
        ok = tot = 0
        for roles in parsed:
            gt = [f for r, f in roles if r == target]
            if not gt:
                continue
            I = np.zeros(D)
            for r, f in roles:
                I += role_vec[r] * fill_mat[fill_id[f]]
            rec = int(np.argmax(fill_mat @ (I * role_vec[target])))
            tot += 1
            ok += int(fillers[rec] == gt[-1])
        dense[target] = {"acc": ok / tot, "n": tot}
    results["dense_bipolar_D4096"] = dense

    # ---------------- sparse block code
    rng = np.random.default_rng(SEED)
    role_idx = {r: rng.integers(0, M, size=K) for r in ROLES}       # [K]
    fill_idx = rng.integers(0, M, size=(n_fill, K))                  # [n_fill, K]

    sparse = {}
    for target in ["GENTILICIUM", "PATRONYMIC", "STATUS"]:
        ok = tot = 0
        r_t = role_idx[target]
        for roles in parsed:
            gt = [f for r, f in roles if r == target]
            if not gt:
                continue
            # superposed memory: per-block count vectors [K, M]
            mem = np.zeros((K, M))
            for r, f in roles:
                bound = (role_idx[r] + fill_idx[fill_id[f]]) % M     # [K]
                mem[np.arange(K), bound] += 1.0
            # unbind: shift memory back by the role's indices, then cleanup
            unbound = mem[np.arange(K)[:, None], (fill_idx + r_t[None, :]).T % M]
            # unbound[k, j] = mem[k, (fill_idx[j,k] + r_t[k]) % M] -> score per filler
            scores = unbound.sum(axis=0)
            rec = int(np.argmax(scores))
            tot += 1
            ok += int(fillers[rec] == gt[-1])
        sparse[target] = {"acc": ok / tot, "n": tot}
    results[f"sparse_block_K{K}xM{M}"] = sparse

    results["_config"] = {"D": D, "K": K, "M": M, "n_fillers": n_fill,
                          "sparsity": 1 / M}
    (OUT / "vsa_sparse_results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
