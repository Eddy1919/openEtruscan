"""Shared heuristic role parser — lifted verbatim from
``research/experiments/vsa_role_filler/vsa_etruscan.py`` (NS1.1) so the graph
and VSA steps of the hybrid experiment segment identically."""

from __future__ import annotations

import re
import unicodedata

PRAENOMINA = set(
    "larθ laris arnθ aule avle vel velθur θefarie marce larce marces "
    "sethre seθre aθ θana θania ramθa larθi larθia velia fasti hasti "
    "θanχvil culni aules velus arnt lart".split()
)
STATUS = set(
    "lautni lautniθa lautn clan sec seχ śeχ puia etera papals nefts cliniiaras cliniar".split()
)
THEONYM = set(
    "tin tinia uni menrva turan fufluns aritimi hercle herecele nethuns "
    "śuri catha selvans veive vetis culsu θesan".split()
)
VERB = set("turce turuce muluvanice muluvanece zinace mulu alice cerine tece".split())
TOMBWORD = set("śuθi suθi θui".split())
EGO = set("mi mini".split())
SEP = re.compile(r"[:·•|/\\\[\]\(\)<>\{\}·•、,\.\s]+")


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s or "").strip().lower()


def tokenize(canon: str) -> list[str]:
    return [t for t in SEP.split(norm(canon)) if t and not re.fullmatch(r"[-–—\d]+", t)]


def parse_roles(toks: list[str]) -> list[tuple[str, str]]:
    """Return list of (role, filler) in order. Heuristic, formulaic-first."""
    roles: list[tuple[str, str]] = []
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
            used[i] = True
        elif not seen_praenomen and t not in PRAENOMINA:
            roles.append(("PRAENOMEN", t))
            used[i] = True
            seen_praenomen = True
        else:
            roles.append(("GENTILICIUM", t))
            used[i] = True
    return roles


ROLES = ["EGO", "VERB", "OBJECT", "STATUS", "THEONYM", "PRAENOMEN", "GENTILICIUM", "PATRONYMIC"]
