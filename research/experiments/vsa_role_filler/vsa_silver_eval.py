"""
NS0.1(silver) + NS1.3 re-score — non-circular where it counts.

Silver definition of a "structural parallel": two HIGH-CONFIDENCE parses (anchored
by a known function word / praenomen, not the greedy fallback) with the SAME role
sequence. We then split each query's silver-positives into:
  - lexical positives    (share >=1 word)   -> lexical methods CAN reach these
  - structural-only pos  (share 0 words)     -> only structure can reach these

The decisive, non-circular numbers are the BASELINES on structural-only positives:
if char-3-gram / token-overlap can't retrieve same-template/zero-word pairs, that
proves lexical retrieval cannot do structural parallel-finding. VSA's own score is
"by construction" (its vector encodes the role sequence); the residual question —
is 'same parsed template' == 'real philological parallel'? — is the human gate.
"""

import json
import re
import unicodedata
import numpy as np
from collections import defaultdict

rng = np.random.default_rng(11)
D, H = 4096, 2048
corpus = json.load(open("corpus.json"))

PRAENOMINA = set(
    "larθ laris arnθ aule avle vel velθur θefarie marce larce marces "
    "sethre seθre aθ θana θania ramθa larθi larθia velia fasti hasti "
    "θanχvil culni aules velus arnt lart".split()
)
STATUS = set(
    "lautni lautniθa lautn clan sec seχ śeχ puia etera papals nefts cliniiaras cliniar".split()
)
THEONYM = set(
    "tin tinia uni menrva turan fufluns aritimi hercle herecele nethuns śuri catha selvans veive vetis culsu θesan".split()
)
VERB = set("turce turuce muluvanice muluvanece zinace mulu alice cerine tece".split())
TOMBWORD = set("śuθi suθi θui".split())
EGO = set("mi mini".split())
ANCHORS = PRAENOMINA | STATUS | THEONYM | VERB | TOMBWORD | EGO
SEP = re.compile(r"[:·•|/\\\[\]\(\)<>\{\}·•、,\.\s]+")


def norm(s):
    return unicodedata.normalize("NFC", s or "").strip().lower()


def tokenize(c):
    return [t for t in SEP.split(norm(c)) if t and not re.fullmatch(r"[-–—\d]+", t)]


def parse_roles(toks):
    roles = []
    used = [False] * len(toks)
    for i, t in enumerate(toks):
        if t in EGO:
            roles.append(("EGO", t))
            used[i] = True
        elif t in VERB:
            roles.append(("VERB", t))
            used[i] = True
        elif t in TOMBWORD:
            roles.append(("OBJECT", t))
            used[i] = True
        elif t in STATUS:
            roles.append(("STATUS", t))
            used[i] = True
        elif t in THEONYM:
            roles.append(("THEONYM", t))
            used[i] = True
    seen = False
    for i, t in enumerate(toks):
        if used[i]:
            continue
        if t in PRAENOMINA and not seen:
            roles.append(("PRAENOMEN", t))
            seen = True
        elif re.search(r"(al|ial|s|sa|isa|us|es)$", t) and seen:
            roles.append(("PATRONYMIC", t))
        elif not seen:
            roles.append(("PRAENOMEN", t))
            seen = True
        else:
            roles.append(("GENTILICIUM", t))
    return roles


# parse + keep HIGH-CONFIDENCE (anchored) multi-role inscriptions
data = []
for r in corpus:
    toks = tokenize(r["canonical"])
    roles = parse_roles(toks)
    anchored = any(t in ANCHORS for t in toks)
    if anchored and len(roles) >= 3:
        data.append(
            {
                "id": r["id"],
                "canon": r["canonical"],
                "toks": toks,
                "roleseq": tuple(rr for rr, _ in roles),
                "wordset": set(toks),
            }
        )
n = len(data)
print(f"corpus 5932 -> anchored, >=3 roles (high-confidence): {n}")

# silver templates
by_tmpl = defaultdict(list)
for i, d in enumerate(data):
    by_tmpl[d["roleseq"]].append(i)
