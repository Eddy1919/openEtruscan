"""
Converter — convenience functions for direct format conversion.
"""

from __future__ import annotations

from openetruscan.adapter import load_adapter
from openetruscan.normalizer import normalize


def to_old_italic(text: str, language: str = "etruscan") -> str:
    """Convert any transcription to Unicode Old Italic characters."""
    return normalize(text, language=language).old_italic


def to_latin(text: str, language: str = "etruscan") -> str:
    """Convert any transcription to canonical Latin transliteration."""
    return normalize(text, language=language).canonical


def to_phonetic(text: str, language: str = "etruscan") -> str:
    """Convert any transcription to IPA phonetic representation."""
    return normalize(text, language=language).phonetic


def convert(
    text: str,
    target: str = "canonical",
    language: str = "etruscan",
) -> str:
    """
    Convert text to a specified target format.

    Args:
        text: Input in any transcription system.
        target: One of "canonical", "old_italic", "phonetic", "ipa".
        language: Language adapter to use.

    Returns:
        Converted text string.
    """
    result = normalize(text, language=language)

    match target:
        case "canonical" | "latin":
            return result.canonical
        case "old_italic" | "unicode":
            return result.old_italic
        case "phonetic" | "ipa":
            return result.phonetic
        case _:
            msg = f"Unknown target format '{target}'. Use: canonical, old_italic, phonetic"
            raise ValueError(msg)
