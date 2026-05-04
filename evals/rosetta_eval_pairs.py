"""Curated Etruscan-Latin equivalences — used as held-out evaluation
data for the Rosetta multilingual encoder.

Pre-2026 pivot these pairs were *training* anchors for a Procrustes
rotation. After moving to a multilingual transformer (XLM-R + LoRA on
Etruscan), the pairs are no longer needed for alignment — the encoder's
pretraining already places Latin and Etruscan in a shared space. They
remain valuable as **eval data**:

    For each pair, embed the Etruscan word, query its top-k Latin
    neighbours in the shared space, and check whether the philological
    consensus (e.g. clan→filius, avil→annus) lands in the top-k.

Citations follow Bonfante & Bonfante (2002), "The Etruscan Language: An
Introduction" 2nd ed., Wallace (2008), "Zikh Rasna", and Pallottino
(1968), "Testimonia Linguae Etruscae".
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


VALID_CATEGORIES = (
    "kinship",
    "civic",
    "religious",
    "time",
    "numeral",
    "verb",
    "theonym",
    "onomastic",
)


@dataclass(frozen=True)
class EvalPair:
    """One Etruscan-Latin equivalence used to grade alignment quality.

    ``category`` lets the eval harness break precision@k down by semantic
    domain. Some categories (theonyms, kinship) are easier than others
    (numerals are notoriously contested in the philological literature),
    and the breakdown surfaces *where* the encoder is doing well rather
    than reporting a single global number.
    """

    etr: str
    lat: str
    gloss: str
    confidence: str  # "low" | "medium" | "high"
    source: str
    category: str = "uncategorised"

    def __post_init__(self) -> None:
        object.__setattr__(self, "etr", unicodedata.normalize("NFC", self.etr).lower())
        object.__setattr__(self, "lat", unicodedata.normalize("NFC", self.lat).lower())
        if self.category not in VALID_CATEGORIES + ("uncategorised",):
            raise ValueError(
                f"EvalPair category {self.category!r} not in {VALID_CATEGORIES}"
            )


EVAL_PAIRS: list[EvalPair] = [
    # Kinship
    EvalPair("clan", "filius", "son", "high", "Bonfante 2002 §96", "kinship"),
    EvalPair("sec", "filia", "daughter", "high", "Bonfante 2002 §97", "kinship"),
    EvalPair("ati", "mater", "mother", "high", "Wallace 2008 §3.4", "kinship"),
    EvalPair("apa", "pater", "father", "high", "Wallace 2008 §3.4", "kinship"),
    EvalPair("puia", "uxor", "wife", "high", "Bonfante 2002 §99", "kinship"),
    EvalPair("nefts", "nepos", "nephew/grandson", "high", "Bonfante 2002 §99", "kinship"),
    EvalPair("ruva", "frater", "brother", "medium", "Bonfante 2002 §99", "kinship"),
    EvalPair("papa", "avus", "grandfather", "medium", "Wallace 2008 §3.4", "kinship"),
    EvalPair("lautn", "familia", "family/lineage", "high", "Pallottino 1968 §47", "kinship"),
    # Civic / magistracies
    EvalPair("zilaθ", "praetor", "magistrate", "high", "Bonfante 2002 §83", "civic"),
    EvalPair("zilθ", "praetor", "magistrate", "high", "Wallace 2008 §3.5", "civic"),
    EvalPair("maru", "magister", "magistracy title", "medium", "Bonfante 2002 §83", "civic"),
    EvalPair("cepen", "sacerdos", "priest", "medium", "Wallace 2008 §3.5", "civic"),
    EvalPair("spura", "civitas", "city/state", "high", "Bonfante 2002 §85", "civic"),
    EvalPair("methlum", "civitas", "community", "medium", "Pallottino 1968 §50", "civic"),
    EvalPair("tular", "fines", "boundaries", "high", "Bonfante 2002 §86", "civic"),
    EvalPair("rasna", "etruscus", "Etruscan (ethnonym)", "high", "Bonfante 2002 §1", "civic"),
    # Funerary / religious
    EvalPair("suθi", "sepulcrum", "tomb", "high", "Bonfante 2002 §90", "religious"),
    EvalPair("ais", "deus", "god (loanword family)", "medium", "Wallace 2008 §3.6", "religious"),
    EvalPair("aiser", "dei", "gods", "medium", "Wallace 2008 §3.6", "religious"),
    EvalPair("fler", "sacrum", "sacred offering", "medium", "Bonfante 2002 §93", "religious"),
    EvalPair("flerχva", "sacra", "sacred things", "medium", "Bonfante 2002 §93", "religious"),
    EvalPair("fanu", "fanum", "sacred place", "medium", "Wallace 2008 §3.6", "religious"),
    # Time / calendar
    EvalPair("avil", "annus", "year", "high", "Bonfante 2002 §82", "time"),
    EvalPair("avils", "annorum", "of years (genitive)", "high", "Bonfante 2002 §82", "time"),
    EvalPair("tiur", "mensis", "month", "high", "Bonfante 2002 §82", "time"),
    EvalPair("usil", "sol", "sun", "high", "Bonfante 2002 §82", "time"),
    EvalPair("tiu", "luna", "moon", "medium", "Pallottino 1968 §52", "time"),
    # Cardinal numerals
    EvalPair("θu", "unus", "one", "medium", "Wallace 2008 §3.7", "numeral"),
    EvalPair("zal", "duo", "two", "high", "Bonfante 2002 §80", "numeral"),
    EvalPair("ci", "tres", "three", "high", "Bonfante 2002 §80", "numeral"),
    EvalPair("huθ", "sex", "six", "medium", "Wallace 2008 §3.7", "numeral"),
    EvalPair("śa", "quattuor", "four", "medium", "Wallace 2008 §3.7", "numeral"),
    EvalPair("maχ", "quinque", "five", "medium", "Wallace 2008 §3.7", "numeral"),
    EvalPair("semφ", "septem", "seven", "medium", "Wallace 2008 §3.7", "numeral"),
    EvalPair("cezp", "octo", "eight", "medium", "Wallace 2008 §3.7", "numeral"),
    EvalPair("nurφ", "novem", "nine", "medium", "Wallace 2008 §3.7", "numeral"),
    EvalPair("śar", "decem", "ten", "high", "Bonfante 2002 §80", "numeral"),
    # Verbs
    EvalPair("turce", "dedit", "gave (votive)", "high", "Bonfante 2002 §75", "verb"),
    EvalPair("mulvanice", "dedicavit", "dedicated", "high", "Bonfante 2002 §75", "verb"),
    EvalPair("mulu", "dedit", "dedicated/gave", "medium", "Pallottino 1968 §57", "verb"),
    EvalPair("ace", "fecit", "made", "high", "Bonfante 2002 §75", "verb"),
    EvalPair("lupuce", "mortuus", "died", "high", "Bonfante 2002 §75", "verb"),
    EvalPair("svalce", "vixit", "lived", "high", "Bonfante 2002 §75", "verb"),
    EvalPair("ame", "est", "is/was", "medium", "Wallace 2008 §3.8", "verb"),
    EvalPair("zinace", "scripsit", "wrote/inscribed", "medium", "Wallace 2008 §3.8", "verb"),
    EvalPair("zich", "scribere", "to write", "medium", "Bonfante 2002 §75", "verb"),
    EvalPair("ziχ", "scriptura", "writing/script", "medium", "Bonfante 2002 §75", "verb"),
    # Theonyms
    EvalPair("tinia", "iuppiter", "Jupiter", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("uni", "iuno", "Juno", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("menrva", "minerva", "Minerva", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("aita", "dis", "Hades/Dis", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("φersipnai", "proserpina", "Persephone", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("turan", "venus", "Venus", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("turms", "mercurius", "Mercury", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("fufluns", "bacchus", "Bacchus/Dionysus", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("hercle", "hercules", "Hercules", "high", "Bonfante 2002 §93", "theonym"),
    EvalPair("nethuns", "neptunus", "Neptune", "high", "Bonfante 2002 §93", "theonym"),
    # Onomastic praenomina
    EvalPair("avle", "aulus", "Aulus (praenomen)", "high", "Bonfante 2002 §62", "onomastic"),
    EvalPair("vel", "velius", "Velius (praenomen)", "medium", "Bonfante 2002 §62", "onomastic"),
    EvalPair("larθ", "lars", "Lars (praenomen)", "high", "Bonfante 2002 §62", "onomastic"),
]


def eval_pairs(min_confidence: str = "medium") -> list[EvalPair]:
    """Return eval pairs filtered by minimum confidence tier."""
    levels = {"low": 0, "medium": 1, "high": 2}
    threshold = levels.get(min_confidence, 1)
    return [p for p in EVAL_PAIRS if levels.get(p.confidence, 0) >= threshold]
