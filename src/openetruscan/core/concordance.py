"""Standard-reference aliases for corpus records.

Scholars cite Etruscan inscriptions by CIE number, by Rix/Meiser *Etruskische
Texte* siglum (``Ta 3.6``), by TLE number or by Trismegistos (TM) number. Most
OpenEtruscan record IDs are none of these: about two thirds are bare numbers
inherited from the Larth dataset. This module turns a record ID into the
references a scholar would use, through Annie Burman's concordance (CC0,
Zenodo 10.5281/zenodo.17209666), and parses whatever a user types into a
lookup key.

What the bare numbers are
-------------------------
Larth (Vico & Spanakis 2023, §3) took 6,578 texts from Jeff Hill's *Corpus
Inscriptionum Etruscarum Plenissimum* (CIEP, 2018), and the bare IDs are
CIEP numbers. Inside the number ranges the CIE has actually published,
CIEP numbering follows CIE numbering. Checked on landmark texts:

* CIEP 3 reads ``tular spu…`` — CIE 3 is the Fiesole boundary stone ET Fs 8.2.
* CIEP 4538 contains ``velθinas … larθals afunes`` — CIE 4538 is the Cippus
  Perusinus, ET Pe 8.4.
* CIEP 5237 reads ``tuθiu χimθm casθialθ lacθ`` — CIE 5237 is the Magliano
  disc, ET AV 4.1.
* CIEP 10001 reads ``mi larθas arsinaia`` (an ownership formula) — CIE 10001
  is ET Ta 2.5, a class-2 ownership text.

Burman's Read Me states that no CIE numbers exist in 6724–8000, 8928–10000 or
12114–20000; a bare number in those gaps is a CIEP-only number and never gets
a CIE alias. Inside the published ranges the CIE alias is recorded with basis
``ciep_cie_numbering`` and confidence ``probable``: the scheme is verified,
the individual record is not. Every alias carries its basis so the site can
say how it was derived.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Alias schemes, in display order.
SCHEMES = ("cie", "et", "tle", "tm", "cii", "cil", "ciep", "bakkum")

SCHEME_LABELS = {
    "cie": "CIE",
    "et": "ET",
    "tle": "TLE",
    "tm": "TM",
    "cii": "CII",
    "cil": "CIL",
    "ciep": "CIEP",
    "bakkum": "Bakkum",
}

#: How an alias was derived. Ordered from strongest to weakest.
BASES = ("own_id", "concordance", "ciep_cie_numbering")

#: Confidence attached to each basis.
CONFIDENCE_FOR_BASIS = {
    "own_id": "certain",
    "concordance": "high",
    "ciep_cie_numbering": "probable",
}

#: CIE number ranges with no published inscriptions (Burman 1.0.3 Read Me,
#: section 4: "there are no CIE numbers 6724-8000, 8928-10000 or 12114-20000").
CIE_GAPS: tuple[tuple[int, int], ...] = ((6724, 8000), (8928, 10000), (12114, 20000))
CIE_MAX = 21071  # CIE II,1,1 (Atria) ends at Tit. 21071.

BURMAN_CITATION = (
    "Burman, A. C. (2025). A Digital Concordance of Etruscan, Faliscan and Early "
    "Latin Inscriptions from Etruria, v1.0.3. Zenodo. "
    "https://doi.org/10.5281/zenodo.17209666 (CC0 1.0)"
)
CIEP_CITATION = (
    "Hill, J. (2018). Corpus Inscriptionum Etruscarum Plenissimum, "
    "via the Larth dataset (Vico & Spanakis 2023)"
)


def cie_number_exists(n: int) -> bool:
    """True when ``n`` falls inside a range the CIE has published."""
    if n < 1 or n > CIE_MAX:
        return False
    return not any(lo <= n <= hi for lo, hi in CIE_GAPS)


# ---------------------------------------------------------------------------
# Reference parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ref:
    """A parsed standard reference.

    ``key`` is the normalised lookup key stored in ``inscription_aliases``
    (``cie:4538``, ``et:pe 8.4``, ``tle:570``, ``tm:153357``). ``display`` is
    the form a scholar would write.
    """

    scheme: str
    key: str
    display: str


_ET_BODY = r"([A-Z][A-Za-z]{0,2})\s+([0-9SGN])\s*\.\s*0*(\d+)\s*([a-z]?)"
_RE_ET_FULL = re.compile(rf"^(?:ET\s*(?:[12¹²]|ii|i)?\s*)?{_ET_BODY}$", re.IGNORECASE)
#: Long texts cited by name: Liber Linteus, Tabula Capuana and Cippus
#: Perusinus (ET's own sigla), and TCo, the usual abbreviation for the
#: Tabula Cortonensis, which parses to its ET² siglum Co 8.3.
_ET_NAMED_DISPLAY = {"ll": "LL", "tc": "TC", "cp": "CP", "tco": "TCo"}
_RE_ET_NAMED = re.compile(r"^ET\s*(?:[12¹²])?\s+(LL|TC|CP|TCo)$", re.IGNORECASE)
_RE_CIE = re.compile(r"^CIE\s*0*(\d+)\s*([a-z]?)(\s*bis)?$", re.IGNORECASE)
_RE_CIEP = re.compile(r"^CIEP\s*0*(\d+)$", re.IGNORECASE)
_RE_TLE = re.compile(r"^TLE\s*0*(\d+)\s*([a-z]?)$", re.IGNORECASE)
_RE_TM = re.compile(r"^(?:TM|Trismegistos)\s*(?:no\.?\s*)?0*(\d+)$", re.IGNORECASE)
_RE_CII = re.compile(r"^CII\s*(App\.?|Suppl\.?)?\s*0*(\d+)\s*([a-z]?)$", re.IGNORECASE)
_RE_CIL = re.compile(
    r"^CIL\s+(I\(2\)|I|III|VI|XI)\s*\.?\s*0*(\d+)(?:\s*\(0*(\d+)\))?$", re.IGNORECASE
)
_RE_BAKKUM = re.compile(r"^Bakkum\s*0*(\d+)\s*([a-z]?)$", re.IGNORECASE)


def _clean(text: str) -> str:
    text = text.replace(" ", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(".,;")


#: ET codes written all caps: the "Ager" and "Origo" codes and NU (coins).
#: Every other code is written Xx (Ta, Cl, Pe). No two codes differ by case
#: alone, so typed or stored case ("At 1.100", "as 1.290") is normalised.
_ET_CAPS_CODES = frozenset({"AH", "AS", "AT", "AV", "OA", "OB", "OI", "NU"})


def _et_ref(region: str, cls: str, num: str, suffix: str) -> Ref:
    if region.upper() in _ET_CAPS_CODES:
        region_norm = region.upper()
    else:
        region_norm = region[0].upper() + region[1:].lower()
    cls = cls.upper()
    n = int(num)
    body = f"{region_norm} {cls}.{n}{suffix.lower()}"
    return Ref("et", f"et:{body.lower()}", f"ET {body}")


def parse_reference(text: str) -> Ref | None:
    """Parse a user-typed or concordance reference into a :class:`Ref`.

    Accepts the forms people actually type: ``CIE 4538``, ``CIE 04538``,
    ``ET Pe 8.4``, ``ET² Pe 8.4``, ``ET2 Pe 8.0004``, ``Pe 8.4``, ``Ta S.8``,
    ``TLE 570``, ``TM 153357``, ``Trismegistos 153357``, ``CII 104``,
    ``CIL XI.1565``, ``CIEP 4538``. Returns ``None`` for anything else,
    including bare numbers (those are ambiguous, see :func:`aliases_for_id`).
    """
    if not text:
        return None
    t = _clean(text)
    if m := _RE_CIE.match(t):
        n, suf = int(m.group(1)), m.group(2).lower()
        # "CIE 5456 bis" is a different inscription from CIE 5456 (Ta 1.46
        # vs Ta 1.45), so it gets its own key.
        if m.group(3):
            return Ref("cie", f"cie:{n}{suf}bis", f"CIE {n}{suf} bis")
        return Ref("cie", f"cie:{n}{suf}", f"CIE {n}{suf}")
    if m := _RE_CIEP.match(t):
        n = int(m.group(1))
        return Ref("ciep", f"ciep:{n}", f"CIEP {n}")
    if m := _RE_TLE.match(t):
        n, suf = int(m.group(1)), m.group(2).lower()
        return Ref("tle", f"tle:{n}{suf}", f"TLE {n}{suf}")
    if m := _RE_TM.match(t):
        n = int(m.group(1))
        return Ref("tm", f"tm:{n}", f"TM {n}")
    if m := _RE_CII.match(t):
        part = (m.group(1) or "").lower().rstrip(".")
        n, suf = int(m.group(2)), m.group(3).lower()
        tag = f"{part} " if part else ""
        disp_part = {"app": "App. ", "suppl": "Suppl. "}.get(part, "")
        return Ref("cii", f"cii:{tag}{n}{suf}", f"CII {disp_part}{n}{suf}")
    if m := _RE_CIL.match(t):
        vol, n, sub = m.group(1).upper(), int(m.group(2)), m.group(3)
        tail = f"({int(sub)})" if sub else ""
        return Ref("cil", f"cil:{vol.lower()}.{n}{tail}", f"CIL {vol}.{n}{tail}")
    if m := _RE_BAKKUM.match(t):
        n, suf = int(m.group(1)), m.group(2).lower()
        return Ref("bakkum", f"bakkum:{n}{suf}", f"Bakkum {n}{suf}")
    if m := _RE_ET_NAMED.match(t):
        code = _ET_NAMED_DISPLAY[m.group(1).lower()]
        if code == "TCo":
            return _et_ref("Co", "8", "3", "")
        return Ref("et", f"et:{code.lower()}", f"ET {code}")
    if m := _RE_ET_FULL.match(t):
        return _et_ref(*m.groups())
    return None


def rix_class_of(ref: Ref) -> str | None:
    """Return the ET text class (``0``–``9``, ``S``, ``G``, ``N``) of an ET ref."""
    if ref.scheme != "et":
        return None
    m = re.match(r"^et:[a-z]+ ([0-9sgn])\.", ref.key)
    return m.group(1).upper() if m else None


def rix_region_of(ref: Ref) -> str | None:
    """Return the ET place/region code (``Ta``, ``Cl``, ``AS``) of an ET ref."""
    if ref.scheme != "et":
        return None
    m = re.match(r"^ET ([A-Za-z]+) [0-9SGN]\.", ref.display)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Burman concordance index
# ---------------------------------------------------------------------------

#: Burman columns and the scheme each one holds.
BURMAN_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # (column, scheme, edition label shown next to the alias)
    ("CIE", "cie", "CIE"),
    ("Meiser. ET2", "et", "ET² (Meiser 2014)"),
    ("Rix. ET1", "et", "ET (Rix 1991)"),
    ("TLE", "tle", "TLE (Pallottino 1968)"),
    ("Trismegistos", "tm", "Trismegistos"),
    ("CII", "cii", "CII (Fabretti 1867)"),
    ("CII Suppl.", "cii", "CII Suppl."),
    ("CII App.", "cii", "CII App. (Gamurrini 1880)"),
    ("CIL I", "cil", "CIL I"),
    ("CIL I(2)", "cil", "CIL I²"),
    ("CIL III", "cil", "CIL III"),
    ("CIL VI", "cil", "CIL VI"),
    ("CIL XI", "cil", "CIL XI"),
    ("Bakkum", "bakkum", "Bakkum 2009"),
)


def _burman_cell_refs(column: str, cell: str) -> list[Ref]:
    """Parse one Burman cell. Cells may hold ranges, ``+add`` notes, or prefixes."""
    cell = _clean(cell)
    if not cell:
        return []
    # Drop editorial tails: "CIE 00176 +add", "CIE 01234 a +add".
    cell = re.sub(r"\s*\+\s*add\.?$", "", cell)
    # Ranges ("CIE 01234–CIE 01236", "CIE 01234-01236") index only the first.
    cell = re.split(r"\s*[–-]\s*(?=CIE|\d)", cell)[0]
    if column in ("Rix. ET1", "Meiser. ET2"):
        cell = re.sub(r"^ET[12]\s+", "ET ", cell)
    elif column == "CII Suppl.":
        cell = re.sub(r"^CII Suppl\.?\s*", "CII Suppl. ", cell)
    elif column == "CII App.":
        cell = re.sub(r"^CII App\.?\s*", "CII App. ", cell)
    elif column == "CIL I(2)":
        cell = cell.replace("CIL I(2) ", "CIL I(2).").replace("CIL I(2)..", "CIL I(2).")
    elif column.startswith("CIL"):
        cell = re.sub(r"^(CIL [IVX]+)\.", r"\1.", cell)
    # "CIE 00176 a" -> "CIE 176a"
    cell = re.sub(r"^(CIE|TLE)\s+0*(\d+)\s+([a-z])\b", r"\1 \2\3", cell)
    ref = parse_reference(cell)
    return [ref] if ref else []


@dataclass(frozen=True)
class ConcordanceRow:
    """One Burman row, parsed. ``refs`` pairs each ref with its edition label."""

    row_no: int
    refs: tuple[tuple[Ref, str], ...]
    multiple: str
    note: str

    def refs_of(self, scheme: str) -> list[Ref]:
        return [r for r, _ in self.refs if r.scheme == scheme]


class ConcordanceIndex:
    """Burman's concordance, indexed by every reference it contains."""

    def __init__(self, rows: Iterable[ConcordanceRow]):
        self.rows: list[ConcordanceRow] = list(rows)
        self.by_key: dict[str, list[ConcordanceRow]] = defaultdict(list)
        self.cie_numbers: set[int] = set()
        for row in self.rows:
            seen: set[str] = set()
            for ref, _label in row.refs:
                if ref.key in seen:
                    continue
                seen.add(ref.key)
                self.by_key[ref.key].append(row)
                if ref.scheme == "cie":
                    m = re.match(r"cie:(\d+)", ref.key)
                    if m:
                        self.cie_numbers.add(int(m.group(1)))
                        # A suffixed CIE number ("cie:176a") is also reachable
                        # by its bare number, flagged as ambiguous by the
                        # caller when several rows share it.
                        # "bis" entries are separate inscriptions and stay
                        # out of the bare number.
                        base = f"cie:{m.group(1)}"
                        if base != ref.key and not ref.key.endswith("bis") and base not in seen:
                            seen.add(base)
                            self.by_key[base].append(row)

    @classmethod
    def from_csv(cls, path: str | Path) -> ConcordanceIndex:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            return cls(_parse_burman_rows(reader))

    def lookup(self, key: str) -> list[ConcordanceRow]:
        return self.by_key.get(key, [])


