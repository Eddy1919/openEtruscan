#!/usr/bin/env python3
"""WP9d — mine word-level Etruscan↔English gloss pairs. Three sources:

1. ibm1        — IBM Model 1 EM word alignment (our implementation), run in
                 BOTH directions over the TRAIN sentence pairs; a pair is
                 kept only when the two directions agree on the argmax
                 (intersection heuristic), t(e|f) ≥ threshold, and the
                 Etruscan word occurs ≥ MIN_COUNT times. Corpus-derived,
                 no human label injected.
2. rosetta_train — the 39-pair TRAIN split of the frozen rosetta benchmark
                 (split exists exactly for this), using the English gloss.
3. lexicon     — a small curated table of uncontested glosses (Bonfante 2002
                 / Wallace 2008 commonplaces: mi, śuθi, turce, clan, puia,
                 major theonym equations).

Leak guard: any Etruscan word that appears in the rosetta TEST split is
excluded from EVERY source — including ibm1 — so the one semantic benchmark
can never be fed its own answers. (For ibm1 this is stricter than necessary;
strictness is cheaper than a footnote.)

Output: out/mined_pairs.csv  (surface, translation, provenance, score)
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from roles import tokenize

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(REPO / "eval/harness"))
from rosetta_eval_pairs import eval_pairs  # noqa: E402

EM_ITERS = 15
T_MIN = 0.30
MIN_COUNT = 3
ENG_TOKEN = re.compile(r"[a-z']+")

LEXICON = {
    "mi": "i", "mini": "me",
    "śuθi": "tomb", "suθi": "tomb", "θui": "here",
    "turce": "gave", "turuce": "gave",
    "muluvanice": "dedicated", "muluvanece": "dedicated",
    "zinace": "made",
    "clan": "son", "sec": "daughter", "puia": "wife",
    "lautni": "freedman",
    "menrva": "minerva", "hercle": "hercules", "uni": "juno",
    "fufluns": "bacchus", "nethuns": "neptune", "aritimi": "artemis",
}


def eng_tokens(s: str) -> list[str]:
    return ENG_TOKEN.findall(s.lower())


def ibm1(src_sents: list[list[str]], tgt_sents: list[list[str]]) -> dict:
    """t[(tgt_word, src_word)] = p(tgt|src), src side includes NULL."""
    t: dict[tuple[str, str], float] = defaultdict(lambda: 1e-6)
    cooc: dict[str, set[str]] = defaultdict(set)
    for s, g in zip(src_sents, tgt_sents):
        for f in s + ["<null>"]:
            for e in g:
                cooc[f].add(e)
    for f, es in cooc.items():
        for e in es:
            t[(e, f)] = 1.0 / len(es)
    for _ in range(EM_ITERS):
        count = defaultdict(float)
        total = defaultdict(float)
        for s, g in zip(src_sents, tgt_sents):
            fs = s + ["<null>"]
            for e in g:
                z = sum(t[(e, f)] for f in fs)
                if z <= 0:
                    continue
                for f in fs:
                    c = t[(e, f)] / z
                    count[(e, f)] += c
                    total[f] += c
        for (e, f), c in count.items():
            t[(e, f)] = c / total[f] if total[f] > 0 else 0.0
    return t


def main() -> None:
    test_etr = {p.etr for p in eval_pairs(min_confidence="low", split="test")}
    print(f"rosetta TEST etruscan words excluded everywhere: {len(test_etr)}")

    pairs = pd.read_csv(OUT / "contrastive_pairs.csv", dtype=str)
    train = pairs[pairs["part"] == "train"]
    etr_sents = [tokenize(s) for s in train["surface"]]
    eng_sents = [eng_tokens(g) for g in train["translation"]]

    etr_count = Counter(w for s in etr_sents for w in s)

    t_fwd = ibm1(etr_sents, eng_sents)          # p(eng | etr)
    t_rev = ibm1(eng_sents, etr_sents)          # p(etr | eng)

    best_eng: dict[str, tuple[str, float]] = {}
    for (e, f), p in t_fwd.items():
        if f == "<null>":
            continue
        if f not in best_eng or p > best_eng[f][1]:
            best_eng[f] = (e, p)
    best_etr: dict[str, tuple[str, float]] = {}
    for (f, e), p in t_rev.items():
        if e == "<null>":
            continue
        if e not in best_etr or p > best_etr[e][1]:
            best_etr[e] = (f, p)

    rows = []
    for f, (e, p) in sorted(best_eng.items()):
        if (p >= T_MIN and etr_count[f] >= MIN_COUNT and f not in test_etr
                and best_etr.get(e, ("", 0))[0] == f):
            rows.append({"surface": f, "translation": e,
                         "provenance": "ibm1", "score": round(p, 4)})
    n_ibm = len(rows)

    for p_ in eval_pairs(min_confidence="low", split="train"):
        if p_.etr not in test_etr:
            rows.append({"surface": p_.etr, "translation": p_.gloss.lower(),
                         "provenance": "rosetta_train", "score": 1.0})
    for f, e in LEXICON.items():
        if f not in test_etr:
            rows.append({"surface": f, "translation": e,
                         "provenance": "lexicon", "score": 1.0})

    mined = pd.DataFrame(rows).drop_duplicates(subset=["surface", "translation"])
    mined.to_csv(OUT / "mined_pairs.csv", index=False)
    print(f"ibm1 {n_ibm} | total mined {len(mined)}")
    print(mined["provenance"].value_counts().to_dict())
    print(mined[mined.provenance == "ibm1"].sort_values("score", ascending=False)
          .head(15).to_string(index=False))


if __name__ == "__main__":
    main()
