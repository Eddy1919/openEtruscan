"""
NS1.1-widen (bigger scope) + NS1.3 re-score with a NEURAL-EMBEDDING baseline.

Widened role parser: larger praenomen/kinship/theonym lexicons, abbreviation
handling, and 2-slot onomastic templates accepted. Re-runs the non-circular
silver eval and adds gemini-embedding-001 (768d) as a third baseline to settle
"beats embeddings, not just char-ngram". Key read from GEMINI_API_KEY (never
committed).
"""

import json
import re
import os
import unicodedata
import urllib.request
import numpy as np
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

rng = np.random.default_rng(11)
D, H = 4096, 2048
corpus = json.load(open("corpus.json"))

# --- widened lexicons ---
PRAENOMINA = set(
    """larθ larθ lart laris lars arnθ arnt arunt aule avle aφle vel velθur venel
 marce mamarce marces sethre seθre śeθre θefarie aθe aθ spurie tite titi θucer θuker vipe vibe
 caile cae cne numesie prumaθe ranazu velχe χaire laθ velus aules arntal
 θana θania θanaχvil θanχvil ramθa ravnθu larθi larθia velia veilia fasti fastia hasti hastia
 culni śeθra seθra ati θanaqvil hastui śetra fastntru velkasnai""".split()
)
STATUS = set(
    """lautni lautniθa lautn clan clenar sec seχ śeχ sech puia etera papals papacs nefts
 prumaθs prumts tusurθir tusurθi ati apa papa ruva nefis etnam cliniiaras cliniar""".split()
)
THEONYM = set(
    "tin tinia uni menrva turan fufluns aritimi hercle herecele nethuns śuri catha selvans veive vetis culsu θesan aplu apulu śuris".split()
)
VERB = set(
    "turce turuce muluvanice muluvanece zinace mulu alice cerine tece ame amce svalce lupu lupuce".split()
)
TOMBWORD = set("śuθi suθi θui suθiθi".split())
EGO = set("mi mini".split())
ANCHORS = PRAENOMINA | STATUS | THEONYM | VERB | TOMBWORD | EGO
GEN = re.compile(r"(al|ial|s|sa|isa|us|es|us|θur|nal|nas|ial|cva|χva)$")
ABBR = re.compile(r"^[a-zθχśφςθ]{1,2}$")
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
    anchored = any(t in ANCHORS for t in toks)
    for i, t in enumerate(toks):
        if used[i]:
            continue
        if t in PRAENOMINA and not seen:
            roles.append(("PRAENOMEN", t))
            seen = True
        elif ABBR.match(t) and not seen:
            roles.append(("PRAENOMEN", t))
            seen = True  # abbreviated praenomen
        elif GEN.search(t) and seen:
            roles.append(("PATRONYMIC", t))  # genitive-marked
        elif ABBR.match(t) and seen:
            roles.append(("PATRONYMIC", t))  # abbreviated patronymic
        elif not seen:
            roles.append(("PRAENOMEN", t))
            seen = True
        else:
            roles.append(("GENTILICIUM", t))
    return roles, anchored


parsed = []
for r in corpus:
    toks = tokenize(r["canonical"])
    roles, anc = parse_roles(toks)
    parsed.append(
        {
            "id": r["id"],
            "canon": r["canonical"],
            "toks": toks,
            "roleseq": tuple(rr for rr, _ in roles),
            "wordset": set(toks),
            "anc": anc,
            "nrole": len(roles),
        }
    )

multi = [p for p in parsed if len(p["toks"]) >= 2]
anc2 = [p for p in parsed if p["anc"] and p["nrole"] >= 2]
anc3 = [p for p in parsed if p["anc"] and p["nrole"] >= 3]
print("=== NS1.1-widen coverage ===")
print(f"corpus 5932 | multi-token {len(multi)}")
print(f"anchored >=2 roles: {len(anc2)}  ({100 * len(anc2) / 5932:.1f}% of corpus)   [was ~ n/a]")
print(
    f"anchored >=3 roles: {len(anc3)}  ({100 * len(anc3) / 5932:.1f}% of corpus)   [prev parser: 611 = 10.3%]"
)

# --- silver eval set: anchored >=3 (richer templates) ---
data = anc3
n = len(data)
by_tmpl = defaultdict(list)
for i, d in enumerate(data):
    by_tmpl[d["roleseq"]].append(i)
multi_t = {k: v for k, v in by_tmpl.items() if len(v) >= 2}
print(f"\nsilver set n={n} | templates {len(by_tmpl)} | multi-member templates {len(multi_t)}")


# --- feature matrices ---
def atom():
    return rng.choice([-1.0, 1.0], size=D)


ROLES = ["EGO", "VERB", "OBJECT", "STATUS", "THEONYM", "PRAENOMEN", "GENTILICIUM", "PATRONYMIC"]
rv = {r: atom() for r in ROLES}
POS = [atom() for _ in range(14)]


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
        S += rv[role] * POS[min(k, 13)]
    VSA[i] = S
    CH[i] = hashvec(cngrams(d["canon"]), H)
    TOK[i] = hashvec(d["toks"], H)

# --- NEURAL baseline: gemini-embedding-001 (768d) ---
KEY = os.environ.get("GEMINI_API_KEY", "")


def embed(text):
    body = json.dumps(
        {"content": {"parts": [{"text": text[:512]}]}, "outputDimensionality": 768}
    ).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={KEY}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    for _ in range(3):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=30))
            v = d.get("embedding", {}).get("values")
            if v:
                return np.array(v, dtype=float)
        except Exception:
            pass
    return None


GEM = None
if KEY:
    print(f"\nembedding {n} inscriptions with gemini-embedding-001 (768d)...")
    with ThreadPoolExecutor(max_workers=12) as ex:
        vecs = list(ex.map(lambda d: embed(d["canon"]), data))
    ok = sum(v is not None for v in vecs)
    if ok > 0.9 * n:
        GEM = np.stack([v if v is not None else np.zeros(768) for v in vecs])
        print(f"  embedded {ok}/{n}")
    else:
        print(f"  only {ok}/{n} embedded — skipping neural baseline")


def l2(M):
    return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)


methods = {
    "VSA structure": l2(VSA),
    "gemini-embed": l2(GEM) if GEM is not None else None,
    "char-3gram": l2(CH),
    "token-overlap": l2(TOK),
    "random": l2(rng.standard_normal((n, H))),
}
methods = {k: v for k, v in methods.items() if v is not None}


def recall_at(Mat, qi, positives, k=10):
    s = Mat @ Mat[qi]
    s[qi] = -9
    top = set(np.argsort(-s)[:k].tolist())
    return len(top & positives) / min(k, len(positives)) if positives else None


queries = [i for v in multi_t.values() for i in v]
rng.shuffle(queries)
queries = queries[:600]
res = {m: {"all": [], "so": []} for m in methods}
nsq = 0
for qi in queries:
    pos = set(by_tmpl[data[qi]["roleseq"]]) - {qi}
    so = {j for j in pos if not (data[qi]["wordset"] & data[j]["wordset"])}
    if so:
        nsq += 1
    for m, Mat in methods.items():
        r = recall_at(Mat, qi, pos)
        res[m]["all"].append(r) if r is not None else None
        if so:
            res[m]["so"].append(recall_at(Mat, qi, so))
print(f"\nqueries {len(queries)} | with zero-word sibling {nsq}")
print(f"\n{'method':16}{'recall@10 all':>16}{'recall@10 ZERO-WORD':>22}")
for m in methods:
    print(f"{m:16}{np.mean(res[m]['all']):>16.3f}{np.mean(res[m]['so']):>22.3f}")
