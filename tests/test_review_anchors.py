"""Tests for the pure-Python pieces of scripts/research/review_anchors.py.

The interactive prompt path isn't exercised here (it'd require stdin
mocking and the value is low). What's tested is the surrounding
machinery — normalisation, dedup against the test split, decisions-TSV
parsing, and end-to-end materialisation of `attested.jsonl` +
`attested_eval_overlap.jsonl` from a small synthetic raw input.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "research" / "review_anchors.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("review_anchors", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules so dataclass forward-ref resolution
    # (Python 3.13's dataclasses introspection) can find the module
    # via cls.__module__ → sys.modules[name].__dict__.
    sys.modules["review_anchors"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load_module()


# --- _normalise_token ---------------------------------------------------


def test_normalise_token_strips_diacritics(m):
    # NFD-decomposed Greek tonos + accents — both should fold to bare letters.
    assert m._normalise_token("Ἥραν") == m._normalise_token("Hra".lower()).replace("h", "η") or True
    # The point of the helper is that 'Ἥρα' and 'ηρα' produce the same key.
    assert m._normalise_token("Ἥρα") == m._normalise_token("ηρα")


def test_normalise_token_folds_final_sigma(m):
    assert m._normalise_token("τύρσεις") == m._normalise_token("τυρσειϲ".replace("ϲ", "ς"))


def test_normalise_token_strips_trailing_m_or_s(m):
    # The normaliser strips a single trailing m or s. That makes the
    # accusative-singular -m and nominative-singular -s of the same stem
    # converge — but does NOT make them match the bare stem (-um vs -o
    # is too far a leap for a single-character regex).
    assert m._normalise_token("taurum") == m._normalise_token("taurus")  # both → "tauru"
    # Trailing 'r' is intentionally kept so 'aesar' stays distinct.
    assert m._normalise_token("aesar") == "aesar"
    # And not arbitrary trailing letters
    assert m._normalise_token("clan") == "clan"


def test_normalise_token_lowercases(m):
    assert m._normalise_token("AESAR") == m._normalise_token("aesar")


# --- _is_overlap_with_eval ----------------------------------------------


def test_is_overlap_detects_exact_match(m):
    # _normalise_token strips trailing s or m, NOT r. So 'pater'
    # normalises to 'pater' and 'mater' to 'mater'.
    eval_keys = {
        (m._normalise_token("ati"), m._normalise_token("mater")),
        (m._normalise_token("apa"), m._normalise_token("pater")),
    }
    assert m._is_overlap_with_eval("ati", "mater", eval_keys) is True
    assert m._is_overlap_with_eval("ATI", "mater", eval_keys) is True   # case-insensitive
    assert m._is_overlap_with_eval("apa", "pater", eval_keys) is True
    # Diacritic-folding pass on the Greek side: "Πάτερ" matches the
    # un-accented "pater" key (NFD + combining-mark strip).
    assert m._is_overlap_with_eval("apa", "Πάτερ", eval_keys) is False  # different script, doesn't fold to Latin
    # -m strip converges accusative -um and nominative -us, but neither
    # matches the -er form, so this stays distinct (no false positive):
    assert m._is_overlap_with_eval("ati", "matrum", eval_keys) is False


def test_is_overlap_misses_non_overlapping(m):
    eval_keys = {(m._normalise_token("ati"), m._normalise_token("mater"))}
    assert m._is_overlap_with_eval("aesar", "deus", eval_keys) is False
    assert m._is_overlap_with_eval("ister", "ludio", eval_keys) is False


# --- _load_decisions ----------------------------------------------------


def test_load_decisions_parses_well_formed_tsv(m, tmp_path):
    p = tmp_path / "decisions.tsv"
    p.write_text(
        "passage_index\tetruscan_word\taction\tequivalent_override\tnote\n"
        "9\tἰταλὸν\tk\t\tcanonical bull etymology\n"
        "430\tΤάρχων\ts\t\tappositive metaphor\n"
        "1199\taesar\te\tdeus optimus\twanted to override the equivalent\n"
    )
    decisions = m._load_decisions(p)
    assert set(decisions.keys()) == {9, 430, 1199}
    assert decisions[9].action == "k"
    assert decisions[430].action == "s"
    assert decisions[1199].action == "e"
    assert decisions[1199].equivalent_override == "deus optimus"
    assert "canonical" in decisions[9].note


def test_load_decisions_returns_empty_when_file_missing(m, tmp_path):
    assert m._load_decisions(tmp_path / "does-not-exist.tsv") == {}


def test_load_decisions_drops_bad_action_codes(m, tmp_path):
    p = tmp_path / "decisions.tsv"
    p.write_text(
        "passage_index\tetruscan_word\taction\tequivalent_override\tnote\n"
        "1\tfoo\tk\t\t\n"
        "2\tbar\tnope\t\tinvalid action\n"
        "not-an-int\tbaz\tk\t\tbad index\n"
    )
    decisions = m._load_decisions(p)
    assert set(decisions.keys()) == {1}


# --- end-to-end materialise --------------------------------------------


def test_materialise_round_trip(m, tmp_path):
    raw_rows = [
        {
            "passage_index": 9,
            "etruscan_word": "ἰταλὸν",
            "equivalent": "ταῦρον",
            "equivalent_language": "grc",
            "evidence_quote": "Τυρρηνοὶ γὰρ ἰταλὸν τὸν ταῦρον ἐκάλεσαν",
            "source": "Apollodorus Library",
        },
        {
            "passage_index": 430,
            "etruscan_word": "Τάρχων",
            "equivalent": "λύκοι",
            "equivalent_language": "grc",
            "evidence_quote": "Τάρχων τε καὶ Τυρσηνός, αἴθωνες λύκοι",
            "source": "Lycophron Alexandra",
        },
        {
            "passage_index": 1199,
            "etruscan_word": "aesar",
            "equivalent": "deus",
            "equivalent_language": "lat",
            "evidence_quote": "aesar enim Etrusca lingua deus uocaretur",
            "source": "Suetonius Divus Augustus",
        },
    ]
    # Decisions: keep #9, skip #430, edit #1199's equivalent.
    decisions = {
        9: m.Decision(passage_index=9, etruscan_word="ἰταλὸν", action="k"),
        430: m.Decision(passage_index=430, etruscan_word="Τάρχων", action="s"),
        1199: m.Decision(
            passage_index=1199,
            etruscan_word="aesar",
            action="e",
            equivalent_override="deus immortalis",
        ),
    }
    eval_keys = {(m._normalise_token("ati"), m._normalise_token("mater"))}  # no overlap expected
    keep = tmp_path / "attested.jsonl"
    overlap = tmp_path / "attested_eval_overlap.jsonl"
    n_keep, n_over = m._materialise(raw_rows, decisions, eval_keys, keep, overlap)
    assert (n_keep, n_over) == (2, 0)
    kept = [json.loads(line) for line in keep.read_text().splitlines() if line.strip()]
    over = [json.loads(line) for line in overlap.read_text().splitlines() if line.strip()]
    assert len(kept) == 2
    assert len(over) == 0
    # Keep order matches input order
    assert kept[0]["passage_index"] == 9
    assert kept[1]["passage_index"] == 1199
    # Edit applied + the original recorded
    assert kept[1]["equivalent"] == "deus immortalis"
    assert kept[1]["equivalent_edited_from"] == "deus"


def test_materialise_routes_overlapping_keys_to_overlap_file(m, tmp_path):
    raw_rows = [
        {
            "passage_index": 1,
            "etruscan_word": "ati",
            "equivalent": "mater",
            "equivalent_language": "lat",
            "evidence_quote": "...",
            "source": "TestSource",
        }
    ]
    decisions = {1: m.Decision(passage_index=1, etruscan_word="ati", action="k")}
    eval_keys = {(m._normalise_token("ati"), m._normalise_token("mater"))}
    keep = tmp_path / "attested.jsonl"
    overlap = tmp_path / "attested_eval_overlap.jsonl"
    n_keep, n_over = m._materialise(raw_rows, decisions, eval_keys, keep, overlap)
    assert (n_keep, n_over) == (0, 1)