def _parse_burman_rows(reader: Iterable[dict[str, str]]) -> Iterator[ConcordanceRow]:
    for i, raw in enumerate(reader, start=2):  # row 1 is the header
        refs: list[tuple[Ref, str]] = []
        for column, _scheme, label in BURMAN_COLUMNS:
            for ref in _burman_cell_refs(column, raw.get(column) or ""):
                refs.append((ref, label))
        if refs:
            yield ConcordanceRow(
                row_no=i,
                refs=tuple(refs),
                multiple=_clean(raw.get("Multiple references?") or ""),
                note=_clean(raw.get("Notes") or ""),
            )


# ---------------------------------------------------------------------------
# Aliases for a record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Alias:
    """One row of ``inscription_aliases``."""

    inscription_id: str
    scheme: str
    lookup_key: str
    value: str
    edition: str
    basis: str
    confidence: str
    source: str
    note: str = ""


_RE_BARE = re.compile(r"^\d+$")

#: Records holding one column, face or side of a long text that the
#: concordance cites under a single siglum. Our IDs are internal
#: (CODEX_LL_VI, LL 2); the siglum is what a scholar looks up. The Tabula
#: Cortonensis (found 1992) postdates ET¹ and is Co 8.3 in ET².
_NAMED_TEXT_IDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:CODEX_LL_[IVXL]+|LL \d+)$"), "ET LL"),  # Liber Linteus
    (re.compile(r"^CODEX_TC_[IVX]+$"), "ET TC"),  # Tabula Capuana
    (re.compile(r"^CODEX_CP_[A-Z]$"), "ET CP"),  # Cippus Perusinus
    (re.compile(r"^CODEX_TCo_[A-Z]$"), "ET Co 8.3"),  # Tabula Cortonensis
    (re.compile(r"^CODEX_PL_(?:INNER|OUTER)$"), "ET Pa 4.2"),  # Piacenza Liver
    (re.compile(r"^CODEX_PY_A_\d+$"), "ET Cr 4.4"),  # Pyrgi tablet A
    (re.compile(r"^CODEX_PY_B_\d+$"), "ET Cr 4.5"),  # Pyrgi tablet B
)


