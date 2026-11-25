"""Reference parsing and concordance aliases (openetruscan.core.concordance)."""

from __future__ import annotations

from pathlib import Path

import pytest

from openetruscan.core.concordance import (
    ConcordanceIndex,
    aliases_for_id,
    cie_number_exists,
    own_reference,
    parse_reference,
    rix_class_of,
    rix_region_of,
    rix_siglum,
)

BURMAN = Path(__file__).resolve().parents[1] / "reference/burman/burman_concordance_1.0.3.csv"


@pytest.fixture(scope="module")
def index() -> ConcordanceIndex:
    return ConcordanceIndex.from_csv(BURMAN)


@pytest.mark.parametrize(
    ("text", "key", "display"),
    [
        ("CIE 4538", "cie:4538", "CIE 4538"),
        ("CIE 04538", "cie:4538", "CIE 4538"),
        ("cie176a", "cie:176a", "CIE 176a"),
        ("ET Pe 8.4", "et:pe 8.4", "ET Pe 8.4"),
        ("ET² Pe 8.4", "et:pe 8.4", "ET Pe 8.4"),
        ("ET2 Pe 8.0004", "et:pe 8.4", "ET Pe 8.4"),
        ("pe 8.4", "et:pe 8.4", "ET Pe 8.4"),
        ("Ta S.8", "et:ta s.8", "ET Ta S.8"),
        ("OI G.12", "et:oi g.12", "ET OI G.12"),
        ("AS 1.290", "et:as 1.290", "ET AS 1.290"),
        ("as 1.290", "et:as 1.290", "ET AS 1.290"),
        ("At 1.100", "et:at 1.100", "ET AT 1.100"),
        ("NU N.1", "et:nu n.1", "ET NU N.1"),
        ("AD 2.3", "et:ad 2.3", "ET Ad 2.3"),
        ("ta 3.6", "et:ta 3.6", "ET Ta 3.6"),
        ("TLE 0570", "tle:570", "TLE 570"),
        ("TM 153357", "tm:153357", "TM 153357"),
        ("Trismegistos 153357", "tm:153357", "TM 153357"),
        ("CII App. 29", "cii:app 29", "CII App. 29"),
        ("CIL XI.1565", "cil:xi.1565", "CIL XI.1565"),
        ("cil xi.1565", "cil:xi.1565", "CIL XI.1565"),
        ("CIE 05456 bis", "cie:5456bis", "CIE 5456 bis"),
        ("CIE 6447bis", "cie:6447bis", "CIE 6447 bis"),
        ("CIEP 14000", "ciep:14000", "CIEP 14000"),
        ("ET LL", "et:ll", "ET LL"),
        ("et tco", "et:co 8.3", "ET Co 8.3"),
        ("cii app 29", "cii:app 29", "CII App. 29"),
    ],
)
def test_parse_reference(text: str, key: str, display: str) -> None:
    ref = parse_reference(text)
    assert ref is not None
    assert (ref.key, ref.display) == (key, display)


@pytest.mark.parametrize("text", ["", "4538", "larθ", "CIE", "Ta 3"])
def test_parse_reference_rejects(text: str) -> None:
    assert parse_reference(text) is None


def test_rix_class_and_region() -> None:
    ref = parse_reference("Ta S.8")
    assert ref is not None
    assert rix_class_of(ref) == "S"
    assert rix_region_of(ref) == "Ta"
    assert rix_region_of(parse_reference("AS 1.290")) == "AS"  # type: ignore[arg-type]


def test_cie_gaps_from_burman_readme() -> None:
    # "There are no CIE numbers 6724-8000, 8928-10000 or 12114-20000."
    assert cie_number_exists(4538)
    assert cie_number_exists(10001)
    assert cie_number_exists(21071)
    for n in (6724, 7500, 9000, 14000, 20000, 21072, 0):
        assert not cie_number_exists(n)


def test_bare_id_is_ciep() -> None:
    ref, basis = own_reference("4538")
    assert ref is not None and ref.display == "CIEP 4538" and basis == "own_id"


