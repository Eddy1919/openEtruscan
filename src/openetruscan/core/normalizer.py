"""
Normalizer engine — the core of OpenEtruscan.

Takes text in ANY transcription system and produces a standardized NormResult
with canonical, phonetic, and Unicode Old Italic representations.
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field

from openetruscan.core.adapter import LanguageAdapter, load_adapter
from openetruscan.core.leiden import EditorialSpan, parse_leiden


@dataclass(frozen=True)
class NormResult:
    """Result of normalizing an ancient text.

    ``apparatus`` carries the Leiden editorial spans (restorations,
    expansions, gaps, unclear readings) parsed out of the input; the markup
    itself never reaches canonical/phonetic/old_italic/tokens. Span offsets
    refer to the *canonical* string, so ``canonical[span.start:span.end]`` is
    exactly the stretch the editor annotated.
    """

    canonical: str
    phonetic: str
    old_italic: str
    source_system: str
    tokens: list[str] = field(default_factory=list)
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)
    apparatus: tuple[EditorialSpan, ...] = ()

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
            "apparatus": [
                {"kind": s.kind, "start": s.start, "end": s.end, "source": s.source}
                for s in self.apparatus
            ],
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


def _preprocess_latex(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Convert LaTeX commands to their philological equivalents.

    Scans left-to-right instead of chaining str.replace so that every output
    character can be traced to the input range that produced it — ``\\theta``
    is six characters, ``θ`` is one, and editorial span offsets must survive
    that shrinkage. The command set is prefix-disjoint, so the scan produces
    exactly the same text the old sequential replacement did.

    Returns (converted_text, chunks) where chunks[j] is the (start, end)
    input range behind output character j.
    """
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
    result: list[str] = []
    chunks: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        for latex_cmd, replacement in replacements.items():
            if text.startswith(latex_cmd, i):
                result.append(replacement)
                chunks.extend([(i, i + len(latex_cmd))] * len(replacement))
                i += len(latex_cmd)
                break
        else:
            result.append(text[i])
            chunks.append((i, i + 1))
            i += 1
    return "".join(result), chunks


def _unicode_to_canonical(text: str, adapter: LanguageAdapter) -> tuple[str, list[tuple[int, int]]]:
    """Convert Unicode Old Italic characters to canonical Latin transliteration.

    Returns (converted_text, chunks) where chunks[j] is the (start, end)
    input range behind output character j, so editorial spans can be remapped
    if a glyph transliterates to more than one character.
    """
    result: list[str] = []
    chunks: list[tuple[int, int]] = []
    for i, char in enumerate(text):
        if adapter.is_in_unicode_range(char):
            # Find which canonical letter maps to this Unicode char
            found = False
            for canonical, mapping in adapter.alphabet.items():
                if mapping.unicode_char == char:
                    result.append(canonical)
                    chunks.extend([(i, i + 1)] * len(canonical))
                    found = True
                    break
            if not found:
                result.append(char)  # Unknown, pass through
                chunks.append((i, i + 1))
        else:
            result.append(char)
            chunks.append((i, i + 1))
    return "".join(result), chunks


def _fold_to_canonical(
    text: str, adapter: LanguageAdapter
) -> tuple[str, list[str], list[tuple[int, int]]]:
    """
    Fold variant spellings to canonical forms.

    Tries longest match first (e.g., "th" before "t" + "h").
    Returns (canonical_text, warnings, chunks) where chunks[j] is the
    (start, end) input range consumed for output character j — a digraph like
    "TH" collapses two input characters into one θ, and editorial span
    offsets have to be remapped through exactly that collapse.
    """
    warnings: list[str] = []
    result: list[str] = []
    chunks: list[tuple[int, int]] = []
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
                chunks.extend([(i, i + length)] * len(resolved))
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
                    chunks.extend([(i, i + 1)] * len(resolved))
                else:
                    warnings.append(f"Unknown character '{char}' at position {i}")
                    lowered = char.lower()
                    result.append(lowered)
                    chunks.extend([(i, i + 1)] * len(lowered))
            elif char in (" ", ".", ",", ";", ":", "-", "'", "\n", "\t"):
                # Standard whitespace and punctuation — pass through silently.
                # Leiden editorial markup ([], (), underdots, half brackets)
                # never reaches this point: parse_leiden strips it up front.
                result.append(char)
                chunks.append((i, i + 1))
            else:
                # Non-standard character — flag it
                warnings.append(f"Unknown character '{char}' at position {i}")
                result.append(char)
                chunks.append((i, i + 1))
            i += 1

    return "".join(result), warnings, chunks


