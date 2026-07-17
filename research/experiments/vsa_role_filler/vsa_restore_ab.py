"""
NS3.1 — structure-aware retrieval for lacuna restoration, A/B vs the shipped RAG.

Same 66-task v2.0.3 gold, same model + prompt; ONLY the retrieved parallels
differ: char-3-gram (lexical, the shipped restorer) vs VSA structural (same
role-template). Question: does feeding structural parallels change/lift
restoration? Gemini via generativelanguage (GEMINI_API_KEY), thinkingBudget=0.
"""

import json
import re
import os
import unicodedata
import urllib.request
import numpy as np
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

rng = np.random.default_rng(5)
D = 4096
SP = "/private/tmp/claude-502/-Users-edoardo-panichi-openEtruscan/8532a981-6dc7-491f-a43f-95bd4351ef34/scratchpad"
POOL = [json.loads(line) for line in open(f"{SP}/blind_pool.jsonl")]
GOLD = json.loads(open(f"{SP}/gold_map.json").read())
corpus = json.load(open(f"{SP}/corpus.json"))
KEY = os.environ["GEMINI_API_KEY"]

# --- widened parser (same as vsa_widen_neural) ---
PRAENOMINA = set(
    "larθ lart laris lars arnθ arnt arunt aule avle vel velθur venel marce mamarce marces sethre seθre śeθre θefarie aθe aθ tite titi vipe caile cae velus aules θana θania θanχvil ramθa ravnθu larθi larθia velia veilia fasti hasti culni seθra ati".split()
)
STATUS = set("lautni lautniθa lautn clan clenar sec seχ śeχ puia etera papals nefts".split())
THEONYM = set(
    "tin tinia uni menrva turan fufluns aritimi hercle nethuns śuri catha selvans".split()
)
VERB = set("turce turuce muluvanice muluvanece zinace lupu ame amce".split())
TOMB = set("śuθi suθi θui".split())
EGO = set("mi mini".split())
GEN = re.compile(r"(al|ial|s|sa|isa|us|es|θur|nal|nas|cva|χva)$")
ABBR = re.compile(r"^[a-zθχśφς]{1,2}$")
SEP = re.compile(r"[:·•|/\\\[\]\(\)<>\{\}·•、,\.\s?]+")


def norm(s):
    return unicodedata.normalize("NFC", s or "").strip().lower()


def tok(c):
    return [t for t in SEP.split(norm(c)) if t and not re.fullmatch(r"[-–—\d]+", t)]


def parse(ts):
    roles = []
    used = [False] * len(ts)
    for i, t in enumerate(ts):
        for S, nm in [
            (EGO, "EGO"),
            (VERB, "VERB"),
            (TOMB, "OBJECT"),
            (STATUS, "STATUS"),
            (THEONYM, "THEONYM"),
        ]:
            if t in S:
                roles.append((nm, t))
                used[i] = True
                break
    seen = False
    for i, t in enumerate(ts):
        if used[i]:
            continue
        if t in PRAENOMINA and not seen:
            roles.append(("PRAENOMEN", t))
            seen = True
        elif ABBR.match(t) and not seen:
            roles.append(("PRAENOMEN", t))
            seen = True
        elif GEN.search(t) and seen:
            roles.append(("PATRONYMIC", t))
        elif not seen:
            roles.append(("PRAENOMEN", t))
            seen = True
        else:
            roles.append(("GENTILICIUM", t))
    return roles


# --- VSA structure vectors over corpus ---
def atom():
    return rng.choice([-1.0, 1.0], size=D)


ROLES = ["EGO", "VERB", "OBJECT", "STATUS", "THEONYM", "PRAENOMEN", "GENTILICIUM", "PATRONYMIC"]
rv = {r: atom() for r in ROLES}
POS = [atom() for _ in range(14)]


def struct_vec(roleseq):
    S = np.zeros(D)
    for k, role in enumerate(roleseq):
        S += rv[role] * POS[min(k, 13)]
    return S


cstruct = np.zeros((len(corpus), D))
ccanon = []
cnorm = []
for i, c in enumerate(corpus):
    rs = [r for r, _ in parse(tok(c["canonical"]))]
    cstruct[i] = struct_vec(rs)
    ccanon.append(c["canonical"])
    cnorm.append(re.sub(r"\W", "", norm(c["canonical"])))
cstruct /= np.linalg.norm(cstruct, axis=1, keepdims=True) + 1e-9


# --- char-3gram over corpus ---
def ng(s, n=3):
    s = re.sub(r"[^\w\U00010300-\U0001032f]", "", norm(s))
    s = f"^{s}$"
    return Counter(s[i : i + n] for i in range(len(s) - n + 1)) if len(s) >= n else Counter([s])


