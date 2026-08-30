#!/usr/bin/env python3
"""Step 5 — fuse the three blocks and evaluate against the frozen harnesses.

Fusion v1: concat [charLM | node2vec | VSA-S], each block L2-normalized, so
cosine over the fused vector weights the three signals equally.

Three evaluations:
  A. Structural-retrieval protocol (replicates vsa_role_filler NS1.3 on the
     cleaned index): mean role-structure Jaccard and mean lexical Jaccard of
     the top-5 neighbours, 120 seeded queries. Systems: char-3gram, VSA-S,
     charLM, graph, fused.
  B. Offline search eval: NDCG@10 against eval/harness/search_eval_queries.jsonl,
     scored on the cleaned index (relevant ids missing from the index are
     dropped from the gain set; queries with no surviving relevant id are
     skipped). Systems: BM25 (sparse), dense (fused), RRF(BM25+dense), and
     optionally cross-encoder rerank of the RRF top-30.
     NOT comparable to the prod-API numbers in run_search_eval.py — the prod
     endpoint has findspot/pleiades/date metadata this index does not carry.
  C. Rosetta diagnostic (n=22 test pairs): charLM word vectors, Etruscan word
     vs a Latin candidate vocabulary, precision@10. Expected ~0 — a
     from-scratch monolingual model has no cross-lingual signal; reported so
     nobody has to rediscover that.

Output: out/results.json + console report.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from roles import ROLES, parse_roles, tokenize

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "eval/harness"))

from openetruscan.ml.neural import CharMLM, CharVocab  # noqa: E402
from rosetta_eval_pairs import eval_pairs  # noqa: E402

K = 10
RRF_K = 60
SEED = 7


def l2(block: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(block, axis=1, keepdims=True)
    return block / np.maximum(n, 1e-9)


# ---------------------------------------------------------------- charLM query encoder
class CharLMEncoder:
    def __init__(self):
        ckpt = torch.load(OUT / "charlm_model.pt", map_location="cpu", weights_only=False)
        self.vocab = CharVocab(
            char_to_idx=ckpt["char_to_idx"],
            idx_to_char={v: k for k, v in ckpt["char_to_idx"].items()},
        )
        self.max_len = ckpt["max_len"]
        self.model = CharMLM(vocab_size=len(self.vocab), d_model=ckpt["d_model"], num_layers=3)
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.eval()

    @torch.no_grad()
    def encode(self, texts: list[str]) -> np.ndarray:
        x = torch.tensor(
            [self.vocab.encode(t.lower(), max_len=self.max_len) for t in texts],
            dtype=torch.long,
        )
        padding_mask = x == 0
        emb = self.model.pos_enc(self.model.embedding(x))
        out = self.model.transformer(emb, src_key_padding_mask=padding_mask)
        m = (~padding_mask).unsqueeze(-1).float()
        pooled = (out * m).sum(1) / m.sum(1).clamp(min=1)
        return pooled.numpy().astype(np.float32)


# ---------------------------------------------------------------- VSA codebook (deterministic rebuild)
def vsa_codebook(index_surfaces: list[str], D: int = 4096):
    rng = np.random.default_rng(SEED)
    parsed = [parse_roles(tokenize(s)) for s in index_surfaces]

    def atom():
        return rng.choice([-1.0, 1.0], size=D)

    role_vec = {r: atom() for r in ROLES}
    pos = [atom() for _ in range(12)]
    fillers = sorted({f for roles in parsed for _, f in roles})
    fill_vec = {f: atom() for f in fillers}
    return role_vec, pos, fill_vec


def vsa_encode_S(text: str, role_vec, pos, D: int = 4096) -> np.ndarray:
    v = np.zeros(D, dtype=np.float32)
    for k, (role, _) in enumerate(parse_roles(tokenize(text))):
        v += (role_vec[role] * pos[min(k, 11)]).astype(np.float32)
    return v


# ---------------------------------------------------------------- BM25
class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.doc_len = np.array([len(d) for d in docs], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) or 1.0
        self.df: Counter = Counter()
        self.tf: list[Counter] = []
        for d in docs:
            c = Counter(d)
            self.tf.append(c)
            self.df.update(c.keys())
        self.N = len(docs)

    def scores(self, query: list[str]) -> np.ndarray:
        s = np.zeros(self.N, dtype=np.float32)
        for term in query:
            df = self.df.get(term)
            if not df:
                continue
            idf = math.log(1 + (self.N - df + 0.5) / (df + 0.5))
            for i, c in enumerate(self.tf):
                f = c.get(term)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                    s[i] += idf * f * (self.k1 + 1) / denom
        return s


# ---------------------------------------------------------------- metrics
def ndcg_at_k(ranked_ids: list[str], relevant: set[str], k: int = K) -> float:
    gains = [1.0 if rid in relevant else 0.0 for rid in ranked_ids[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def rrf(rankings: list[np.ndarray], n: int) -> np.ndarray:
    score = np.zeros(n)
    for ranked in rankings:
        for pos_i, doc in enumerate(ranked):
            score[doc] += 1.0 / (RRF_K + pos_i + 1)
    return score


def jacc(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def ngrams(s: str, n: int = 3) -> Counter:
    s = re.sub(r"[^\wÀ-Ͽ\U00010300-\U0001032f]", "", s.lower())
    return Counter(s[i : i + n] for i in range(len(s) - n + 1)) if len(s) >= n else Counter([s])


def cos_counter(a: Counter, b: Counter) -> float:
    dot = sum(v * b[k] for k, v in a.items() if k in b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


# ---------------------------------------------------------------- eval A: structural protocol
def eval_structural(index_df, blocks) -> dict:
    parsed = [parse_roles(tokenize(s)) for s in index_df["surface"]]
    pool_idx = [i for i, r in enumerate(parsed) if len(r) >= 3]
    roleseq = {i: tuple(r for r, _ in parsed[i]) for i in pool_idx}
    toks = {i: set(tokenize(index_df["surface"].iloc[i])) for i in pool_idx}
    ngs = {i: ngrams(index_df["surface"].iloc[i]) for i in pool_idx}

    rng = np.random.default_rng(SEED)
    queries = rng.choice(len(pool_idx), size=min(120, len(pool_idx)), replace=False)

    systems = {name: l2(mat[pool_idx]) for name, mat in blocks.items()}
    results = {}
    for name, mat in systems.items():
        st, lex = [], []
        for qi in queries:
            sims = mat @ mat[qi]
            sims[qi] = -9
            top = np.argsort(-sims)[:5]
            q_global = pool_idx[qi]
            for j in top:
                jg = pool_idx[j]
                st.append(jacc(set(roleseq[q_global]), set(roleseq[jg])))
                lex.append(jacc(toks[q_global], toks[jg]))
        results[name] = {"structure_sim": float(np.mean(st)), "lexical_overlap": float(np.mean(lex))}

    st, lex = [], []
    for qi in queries:
        qg = pool_idx[qi]
        sims = np.array(
            [cos_counter(ngs[qg], ngs[pool_idx[j]]) if j != qi else -9 for j in range(len(pool_idx))]
        )
        for j in np.argsort(-sims)[:5]:
            jg = pool_idx[j]
            st.append(jacc(set(roleseq[qg]), set(roleseq[jg])))
            lex.append(jacc(toks[qg], toks[jg]))
    results["char3gram"] = {"structure_sim": float(np.mean(st)), "lexical_overlap": float(np.mean(lex))}
    results["_n_queries"] = int(len(queries))
    results["_pool"] = len(pool_idx)
    return results


# ---------------------------------------------------------------- eval B: search NDCG
def eval_search(index_df, fused, charlm_enc, role_vec, pos, graph_entity_vec) -> dict:
    ids = index_df["id"].tolist()
    id_set = set(ids)
    docs = [tokenize(s) for s in index_df["surface"]]
    bm25 = BM25(docs)

    queries = [json.loads(line) for line in
               (REPO / "eval/harness/search_eval_queries.jsonl").read_text().splitlines()]

    dim_char = charlm_enc.encode(["mi"]).shape[1]
    fused_n = fused  # already per-block normalized + concatenated

    def query_vec(q: str) -> np.ndarray:
        cv = l2(charlm_enc.encode([q]))[0]
        gtoks = parse_roles(tokenize(q))
        gvecs = [graph_entity_vec[f"{r}:{f}"] for r, f in gtoks if f"{r}:{f}" in graph_entity_vec]
        gv = np.mean(gvecs, axis=0) if gvecs else np.zeros(next(iter(graph_entity_vec.values())).shape[0], dtype=np.float32)
        gv = gv / max(np.linalg.norm(gv), 1e-9)
        sv = vsa_encode_S(q, role_vec, pos)
        sv = sv / max(np.linalg.norm(sv), 1e-9)
        return np.concatenate([cv, gv.astype(np.float32), sv])

    try:
        from sentence_transformers import CrossEncoder
        reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    except Exception as exc:  # model download blocked / package issue
        print(f"reranker unavailable, skipping: {exc}")
        reranker = None

    per_cat: dict[str, dict[str, list[float]]] = {}
    skipped = 0
    for q in queries:
        relevant = {r for r in q["relevant_ids"] if r in id_set}
        if not relevant:
            skipped += 1
            continue
        cat = q["category"]
        qtoks = tokenize(q["query"])
        bm = bm25.scores(qtoks)
        bm_rank = np.argsort(-bm)
        qv = query_vec(q["query"])
        dense = fused_n @ qv
        dense_rank = np.argsort(-dense)
        fused_score = rrf([bm_rank[:100], dense_rank[:100]], len(ids))
        rrf_rank = np.argsort(-fused_score)

        systems = {
            "bm25": bm_rank,
            "dense_fused": dense_rank,
            "rrf_bm25+dense": rrf_rank,
        }
        if reranker is not None:
            cand = rrf_rank[:30]
            pairs = [(q["query"], index_df["surface"].iloc[i]) for i in cand]
            ce = reranker.predict(pairs, show_progress_bar=False)
            systems["rrf+minilm_rerank"] = cand[np.argsort(-ce)]

        for name, rank in systems.items():
            ranked_ids = [ids[i] for i in rank[:K]]
            per_cat.setdefault(name, {}).setdefault(cat, []).append(
                ndcg_at_k(ranked_ids, relevant)
            )

    report: dict = {"skipped_queries_no_relevant_in_index": skipped}
    for name, cats in per_cat.items():
        cat_means = {c: float(np.mean(v)) for c, v in sorted(cats.items())}
        report[name] = {
            "per_category": cat_means,
            "n_per_category": {c: len(v) for c, v in sorted(cats.items())},
            "macro_mean": float(np.mean(list(cat_means.values()))),
        }
    return report


# ---------------------------------------------------------------- eval C: rosetta diagnostic
def eval_rosetta(charlm_enc) -> dict:
    test = eval_pairs(split="test")
    all_pairs = eval_pairs(min_confidence="low", split=None)
    latin_vocab = sorted({p.lat for p in all_pairs})
    lat_vecs = l2(charlm_enc.encode(latin_vocab))
    hits = 0
    for p in test:
        ev = l2(charlm_enc.encode([p.etr]))[0]
        sims = lat_vecs @ ev
        top = [latin_vocab[i] for i in np.argsort(-sims)[:K]]
        hits += int(p.lat in top)
    return {"n": len(test), "candidates": len(latin_vocab),
            "p_at_10": hits / len(test) if test else 0.0}


def main() -> None:
    index_df = pd.read_csv(OUT / "index.csv", dtype={"surface": str})
    index_df["surface"] = index_df["surface"].fillna("")

    charlm = np.load(OUT / "charlm_vectors.npy")
    graph = np.load(OUT / "graph_vectors.npy")
    vsa_S = np.load(OUT / "vsa_S.npy")
    fused = np.concatenate([l2(charlm), l2(graph), l2(vsa_S)], axis=1)

    blocks = {"charLM": charlm, "graph_node2vec": graph, "vsa_S": vsa_S, "fused": fused}
    print("=== A. structural retrieval protocol ===")
    structural = eval_structural(index_df, blocks)
    print(json.dumps(structural, indent=2))

    charlm_enc = CharLMEncoder()
    role_vec, pos, _fill = vsa_codebook(index_df["surface"].tolist())

    # entity node vectors for query-side graph encoding: rebuild the node list
    # exactly as graph_embed.py did and read back the trained matrix is not
    # persisted per-entity, so approximate entity vectors by the mean of the
    # inscriptions that contain the entity (equivalent up to one smoothing hop).
    graph_entity_vec: dict[str, np.ndarray] = {}
    ent_rows: dict[str, list[int]] = {}
    for i, s in enumerate(index_df["surface"]):
        for r, f in parse_roles(tokenize(s)):
            ent_rows.setdefault(f"{r}:{f}", []).append(i)
    for e, rows in ent_rows.items():
        if len(rows) >= 2:
            graph_entity_vec[e] = graph[rows].mean(axis=0)

    print("=== B. offline search eval (NDCG@10) ===")
    search = eval_search(index_df, fused, charlm_enc, role_vec, pos, graph_entity_vec)
    print(json.dumps(search, indent=2))

    print("=== C. rosetta diagnostic (expected ~0) ===")
    rosetta = eval_rosetta(charlm_enc)
    print(json.dumps(rosetta, indent=2))

    results = {"structural": structural, "search_ndcg10": search, "rosetta_diag": rosetta}
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print("saved out/results.json")


if __name__ == "__main__":
    main()