def test_compound_cie_id_points_at_base_number() -> None:
    ref, _ = own_reference("CIE 18.A.1")
    assert ref is not None and ref.key == "cie:18"


def test_aliases_for_cie_record(index: ConcordanceIndex) -> None:
    al = {a.lookup_key: a for a in aliases_for_id("CIE 4538", index)}
    assert al["cie:4538"].basis == "own_id"
    assert al["et:pe 8.4"].basis == "concordance"
    assert al["et:pe 8.4"].confidence == "high"
    assert "ET² (Meiser 2014)" in al["et:pe 8.4"].edition
    assert al["tm:153357"].value == "TM 153357"
    assert al["tle:570"].value == "TLE 570"


def test_aliases_for_bare_ciep_number(index: ConcordanceIndex) -> None:
    """Cippus Perusinus: CIEP 4538 read as CIE 4538, flagged as probable."""
    al = {a.lookup_key: a for a in aliases_for_id("4538", index)}
    assert al["ciep:4538"].basis == "own_id"
    assert al["cie:4538"].basis == "ciep_cie_numbering"
    assert al["cie:4538"].confidence == "probable"
    assert al["et:pe 8.4"].basis == "ciep_cie_numbering"


def test_bare_number_in_cie_gap_gets_no_cie_alias(index: ConcordanceIndex) -> None:
    keys = {a.lookup_key for a in aliases_for_id("14000", index)}
    assert keys == {"ciep:14000"}


def test_rix_siglum_prefers_et2(index: ConcordanceIndex) -> None:
    # CIE 176a is Vt 0.1 in Rix 1991 but Vt 3.4 in Meiser 2014.
    ref, basis = rix_siglum(aliases_for_id("CIE 176a", index))
    assert ref is not None and ref.key == "et:vt 3.4" and basis == "concordance"


def test_own_et_siglum(index: ConcordanceIndex) -> None:
    al = aliases_for_id("Ta 3.6", index)
    keys = {a.lookup_key for a in al}
    assert {"et:ta 3.6", "cie:10007", "tm:146600"} <= keys
    ref, basis = rix_siglum(al)
    assert ref is not None and rix_class_of(ref) == "3" and basis == "own_id"


def test_cie_bis_is_its_own_inscription(index: ConcordanceIndex) -> None:
    """CIE 5456 is Ta 1.45 and CIE 5456 bis is Ta 1.46; neither absorbs the other."""
    plain = {r.key for row in index.lookup("cie:5456") for r in (ref for ref, _ in row.refs)}
    bis = {r.key for row in index.lookup("cie:5456bis") for r in (ref for ref, _ in row.refs)}
    assert "et:ta 1.45" in plain and "et:ta 1.46" not in plain
    assert "et:ta 1.46" in bis


@pytest.mark.parametrize(
    ("record_id", "siglum", "also"),
    [
        ("CODEX_LL_VI", "et:ll", "tle:1"),
        ("LL 2", "et:ll", "tle:1"),
        ("CODEX_TC_II", "et:tc", "cie:8682"),
        ("CODEX_CP_A", "et:cp", "cie:4538"),
        ("CODEX_TCo_B", "et:co 8.3", "tm:173868"),
        ("CODEX_PL_INNER", "et:pa 4.2", "tle:719"),
        ("CODEX_PY_A_1", "et:cr 4.4", "tle:874"),
        ("CODEX_PY_B_1", "et:cr 4.5", "tle:875"),
    ],
)
def test_parts_of_named_texts_carry_the_texts_siglum(
    index: ConcordanceIndex, record_id: str, siglum: str, also: str
) -> None:
    """Our internal IDs for columns and faces of long texts resolve by siglum,
    and the concordance row is used (so the text is not indexed as missing)."""
    rows: list = []
    al = aliases_for_id(record_id, index, rows_out=rows)
    own = next(a for a in al if a.basis == "own_id")
    assert own.lookup_key == siglum
    assert record_id in own.note
    assert also in {a.lookup_key for a in al}
    assert rows