cng = [ng(c) for c in ccanon]


def cos_c(a, b):
    ks = set(a) | set(b)
    dot = sum(a[k] * b[k] for k in ks)
    na = np.sqrt(sum(v * v for v in a.values()))
    nb = np.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0


def visible(m, w):
    s = m.index("?")
    return m[:s] + m[s + w :]


def gold_full(row):
    return row["masked"].replace("?" * row["width"], GOLD[row["key"]], 1)


def parallels_char(row, k=8):
    q = ng(visible(row["masked"], row["width"]))
    gf = re.sub(r"\W", "", norm(gold_full(row)))
    sims = [(cos_c(q, cng[i]), i) for i in range(len(corpus))]
    out = []
    for _s, i in sorted(sims, reverse=True):
        if cnorm[i] and (cnorm[i] in gf or gf in cnorm[i]):
            continue
        out.append(ccanon[i])  # leakage-excluded
        if len(out) >= k:
            break
    return out


def parallels_vsa(row, k=8):
    rs = [r for r, _ in parse(tok(visible(row["masked"], row["width"])))]
    if len(rs) < 2:
        return []  # no structure -> no structural parallels
    qv = struct_vec(rs)
    qv /= np.linalg.norm(qv) + 1e-9
    sims = cstruct @ qv
    gf = re.sub(r"\W", "", norm(gold_full(row)))
    out = []
    for i in np.argsort(-sims):
        if cnorm[i] and (cnorm[i] in gf or gf in cnorm[i]):
            continue
        out.append(ccanon[i])
        if len(out) >= k:
            break
    return out


SYS = "You are restoring damaged Etruscan inscriptions. Use the parallel inscriptions as evidence for the characters that filled the marked lacuna. Output JSON only; do not change anything outside the lacuna."
USER = """## Inscription (single lacuna, ? of width {w})
```
{m}
```
## Parallel inscriptions
{par}
Return JSON: {{"restored_lacuna":"<exactly {w} chars>","confidence":"high|medium|low"}}"""


def gemini(prompt):
    body = json.dumps(
        {
            "system_instruction": {"parts": [{"text": SYS}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},
                "maxOutputTokens": 512,
            },
        }
    ).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={KEY}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    for _ in range(3):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=40))
            t = d["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```json?|```$", "", t.strip()).strip()).get(
                "restored_lacuna", ""
            )
        except Exception:
            pass
    return None


def clean(g):
    g = (g or "").strip()
    return bool(g) and not re.search(r"-{2,}", g) and not re.search(r"\d", g)


tasks = [r for r in POOL if clean(GOLD[r["key"]])]


def run(row, which):
    par = parallels_char(row) if which == "char" else parallels_vsa(row)
    if which == "vsa" and not par:
        return ("nostruct", None)
    plist = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(par)) or "(none)"
    pred = gemini(USER.format(w=row["width"], m=row["masked"], par=plist))
    return ("ok", pred)


def score(which):
    with ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(lambda r: (r, run(r, which)), tasks))
    return res


print(f"tasks (clean gold): {len(tasks)}")
resA = score("char")
resB = score("vsa")


def span(pred, row):
    return pred is not None and pred == GOLD[row["key"]]


A = {r["key"]: (st, pr) for r, (st, pr) in resA}
B = {r["key"]: (st, pr) for r, (st, pr) in resB}
# subset where VSA had structure
vsa_keys = [r["key"] for r in tasks if B[r["key"]][0] == "ok"]
print(f"tasks where visible part parsed to structure (VSA applies): {len(vsa_keys)}/{len(tasks)}")


def acc(keys, M):
    ks = [k for k in keys]
    return (
        np.mean([span(M[k][1], next(r for r in tasks if r["key"] == k)) for k in ks]) if ks else 0
    )


allk = [r["key"] for r in tasks]
print(f"\nspan-exact, ALL {len(allk)} tasks:")
print(f"  char-3gram RAG : {acc(allk, A):.3f}")
print(
    f"  VSA-structural : {acc([k for k in allk if B[k][0] == 'ok'] + [k for k in allk if B[k][0] != 'ok'], {**B, **{k: A[k] for k in allk if B[k][0] != 'ok'}}):.3f}  (falls back to char where no structure)"
)
print(f"\nspan-exact, STRUCTURED subset ({len(vsa_keys)} tasks where VSA applies):")
print(f"  char-3gram RAG : {acc(vsa_keys, A):.3f}")
print(f"  VSA-structural : {acc(vsa_keys, B):.3f}")
