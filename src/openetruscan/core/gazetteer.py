"""
Findspot → Pleiades gazetteer matching.

Pelagios's mandate is "linking the past through places": every inscription whose
findspot we can tie to a Pleiades place URI becomes a unit of linked-data value.
This module is the *matching* core behind that — it takes the messy Latin/modern
findspot strings the corpus actually carries ("Clusii in agro", "Perusiae",
"Volaterris") and proposes the Pleiades place(s) they most likely denote.

It deliberately depends on nothing outside the standard library so it is always
importable and unit-testable. The network-touching parts (downloading the
Pleiades dump) and the human-in-the-loop review live in
``scripts/data_pipeline/`` and consume this module.

The hard part is not the string-similarity metric but the *normalisation*:
Latin places appear in whatever case the source sentence needed (locative
``Clusii``, genitive ``Clusii``, ablative ``Volaterris``, nominative
``Clusium``), often wrapped in a locative phrase (``Clusii in agro``). Stripping
those down to a comparable stem is what makes a plain ``difflib`` ratio work.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

__all__ = [
    "GazetteerPlace",
    "LinkCandidate",
    "FindspotProposal",
    "normalize_place_name",
    "stem_place_name",
    "score_match",
    "propose_links",
]

# Tokens that are scaffolding around a place name, not part of it. Latin
# locative/proximity phrasing ("Clusii in agro", "prope Volaterras", "ager
# Tarquiniensis") plus a few modern-editorial equivalents.
_STOPWORD_TOKENS = frozenset(
    {
        "in",
        "agro",
        "ager",
        "agri",
        "prope",
        "apud",
        "loc",
        "localita",
        "località",
        "near",
        "presso",
        "dintorni",
        "di",
        "da",
        "del",
        "della",
        "the",
        "of",
        "territorio",
        "territory",
    }
)

# Common Latin case endings, longest first so we strip the most specific match.
# These are heuristics, not a morphological analyser — they only need to make
# inflected surface forms of the same toponym collapse onto a shared stem.
# Single-step suffixes only: stripping one of these collapses inflected forms
# onto a shared stem (Clusium/Clusii → "clusi", Perusia/Perusiae → "perusi").
# Multi-vowel endings like "-ii"/"-iae" are deliberately absent — stripping
# them whole over-shortens one inflection but not its sibling, splitting the
# stem (the bug this list was rewritten to avoid).
_LATIN_ENDINGS = (
    "ensibus",
    "ensis",
    "ensi",
    "ibus",
    "arum",
    "orum",
    "ae",
    "is",
    "os",
    "us",
    "um",
    "am",
    "as",
    "es",
    "em",
    "im",
    "o",
    "a",
    "i",
    "e",
)


def _strip_diacritics(text: str) -> str:
    """Fold accented characters to ASCII (è → e), leaving other letters intact."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_place_name(name: str) -> str:
    """
    Normalise a place / findspot string for comparison.

    Lowercases, folds diacritics, drops punctuation, and removes locative
    scaffolding tokens. Does *not* strip Latin endings — see ``stem_place_name``
    for that. Returns a single space-joined string (possibly empty).
    """
    if not name:
        return ""
    folded = _strip_diacritics(name).lower()
    # Replace any non-alphanumeric run with a space so "in-agro" / "(prope)" split.
    cleaned = "".join(ch if ch.isalnum() else " " for ch in folded)
    tokens = [t for t in cleaned.split() if t and t not in _STOPWORD_TOKENS]
    return " ".join(tokens)


def _stem_token(token: str) -> str:
    """Strip one Latin case ending, keeping a minimum stem length of 3."""
    for ending in _LATIN_ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 3:
            return token[: -len(ending)]
    return token


def stem_place_name(name: str) -> str:
    """
    Aggressively normalise to a case-insensitive Latin stem.

    ``Clusium``, ``Clusii``, ``Clusii in agro`` and ``Clusinum`` all collapse
    toward ``clus``-ish stems that match each other under string similarity.
    """
    normalized = normalize_place_name(name)
    if not normalized:
        return ""
    return " ".join(_stem_token(t) for t in normalized.split())


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score_match(findspot: str, place_name: str) -> float:
    """
    Similarity in ``[0.0, 1.0]`` between a findspot string and a gazetteer name.

    Combines two views so neither inflection nor word-order quirks dominate:
    a ``difflib`` ratio on the lightly-normalised forms and another on the
    Latin-stemmed forms; the stronger of the two wins, with an exact
    stem-equality shortcut to 1.0.
    """
    fs_norm, pl_norm = normalize_place_name(findspot), normalize_place_name(place_name)
    if not fs_norm or not pl_norm:
        return 0.0
    if fs_norm == pl_norm:
        return 1.0

    fs_stem, pl_stem = stem_place_name(findspot), stem_place_name(place_name)
    if fs_stem and fs_stem == pl_stem:
        return 1.0

    return max(_ratio(fs_norm, pl_norm), _ratio(fs_stem, pl_stem))


@dataclass(frozen=True)
class GazetteerPlace:
    """A Pleiades place plus the name strings it can be matched against."""

    pleiades_id: str
    title: str
    names: tuple[str, ...] = ()
    lat: float | None = None
    lon: float | None = None

    def all_names(self) -> tuple[str, ...]:
        """Title plus every attested/variant name, de-duplicated, title first."""
        seen: dict[str, None] = {}
        for n in (self.title, *self.names):
            if n and n not in seen:
                seen[n] = None
        return tuple(seen)


@dataclass(frozen=True)
class LinkCandidate:
    """One proposed Pleiades place for a findspot, with its evidence."""

    pleiades_id: str
    title: str
    score: float
    matched_name: str
    uri: str


@dataclass
class FindspotProposal:
    """All candidate Pleiades links for a single findspot string."""

    findspot: str
    candidates: list[LinkCandidate] = field(default_factory=list)

    @property
    def best(self) -> LinkCandidate | None:
        return self.candidates[0] if self.candidates else None


PLEIADES_PLACE_URI = "https://pleiades.stoa.org/places/{}"


def propose_links(
    findspots: list[str],
    places: list[GazetteerPlace],
    *,
    threshold: float = 0.84,
    top_k: int = 3,
) -> list[FindspotProposal]:
    """
    Propose Pleiades links for each findspot.

    For every findspot, scores it against every name of every gazetteer place,
    keeps the best score per place, and returns up to ``top_k`` candidates at or
    above ``threshold``, sorted by score descending. Findspots with no candidate
    above threshold are returned with an empty candidate list so the caller can
    distinguish "reviewed, no match" from "not yet attempted".
    """
    proposals: list[FindspotProposal] = []
    for findspot in findspots:
        per_place: dict[str, LinkCandidate] = {}
        for place in places:
            best_for_place = 0.0
            best_name = ""
            for name in place.all_names():
                s = score_match(findspot, name)
                if s > best_for_place:
                    best_for_place, best_name = s, name
            if best_for_place >= threshold:
                existing = per_place.get(place.pleiades_id)
                if existing is None or best_for_place > existing.score:
                    per_place[place.pleiades_id] = LinkCandidate(
                        pleiades_id=place.pleiades_id,
                        title=place.title,
                        score=round(best_for_place, 4),
                        matched_name=best_name,
                        uri=PLEIADES_PLACE_URI.format(place.pleiades_id),
                    )
        candidates = sorted(per_place.values(), key=lambda c: c.score, reverse=True)[:top_k]
        proposals.append(FindspotProposal(findspot=findspot, candidates=candidates))
    return proposals
