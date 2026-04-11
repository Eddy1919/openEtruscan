"""
Normalizer engine — the core of OpenEtruscan.

Takes text in ANY transcription system and produces a standardized NormResult
with canonical, phonetic, and Unicode Old Italic representations.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from openetruscan.core.adapter import LanguageAdapter, load_adapter


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
    # 1. Check for Old Italic Unicode characters (U+10300–U+1032F)
    # The adapter defines the bounds for a specific script.
    for char in text:
        if adapter.is_in_unicode_range(char):
            return "unicode"

    # 2. Check for philological symbols commonly used in scholarship (e.g. CIE, TLE)
    philological_chars = {"θ", "φ", "χ", "ś", "Θ", "Φ", "Χ", "Ś"}
    if any(c in philological_chars for c in text):
        return "philological"

    # 3. Check for LaTeX commands if the input is exported from a digital edition
    if "\\" in text and any(cmd in text for cmd in ["\\d{", "\\theta", "\\phi"]):
        return "latex"

    # 4. Corpus Isitituto di Studi Etruschi (CIE) standard uses uppercase ASCII
    # with specific character markers.
    alpha_chars = [c for c in text if c.isalpha()]
    if alpha_chars and all(c.isupper() for c in alpha_chars):
        return "cie"

    # Match common CIE character combinations (e.g. TH for Theta)
    cie_patterns = [r"TH", r"PH", r"CH", r"SH", r"Ś", r"ŚŚ"]
    if any(re.search(p, text) for p in cie_patterns):
        return "cie"

    # 5. Default to web_safe if no specific markers are found
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
        # NOTE: The "s2" web-safe variant for ś depends on this longest-match
        # approach.  If "s2" is ever removed from an adapter's variant list,
        # the digit "2" alone will emit an "Unknown character" warning.
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
    """
    Convert canonical text to Unicode Old Italic characters (U+10300–U+1032F).
    Ensures precise mapping according to Unicode Italic specifications.
    """
    result: list[str] = []
    for char in canonical:
        unicode_char = adapter.to_unicode(char)
        if unicode_char is not None:
            # Validate against Old Italic block reach
            codepoint = ord(unicode_char)
            if 0x10300 <= codepoint <= 0x1032F:
                result.append(unicode_char)
            else:
                # Warning: mapped char is outside the standard Old Italic block
                result.append(char)
        elif char == " ":
            result.append(" ")
        else:
            result.append(char)
    return "".join(result)


def _tokenize(canonical: str) -> list[str]:
    """Split canonical text into tokens (words)."""
    return [t for t in re.split(r"\s+", canonical.strip()) if t]


def _validate_phonotactics(canonical: str, adapter: LanguageAdapter) -> list[str]:
    """Check canonical text against phonotactic constraints."""
    warnings: list[str] = []
    words = _tokenize(canonical)
    rules = adapter.phonotactics

    for word in words:
        # Check forbidden word-final characters
        for forbidden in rules.forbidden_word_final:
            if word.endswith(forbidden):
                warnings.append(
                    f"Word '{word}' ends with '{forbidden}' (forbidden in {adapter.display_name})"
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
    # --- NORMALIZATION PIPELINE ---

    # 1. Load the language-specific conversion rules
    adapter = load_adapter(language)

    # 2. Clean input and perform Unicode NFC normalization for safety
    text = unicodedata.normalize("NFC", text.strip())

    # 3. Detect the source transcription system
    if source_system == "auto":
        source_system = detect_source_system(text, adapter)

    # 4. Preliminary conversion steps for non-Latin systems
    if source_system == "latex":
        # Handle backslash commands
        text = _preprocess_latex(text)
    elif source_system == "unicode":
        # Map Old Italic glyphs back to Latin transliteration
        text = _unicode_to_canonical(text, adapter)

    # 5. The Core Step: Map all variants to the canonical phonological system
    # Longest-match strategy ensures digraphs like 'th' are caught.
    canonical, fold_warnings = _fold_to_canonical(text, adapter)

    # 6. Linguistic validation: Check if produced text follows epigraphic rules
    phono_warnings = _validate_phonotactics(canonical, adapter)

    # 7. Generate derivative representations for FE and Research
    # - Phonetic (IPA) for accessibility/edu
    # - Old Italic (Unicode) for visual rendering
    # - Tokens (List) for search indexing
    phonetic = _to_phonetic(canonical, adapter)
    old_italic = _to_old_italic(canonical, adapter)
    tokens = _tokenize(canonical)

    # 8. Score the conversion — higher warnings lower the confidence
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