def own_reference(record_id: str) -> tuple[Ref | None, str]:
    """The reference a record's own ID already is, and the basis to use.

    Returns ``(ref, basis)``. Bare numbers become ``CIEP n``; the parts of
    the long named texts become that text's siglum (``CODEX_LL_VI`` → ET LL).
    """
    rid = record_id.strip()
    if _RE_BARE.match(rid):
        n = int(rid)
        return Ref("ciep", f"ciep:{n}", f"CIEP {n}"), "own_id"
    for rx, siglum in _NAMED_TEXT_IDS:
        if rx.match(rid):
            return parse_reference(siglum), "own_id"
    ref = parse_reference(rid)
    if ref is None and (m := _RE_CIE_COMPOUND.match(rid)):
        # "CIE 18.A.1", "CIE 19-20", "CIE 52a, b": a part or a run of CIE
        # entries. The first CIE number is the reference a scholar would
        # look up; it is shared with sibling parts, so the resolver will
        # offer a choice rather than redirect.
        n = int(m.group(1))
        ref = Ref("cie", f"cie:{n}", f"CIE {n}")
    return ref, "own_id"


_RE_CIE_COMPOUND = re.compile(r"^CIE\s+0*(\d+)(?:[a-z]?)(?:[.,\s-].*)$", re.IGNORECASE)


