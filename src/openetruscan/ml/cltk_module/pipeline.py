"""
Etruscan NLP Pipeline for CLTK.

Provides tokenization, normalization, phonetic transcription,
and prosopographical NER — all wrapping the existing OpenEtruscan
library so that scholars using CLTK get Etruscan support for free.

Standalone usage::

    from openetruscan.cltk_module.pipeline import EtruscanPipeline

    pipe = EtruscanPipeline()
    result = pipe.analyze("mi larθal lecnes")
    for word in result:
        print(word)

CLTK integration (once upstreamed)::

    from cltk import NLP
    nlp = NLP(language="ett")
    doc = nlp.analyze(text="mi larθal lecnes")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openetruscan.core.adapter import load_adapter
from openetruscan.core.normalizer import normalize as _normalize


@dataclass
class EtruscanWord:
    """Token-level analysis result, mirrors cltk.core.data_types.Word."""

    string: str
    """Original surface form."""

    normalized: str
    """Canonical / normalised form."""

    phonetic: str
    """IPA transcription."""

    old_italic: str
    """Old Italic Unicode rendering."""

    ner_tag: str | None = None
    """Named entity tag: PRAENOMEN, GENTILICIUM, PATRONYMIC, or None."""

    ner_detail: dict[str, Any] = field(default_factory=dict)
    """Full NER detail from prosopography (gender, clan, etc.)."""

    def __repr__(self) -> str:
        """Return a string representation of the word including phonetic and NER tags."""
        tag = f" [{self.ner_tag}]" if self.ner_tag else ""
        return f"Word({self.string!r} → /{self.phonetic}/{tag})"


@dataclass
class EtruscanDoc:
    """Document-level analysis result, mirrors cltk.core.data_types.Doc."""

    raw: str
    language: str = "ett"
    words: list[EtruscanWord] = field(default_factory=list)

    @property
    def tokens(self) -> list[str]:
        """Return a list of original raw surface tokens."""
        return [w.string for w in self.words]

    @property
    def normalized_text(self) -> str:
        """Return the full canonicalized text of the document."""
        return " ".join(w.normalized for w in self.words)

    @property
    def phonetic_text(self) -> str:
        """Return the document-level phonetic transcription in IPA."""
        return " ".join(w.phonetic for w in self.words)

    @property
    def entities(self) -> list[EtruscanWord]:
        """Filter and return only tokens identified as named entities."""
        return [w for w in self.words if w.ner_tag]


class EtruscanPipeline:
    """
    Full Etruscan NLP pipeline.

    Processes:
      1. Tokenization (whitespace + inscription-aware)
      2. Normalization (multi-system → canonical)
      3. Phonetic transcription (canonical → IPA)
      4. Old Italic rendering (canonical → Unicode Old Italic)
      5. NER / Prosopography (name detection via onomastic lexicon)
    """

    def __init__(self, language: str = "etruscan") -> None:
        """Initialize the pipeline and build the onomastic search index."""
        self.adapter = load_adapter(language)
        self._language = language
        self._onomastics: dict[str, dict[str, Any]] = {}
        self._build_onomastic_index()

    def _build_onomastic_index(self) -> None:
        """Build a lookup table from the adapter's onomastics data."""
        ono = self.adapter.onomastics
        if ono is None:
            return

        # Index praenomina: known_praenomina is dict[str, list[str]]
        # e.g. {"male": ["larθ", "vel", ...], "female": ["θana", "ramθa", ...]}
        for gender, names in (ono.known_praenomina or {}).items():
            for name in names:
                self._onomastics[name.lower()] = {
                    "tag": "PRAENOMEN",
                    "gender": gender,
                }

        # Index gentilicia: a list of known clan names
        for name in ono.known_gentilicia or []:
            self._onomastics[name.lower()] = {
                "tag": "GENTILICIUM",
                "gender": "unknown",
            }

    def tokenize(self, text: str) -> list[str]:
        """
        Tokenize inscription text.

        Handles whitespace separation and strips editorial marks
        like brackets, question marks, etc.
        """
        import re

        # Remove editorial marks: [, ], (, ), ?, !
        cleaned = re.sub(r"[\[\](){}?!]", "", text)
        # Split on whitespace
        tokens = cleaned.split()
        return [t.strip() for t in tokens if t.strip()]

    def _detect_ner(self, normalized_form: str) -> tuple[str | None, dict]:
        """Detect named entities using the onomastic index."""
        lower = normalized_form.lower()

        # Direct lookup
        if lower in self._onomastics:
            entry = self._onomastics[lower]
            return entry["tag"], entry

        # Gentilicial suffix matching via gender_markers
        ono = self.adapter.onomastics
        if ono:
            for gender, suffixes in (ono.gender_markers or {}).items():
                for suffix in suffixes:
                    if lower.endswith(suffix):
                        return "GENTILICIUM", {
                            "tag": "GENTILICIUM",
                            "suffix": suffix,
                            "gender": gender,
                        }

        # Patronymic detection: genitive -al / -la endings on known names
        if lower.endswith("al") or lower.endswith("la"):
            stem = lower[:-2]
            if stem in self._onomastics:
                return "PATRONYMIC", {
                    "tag": "PATRONYMIC",
                    "stem": stem,
                    "parent": self._onomastics[stem],
                }

        return None, {}

    def analyze(self, text: str) -> EtruscanDoc:
        """
        Run the full pipeline on input text.

        Args:
            text: Raw inscription text in any supported transcription system.

        Returns:
            EtruscanDoc with token-level analysis.
        """
        tokens = self.tokenize(text)
        words: list[EtruscanWord] = []

        for token in tokens:
            # Run the normalizer (returns NormResult)
            result = _normalize(token, language=self._language)

            # NER detection on the canonical form
            ner_tag, ner_detail = self._detect_ner(result.canonical)

            words.append(
                EtruscanWord(
                    string=token,
                    normalized=result.canonical,
                    phonetic=result.phonetic,
                    old_italic=result.old_italic,
                    ner_tag=ner_tag,
                    ner_detail=ner_detail,
                )
            )

        return EtruscanDoc(raw=text, words=words)

    def __repr__(self) -> str:
        """Return pipeline metadata and onomastic coverage."""
        return (
            f"EtruscanPipeline("
            f"language={self._language!r}, "
            f"onomastics={len(self._onomastics)} names)"
        )
