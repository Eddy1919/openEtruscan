"""
NS1.4 — prosopography by VSA unbinding + cross-stone family linking.

Two things fall out of the role-filler encoding:
  (a) unbind GENTILICIUM -> gens membership (group stones into families);
  (b) a child stone's PATRONYMIC is the genitive of the parent's praenomen, so we
      can LINK it to the parent's own stone in the same gens -> reconstruct
      multi-inscription family chains automatically.
Plus a VSA relational-analogy check (child -> parent) as vector algebra.
"""

import json
import re
import unicodedata
import numpy as np
from collections import defaultdict

rng = np.random.default_rng(3)
D = 4096
corpus = json.load(open("corpus.json"))
PRAENOMINA = set(
    """larθ lart laris lars arnθ arnt arunt aule avle aφle vel velθur venel marce mamarce
 marces sethre seθre śeθre θefarie aθe aθ spurie tite titi θucer θuker vipe vibe caile cae cne
 numesie ranazu velχe χaire velus aules θana θania θanaχvil θanχvil ramθa ravnθu larθi larθia
 velia veilia fasti fastia hasti hastia culni śeθra seθra ati""".split()
)
STATUS = set("lautni lautniθa lautn clan clenar sec seχ śeχ sech puia etera papals nefts".split())
KIN = set("clan clenar sec seχ śeχ sech".split())  # son/daughter markers
THEONYM = set(
    "tin tinia uni menrva turan fufluns aritimi hercle nethuns śuri catha selvans".split()
)
VERB = set("turce turuce muluvanice muluvanece zinace lupu lupuce ame amce".split())
TOMB = set("śuθi suθi θui".split())
EGO = set("mi mini".split())
ANCH = PRAENOMINA | STATUS | THEONYM | VERB | TOMB | EGO
GEN = re.compile(r"(al|ial|s|sa|isa|us|es|θur|nal|nas|cva|χva)$")
ABBR = re.compile(r"^[a-zθχśφς]{1,2}$")
SEP = re.compile(r"[:·•|/\\\[\]\(\)<>\{\}·•、,\.\s]+")


def norm(s):
    return unicodedata.normalize("NFC", s or "").strip().lower()


def tok(c):
    return [t for t in SEP.split(norm(c)) if t and not re.fullmatch(r"[-–—\d]+", t)]


def parse(ts):
    roles = []
    used = [False] * len(ts)
    for i, t in enumerate(ts):
        for S, name in [
            (EGO, "EGO"),
            (VERB, "VERB"),
            (TOMB, "OBJECT"),
            (STATUS, "STATUS"),
            (THEONYM, "THEONYM"),
        ]:
            if t in S:
                roles.append((name, t))
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


recs = []
for r in corpus:
    ts = tok(r["canonical"])
    roles = parse(ts)
    d = {"id": r["id"], "canon": r["canonical"]}
    for role, f in roles:
        d.setdefault(role, []).append(f)
    d["roles"] = roles
    d["anc"] = any(t in ANCH for t in ts)
    recs.append(d)

# ---- (a) gens membership ----
gens = defaultdict(list)
for d in recs:
    for g in d.get("GENTILICIUM", []):
        if len(g) >= 3:
            gens[g].append(d)
big = sorted(((g, m) for g, m in gens.items() if len(m) >= 3), key=lambda x: -len(x[1]))
print("=== prosopography ===")
print(f"distinct gentilicia (>=3 chars): {len([g for g in gens if len(g)>=3])}")
print(f"gentes with >=3 attested members: {len(big)}")
print("top gentes:", [(g, len(m)) for g, m in big[:8]])


# ---- (b) cross-stone family linking via patronymic ----
def stem(patr):  # genitive -> praenomen stem
    return re.sub(r"(al|ial|us|es|s|sa|isa|nal|nas)$", "", patr)


# index praenomen within a gens -> stones
gens_praen = defaultdict(lambda: defaultdict(list))
for d in recs:
    for g in d.get("GENTILICIUM", []):
        for p in d.get("PRAENOMEN", []):
            gens_praen[g][p].append(d)


# quality filters: skip giant texts (parser overfires) and 1-char abbreviations
def SHORT(d):
    return 2 <= len(d["roles"]) <= 6


def clean(x):
    return len(x) >= 3


links = []
for d in recs:
    # filiation in Etruscan is usually the PATRONYMIC alone (no clan/sec word needed)
    if not d.get("PATRONYMIC") or not SHORT(d):
        continue
    for g in d.get("GENTILICIUM", []):
        if not clean(g):
            continue
        for patr in d.get("PATRONYMIC", []):
            s = stem(patr)
            if clean(s) and s in gens_praen.get(g, {}):
                for parent in gens_praen[g][s]:
                    if (
                        parent["id"] != d["id"]
                        and SHORT(parent)
                        and clean(parent.get("PRAENOMEN", [""])[0])
                    ):
                        links.append((d, parent, g, s))
print(f"\n=== reconstructed parent-child links (cross-stone): {len(links)} ===")
seen = set()
for child, parent, g, s in links[:8]:
    key = (child["id"], parent["id"])
    if key in seen:
        continue
    seen.add(key)
    cp = "·".join(child.get("PRAENOMEN", ["?"]))
    print(f"  {cp} {g} ({'/'.join(child.get('STATUS',[]))}) —child-of→ {s} {g}")
    print(f"    child : [{child['id']}] {child['canon']!r}")
    print(f"    parent: [{parent['id']}] {parent['canon']!r}")

# ---- one family dossier ----
if big:
    g, members = big[0]
    print(f"\n=== family dossier: gens '{g}' ({len(members)} stones) ===")
    for m in members[:10]:
        pr = "·".join(m.get("PRAENOMEN", ["?"]))
        pa = "·".join(m.get("PATRONYMIC", [])) or "—"
        print(f"  [{m['id']:>10}] praenomen={pr:12} patronymic={pa:12} :: {m['canon']!r}")


# ---- (c) VSA relational analogy: child -> parent as vector algebra ----
def atom():
    return rng.choice([-1.0, 1.0], size=D)


CHILD, PARENT = atom(), atom()
fillers = sorted({f for d in recs for _, f in d["roles"]})
fv = {f: atom() for f in fillers}
fmat = np.stack([fv[f] for f in fillers])
pairs = []
for child, _parent, _g, s in links:
    cp = child.get("PRAENOMEN", [None])[0]
    pp = s
    if cp in fv and pp in fv:
        pairs.append((cp, pp))
if len(pairs) >= 20:
    rng.shuffle(pairs)
    k = len(pairs) // 2
    T = np.zeros(D)  # learn "is-child-of" transform
    for cp, pp in pairs[:k]:
        T += fv[cp] * fv[pp]
    T = np.sign(T)
    ok = 0
    for cp, pp in pairs[k:]:
        pred = fillers[int(np.argmax(fmat @ (fv[cp] * T)))]  # analogy: parent ≈ child ⊗ T
        ok += int(pred == pp)
    print(f"\n=== VSA relational analogy (child⊗T→parent), held-out {len(pairs)-k} ===")
    print(
        f"  parent recovered: {ok}/{len(pairs)-k} = {100*ok/(len(pairs)-k):.0f}%  (random ~ {100/len(fillers):.2f}%)"
    )
else:
    print(f"\n(only {len(pairs)} clean child-parent name pairs; analogy test skipped)")
