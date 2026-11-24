"""Findspot strings → place, precision, custody (openetruscan.core.findspots)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from openetruscan.core.findspots import classify_findspot, load_et_regions, load_places

REF = Path(__file__).resolve().parents[1] / "reference"


@pytest.fixture(scope="module")
def kinds() -> dict[str, str]:
    return {k: p.kind for k, p in load_places(REF / "places.csv").items()}


@pytest.mark.parametrize(
    ("raw", "role", "place", "precision"),
    [
        ("Clusii in agro", "findspot", "clusium", "territory"),
        ("Clusii", "findspot", "clusium", "city"),
        ("Clusium cum agro", "findspot", "clusium", "territory"),
        ("Ager Clusinus", "findspot", "clusium", "territory"),
        ("Volaterris", "findspot", "volaterrae", "city"),
        ("Ager Tarquiniensis", "findspot", "tarquinii", "territory"),
        ("Campania", "findspot", "campania", "region"),
        ("Pyrgi", "findspot", "pyrgi", "site"),
        ("Volsinii", "findspot", "volsinii_veteres", "territory"),
        ("in contrada chiusina", "findspot", "clusium", "territory"),
        ("in Città della Pieve FA.", "findspot", "clusium", "territory"),
    ],
)
def test_findspot_strings(
    kinds: dict[str, str], raw: str, role: str, place: str, precision: str
) -> None:
    c = classify_findspot(raw, kinds)
    assert (c.role, c.place_key, c.precision) == (role, place, precision)


@pytest.mark.parametrize(
    "raw",
    [
        "in museo publico Clusino GA.",
        "in museo publico Clusino (succ.) Da.",
        "Clusii in museo publico",
        "Clusii in aedibus Orestis Mignonii BROGI",
        "Parisiensi",
    ],
)
def test_custody_only_strings(kinds: dict[str, str], raw: str) -> None:
    c = classify_findspot(raw, kinds)
    assert c.role == "current_location"
    assert c.place_key is None
    assert c.current_location


@pytest.mark.parametrize(
    "raw",
    [
        "olim Clusii in museo publico Clusino (magaz.) GA.",
        "olim Cortonae in museo Venuti",
        "olim in museo Gualterio GORI (FA.).",
    ],
)
def test_former_keeper_only(kinds: dict[str, str], raw: str) -> None:
    """A string naming only where the object used to be kept is neither a
    findspot nor a current location."""
    c = classify_findspot(raw, kinds)
    assert c.role == "current_location"
    assert c.place_key is None
    assert c.current_location is None


def test_olim_with_a_keeper_that_still_has_it(kinds: dict[str, str]) -> None:
    c = classify_findspot(
        "olim Clusii in museo Casuccini FA., SALIN., tum in museo publico Panormitano FA., "
        "ubi (no. 5818) adhuc (1886) DA.",
        kinds,
    )
    assert c.role == "current_location" and c.place_key is None
    assert c.current_location is not None
    assert c.current_location.startswith("tum in museo publico Panormitano")


@pytest.mark.parametrize(
    "raw",
    [
        "Clusii in collectione Dominici Galeotti FA., nunc ubi sit, non comperi.",
        "olim Clusii in Santa Mustiola PASSERI bis (FA.), nunc videtur perisse.",
        "Clusii in museo Paolozzi, nunc latet",
        "a. 1880 presso Domenico Galeotti GA., nunc ubi sit, non comperi.",
        "Ossuarium tofinum LANZI; olim in museo publico Florentino LANZI, ubi nunc desideratur.",
        "in museo publico Berolinensi CONEST. (Fa.), ubi non inveni.",
        "in museo publico Florentino LANZI, (no. 256) Conest. Fa., ubi non invenimus.",
        "Volaterris LANZI, tum in museo publico Florentino (gall. no. 221) CONEST., Fa., "
        "ubi frustra quaesivi.",
        "non fuit cum ceteris in museo publico Florentino LANZI, ubi extet ignoratur FA.",
    ],
)
def test_lost_objects_have_no_current_location(kinds: dict[str, str], raw: str) -> None:
    """Strings saying the object is lost ("nunc latet") give no current
    location, and are still moved out of `findspot` like a custody note."""
    c = classify_findspot(raw, kinds)
    assert c.current_location is None
    assert c.role in ("current_location", "description")


@pytest.mark.parametrize(
    ("raw", "place"),
    [
        (
            "Volaterras in loco i Marmini dicto a Iusto Cineio, olim in huius aedibus ZANN., "
            "nunc videtur latere.",
            "volaterrae",
        ),
        (
            "repertum Saenae, olim Montepolitiani presso il Sig. Pietro Bucelli Maffei, "
            "nunc videtur periisse.",
            "saena",
        ),
    ],
)
def test_lost_after_a_findspot_keeps_only_the_findspot(
    kinds: dict[str, str], raw: str, place: str
) -> None:
    c = classify_findspot(raw, kinds)
    assert (c.role, c.place_key, c.current_location) == ("findspot", place, None)


def test_a_described_side_is_not_a_lost_object(kinds: dict[str, str]) -> None:
    """ "in latere sinistro" is the side the letters are on, not "latere" (lost)."""
    c = classify_findspot(
        "Parvum ossuarium ex lapide calcaro GA.; litteris (alt. 0,042 PA.) in fronte et in "
        "latere sinistro insculptis GA., PA.; in museo publico Florentino GA., ubi adhuc (1885) PA.",
        kinds,
    )
    assert c.current_location is not None
    assert c.current_location.startswith("in museo publico Florentino")


def test_non_inveni_about_letter_forms_is_not_a_lost_object(kinds: dict[str, str]) -> None:
    c = classify_findspot(
        "forma aviles nisi Faesulis et Volaterris non inveni; "
        "nunc (1893) Florentiae in aedibus Antinori DEFEIS",
        kinds,
    )
    assert c.current_location is not None
    assert c.current_location.startswith("nunc (1893) Florentiae")


def test_olim_after_a_findspot_keeps_the_findspot(kinds: dict[str, str]) -> None:
    c = classify_findspot("Clusii in agro, olim in museo Casuccini", kinds)
    assert c.place_key == "clusium"


def test_findspot_and_current(kinds: dict[str, str]) -> None:
    c = classify_findspot("Clusii FA., nunc (1886) in museo publico Clusino (succ.) DA.", kinds)
    assert c.role == "findspot_and_current"
    assert c.place_key == "clusium"
    assert c.current_location is not None and c.current_location.startswith("nunc (1886)")


def test_description_is_not_a_place(kinds: dict[str, str]) -> None:
    c = classify_findspot("Operculum ossuarii ex lapide tiburtino", kinds)
    assert c.role == "description"


def test_custody_clause_is_trimmed(kinds: dict[str, str]) -> None:
    raw = (
        "Operculum ossuarii (lat. 0,57 Fa.); litteris haud dubie insculptis; "
        "Volaterris in museo Guarnacci (no. 371) Fa."
    )
    c = classify_findspot(raw, kinds)
    assert c.current_location is not None
    assert c.current_location.startswith("Volaterris in museo Guarnacci")
    assert "Operculum" not in c.current_location


def test_reference_tables_are_consistent() -> None:
    places = load_places(REF / "places.csv")
    regions = load_et_regions(REF / "et_regions.csv")
    for code, r in regions.items():
        assert r.place_key is None or r.place_key in places, code
        assert (r.place_key is None) == (r.precision is None), code
    with open(REF / "findspot_gazetteer.csv", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            assert row["place_key"] == "" or row["place_key"] in places, row["findspot"]
            if row["place_key"]:
                assert row["precision"] in ("site", "city", "territory", "region")
