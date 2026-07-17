"""Leakage ablation: re-run RAG but STRIP any parallel that locally spells out the
gold answer (context-window match), isolating generalization from formula-copying."""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
import rag_restore as R


def norm(s):
    return re.sub(r"[^\wθχφσśπ𐌀-𐌿]", "", (s or "").lower())


def answer_window(row):
    """last2(left) + gold + first2(right), normalized — the local copy signal."""
    m = row["masked"]
    w = row["width"]
    g = R.GOLD[row["key"]]
    start = m.index("?")
    left = norm(m[:start])
    right = norm(m[start + w :])
    return norm(left[-2:] + g + right[:2])


def retrieve_noleak(row, k=8):
    win = answer_window(row)
    pars = R.retrieve(row, k=40)  # over-retrieve, then filter answer-revealing ones
    kept = [p for p in pars if win not in norm(p)]
    return kept[:k], len(pars) - len(kept[: len(pars)])  # kept, n_filtered(approx)


def run(mid):
    def one(row):
        pars, _ = retrieve_noleak(row, k=8)
        parallels = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(pars)) or "(none found)"
        up = R.USER_TEMPLATE.format(
            width=row["width"],
            masked_text=row["masked"],
            parallels=parallels,
            id_json=json.dumps(row["id"]),
        )
        p = R.parse(R.call(mid, up, 0.0), row["width"], row["masked"])
        return dict(
            key=row["key"],
            id=row["id"],
            model=f"{mid}+ragNOLEAK",
            masked=row["masked"],
            width=row["width"],
            width_bucket=row["width_bucket"],
            gold_lacuna=R.GOLD[row["key"]],
            **p,
        )

    with ThreadPoolExecutor(max_workers=10) as ex:
        return list(ex.map(one, R.POOL))


if __name__ == "__main__":
    mid = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.5-flash"
    rows = run(mid)
    (R.SP / f"ragnoleak_{mid}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    )
    # how many tasks had an answer-revealing parallel in their top-8 originally?
    revealed = sum(
        1
        for row in R.POOL
        if answer_window(row) in "\n".join(norm(p) for p in R.retrieve(row, k=8))
    )
    print(
        f"wrote {len(rows)} | tasks whose top-8 contained an answer-revealing parallel: {revealed}/{len(R.POOL)}"
    )
