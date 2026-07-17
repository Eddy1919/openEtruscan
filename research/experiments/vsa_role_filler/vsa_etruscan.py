"""
WP1 — Vector-Symbolic role-filler encoding on the real Etruscan corpus.
NS1.1 heuristic role parser + NS1.2 HRR/MAP encoder + NS1.3 structural retrieval.

Existence-proof / feasibility spike: does binding-as-algebra (a) round-trip
(unbind recovers the filler) and (b) retrieve STRUCTURAL parallels that a
char-3-gram baseline misses (same epigraphic structure, different words)?
"""

import json
import re
import unicodedata
import numpy as np
from collections import Counter

rng = np.random.default_rng(7)
D = 4096
corpus = json.load(open("corpus.json"))  # [{id, canonical}]

# ---------- NS1.1: heuristic role parser ----------
PRAENOMINA = set(
    "larθ laris arnθ aule avle vel velθur θefarie marce larce marces "
    "sethre seθre aθ θana θania ramθa larθi larθia velia fasti hasti "
    "θanχvil culni aules velus arnt lart".split()
)
STATUS = set(
    "lautni lautniθa lautn clan sec seχ śeχ puia etera papals nefts " "cliniiaras cliniar".split()
)
THEONYM = set(
    "tin tinia uni menrva turan fufluns aritimi hercle herecele nethuns "
    "śuri catha selvans veive vetis culsu θesan".split()
)
VERB = set("turce turuce muluvanice muluvanece zinace mulu alice cerine tece".split())
TOMBWORD = set("śuθi suθi θui".split())
EGO = set("mi mini".split())
SEP = re.compile(r"[:·•|/\\\[\]\(\)<>\{\}·•、,\.\s]+")


def norm(s):
    return unicodedata.normalize("NFC", s or "").strip().lower()


def tokenize(canon):
    toks = [t for t in SEP.split(norm(canon)) if t and not re.fullmatch(r"[-–—\d]+", t)]
    return toks


def parse_roles(toks):
    """Return list of (role, filler) in order. Heuristic, formulaic-first."""
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
    # onomastic backbone on remaining tokens, in order
    pr123 = [i for i, t in enumerate(toks) if not used[i]]
    seen_praenomen = False
    for i in pr123:
        t = toks[i]
        if t in PRAENOMINA and not seen_praenomen:
            roles.append(("PRAENOMEN", t))
            used[i] = True
            seen_praenomen = True
        elif re.search(r"(al|ial|s|sa|isa|us|es)$", t) and seen_praenomen:
            roles.append(("PATRONYMIC", t))
            used[i] = True  # genitive-marked
        elif not seen_praenomen and t not in PRAENOMINA:
            # leading non-praenomen word in a name string -> treat as praenomen-slot filler
            roles.append(("PRAENOMEN", t))
            used[i] = True
            seen_praenomen = True
        else:
            roles.append(("GENTILICIUM", t))
            used[i] = True
    return roles


parsed = []
for r in corpus:
    toks = tokenize(r["canonical"])
    roles = parse_roles(toks)
    parsed.append({"id": r["id"], "canon": r["canonical"], "toks": toks, "roles": roles})

multi = [p for p in parsed if len(p["toks"]) >= 2]
ge2roles = [p for p in parsed if len(p["roles"]) >= 2]
print(
    f"corpus: {len(corpus)} | multi-token: {len(multi)} | parsed into >=2 roles: {len(ge2roles)}"
    f" ({100*len(ge2roles)/len(multi):.0f}% of multi-token)"
)
role_counts = Counter(role for p in parsed for role, _ in p["roles"])
print("role distribution:", dict(role_counts.most_common()))


# ---------- NS1.2: HRR/MAP codebook + encoder ----------
def atom():
    return rng.choice([-1.0, 1.0], size=D)


ROLES = ["EGO", "VERB", "OBJECT", "STATUS", "THEONYM", "PRAENOMEN", "GENTILICIUM", "PATRONYMIC"]
role_vec = {r: atom() for r in ROLES}
POS = [atom() for _ in range(12)]  # position atoms (ordered structure)
fillers = sorted({f for p in parsed for _, f in p["roles"]})
fill_vec = {f: atom() for f in fillers}
fill_mat = np.stack([fill_vec[f] for f in fillers])  # cleanup memory


def bind(a, b):
    return a * b  # MAP binding (self-inverse, bipolar)