def _remap_spans(
    spans: Sequence[EditorialSpan],
    chunks: Sequence[tuple[int, int]],
    warnings: list[str],
) -> list[EditorialSpan]:
    """Translate editorial span offsets through a length-changing transform.

    ``chunks[j]`` is the input range that produced output character j; chunk
    ranges are contiguous and non-decreasing because every transform consumes
    its input left-to-right. A span [s, e) over the input therefore maps to
    the output characters whose chunks overlap it. When a boundary lands in
    the middle of a chunk — a span edge inside a digraph like "TH" — the span
    is snapped outward (start floored, end ceiled): claiming slightly too
    much for the editor is safer than silently splitting a letter, and the
    widening is reported as a warning.

    Zero-width spans (gaps) keep their position: the first output character
    whose chunk starts at or after the gap.
    """
    if not spans:
        return []
    starts = [c[0] for c in chunks]
    ends = [c[1] for c in chunks]
    remapped: list[EditorialSpan] = []
    for span in spans:
        if span.start == span.end:
            pos = bisect_left(starts, span.start)
            remapped.append(EditorialSpan(span.kind, pos, pos, span.source))
            continue
        new_start = bisect_right(ends, span.start)
        new_end = bisect_left(starts, span.end)
        if new_end < new_start:
            new_end = new_start
        if new_start < new_end and (starts[new_start] < span.start or ends[new_end - 1] > span.end):
            warnings.append("span boundary crossed a digraph; widened")
        remapped.append(EditorialSpan(span.kind, new_start, new_end, span.source))
    return remapped


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

    # 2b. Strip Leiden editorial markup before anything else looks at the
    # text. Brackets, underdots, and gap notation are the editor's claims
    # about the inscription, not letters — detection must not mistake them
    # for transcription-system markers, and folding must never emit them.
    # The spans survive as the apparatus, remapped through every subsequent
    # length-changing transform so their offsets track the canonical string.
    leiden = parse_leiden(text)
    text = leiden.text
    spans = list(leiden.spans)
    leiden_warnings = list(leiden.warnings)
    remap_warnings: list[str] = []

    # 3. Detect the source transcription system
    if source_system == "auto":
        source_system = detect_source_system(text, adapter)

    # 4. Preliminary conversion steps for non-Latin systems
    if source_system == "latex":
        # Handle backslash commands
        text, chunks = _preprocess_latex(text)
        spans = _remap_spans(spans, chunks, remap_warnings)
    elif source_system == "unicode":
        # Map Old Italic glyphs back to Latin transliteration
        text, chunks = _unicode_to_canonical(text, adapter)
        spans = _remap_spans(spans, chunks, remap_warnings)

    # 5. The Core Step: Map all variants to the canonical phonological system
    # Longest-match strategy ensures digraphs like 'th' are caught.
    canonical, fold_warnings, fold_chunks = _fold_to_canonical(text, adapter)
    spans = _remap_spans(spans, fold_chunks, remap_warnings)

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
    all_warnings = leiden_warnings + fold_warnings + remap_warnings + phono_warnings
    confidence = max(0.0, 1.0 - (len(all_warnings) * 0.15))

    return NormResult(
        canonical=canonical,
        phonetic=phonetic,
        old_italic=old_italic,
        source_system=source_system,
        tokens=tokens,
        confidence=confidence,
        warnings=all_warnings,
        apparatus=tuple(spans),
    )
