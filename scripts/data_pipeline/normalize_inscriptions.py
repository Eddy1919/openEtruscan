#!/usr/bin/env python3
"""
Deterministic normalization for the Etruscan inscriptions corpus.

Produces a `canonical_clean` column (without overwriting existing
`canonical`) and regenerates `old_italic` from the clean column when
the row is fully convertible. Each row is also tagged with
`data_quality` ∈ {clean, needs_review, ocr_failed}.

Why this exists
---------------
The prod dump audit (6,633 rows, /tmp/prod_dump/prod-inscriptions.sql)
shows three things mixed together in the `canonical` column:

  1. Real philological signal we MUST keep:
       - Greek-block θ χ σ φ ξ ς (and their capitals) — standard
         Etruscan transliteration (Bonfante 2002, Wallace 2008,
         Pallottino 1968).
       - Latin sibilants ś Ś š ń and IPA dots ṛ ṭ ḥ ṿ ṣ ṇ ẹ.
       - Old Italic glyphs already in U+10300..U+1032F.
       - Word separators · • and the structural punctuation [] () . , : ; | -

  2. Mirror-glyph OCR corruption (~1.4k chars across ~250 rows):
       - Cyrillic Э И Я О А Ѵ З Ч  (≈494 chars)  ← retrograde N R E …
       - Latin-Ext-B Ǝ Ƨ Ɔ Ʀ Ɐ ǝ   (≈619 chars)
       - Number Forms ↄ Ↄ           (≈100 chars)
       - Math ∃ ∂                   (≈19 chars)
       - Stragglers ê þ ð ° Æ Ç     (mostly typos / ASCII-θ stand-ins)

  3. Unrecoverable OCR garbage (~140 rows):
       - Digits or `+` embedded in transliteration ("IAN8VJV1 ANV+:")
         — these are 1↔I, 8↔B, 9↔R substitutions from a broken
         OCR pass that we cannot back out deterministically.

The deterministic mapping below recovers (2). Rows still failing the
character contract after normalization are flagged needs_review;
rows containing digit-substitution junk are flagged ocr_failed.

Usage
-----
  # Dry-run report against the local extract (no writes):
  python scripts/data_pipeline/normalize_inscriptions.py

  # Emit normalized JSONL (one row per line, with extra fields):
  python scripts/data_pipeline/normalize_inscriptions.py \\
      --input  /tmp/etruscan-prod-rawtext-v1.jsonl \\
      --output /tmp/etruscan-prod-rawtext-v1.normalized.jsonl

  # Emit a SQL UPDATE script (no DB connection — review before applying):
  python scripts/data_pipeline/normalize_inscriptions.py --emit-sql \\
      > /tmp/normalize.sql

This script does NOT connect to any database. It reads JSONL and
writes JSONL or SQL. The user reviews the diff and applies the SQL
manually via psql/SSH tunnel.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

# Cyrillic mirror-glyphs left in the corpus by an OCR pass that read
# retrograde Etruscan as left-to-right and grabbed visually-similar
# code points from the Cyrillic block. Mapping is to the *intended*
# Latin letter, not the rotated form.
CYRILLIC_MAP: dict[str, str] = {
    "Э": "e",   # mirror E
    "И": "n",   # mirror N (И is N's mirror in Cyrillic)
    "Я": "r",   # mirror R
    "О": "o",   # lookalike O
    "А": "a",   # lookalike A
    "Т": "t",
    "Е": "e",
    "Ч": "kh",  # phonetic — corresponds to χ in Etruscan transliteration
    "З": "z",
    "Ј": "i",
    "Ѵ": "v",   # archaic Cyrillic izhitsa = Latin V
}

# Latin-Extended-B / IPA Extensions mirror-glyphs. Same root cause as
# the Cyrillic set above. Ǝ Ƨ Ɔ Ʀ are explicit "reversed letter"
# code points — they were never meant to appear in Etruscan
# transliteration.
LATIN_EXT_MIRROR_MAP: dict[str, str] = {
    "Ǝ": "e",
    "ǝ": "e",
    "Ɔ": "c",
    "Ƨ": "s",
    "Ʀ": "r",
    "Ɐ": "a",   # turned A
    "Ɯ": "m",
    "Ɛ": "e",   # open-E, occasionally used as θ stand-in but treated as e here
}

# Roman Numerals / Number Forms block — Ↄ ↄ are "reversed C", another
# OCR artifact on retrograde inscriptions.
NUMBER_FORMS_MAP: dict[str, str] = {
    "Ↄ": "c",
    "ↄ": "c",
    "⅃": "l",
}

# Math block — ∃ "there exists" is a perfect mirror E and shows up in
# OCR output for the same retrograde reason.
MATH_MAP: dict[str, str] = {
    "∃": "e",
    "∂": "",   # partial-derivative is noise; drop it
}

# Latin-1 / Latin-Extended-A stragglers. The two big ones:
#   ê (44×) — mojibake of e from a wrong-encoding pass
#   þ (5×)  — the corpus uses þ as an ASCII stand-in for θ in a
#             handful of records (e.g. "lþ: arntni : creice"). Map
#             back to θ to keep philological consistency.
LATIN1_STRAGGLERS_MAP: dict[str, str] = {
    "ê": "e",
    "þ": "θ",
    "Þ": "Θ",
    "ð": "",   # rare and inconsistent, drop
    "Ð": "",
    "°": "",
    "Æ": "ae",
    "Ç": "c",
    "Å": "a",
    "υ": "u",  # Greek upsilon used as mojibake for u in CIE 2709-2711 etc.
    "ϑ": "θ",  # curly-theta variant — same phoneme as θ
    "ț": "t",  # Romanian t-cedilla — single occurrence (CIE 3281), a typo
}

# Combine all corruption maps into one for a single-pass translate().
CORRUPTION_MAP: dict[str, str] = {
    **CYRILLIC_MAP,
    **LATIN_EXT_MIRROR_MAP,
    **NUMBER_FORMS_MAP,
    **MATH_MAP,
    **LATIN1_STRAGGLERS_MAP,
}

# Latin → Old Italic glyph mapping. Standard correspondence used
# throughout Etruscan epigraphy (Bonfante 2002, Wallace 2008).
# Values are U+10300..U+1031F. Greek-block θ φ χ σ map to their
# direct Old Italic counterparts; ś / σ both render as 𐌑 (san),
# the sibilant variant distinct from 𐌔 (sigma).
LATIN_TO_OLD_ITALIC: dict[str, str] = {
    "a": "𐌀", "b": "𐌁", "c": "𐌂", "d": "𐌃", "e": "𐌄",
    "v": "𐌅", "z": "𐌆", "h": "𐌇", "θ": "𐌈", "i": "𐌉",
    "k": "𐌊", "l": "𐌋", "m": "𐌌", "n": "𐌍", "o": "𐌏",
    "p": "𐌐", "ś": "𐌑", "q": "𐌒", "r": "𐌓", "s": "𐌔",
    "t": "𐌕", "u": "𐌖", "x": "𐌗", "φ": "𐌘", "χ": "𐌙",
    "f": "𐌚",
    # Greek sigma (any case) and final sigma render as san — both are
    # used in the Pallottino-style transliteration for the SAN sibilant.
    "σ": "𐌑", "ς": "𐌑",
    # Diacritical sibilants and IPA dot-below transcriptions: render
    # as the corresponding bare-letter glyph (the diacritic is a
    # phonetic marker that has no Old Italic correspondent).
    "š": "𐌔", "ń": "𐌍",
    "ṛ": "𐌓", "ṭ": "𐌕", "ḥ": "𐌇", "ṿ": "𐌅",
    "ṣ": "𐌔", "ṇ": "𐌍", "ẹ": "𐌄",
    # Capitals fold to their lowercase glyph (Old Italic has no case).
    "Θ": "𐌈", "Φ": "𐌘", "Χ": "𐌙", "Ś": "𐌑",
}

# Whitelist: characters allowed in `canonical_clean`. Anything outside
# this set after normalization means the row needs human review.
ALLOWED_LETTERS = (
    "abcdefghiklmnopqrstuvxyz"   # Latin (Etruscan never uses j/w)
    "θχσφξς"                     # Greek phonemes (lower)
    "ΘΧΣΦΞ"                      # Greek phonemes (upper, used for proper names)
    "śŚšńṛṭḥṿṣṇẹ"                # diacritical sibilants + IPA
)
ALLOWED_PUNCT = " .,:;|·•[]()<>{}-_'\"?!/…—"
ALLOWED_DIGITS = ""  # digits in the body are OCR junk; only allowed in IDs

ALLOWED_CHARSET = (
    set(ALLOWED_LETTERS)
    | set(ALLOWED_LETTERS.upper())
    | set(ALLOWED_PUNCT)
    | set(ALLOWED_DIGITS)
)
# Old Italic glyphs are also allowed if a row mixes scripts.
ALLOWED_CHARSET |= {chr(cp) for cp in range(0x10300, 0x10330)}

# OCR-failure heuristic: digits or `+` inside the transliteration body
# are diagnostic of the broken-OCR rows like "IAN8VJV1 ANV+: VEA".
OCR_GARBAGE_RE = re.compile(r"[0-9]|\+")

# Roman numeral characters. A multi-letter ALL-CAPS Latin token whose
# letters are all in this set is treated as a numeral (e.g. "XXIX",
# "CVI" in "avils : CVI murce") rather than Latin orthography.
ROMAN_NUMERAL_CHARS = frozenset("IVXLCDM")

# Editorial-markup characters that distinguish a fragmented token from
# an attested one: Leiden brackets, expansions, uncertainty markers.
EDITORIAL_MARKERS = frozenset("[]<>{}()?!")

# Tokenizer for word-level splits. Etruscan word separators in this
# corpus are space, ·, •, |, : (and sometimes ;).
WORD_SPLIT_RE = re.compile(r"[\s·•|:;]+")


# ---------------------------------------------------------------------------
# Core normalization
# ---------------------------------------------------------------------------

@dataclass
class NormalizedRow:
    id: str
    raw_text: str
    canonical: str                # original, unchanged
    canonical_clean: str          # post-mapping
    old_italic_v2: str | None     # regenerated from canonical_clean, or None
    canonical_words_only: str     # intact tokens only, space-joined
    intact_token_ratio: float     # intact_tokens / total_tokens, 0..1
    data_quality: str             # clean | needs_review | ocr_failed
    residual_invalid: list[str]   # chars that failed the contract

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "raw_text": self.raw_text,
            "canonical": self.canonical,
            "canonical_clean": self.canonical_clean,
            "old_italic_v2": self.old_italic_v2,
            "canonical_words_only": self.canonical_words_only,
            "intact_token_ratio": round(self.intact_token_ratio, 3),
            "data_quality": self.data_quality,
            "residual_invalid": self.residual_invalid,
        }, ensure_ascii=False)


def apply_corruption_map(s: str) -> str:
    """Apply the deterministic corruption map in a single pass."""
    out: list[str] = []
    for ch in s:
        if ch in CORRUPTION_MAP:
            out.append(CORRUPTION_MAP[ch])
        else:
            out.append(ch)
    return "".join(out)


def is_intact_token(t: str) -> bool:
    """
    A token is 'intact' if it is an attested whole word — no editorial
    brackets/braces/parens, no uncertainty markers, no lacuna dashes.

    A token like `[lar]θ` or `arnθ[ial]` is partially restored by an
    editor; a token like `v--lthurthelen----` straddles a lacuna. Both
    are unsuitable for word-embedding training, where the model should
    learn from real complete forms.
    """
    if not t:
        return False
    if any(ch in EDITORIAL_MARKERS for ch in t):
        return False
    if "-" in t:
        return False
    return True


def words_only_view(canonical: str) -> tuple[str, float]:
    """
    Extract intact tokens and report what fraction of the row's tokens
    were intact. The string is single-space-joined; the ratio is for
    downstream filtering (e.g. drop rows where intact_token_ratio < 0.5).
    """
    tokens = [t for t in WORD_SPLIT_RE.split(canonical) if t]
    if not tokens:
        return "", 0.0
    intact = [t for t in tokens if is_intact_token(t)]
    return " ".join(intact), len(intact) / len(tokens)


def has_latin_orthography(s: str) -> bool:
    """
    True if the canonical contains Roman/scholarly-Latin orthography
    rather than Etruscan transliteration. A multi-letter all-uppercase
    Latin token (HASTI, PVLFENNIA, ZANIDIA) is the diagnostic.

    Pure Roman numerals (XXIX, CVI) are explicitly NOT Latin orthography
    here — they appear in legitimate late-Etruscan funerary formulae
    like "avils : CVI murce" (Ta 1.107) and should still get an Old
    Italic regeneration.

    Why this guard exists: when the canonical is Latin orthography,
    letter-by-letter remapping into Old Italic produces a glyph stream
    that does not represent any inscription that ever existed
    (e.g. PVLFENNIA → 𐌐𐌅𐌋𐌚𐌄𐌍𐌍𐌉𐌀). Better to abstain.
    """
    for token in re.findall(r"[A-Za-z]+", s):
        if len(token) < 2:
            continue
        upper = sum(1 for c in token if c.isupper())
        # All-caps multi-letter token (HASTI, PVLFENNIA, ZANIDIA) — but
        # not Roman numerals (XXIX, CVI).
        if upper == len(token):
            if not all(c in ROMAN_NUMERAL_CHARS for c in token):
                return True
        # Mostly-uppercase token of length ≥4. Catches partially-recovered
        # retrograde garbage like MVOVsIAO or OeAS (CIE 2261), where the
        # Cyrillic / Latin-Ext-B mapping turned a few mirror-glyphs into
        # lowercase but most of the row is still all-caps OCR noise.
        elif len(token) >= 4 and upper / len(token) >= 0.75:
            return True
        # Title-case Latin proper noun (Pulfennius, Calamus). True
        # Etruscan transliteration is overwhelmingly lowercase; an
        # initial capital + lowercase tail of length ≥4 is a Roman
        # name in a bilingual or Latin row (CIE 2613 etc.).
        elif re.fullmatch(r"[A-Z][a-z]+", token) and len(token) >= 4:
            return True
    return False


def to_old_italic(canonical_clean: str) -> str | None:
    """
    Render canonical_clean as Old Italic glyphs. Returns None if any
    letter in the input has no Old Italic correspondence (so we never
    emit a partial transliteration that would silently lose phonemes).
    Punctuation, whitespace, and Old Italic glyphs already present
    pass through unchanged.
    """
    out: list[str] = []
    for ch in canonical_clean:
        if ch in LATIN_TO_OLD_ITALIC:
            out.append(LATIN_TO_OLD_ITALIC[ch])
        elif ch.lower() in LATIN_TO_OLD_ITALIC:
            out.append(LATIN_TO_OLD_ITALIC[ch.lower()])
        elif ch in ALLOWED_PUNCT or ch.isspace():
            out.append(ch)
        elif 0x10300 <= ord(ch) <= 0x1032F:
            out.append(ch)
        else:
            # Any letter we cannot map deterministically — bail.
            return None
    return "".join(out)


def validate(canonical_clean: str) -> list[str]:
    """Return characters that violate the cleanliness contract."""
    return [ch for ch in canonical_clean if ch not in ALLOWED_CHARSET]


def classify(canonical: str, canonical_clean: str, residual: list[str]) -> str:
    if OCR_GARBAGE_RE.search(canonical):
        return "ocr_failed"
    if residual:
        return "needs_review"
    return "clean"


def normalize_row(row: dict) -> NormalizedRow:
    rid = row.get("id", "")
    raw = row.get("raw_text", "") or ""
    canonical = row.get("canonical", "") or ""
    cleaned = apply_corruption_map(canonical)
    residual = validate(cleaned)
    quality = classify(canonical, cleaned, residual)
    # Regenerate Old Italic only for clean rows that are also free of
    # Latin orthography. Two abstention reasons, both safer than a
    # silently-wrong rendering:
    #   - residual chars (quality != clean) → unmapped letters would
    #     drop phonemes
    #   - Latin orthography (HASTI, PVLFENNIA) → letter-mapping a Roman
    #     transliteration into Old Italic produces a glyph stream that
    #     never existed in any inscription
    oi = (
        to_old_italic(cleaned)
        if quality == "clean" and not has_latin_orthography(cleaned)
        else None
    )
    # words-only and intact-ratio are only meaningful for clean rows.
    # Computing them on ocr_failed / needs_review rows would surface
    # OCR garbage like "I3HAAINAOAR3H2391" with ratio=1.0 and trick
    # any downstream filter that uses the ratio without first checking
    # data_quality.
    if quality == "clean":
        words, ratio = words_only_view(cleaned)
    else:
        words, ratio = "", 0.0
    return NormalizedRow(
        id=rid,
        raw_text=raw,
        canonical=canonical,
        canonical_clean=cleaned,
        old_italic_v2=oi,
        canonical_words_only=words,
        intact_token_ratio=ratio,
        data_quality=quality,
        residual_invalid=sorted(set(residual)),
    )


# ---------------------------------------------------------------------------
# IO + reporting
# ---------------------------------------------------------------------------

def iter_rows(path: Path) -> Iterator[dict]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def report(rows: Iterable[NormalizedRow]) -> None:
    rows = list(rows)
    n = len(rows)
    by_quality = collections.Counter(r.data_quality for r in rows)
    n_changed = sum(1 for r in rows if r.canonical != r.canonical_clean)
    n_oi_emitted = sum(1 for r in rows if r.old_italic_v2 is not None)
    residual_chars: collections.Counter[str] = collections.Counter()
    for r in rows:
        residual_chars.update(r.residual_invalid)

    print(f"=== normalize_inscriptions: dry-run report ({n:,} rows) ===")
    print()
    print("data_quality breakdown:")
    for q in ("clean", "needs_review", "ocr_failed"):
        c = by_quality.get(q, 0)
        pct = 100.0 * c / n if n else 0.0
        print(f"  {q:14s} {c:>6,d}  ({pct:5.1f}%)")
    print()
    print(f"rows with canonical_clean != canonical: {n_changed:,} ({100*n_changed/n:.1f}%)")
    print(f"rows where old_italic_v2 was regenerated: {n_oi_emitted:,} ({100*n_oi_emitted/n:.1f}%)")
    print()
    if residual_chars:
        print("residual chars still failing the contract after mapping:")
        for ch, c in residual_chars.most_common(25):
            print(f"  U+{ord(ch):04X} {ch!r:8s} {c:>6d}")
        print()
    # Show 10 representative diffs so a human can sanity-check the map.
    print("sample changes (first 10 rows where canonical changed):")
    shown = 0
    for r in rows:
        if r.canonical != r.canonical_clean and shown < 10:
            print(f"  [{r.data_quality:12s}] {r.id}")
            print(f"      before: {r.canonical[:90]!r}")
            print(f"      after : {r.canonical_clean[:90]!r}")
            if r.old_italic_v2:
                print(f"      old_italic_v2: {r.old_italic_v2[:90]!r}")
            shown += 1


def emit_jsonl(rows: Iterable[NormalizedRow], path: Path) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(r.to_json())
            f.write("\n")


def emit_csv(rows: Iterable[NormalizedRow], path: Path) -> None:
    """
    Write a CSV with the columns this script is authoritative for. The
    user joins this against the rest of the prod columns (findspot,
    phonetic, provenance_status, task_tags) on `id` to produce the
    full Kaggle/Zenodo export.
    """
    with path.open("w", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow([
            "id", "raw_text", "canonical_transliterated",
            "canonical_italic", "canonical_words_only",
            "intact_token_ratio", "data_quality",
        ])
        for r in rows:
            w.writerow([
                r.id,
                r.raw_text,
                r.canonical_clean,
                r.old_italic_v2 if r.old_italic_v2 is not None else "",
                r.canonical_words_only,
                f"{r.intact_token_ratio:.3f}",
                r.data_quality,
            ])


def emit_sql(rows: Iterable[NormalizedRow], out=sys.stdout) -> None:
    """
    Emit an idempotent SQL update script. Reviewer must inspect before
    running it against prod — this script does NOT execute SQL itself.
    """
    out.write("-- Generated by normalize_inscriptions.py — review before applying.\n")
    out.write("BEGIN;\n")
    out.write("ALTER TABLE inscriptions "
              "ADD COLUMN IF NOT EXISTS canonical_clean TEXT, "
              "ADD COLUMN IF NOT EXISTS old_italic_v2 TEXT, "
              "ADD COLUMN IF NOT EXISTS data_quality TEXT;\n")
    for r in rows:
        clean_sql = r.canonical_clean.replace("'", "''")
        oi_sql = ("'" + r.old_italic_v2.replace("'", "''") + "'") if r.old_italic_v2 is not None else "NULL"
        id_sql = r.id.replace("'", "''")
        out.write(
            f"UPDATE inscriptions SET "
            f"canonical_clean = '{clean_sql}', "
            f"old_italic_v2 = {oi_sql}, "
            f"data_quality = '{r.data_quality}' "
            f"WHERE id = '{id_sql}';\n"
        )
    out.write("COMMIT;\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--input", type=Path,
                   default=Path("/tmp/etruscan-prod-rawtext-v1.jsonl"))
    p.add_argument("--output", type=Path,
                   help="Write normalized JSONL to this path.")
    p.add_argument("--csv", type=Path,
                   help="Write CSV (id, raw_text, canonical_transliterated, "
                        "canonical_italic, data_quality) to this path.")
    p.add_argument("--emit-sql", action="store_true",
                   help="Print an UPDATE script to stdout instead of a report.")
    p.add_argument("--limit", type=int,
                   help="Process only the first N rows (debug).")
    args = p.parse_args()

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2

    rows_iter = iter_rows(args.input)
    if args.limit:
        rows_iter = (r for i, r in enumerate(rows_iter) if i < args.limit)
    normalized = [normalize_row(r) for r in rows_iter]

    if args.emit_sql:
        emit_sql(normalized)
    elif args.csv:
        emit_csv(normalized, args.csv)
        print(f"wrote {len(normalized):,} rows to {args.csv}", file=sys.stderr)
    elif args.output:
        emit_jsonl(normalized, args.output)
        print(f"wrote {len(normalized):,} rows to {args.output}", file=sys.stderr)
    else:
        report(normalized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