multi_templates = {k: v for k, v in by_tmpl.items() if len(v) >= 2}
print(f"distinct templates: {len(by_tmpl)} | templates with >=2 members: {len(multi_templates)}")
print(
    "top templates:",
    [("·".join(k), len(v)) for k, v in sorted(by_tmpl.items(), key=lambda x: -len(x[1]))[:6]],
)


# ---- feature matrices (all dense -> uniform fast cosine) ----
def atom():
    return rng.choice([-1.0, 1.0], size=D)


ROLES = ["EGO", "VERB", "OBJECT", "STATUS", "THEONYM", "PRAENOMEN", "GENTILICIUM", "PATRONYMIC"]
rv = {r: atom() for r in ROLES}
POS = [atom() for _ in range(12)]


def hashvec(items, dim):
    v = np.zeros(dim)
    for it in items:
        h = hash(it)
        v[h % dim] += 1.0 if (h // dim) % 2 else -1.0
    return v


def cngrams(s):
    s = re.sub(r"[^\w\U00010300-\U0001032f]", "", norm(s))
    s = f"^{s}$"
    return [s[i : i + 3] for i in range(len(s) - 2)] if len(s) >= 3 else [s]


VSA = np.zeros((n, D))
CH = np.zeros((n, H))
TOK = np.zeros((n, H))
for i, d in enumerate(data):
    S = np.zeros(D)
    for k, role in enumerate(d["roleseq"]):
        S += rv[role] * POS[min(k, 11)]
    VSA[i] = S
    CH[i] = hashvec(cngrams(d["canon"]), H)
    TOK[i] = hashvec(d["toks"], H)


def l2(M):
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)


VSA, CH, TOK = l2(VSA), l2(CH), l2(TOK)
RAND = l2(rng.standard_normal((n, H)))
methods = {"VSA structure": VSA, "char-3gram": CH, "token-overlap": TOK, "random": RAND}


# ---- evaluation ----
def recall_at(Mat, qi, positives, k=10):
    s = Mat @ Mat[qi]
    s[qi] = -9
    top = set(np.argsort(-s)[:k].tolist())
    if not positives:
        return None
    return len(top & positives) / min(k, len(positives))


# queries: members of multi-member templates
queries = [i for v in multi_templates.values() for i in v]
rng.shuffle(queries)
queries = queries[:600]
res = {m: {"all": [], "structonly": []} for m in methods}
n_structq = 0
for qi in queries:
    tmpl = data[qi]["roleseq"]
    qwords = data[qi]["wordset"]
    pos = set(by_tmpl[tmpl]) - {qi}
    structonly = {j for j in pos if not (qwords & data[j]["wordset"])}
    if structonly:
        n_structq += 1
    for m, Mat in methods.items():
        r_all = recall_at(Mat, qi, pos)
        if r_all is not None:
            res[m]["all"].append(r_all)
        if structonly:
            res[m]["structonly"].append(recall_at(Mat, qi, structonly))

print(f"\nqueries: {len(queries)} | with >=1 structural-only (zero-word) sibling: {n_structq}")
print(f"\n{'method':16} {'recall@10 (all same-tmpl)':>26} {'recall@10 (ZERO-WORD only)':>28}")
for m in methods:
    a = np.mean(res[m]["all"])
    s = np.mean(res[m]["structonly"])
    print(f"{m:16} {a:>26.3f} {s:>28.3f}")

print("\n--- the non-circular read ---")
print("Baselines on ZERO-WORD same-template pairs are the honest test: if char-3gram")
print("and token-overlap score ~0 there, lexical retrieval CANNOT find structural")
print("parallels. VSA scoring high there is by construction (it encodes the template).")

# spot-check list for a philologist: VSA-found zero-word same-template pairs
print("\n=== philologist spot-check: VSA zero-word structural parallels ===")
shown = 0
for qi in queries:
    s = VSA @ VSA[qi]
    s[qi] = -9
    j = int(np.argmax(s))
    if data[j]["roleseq"] == data[qi]["roleseq"] and not (data[qi]["wordset"] & data[j]["wordset"]):
        print(f"  {'·'.join(data[qi]['roleseq'])}")
        print(f"    [{data[qi]['id']}] {data[qi]['canon']!r}")
        print(f"    [{data[j]['id']}] {data[j]['canon']!r}")
        shown += 1
    if shown >= 6:
        break
