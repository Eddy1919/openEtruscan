#!/usr/bin/env python3
"""Step 4 — VSA role-filler vectors (the "frontier spike" block).

Re-runs the WP1 HRR/MAP encoder (research/experiments/vsa_role_filler/) over
the *cleaned* index: bipolar atoms, D=4096, seed 7, MAP binding. Two vectors
per inscription:
  * S (structure): sum of role⊗position — captures the epigraphic formula
  * I (content)  : sum of role⊗filler   — captures who/what fills the slots

Zero training. Bipolar hypervectors are the dense equivalent of a spike-count
code, which is why this block stands in for the neuromorphic reading of the
plan.

Output: out/vsa_S.npy, out/vsa_I.npy (float32, [n_index, 4096])
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
SEED = 7


def main() -> None:
    rng = np.random.default_rng(SEED)
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    index_df["surface"] = index_df["surface"].fillna("")

    parsed = [parse_roles(tokenize(s)) for s in index_df["surface"]]

    def atom():
        return rng.choice([-1.0, 1.0], size=D)

    role_vec = {r: atom() for r in ROLES}
    pos = [atom() for _ in range(12)]
    fillers = sorted({f for roles in parsed for _, f in roles})
    fill_vec = {f: atom() for f in fillers}

    S = np.zeros((len(parsed), D), dtype=np.float32)
    I = np.zeros((len(parsed), D), dtype=np.float32)
    for n, roles in enumerate(parsed):
        for k, (role, fill) in enumerate(roles):
            I[n] += (role_vec[role] * fill_vec[fill]).astype(np.float32)
            S[n] += (role_vec[role] * pos[min(k, 11)]).astype(np.float32)

    np.save(OUT / "vsa_S.npy", S)
    np.save(OUT / "vsa_I.npy", I)
    n_roles = sum(len(r) for r in parsed)
    stats = {"rows": len(parsed), "distinct_fillers": len(fillers), "total_roles": n_roles,
             "rows_with_roles": int(sum(bool(r) for r in parsed))}
    (OUT / "vsa_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