def encode(roles):
    """content vector I = sum role*filler ; structure vector S = sum role*pos."""
    ivec = np.zeros(D)
    svec = np.zeros(D)
    for k, (role, fill) in enumerate(roles):
        ivec += bind(role_vec[role], fill_vec[fill])
        svec += bind(role_vec[role], POS[min(k, 11)])
    return ivec, svec


for p in parsed:
    p["I"], p["S"] = encode(p["roles"])


def cleanup(vec):
    sims = fill_mat @ vec
    j = int(np.argmax(sims))
    return fillers[j]


# round-trip unbind accuracy for GENTILICIUM and PATRONYMIC
def roundtrip(role):
    ok = tot = 0
    for p in parsed:
        gt = [f for rr, f in p["roles"] if rr == role]
        if not gt:
            continue
        rec = cleanup(bind(p["I"], role_vec[role]))
        tot += 1
        ok += int(rec == gt[-1])
    return ok, tot


for role in ["GENTILICIUM", "PATRONYMIC", "STATUS"]:
    ok, tot = roundtrip(role)
    if tot:
        print(f"round-trip unbind {role:12}: {ok}/{tot} = {100*ok/tot:.1f}%")


# ---------- NS1.3: structural retrieval vs char-3-gram ----------
def ngrams(s, n=3):
    s = re.sub(r"[^\wÀ-Ͽ\U00010300-\U0001032f]", "", norm(s))
    c = Counter(s[i : i + n] for i in range(len(s) - n + 1)) if len(s) >= n else Counter([s])
    return c


def cos_counter(a, b):
    ks = set(a) | set(b)
    dot = sum(a[k] * b[k] for k in ks)
    na = np.sqrt(sum(v * v for v in a.values()))
    nb = np.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


pool = [p for p in ge2roles if len(p["roles"]) >= 3]  # need real structure
Smat = np.stack([p["S"] for p in pool])
Smat /= np.linalg.norm(Smat, axis=1, keepdims=True) + 1e-9
for p in pool:
    p["ng"] = ngrams(p["canon"])


def roleseq(p):
    return tuple(r for r, _ in p["roles"])


def tokset(p):
    return set(p["toks"])


def jacc(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0


rs = rng.choice(len(pool), size=min(120, len(pool)), replace=False)
vsa_struct = []
vsa_lex = []
ng_struct = []
ng_lex = []
for qi in rs:
    q = pool[qi]
    # VSA structural top-5
    sims = Smat @ (q["S"] / (np.linalg.norm(q["S"]) + 1e-9))
    sims[qi] = -9
    top = np.argsort(-sims)[:5]
    vsa_struct += [jacc(set(roleseq(q)), set(roleseq(pool[j]))) for j in top]
    vsa_lex += [jacc(tokset(q), tokset(pool[j])) for j in top]
    # char-3gram top-5
    ns = np.array(
        [cos_counter(q["ng"], pool[j]["ng"]) if j != qi else -9 for j in range(len(pool))]
    )
    topn = np.argsort(-ns)[:5]
    ng_struct += [jacc(set(roleseq(q)), set(roleseq(pool[j]))) for j in topn]
    ng_lex += [jacc(tokset(q), tokset(pool[j])) for j in topn]

print("\n=== NS1.3 structural retrieval (top-5, n=%d queries) ===" % len(rs))
print("                     role-structure sim   lexical(word) overlap")
print(f"VSA structure vec  :      {np.mean(vsa_struct):.3f}                {np.mean(vsa_lex):.3f}")
print(f"char-3-gram baseline:      {np.mean(ng_struct):.3f}                {np.mean(ng_lex):.3f}")
print(
    "(VSA should give HIGH structure sim at LOW lexical overlap = parallels char-ngram can't see)"
)

# concrete examples
print("\n=== example: same structure, different words (VSA-found) ===")
shown = 0
for qi in rs:
    q = pool[qi]
    sims = Smat @ (q["S"] / (np.linalg.norm(q["S"]) + 1e-9))
    sims[qi] = -9
    j = int(np.argmax(sims))
    if (
        jacc(tokset(q), tokset(pool[j])) == 0
        and roleseq(q) == roleseq(pool[j])
        and len(q["roles"]) >= 3
    ):
        print(f"  [{q['id']}] {q['canon']!r}")
        print(f"    ~struct~ [{pool[j]['id']}] {pool[j]['canon']!r}")
        print(f"    roles: {roleseq(q)}  (0 shared words)")
        shown += 1
    if shown >= 4:
        break
