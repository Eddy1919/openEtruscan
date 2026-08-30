#!/usr/bin/env python3
"""Cross-reference the published corpus against the known Latin–Etruscan
bilingual inscriptions.

Input:  bilinguals.jsonl — one record per known bilingual:
          {"ids": ["CIE 1288", "TLE 472", ...],   # any identifiers in use
           "findspot": "...",
           "etr_text": "...",                      # Etruscan half if known
           "lat_text": "...",                      # Latin half if known
           "fixes": "...",                         # what equation it anchors
           "source_url": "..."}
        research/data/openetruscan_clean_grouped.csv (fetch_data.py)

Matching, two passes:
  1. id match — corpus `id` equals any identifier (normalized: case, spacing)
  2. text match — token-overlap between the bilingual's Etruscan half and a
     corpus row (Jaccard over the shared tokenizer), reported above a
     threshold so near-duplicates and variant editions surface too

Output: crossref_report.csv (bilingual ids, match kind, corpus id, score)
        + console summary. The report is review material for adjudication,
        not gold by itself.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO / "research/experiments/hybrid_embed"))
from roles import tokenize  # noqa: E402  (shared Etruscan tokenizer)

TEXT_JACCARD_MIN = 0.5


def norm_id(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def main() -> None:
    bil_path = HERE / "bilinguals.jsonl"
    if not bil_path.exists():
        print("bilinguals.jsonl not found — seed it first (see docstring).")
        raise SystemExit(1)
    bilinguals = [json.loads(l) for l in bil_path.read_text().splitlines() if l.strip()]

    corpus = pd.read_csv(REPO / "research/data/openetruscan_clean_grouped.csv",
                         dtype=str).fillna("")
    corpus_ids = {norm_id(i): i for i in corpus["id"].fillna("")}
    corpus_toks = [(row["id"], set(tokenize(row.get("canonical_words_only") or
                                           row.get("canonical_transliterated") or "")))
                   for _, row in corpus.iterrows()]

    rows = []
    for b in bilinguals:
        matched = False
        for ident in b.get("ids", []):
            hit = corpus_ids.get(norm_id(ident))
            if hit:
                rows.append({"bilingual": "; ".join(b["ids"]), "match": "id",
                             "corpus_id": hit, "score": 1.0,
                             "fixes": b.get("fixes", "")})
                matched = True
        etr = b.get("etr_text") or ""
        btoks = set(tokenize(etr))
        if btoks:
            for cid, ctoks in corpus_toks:
                s = jaccard(btoks, ctoks)
                if s >= TEXT_JACCARD_MIN:
                    rows.append({"bilingual": "; ".join(b["ids"]), "match": "text",
                                 "corpus_id": cid, "score": round(s, 3),
                                 "fixes": b.get("fixes", "")})
                    matched = True
        if not matched:
            rows.append({"bilingual": "; ".join(b["ids"]), "match": "none",
                         "corpus_id": "", "score": 0.0, "fixes": b.get("fixes", "")})

    report = pd.DataFrame(rows).sort_values(["match", "score"], ascending=[True, False])
    report.to_csv(HERE / "crossref_report.csv", index=False)
    n_hit = (report["match"] != "none").sum()
    print(f"bilinguals: {len(bilinguals)} | rows with a corpus match: "
          f"{report[report.match != 'none']['bilingual'].nunique()} | "
          f"match rows: {n_hit}")
    print(report.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
