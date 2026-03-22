"""
Adapter loader — reads YAML language definitions.

Each adapter YAML file defines an ancient language's alphabet, equivalence
classes, phonotactics, and onomastic patterns. The engine is language-agnostic;
all language-specific knowledge lives in these YAML files.
"""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class LetterMapping:
    """A single letter in an ancient alphabet."""

    canonical: str
    unicode_char: str
    ipa: str
    variants: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class EquivalenceClass:
    """A group of characters scholars use interchangeably."""

    canonical: str
    members: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Phonotactics:
    """Sound combination constraints for validation."""

    forbidden_word_final: list[str] = field(default_factory=list)
    forbidden_clusters: list[str] = field(default_factory=list)
    max_consonant_cluster: int = 3
    vowels: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class OnomasticRules:
    """Naming formula patterns for a language."""

    formula_order: list[str] = field(default_factory=list)
    genitive_markers: dict[str, list[str]] = field(default_factory=dict)
    gender_markers: dict[str, list[str]] = field(default_factory=dict)
    known_praenomina: dict[str, list[str]] = field(default_factory=dict)
    known_gentilicia: list[str] = field(default_factory=list)


@dataclass
class LanguageAdapter:
    """Complete language definition loaded from a YAML adapter file."""

    language_id: str
    display_name: str
    iso_639_3: str
    script: str
    unicode_range: tuple[int, int]
    direction: str  # "ltr" or "rtl"
    alphabet: dict[str, LetterMapping]
    equivalence_classes: dict[str, EquivalenceClass]
    phonotactics: Phonotactics
    onomastics: OnomasticRules

    # Derived lookup tables (built on load)
    _variant_to_canonical: dict[str, str] = field(default_factory=dict, repr=False)
    _canonical_to_unicode: dict[str, str] = field(default_factory=dict, repr=False)
    _canonical_to_ipa: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Build lookup tables for fast normalization."""
        # Map every known variant → canonical form
        for canonical, mapping in self.alphabet.items():
            self._canonical_to_unicode[canonical] = mapping.unicode_char
            self._canonical_to_ipa[canonical] = mapping.ipa
            for variant in mapping.variants:
                self._variant_to_canonical[variant] = canonical
            # The canonical form also maps to itself
            self._variant_to_canonical[canonical] = canonical

        # Equivalence classes override individual letter variants
        for eq_class in self.equivalence_classes.values():
            for member in eq_class.members:
                self._variant_to_canonical[member] = eq_class.canonical

    def resolve_variant(self, char_or_sequence: str) -> str | None:
        """Resolve a variant spelling to its canonical form, or None if unknown."""
        return self._variant_to_canonical.get(char_or_sequence)

    def to_unicode(self, canonical: str) -> str | None:
        """Convert a canonical character to its Unicode Old Italic codepoint."""
        return self._canonical_to_unicode.get(canonical)

    def to_ipa(self, canonical: str) -> str | None:
        """Convert a canonical character to its IPA representation."""
        return self._canonical_to_ipa.get(canonical)

    def is_in_unicode_range(self, char: str) -> bool:
        """Check if a character falls within this language's Unicode range."""
        cp = ord(char)
        return self.unicode_range[0] <= cp <= self.unicode_range[1]


def _parse_alphabet(raw: dict[str, Any]) -> dict[str, LetterMapping]:
    """Parse the alphabet section of a YAML adapter."""
    result = {}
    for canonical, data in raw.items():
        result[canonical] = LetterMapping(
            canonical=canonical,
            unicode_char=data.get("unicode", ""),
            ipa=data.get("ipa", ""),
            variants=data.get("variants", []),
            notes=data.get("notes", ""),
        )
    return result


def _parse_equivalence_classes(raw: dict[str, Any]) -> dict[str, EquivalenceClass]:
    """Parse equivalence classes from YAML."""
    result = {}
    for name, data in raw.items():
        result[name] = EquivalenceClass(
            canonical=data["canonical"],
            members=data.get("members", []),
        )
    return result


def _parse_phonotactics(raw: dict[str, Any]) -> Phonotactics:
    """Parse phonotactic constraints from YAML."""
    return Phonotactics(
        forbidden_word_final=raw.get("forbidden_word_final", []),
        forbidden_clusters=raw.get("forbidden_clusters", []),
        max_consonant_cluster=raw.get("max_consonant_cluster", 3),
        vowels=raw.get("vowels", []),
        notes=raw.get("notes", ""),
    )


def _parse_onomastics(raw: dict[str, Any]) -> OnomasticRules:
    """Parse onomastic rules from YAML."""
    return OnomasticRules(
        formula_order=raw.get("formula_order", []),
        genitive_markers=raw.get("genitive_markers", {}),
        gender_markers=raw.get("gender_markers", {}),
        known_praenomina=raw.get("known_praenomina", {}),
        known_gentilicia=raw.get("known_gentilicia", []),
    )


def load_adapter(language_id: str) -> LanguageAdapter:
    """
    Load a language adapter by ID.

    Looks for `{language_id}.yaml` in the adapters directory.
    """
    # Try package resources first (installed via pip)
    try:
        adapter_dir = importlib.resources.files("openetruscan.adapters")
        yaml_path = adapter_dir / f"{language_id}.yaml"
        yaml_text = yaml_path.read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError) as err: # Catch the initial error
        # Fallback to filesystem (development mode)
        adapter_dir = Path(__file__).parent / "adapters"
        yaml_file = adapter_dir / f"{language_id}.yaml"
        if not yaml_file.exists():
            msg = (
                f"No adapter found for language '{language_id}'. "
                f"Looked in: {adapter_dir}\n"
                f"Available adapters: {list_available_adapters()}"
            )
            raise FileNotFoundError(msg) from err # Re-raise with 'from err'
        yaml_text = yaml_file.read_text(encoding="utf-8")

    raw = yaml.safe_load(yaml_text)

    unicode_range = raw.get("unicode_range", [0, 0])

    return LanguageAdapter(
        language_id=raw["language_id"],
        display_name=raw.get("display_name", raw["language_id"].title()),
        iso_639_3=raw.get("iso_639_3", ""),
        script=raw.get("script", ""),
        unicode_range=(unicode_range[0], unicode_range[1]),
        direction=raw.get("direction", "ltr"),
        alphabet=_parse_alphabet(raw.get("alphabet", {})),
        equivalence_classes=_parse_equivalence_classes(
            raw.get("equivalence_classes", {})
        ),
        phonotactics=_parse_phonotactics(raw.get("phonotactics", {})),
        onomastics=_parse_onomastics(raw.get("onomastics", {})),
    )


def list_available_adapters() -> list[str]:
    """List all available language adapter IDs."""
    try:
        adapter_dir = importlib.resources.files("openetruscan.adapters")
        # importlib.resources returns Traversable objects
        return sorted(
            p.name.removesuffix(".yaml")
            for p in adapter_dir.iterdir()
            if hasattr(p, "name") and p.name.endswith(".yaml")
        )
    except (TypeError, FileNotFoundError):
        adapter_dir = Path(__file__).parent / "adapters"
        return sorted(p.stem for p in adapter_dir.glob("*.yaml"))
