"""
Leiden-convention parser — separating editorial judgement from epigraphic text.

Printed editions of ancient inscriptions annotate their readings with the
Leiden convention. The markup encodes claims *about* the text, not letters
that were ever incised:

- ``[abc]`` — text lost from the support and restored by the editor
  (EpiDoc ``<supplied reason="lost">``).
- ``(abc)`` — an abbreviation on the stone, expanded by the editor
  (EpiDoc ``<ex>``).
- ``[...]``, ``[--]``, or a bare run of three or more dashes — lost text the
  editor declines to restore. Each dot or dash stands for roughly one lost
  letter; ``…`` means even the width is unknown (EpiDoc ``<gap/>``).
- A combining dot below (U+0323), whether the letter arrives precomposed or
  decomposed — the letter is physically present but its reading is doubtful
  (EpiDoc ``<unclear>``).
- ``⸢abc⸣`` (half brackets U+2E22/U+2E23) — damaged but still legible,
  likewise ``<unclear>``.

If these markers leak into a canonical reading they poison everything
downstream: phonetic transcription, Old Italic rendering, tokenization, and
the FTS index all treat the editor's brackets as if they were letters. This
module splits an edition string into the plain reading (markup removed) and a
tuple of EditorialSpan records whose offsets point into that stripped text.

It is deliberately a pure parser — no adapter, no normalizer, no I/O — so the
normalizer can remap the spans through its own folding steps and the EpiDoc
exporter can turn them into TEI elements, without either depending on the
other's internals.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: Combining dot below — the Leiden "reading unclear" diacritic. Kept as an
#: escape: the bare combining character is invisible in source.
_UNDERDOT = "\u0323"
#: Half brackets (⸢ ⸣) — text partially damaged but still legible.
_HALF_OPEN = "\u2e22"
_HALF_CLOSE = "\u2e23"

_OPENERS = {"[": "supplied", "(": "expansion", _HALF_OPEN: "unclear"}
_CLOSERS = {"]": "[", ")": "(", _HALF_CLOSE: _HALF_OPEN}

#: Square-bracket content that denotes a gap rather than a restoration: only
#: dots, dashes, ellipses, and incidental spaces (editions often print
#: ``[- - -]``). ``[]`` has no marker characters at all, so it falls through
#: to the (empty) restoration case rather than becoming a zero-width gap.
_GAP_CONTENT = re.compile(r"[.\-… ]+")


@dataclass(frozen=True)
class EditorialSpan:
    """One editorial claim about a stretch of the stripped text.

    ``start``/``end`` index into the *stripped* text (``LeidenParse.text``),
    never into the raw edition string; ``source`` preserves the original
    marked substring (e.g. ``"[larθ]"``, ``"(an)"``, ``"[..]"``, ``"θ̣"``) so
    the editor's exact notation survives even after the markup is gone.
    Gap spans are zero-width (``start == end``): the lost letters contribute
    nothing to the text, and the position marks where they would have stood.
    """

    kind: str  # "supplied" | "expansion" | "gap" | "unclear"
    start: int
    end: int
    source: str


@dataclass(frozen=True)
class LeidenParse:
    """Result of parsing a Leiden-annotated edition string."""

    text: str
    spans: tuple[EditorialSpan, ...]
    warnings: tuple[str, ...]


def gap_extent(source: str) -> int | None:
    """Estimated width of a gap in letters, or ``None`` when unknown.

    Each dot or dash in the gap notation stands for roughly one lost letter;
    an ellipsis anywhere in the notation means the editor could not even
    estimate the width, so no number is safe to report.
    """
    if "…" in source:
        return None
    return sum(1 for ch in source if ch in ".-")


def _strip_underdot(char: str) -> str | None:
    """Return ``char`` without its combining dot below, or ``None`` if it has none.

    NFC leaves most epigraphically interesting combinations decomposed
    (``θ`` + U+0323 has no precomposed form) but does compose others
    (``d`` + U+0323 → ``ḍ`` U+1E0D), so both shapes must be recognised.
    Decomposing per character keeps the check cheap and leaves every other
    diacritic on the letter untouched.
    """
    decomposed = unicodedata.normalize("NFD", char)
    if _UNDERDOT not in decomposed:
        return None
    return unicodedata.normalize("NFC", decomposed.replace(_UNDERDOT, ""))


def parse_leiden(raw: str) -> LeidenParse:
    """Split a Leiden-annotated string into plain text plus editorial spans.

    A single left-to-right scan with a bracket stack: openers remember where
    they started (in the raw string and in the output), closers decide what
    the group meant. A square-bracket group whose content is only dots and
    dashes is a gap — its placeholder characters are discarded rather than
    kept, because they were never a reading. Nested groups each get their own
    span; mismatched or orphaned brackets are dropped with a warning instead
    of raising, since real corpus data contains plenty of imperfect markup
    and a normalizer that crashes on it is useless.
    """
    out: list[str] = []
    spans: list[EditorialSpan] = []
    warnings: list[str] = []
    # Open bracket groups: (opener char, index into raw, len(out) at open).
    stack: list[tuple[str, int, int]] = []

    i = 0
    n = len(raw)
    while i < n:
        char = raw[i]

        if char in _OPENERS:
            stack.append((char, i, len(out)))
            i += 1
        elif char in _CLOSERS:
            if stack and stack[-1][0] == _CLOSERS[char]:
                opener, raw_start, out_start = stack.pop()
                source = raw[raw_start : i + 1]
                content = raw[raw_start + 1 : i]
                if opener == "[" and content.strip() and _GAP_CONTENT.fullmatch(content):
                    # The dots/dashes were scanned into `out` as ordinary
                    # characters; a gap contributes no text, so drop them.
                    del out[out_start:]
                    spans.append(EditorialSpan("gap", out_start, out_start, source))
                    width = gap_extent(content)
                    if width is None:
                        warnings.append("gap of unknown width")
                    else:
                        warnings.append(f"unrestorable gap of width {width}")
                else:
                    kind = _OPENERS[opener]
                    spans.append(EditorialSpan(kind, out_start, len(out), source))
            else:
                warnings.append("unbalanced editorial bracket")
            i += 1
        elif char == "-":
            run_end = i
            while run_end < n and raw[run_end] == "-":
                run_end += 1
            run = raw[i:run_end]
            if len(run) >= 3 and not stack:
                # A bare run of three-plus dashes is gap notation even without
                # brackets. Inside a bracket group the dashes stay in `out`
                # and the closing bracket classifies the whole group instead.
                spans.append(EditorialSpan("gap", len(out), len(out), run))
                warnings.append(f"unrestorable gap of width {len(run)}")
            else:
                out.extend(run)
            i = run_end
        elif char == _UNDERDOT:
            # Decomposed form: the dot arrives after its base letter.
            if out:
                spans.append(EditorialSpan("unclear", len(out) - 1, len(out), out[-1] + char))
            else:
                warnings.append("stray combining underdot")
            i += 1
        else:
            base = _strip_underdot(char)
            if base is not None:
                start = len(out)
                out.extend(base)
                spans.append(EditorialSpan("unclear", start, len(out), char))
            else:
                out.append(char)
            i += 1

    # Openers never closed: the content stays (it was read, after all) but no
    # claim can be attached to it, so the orphan bracket is simply removed.
    for _ in stack:
        warnings.append("unbalanced editorial bracket")

    spans.sort(key=lambda s: (s.start, s.end))
    return LeidenParse(text="".join(out), spans=tuple(spans), warnings=tuple(warnings))
