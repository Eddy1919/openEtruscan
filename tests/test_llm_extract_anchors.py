"""Tests for the pure-Python pieces of scripts/research/llm_extract_anchors.py.

The actual Gemini call is not exercised here — that's a paid Vertex call
and lives behind manual invocation. What's tested is the surrounding
machinery that decides what to send to the model and what to keep from
its response, which is where most of the precision-vs-recall trade-off
lives:

  - `_smart_truncate`: long passages get windowed around Etruscan-mention
    keywords. Short passages pass through unchanged. The windowing
    decision is what keeps the per-passage token cost from blowing up
    on the few outlier passages (max=930k chars in the corpus).
  - `_parse_model_output`: strips markdown fences if present, rejects
    non-list responses, tolerates whitespace.
  - `_validate_gloss`: drops glosses missing required fields or whose
    `evidence_quote` isn't a verbatim substring. This is the second
    line of defence against the model hallucinating a citation.
  - `_load_resume_state`: the resumability contract that lets a
    interrupted run pick up without re-paying for already-processed
    passages.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "research" / "llm_extract_anchors.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("llm_extract_anchors", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load_module()


# --- _smart_truncate -----------------------------------------------------


def test_smart_truncate_short_passage_passes_through(m):
    text = "Brevis textus de Tuscis."
    out, truncated = m._smart_truncate(text)
    assert out == text
    assert truncated is False


def test_smart_truncate_long_passage_with_keyword_windows_to_context(m):
    # 10k filler + keyword + 10k filler = passage > _MAX_PASSAGE_CHARS
    filler = "x" * 10_000
    text = filler + " Tyrrhenians said hello " + filler
    out, truncated = m._smart_truncate(text)
    assert truncated is True
    assert "Tyrrhenians said hello" in out
    # The window keeps ±1500 chars around the hit, plus separators.
    # Total should be comfortably under the raw passage length.
    assert len(out) < len(text) // 2


def test_smart_truncate_long_passage_with_multiple_keywords_merges_windows(m):
    # Put each keyword far enough apart that windows DON'T overlap, with
    # far-away head and tail filler that should be entirely outside the
    # ±1500-char windows around any keyword.
    head = "y" * 3000
    tail = "z" * 3000
    sep = "g" * 4000   # > 2 × 1500, so windows around adjacent keywords don't overlap
    # Pad each keyword with whitespace so the `\b` word boundary in the
    # keyword regex actually matches (yyTusci would not — both `y` and `T`
    # are word characters).
    text = head + " " + sep + " Tusci " + sep + " Etrusci " + sep + " Tyrrhenians " + sep + " " + tail
    out, truncated = m._smart_truncate(text)
    assert truncated is True
    # All three keywords still present after windowing.
    assert "Tusci" in out
    assert "Etrusci" in out
    assert "Tyrrhenians" in out
    # Far head/tail filler should not survive — the first ~1500 chars of
    # `head` and the last ~1500 chars of `tail` are outside any window.
    assert "y" * 1500 not in out
    assert "z" * 1500 not in out
    # And the windows should be separated by an ellipsis marker, since
    # the gap between keyword windows (here ~1000 chars) is < the window
    # width but their non-overlap is guaranteed by the 4000-char sep.
    assert "[...]" in out


def test_smart_truncate_long_passage_without_keyword_falls_back_to_head_tail(m):
    text = "A" * 5000 + "B" * 5000  # no keyword anywhere
    out, truncated = m._smart_truncate(text)
    assert truncated is True
    assert out.startswith("A")
    assert out.endswith("B")
    assert "truncated" in out


# --- _parse_model_output -------------------------------------------------


def test_parse_model_output_strict_list_round_trip(m):
    raw = json.dumps([{"etruscan_word": "aesar"}])
    assert m._parse_model_output(raw) == [{"etruscan_word": "aesar"}]


def test_parse_model_output_strips_markdown_fence(m):
    raw = "```json\n[{\"x\": 1}]\n```"
    assert m._parse_model_output(raw) == [{"x": 1}]


def test_parse_model_output_strips_bare_fence(m):
    raw = "```\n[]\n```"
    assert m._parse_model_output(raw) == []


def test_parse_model_output_rejects_non_list(m):
    assert m._parse_model_output('{"x": 1}') is None


def test_parse_model_output_rejects_garbage(m):
    assert m._parse_model_output("not even json") is None


def test_parse_model_output_handles_empty_string(m):
    # Defensive: an empty response shouldn't crash the loop.
    assert m._parse_model_output("") is None


# --- _validate_gloss -----------------------------------------------------

_CANONICAL_PASSAGE = (
    "prosperum ac salutarem sibi praesumebat, quod gentile illi cognomen erat, "
    "vel quia eo verbo Tusci deum significant; aesar enim Etrusca lingua deus vocatur."
)


def test_validate_gloss_accepts_canonical_aesar(m):
    g = {
        "etruscan_word": "aesar",
        "equivalent": "deus",
        "equivalent_language": "lat",
        "evidence_quote": "aesar enim Etrusca lingua deus vocatur",
    }
    ok, why = m._validate_gloss(g, _CANONICAL_PASSAGE)
    assert ok, why


def test_validate_gloss_rejects_invalid_language(m):
    g = {
        "etruscan_word": "aesar",
        "equivalent": "deus",
        "equivalent_language": "ger",  # not lat/grc
        "evidence_quote": "aesar enim Etrusca lingua deus vocatur",
    }
    ok, why = m._validate_gloss(g, _CANONICAL_PASSAGE)
    assert not ok
    assert "equivalent_language" in (why or "")


def test_validate_gloss_rejects_missing_field(m):
    g = {
        "etruscan_word": "aesar",
        "equivalent": "deus",
        # equivalent_language missing
        "evidence_quote": "aesar enim Etrusca lingua deus vocatur",
    }
    ok, why = m._validate_gloss(g, _CANONICAL_PASSAGE)
    assert not ok
    assert "equivalent_language" in (why or "")


def test_validate_gloss_rejects_empty_field(m):
    g = {
        "etruscan_word": "aesar",
        "equivalent": "",  # empty
        "equivalent_language": "lat",
        "evidence_quote": "aesar enim Etrusca lingua deus vocatur",
    }
    ok, why = m._validate_gloss(g, _CANONICAL_PASSAGE)
    assert not ok
    assert "equivalent" in (why or "")


def test_validate_gloss_rejects_hallucinated_quote(m):
    g = {
        "etruscan_word": "lautn",
        "equivalent": "familia",
        "equivalent_language": "lat",
        # This phrase isn't anywhere in the canonical Suetonius passage,
        # but is the kind of thing the model might confabulate from
        # outside knowledge ("I know lautn = familia").
        "evidence_quote": "lautn apud Tuscos familia vocatur",
    }
    ok, why = m._validate_gloss(g, _CANONICAL_PASSAGE)
    assert not ok
    assert "verbatim" in (why or "")


# --- _load_resume_state --------------------------------------------------


def test_load_resume_state_empty_when_no_sidecar(m, tmp_path):
    p = tmp_path / "missing.sidecar"
    assert m._load_resume_state(p) == set()


def test_load_resume_state_counts_only_processed_status(m, tmp_path):
    p = tmp_path / "sidecar.jsonl"
    rows = [
        {"passage_index": 0, "status": "processed", "n_glosses": 0},
        {"passage_index": 1, "status": "processed", "n_glosses": 1},
        {"passage_index": 2, "status": "parse_error"},   # not "processed" → skip
        {"passage_index": 3, "status": "api_error"},     # not "processed" → skip
        {"passage_index": 4, "status": "processed", "n_glosses": 0},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert m._load_resume_state(p) == {0, 1, 4}


def test_load_resume_state_tolerates_bad_lines(m, tmp_path):
    p = tmp_path / "sidecar.jsonl"
    p.write_text(
        '{"passage_index": 0, "status": "processed", "n_glosses": 0}\n'
        "not-json\n"
        "\n"
        '{"passage_index": "five", "status": "processed"}\n'  # bad int
        '{"passage_index": 2, "status": "processed", "n_glosses": 0}\n'
    )
    # Good lines kept; bad lines silently dropped (we don't want a single
    # corrupt row to wedge a 60-min run during resume).
    assert m._load_resume_state(p) == {0, 2}