def aliases_for_id(
    record_id: str,
    index: ConcordanceIndex,
    rows_out: list[ConcordanceRow] | None = None,
) -> list[Alias]:
    """Every standard reference that resolves to ``record_id``.

    The record's own ID comes first (basis ``own_id``). Concordance rows are
    found through the own ID; for a bare CIEP number inside a published CIE
    range the CIE number is tried too, with basis ``ciep_cie_numbering``.
    When ``rows_out`` is given, the concordance rows used are appended to it.
    """
    own, _ = own_reference(record_id)
    if own is None:
        return []
    out: dict[tuple[str, str], Alias] = {}

    def add(ref: Ref, edition: str, basis: str, source: str, note: str = "") -> None:
        k = (ref.scheme, ref.key)
        if k in out:
            prev = out[k]
            if BASES.index(prev.basis) < BASES.index(basis):
                return
            if prev.basis == basis:
                if edition not in prev.edition.split("; "):
                    out[k] = Alias(**{**prev.__dict__, "edition": f"{prev.edition}; {edition}"})
                return
        out[k] = Alias(
            inscription_id=record_id,
            scheme=ref.scheme,
            lookup_key=ref.key,
            value=ref.display,
            edition=edition,
            basis=basis,
            confidence=CONFIDENCE_FOR_BASIS[basis],
            source=source,
            note=note,
        )

    own_source = "OpenEtruscan record ID"
    own_edition = SCHEME_LABELS.get(own.scheme, own.scheme.upper())
    if own.scheme == "ciep":
        own_source = CIEP_CITATION
    own_note = ""
    if own.scheme != "ciep" and own.display.replace(" ", "").lower() not in (
        record_id.replace(" ", "").lower(),
        f"et{record_id.replace(' ', '').lower()}",
    ):
        own_note = f"Record {record_id} is one part of, or spans, {own.display}."
    add(own, own_edition, "own_id", own_source, own_note)

    rows: list[ConcordanceRow] = []
    basis = "concordance"
    if own.scheme == "ciep":
        n = int(own.key.split(":")[1])
        if cie_number_exists(n) and n in index.cie_numbers:
            cie_ref = Ref("cie", f"cie:{n}", f"CIE {n}")
            add(
                cie_ref,
                "CIE",
                "ciep_cie_numbering",
                CIEP_CITATION,
                "CIEP numbering follows CIE inside published CIE ranges; "
                "this record's identity with CIE n is not individually checked.",
            )
            rows = index.lookup(cie_ref.key)
            basis = "ciep_cie_numbering"
    else:
        rows = index.lookup(own.key)

    if rows_out is not None:
        rows_out.extend(rows)
    multiple_note = ""
    if len(rows) > 1:
        multiple_note = (
            f"{len(rows)} concordance rows share this reference "
            "(one reference may cover several inscriptions)."
        )
    for row in rows:
        for ref, label in row.refs:
            if ref.key == own.key:
                continue
            note = multiple_note or (row.multiple if row.multiple else "")
            add(ref, label, basis, BURMAN_CITATION, note)
    return sorted(
        out.values(),
        key=lambda a: (BASES.index(a.basis), SCHEMES.index(a.scheme), a.lookup_key),
    )


def rix_siglum(aliases: Iterable[Alias]) -> tuple[Ref | None, str | None]:
    """The single ET siglum for a record, and the basis it came through.

    Prefers ET² (Meiser 2014) over ET (Rix 1991). Returns ``(None, None)``
    when the record has no ET siglum or when several distinct numbered
    sigla compete (a ``Multiple references`` case), so no text class is
    guessed.
    """
    et2: dict[str, tuple[Ref, str]] = {}
    other: dict[str, tuple[Ref, str]] = {}
    for a in aliases:
        if a.scheme != "et":
            continue
        ref = parse_reference(a.value)
        if ref is None or rix_class_of(ref) is None:
            continue
        bucket = et2 if "ET²" in a.edition else other
        bucket.setdefault(ref.key, (ref, a.basis))
    for bucket in (et2, other):
        if len(bucket) == 1:
            return next(iter(bucket.values()))
        if len(bucket) > 1:
            return None, None
    return None, None
