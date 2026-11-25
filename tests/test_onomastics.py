"""Name extraction for the Name Index (openetruscan.core.onomastics)."""

from __future__ import annotations

import pytest

from openetruscan.core.onomastics import extract_names, load_lexicon, words


@pytest.fixture(scope="module")
def lex():  # type: ignore[no-untyped-def]
    return load_lexicon()


def _read(text: str, lex) -> list[tuple[str, str, str]]:  # type: ignore[no-untyped-def]
    return [(n.form, n.lemma, n.basis) for n in extract_names(text, lex)]


def test_praenomen_and_family_name(lex) -> None:  # type: ignore[no-untyped-def]
    assert _read("θana : cainei : velus", lex) == [
        ("θana", "θana", "praenomen_list"),
        ("cainei", "cainei", "follows_praenomen"),
        ("velus", "vel", "praenomen_list"),
    ]


def test_case_forms_share_the_praenomen_lemma(lex) -> None:  # type: ignore[no-untyped-def]
    names = extract_names("larθ ferinie arnθus larθal", lex)
    assert [(n.form, n.lemma, n.gender) for n in names if n.name_type == "praenomen"] == [
        ("larθ", "larθ", "m"),
        ("arnθus", "arnθ", "m"),
        ("larθal", "larθ", "m"),
    ]


def test_only_listed_praenomina_are_high(lex) -> None:  # type: ignore[no-untyped-def]
    conf = {n.basis: n.confidence for n in extract_names("vl canzna aθ:cainal larθi vipinei", lex)}
    assert conf == {
        "praenomen_abbreviation": "probable",
        "follows_praenomen": "probable",
        "praenomen_list": "high",
    }


def test_abbreviation_is_kept_as_written(lex) -> None:  # type: ignore[no-untyped-def]
    assert _read("aθ:tetina:helial", lex)[0] == ("aθ", "aθ.", "praenomen_abbreviation")


@pytest.mark.parametrize(
    "text",
    [
        "L CAECINA L F TLABONI VIX ANN S XXX",  # Latin, no interpunct after L
        "a b c d e v z h θ k l m n",  # abecedarium
        "FLAVIA C F A III",  # Roman numerals
        "a) mi capi",  # side label
    ],
)
def test_single_letters_need_a_naming_formula(text: str, lex) -> None:  # type: ignore[no-untyped-def]
    assert not [n for n in extract_names(text, lex) if n.basis == "praenomen_abbreviation"]


def test_no_entry_is_a_phrase(lex) -> None:  # type: ignore[no-untyped-def]
    text = (
        "a. in parte adversa: ....quei stipulatum eius.... larθ velχas arnθal clan "
        "--- lamina b --- 1. acep fulθuna mazutini 2. l.larθi θa armne"
    )
    for n in extract_names(text, lex):
        assert " " not in n.form and len(n.form) <= 20, n


def test_fragments_and_known_words_are_not_family_names(lex) -> None:  # type: ignore[no-untyped-def]
    assert _read("larθ --------vetinei", lex) == [("larθ", "larθ", "praenomen_list")]
    assert _read("larθ clan", lex) == [("larθ", "larθ", "praenomen_list")]
    assert _read("arnθ avils", lex) == [("arnθ", "arnθ", "praenomen_list")]


def test_editorial_marks_inside_a_word(lex) -> None:  # type: ignore[no-untyped-def]
    assert [w for w, _ in words("avil[e] θansi(e) ra[m]θa")] == ["avile", "θansie", "ramθa"]
    assert _read("ra[m]θa vipinei", lex)[0][:2] == ("ramθa", "ramθa")


def test_kinship_words_with_case_endings_or_enclitic_c(lex) -> None:  # type: ignore[no-untyped-def]
    for text in ("vel clanc", "larθ papas", "arnθ papalserc", "larθ cleniarc", "θana (vacat)"):
        assert [n.name_type for n in extract_names(text, lex)] == ["praenomen"], text
    # A family name with the enclitic is still a family name.
    assert _read("larθ vipinnalc", lex)[1] == ("vipinnalc", "vipinnalc", "follows_praenomen")


def test_praenomen_after_praenomen_is_not_a_family_name(lex) -> None:  # type: ignore[no-untyped-def]
    assert _read("au cae arntal", lex)[-1] == ("arntal", "arnθ", "praenomen_list")
    assert _read("larθial ramθasa", lex)[1] == ("ramθasa", "ramθa", "praenomen_list")


def test_sigma_forms_stay_searchable(lex) -> None:  # type: ignore[no-untyped-def]
    # Lower-cased letter by letter like Postgres lower(): VELΣ -> velσ.
    assert [w for w, _ in words("LARΘ VELΣ")] == ["larθ", "velσ"]
    assert _read("LARΘ VELΣ", lex)[1] == ("velσ", "vel", "praenomen_list")
    # A written ς is kept in the form, so /search?q=<form> finds the record;
    # lookups and headwords treat ς as σ.
    assert _read("velς apunaς", lex) == [
        ("velς", "vel", "praenomen_list"),
        ("apunaς", "apunaσ", "follows_praenomen"),
    ]


def test_caile_is_its_own_praenomen(lex) -> None:  # type: ignore[no-untyped-def]
    assert _read("mi cailes cutus", lex)[0][:2] == ("cailes", "caile")
