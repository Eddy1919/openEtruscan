"""Personal names in Etruscan texts: praenomina and the family names after them.

The Name Index used to list whatever a formula parser returned for a whole
inscription (``scripts/attic/migrate_graph.py``), so one "name" could be an
entire text or an apparatus note. This module reads names word by word:

* A **praenomen** is a form listed in ``reference/praenomina.csv``: the
  common first names, a closed class, with the spellings and case forms
  this corpus attests (``larθ``, ``larθal``, ``larθus`` …).
* An **abbreviated praenomen** (``a``, ``lθ``, ``vl`` …) counts only inside
  a naming formula: a name-like word must follow it, and a single letter
  must also be followed by an interpunct or a dot. Side labels (``a)``),
  abecedaria and facsimile capitals stay out. Abbreviations are indexed as
  written, not expanded, because one abbreviation can stand for more than
  one praenomen.
* The word right after a praenomen is read as the **family name**
  (gentilicium), since the Etruscan naming formula is praenomen +
  gentilicium. It is skipped when it is a praenomen itself, a word with a
  known non-name meaning, or not word-like. The rule usually holds, not
  always, so these rows are ``probable``.

Cognomina, theonyms and place names are not extracted.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[3] / "reference"
GOLD_GLOSSES = (
    Path(__file__).resolve().parents[3] / "research/anchors/gold_glosses/gold_glosses.jsonl"
)

NAME_TYPES = ("praenomen", "gentilicium")
BASES = ("praenomen_list", "praenomen_abbreviation", "follows_praenomen")

#: Words with a known meaning that are not personal names and often stand
#: next to one: kinship terms with their case forms, demonstratives and
#: pronouns, "year(s)", "died", magistracies, the god Tin, and editorial
#: notes left in a reading ("vacat"). ``gold_glosses.jsonl`` adds the rest
#: of the glossed vocabulary. A word is also skipped when it is one of these
#: plus the enclitic ``-c`` "and" (``clanc``, ``papalserc``).
NON_NAMES = frozenset(
    "mi mini eca ecn ca ta cn ita "
    "clan clans clanś clen clens clensi clenśi clenar cleniar clenaraśi cliniiaras "
    "sec secs seχ seχis sexis puia puias ati atiś apa apas apasi "
    "papa papas papasa papacs papals papalser teta tetal tetals nefts neftś nefiś "
    "prumts prumaθś ruva ruvaś lautni lautnita lautniθa lautnitza etera eteri "
    "avil avils lupu lupuce svalce zilaχ zilχ zilc amce θui "
    "suθi suθina turce mulu mulvanice muluvanice ein etnam ipa ais aiser tin tins "
    "tinal tinia "
    "vacat vac sic lacuna".split()
)

# Etruscan transliteration letters. A word with b, d, g, o or Latin x is
# Latin, a facsimile reading or noise.
_NAMELIKE = re.compile(r"[aceifhklmnpqrstuvzθφχσśςšξ]{3,}")
_VOWEL = re.compile(r"[aeiu]")
_ROMAN = re.compile(r"[ivxlc]+")
# Editorial brackets and parentheses mark restored or expanded letters
# inside a word ("avil[e]", "θansi(e)"): drop the marks, keep the letters.
_EDITORIAL = re.compile(r"[\[\](){}<>]")
# Word separators: whitespace, interpuncts, dots. The separator after a
# word is kept to read abbreviations.
_SPLIT = re.compile(r"[\s:·•|,;/⁝.]+")
_INTERPUNCT = re.compile(r"[:·•|⁝.]")


@dataclass(frozen=True)
class Praenomen:
    lemma: str
    gender: str  # "m" | "f"


@dataclass(frozen=True)
class NameLexicon:
    forms: dict[str, Praenomen]
    abbreviations: frozenset[str]
    non_names: frozenset[str]


@dataclass(frozen=True)
class NameToken:
    position: int  # word index in the text
    form: str  # as written, lower-cased letter by letter like Postgres lower()
    lemma: str  # praenomen headword; the form itself, ς as σ, otherwise ("a." for abbreviations)
    name_type: str  # see NAME_TYPES
    gender: str | None
    basis: str  # see BASES
    confidence: str  # "high" | "probable"


def _lower(s: str) -> str:
    # Letter by letter, as Postgres lower() does, so a stored form is a
    # substring of lower(canonical) and the site's search finds it.
    # str.lower() would turn a word-final capital Σ into ς; Postgres gives σ.
    return "".join(c.lower() for c in s)


def _key(w: str) -> str:
    # ς and σ are one letter: look words up and group headwords with σ,
    # but keep the form as written.
    return w.replace("ς", "σ")


def _norm(s: str) -> str:
    return _key(_lower(unicodedata.normalize("NFC", s).strip()))


def load_lexicon(
    praenomina: Path = REFERENCE / "praenomina.csv",
    glosses: Path | None = GOLD_GLOSSES,
) -> NameLexicon:
    """Praenomen forms and abbreviations, and the words known not to be names."""
    forms: dict[str, Praenomen] = {}
    abbreviations: set[str] = set()
    with open(praenomina, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            form = _norm(row["form"])
            if row["kind"] == "abbreviation":
                abbreviations.add(form)
            else:
                forms[form] = Praenomen(_norm(row["lemma"]), row["gender"])
    non_names = set(NON_NAMES)
    if glosses is not None and glosses.exists():
        with open(glosses, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                g = json.loads(line)
                if "praenomen" not in (g.get("gloss_en") or ""):
                    non_names.add(_norm(g["etr"]))
    non_names -= set(forms)
    return NameLexicon(forms, frozenset(abbreviations), frozenset(non_names))


def words(text: str) -> list[tuple[str, str]]:
    """``(word, separator after it)`` pairs, lower-cased.

    Dashes mark lost letters and stay on the word, so a fragment
    ("--------vetinei") never reads as a whole name. A run of dashes alone
    is dropped.
    """
    text = _EDITORIAL.sub("", unicodedata.normalize("NFC", text or ""))
    out: list[tuple[str, str]] = []
    pos = 0
    for m in _SPLIT.finditer(text + " "):
        w = _lower(text[pos : m.start()])
        pos = m.end()
        if w.strip("-–—"):
            out.append((w, m.group()))
    return out


def _word_like(w: str) -> bool:
    return bool(_NAMELIKE.fullmatch(w) and _VOWEL.search(w) and not _ROMAN.fullmatch(w))


def _could_be_name(w: str | None, lex: NameLexicon) -> bool:
    if w is None or not _word_like(w):
        return False
    k = _key(w)
    # "clanc" is clan + the enclitic -c "and", not a family name.
    stems = (k, k[:-1]) if k.endswith("c") else (k,)
    return not any(s in lex.forms or s in lex.non_names for s in stems) and (
        k not in lex.abbreviations
    )


def extract_names(text: str, lex: NameLexicon) -> list[NameToken]:
    """The praenomina in ``text`` and the family name after each one."""
    ws = words(text)
    found: dict[int, NameToken] = {}
    for i, (w, sep) in enumerate(ws):
        k = _key(w)
        nxt = ws[i + 1][0] if i + 1 < len(ws) else None
        is_praenomen = False
        if k in lex.forms:
            p = lex.forms[k]
            found.setdefault(
                i, NameToken(i, w, p.lemma, "praenomen", p.gender, "praenomen_list", "high")
            )
            is_praenomen = True
        elif (
            k in lex.abbreviations
            and _could_be_name(nxt, lex)
            and (len(w) > 1 or _INTERPUNCT.search(sep))
        ):
            found.setdefault(
                i,
                NameToken(i, w, f"{k}.", "praenomen", None, "praenomen_abbreviation", "probable"),
            )
            is_praenomen = True
        if is_praenomen and nxt is not None and _could_be_name(nxt, lex):
            found.setdefault(
                i + 1,
                NameToken(
                    i + 1, nxt, _key(nxt), "gentilicium", None, "follows_praenomen", "probable"
                ),
            )
    return [found[k] for k in sorted(found)]


def index_corpus(
    records: Iterable[tuple[str, str]], lex: NameLexicon
) -> dict[str, list[NameToken]]:
    """``{inscription_id: names}`` for every record that has at least one."""
    out: dict[str, list[NameToken]] = {}
    for rid, text in records:
        names = extract_names(text, lex)
        if names:
            out[rid] = names
    return out
