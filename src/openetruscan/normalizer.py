"""
Normalizer engine — the core of OpenEtruscan.

Takes text in ANY transcription system and produces a standardized NormResult
with canonical, phonetic, and Unicode Old Italic representations.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from openetruscan.adapter import LanguageAdapter, load_adapter


@dataclass(frozen=True)
class NormResult:
    """Result of normalizing an ancient text."""

    canonical: str
    phonetic: str
    old_italic: str
    source_system: str
    tokens: list[str] = field(default_factory=list)
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "canonical": self.canonical,
            "phonetic": self.phonetic,
            "old_italic": self.old_italic,
            "source_system": self.source_system,
            "tokens": self.tokens,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }


def detect_source_system(text: str, adapter: LanguageAdapter) -> str:
    """
    Auto-detect which transcription system the input uses.

    Heuristics:
    - Contains Unicode characters in the language's range → "unicode"
    - Contains special phonetic symbols (θ, φ, χ, ś) → "philological"
    - All ASCII uppercase → "cie"
    - Contains backslash commands → "latex"
    - Otherwise → "web_safe"
    """
    # Check for Old Italic Unicode characters
    for char in text:
        if adapter.is_in_unicode_range(char):
            return "unicode"

    # Check for philological symbols
    philological_chars = {"θ", "φ", "χ", "ś", "Θ", "Φ", "Χ", "Ś"}
    if any(c in philological_chars for c in text):
        return "philological"

    # Check for LaTeX commands
    if "\\" in text and any(cmd in text for cmd in ["\\d{", "\\theta", "\\phi"]):
        return "latex"

    # All uppercase ASCII → CIE standard
    alpha_chars = [c for c in text if c.isalpha()]
    if alpha_chars and all(c.isupper() for c in alpha_chars):
        return "cie"

    return "web_safe"


def _preprocess_latex(text: str) -> str:
    """Convert LaTeX commands to their philological equivalents."""
    replacements = {
        "\\d{h}": "θ",
        "\\theta": "θ",
        "\\d{p}": "φ",
        "\\phi": "φ",
        "\\d{k}": "χ",
        "\\chi": "χ",
        "\\'{s}": "ś",
        "\\v{s}": "ś",
    }
    for latex_cmd, replacement in replacements.items():
        text = text.replace(latex_cmd, replacement)
    return text


def _unicode_to_canonical(text: str, adapter: LanguageAdapter) -> str:
    """Convert Unicode Old Italic characters to canonical Latin transliteration."""
    result = []
    for char in text:
        if adapter.is_in_unicode_range(char):
            # Find which canonical letter maps to this Unicode char
            found = False
            for canonical, mapping in adapter.alphabet.items():
                if mapping.unicode_char == char:
                    result.append(canonical)
                    found = True
                    break
            if not found:
                result.append(char)  # Unknown, pass through
        else:
            result.append(char)
    return "".join(result)


def _fold_to_canonical(text: str, adapter: LanguageAdapter) -> tuple[str, list[str]]:
    """
    Fold variant spellings to canonical forms.

    Tries longest match first (e.g., "th" before "t" + "h").
    Returns (canonical_text, warnings).
    """
    warnings: list[str] = []
    result: list[str] = []
    i = 0

    while i < len(text):
        matched = False

        # Try longest match first (up to 3 characters for digraphs like "th")
        for length in range(min(3, len(text) - i), 0, -1):
            chunk = text[i : i + length]
            resolved = adapter.resolve_variant(chunk)
            if resolved is not None:
                result.append(resolved)
                i += length
                matched = True
                break

        if not matched:
            char = text[i]
            if char.isalpha():
                # Try case-insensitive
                resolved = adapter.resolve_variant(char.lower())
                if resolved is not None:
                    result.append(resolved)
                else:
                    warnings.append(f"Unknown character '{char}' at position {i}")
                    result.append(char.lower())
            elif char in (" ", ".", ",", ";", ":", "-", "'", "[", "]", "(", ")", "\n", "\t"):
                # Standard whitespace and punctuation — pass through silently
                result.append(char)
            else:
                # Non-standard character — flag it
                warnings.append(f"Unknown character '{char}' at position {i}")
                result.append(char)
            i += 1

    return "".join(result), warnings


def _to_phonetic(canonical: str, adapter: LanguageAdapter) -> str:
    """Convert canonical text to IPA phonetic representation."""
    parts: list[str] = []
    for char in canonical:
        ipa = adapter.to_ipa(char)
        if ipa is not None:
            parts.append(ipa)
        elif char == " ":
            parts.append(" ")
        elif not char.isalpha():
            parts.append(char)
        else:
            parts.append(char)
    return "/" + ".".join("".join(parts).split()) + "/"


def _to_old_italic(canonical: str, adapter: LanguageAdapter) -> str:
    """Convert canonical text to Unicode Old Italic characters."""
    result: list[str] = []
    for char in canonical:
        unicode_char = adapter.to_unicode(char)
        if unicode_char is not None:
            result.append(unicode_char)
        elif char == " ":
            result.append(" ")
        else:
            result.append(char)
    return "".join(result)


def _tokenize(canonical: str) -> list[str]:
    """Split canonical text into tokens (words)."""
    return [t for t in re.split(r"\s+", canonical.strip()) if t]


def _validate_phonotactics(
    canonical: str, adapter: LanguageAdapter
) -> list[str]:
    """Check canonical text against phonotactic constraints."""
    warnings: list[str] = []
    words = _tokenize(canonical)
    rules = adapter.phonotactics

    for word in words:
        # Check forbidden word-final characters
        for forbidden in rules.forbidden_word_final:
            if word.endswith(forbidden):
                warnings.append(
                    f"Word '{word}' ends with '{forbidden}' "
                    f"(forbidden in {adapter.display_name})"
                )

        # Check forbidden clusters
        for cluster in rules.forbidden_clusters:
            if cluster in word:
                warnings.append(
                    f"Word '{word}' contains cluster '{cluster}' "
                    f"(forbidden in {adapter.display_name})"
                )

    return warnings


def normalize(
    text: str,
    language: str = "etruscan",
    source_system: str = "auto",
) -> NormResult:
    """
    Normalize ancient text from any transcription system to canonical form.

    Args:
        text: Input text in any transcription system.
        language: Language adapter to use (default: "etruscan").
        source_system: Force a specific source system, or "auto" to detect.

    Returns:
        NormResult with canonical, phonetic, old_italic, and metadata.
    """
    adapter = load_adapter(language)

    # Step 1: Unicode NFC normalization
    text = unicodedata.normalize("NFC", text.strip())

    # Step 2: Detect source system
    if source_system == "auto":
        source_system = detect_source_system(text, adapter)

    # Step 3: Preprocess based on source system
    if source_system == "latex":
        text = _preprocess_latex(text)
    elif source_system == "unicode":
        text = _unicode_to_canonical(text, adapter)

    # Step 4: Fold variants to canonical
    canonical, fold_warnings = _fold_to_canonical(text, adapter)

    # Step 5: Validate phonotactics
    phono_warnings = _validate_phonotactics(canonical, adapter)

    # Step 6: Generate representations
    phonetic = _to_phonetic(canonical, adapter)
    old_italic = _to_old_italic(canonical, adapter)
    tokens = _tokenize(canonical)

    # Step 7: Calculate confidence
    all_warnings = fold_warnings + phono_warnings
    confidence = max(0.0, 1.0 - (len(all_warnings) * 0.15))

    return NormResult(
        canonical=canonical,
        phonetic=phonetic,
        old_italic=old_italic,
        source_system=source_system,
        tokens=tokens,
        confidence=confidence,
        warnings=all_warnings,
    )
