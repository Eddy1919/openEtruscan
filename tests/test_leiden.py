"""Tests for the Leiden-convention parser."""

import pytest

from openetruscan.core.leiden import EditorialSpan, gap_extent, parse_leiden

# Each case: raw edition string, expected stripped text, expected spans
# as (kind, start, end, source), expected warning fragments.
CASES = [
    # No markup at all — parser must be a strict no-op.
    ("larθal", "larθal", [], []),
    ("", "", [], []),
    ("mi larθal śuθi", "mi larθal śuθi", [], []),
    # Supplied: editor's restoration of lost text.
    ("[larθ]al", "larθal", [("supplied", 0, 4, "[larθ]")], []),
    ("mi [lar]θal", "mi larθal", [("supplied", 3, 6, "[lar]")], []),
    # Expansion: editor spelling out an abbreviation.
    ("cl(an)", "clan", [("expansion", 2, 4, "(an)")], []),
    # Gap notation: dots/dashes inside brackets, one per lost letter.
    ("[.]", "", [("gap", 0, 0, "[.]")], ["unrestorable gap of width 1"]),
    ("[..]", "", [("gap", 0, 0, "[..]")], ["unrestorable gap of width 2"]),
    ("[...]", "", [("gap", 0, 0, "[...]")], ["unrestorable gap of width 3"]),
    ("[-]", "", [("gap", 0, 0, "[-]")], ["unrestorable gap of width 1"]),
    ("[--]", "", [("gap", 0, 0, "[--]")], ["unrestorable gap of width 2"]),
    ("[---]", "", [("gap", 0, 0, "[---]")], ["unrestorable gap of width 3"]),
    ("[- - -]", "", [("gap", 0, 0, "[- - -]")], ["unrestorable gap of width 3"]),
    ("[…]", "", [("gap", 0, 0, "[…]")], ["gap of unknown width"]),
    # Bare dash runs of three or more are gaps too; shorter runs are not.
    ("mi --- lar", "mi  lar", [("gap", 3, 3, "---")], ["unrestorable gap of width 3"]),
    ("mi-lar", "mi-lar", [], []),
    ("mi--lar", "mi--lar", [], []),
    # Unclear: combining dot below, decomposed and precomposed.
    ("θ̣", "θ", [("unclear", 0, 1, "θ̣")], []),
    ("ḍ", "d", [("unclear", 0, 1, "ḍ")], []),
    (
        "laṛθ",
        "larθ",
        [("unclear", 2, 3, "ṛ")],
        [],
    ),
    # Consecutive underdotted letters: one width-1 span per letter.
    (
        "θ̣ạ",
        "θa",
        [("unclear", 0, 1, "θ̣"), ("unclear", 1, 2, "ạ")],
        [],
    ),
    # Unclear: half brackets around damaged-but-legible text.
    ("⸢lar⸣θal", "larθal", [("unclear", 0, 3, "⸢lar⸣")], []),
    # Unbalanced markup must degrade gracefully, never crash.
    ("[larθal", "larθal", [], ["unbalanced editorial bracket"]),
    ("larθ]al", "larθal", [], ["unbalanced editorial bracket"]),
    ("(larθal", "larθal", [], ["unbalanced editorial bracket"]),
    ("lar)θal", "larθal", [], ["unbalanced editorial bracket"]),
    (
        "[lar)θ",
        "larθ",
        [],
        ["unbalanced editorial bracket", "unbalanced editorial bracket"],
    ),
    # Nesting: each group gets its own span, sorted by start offset.
    (
        "[la(rθ)al]",
        "larθal",
        [("supplied", 0, 6, "[la(rθ)al]"), ("expansion", 2, 4, "(rθ)")],
        [],
    ),
    # Empty brackets are an (empty) restoration, not a gap.
    ("la[]rθ", "larθ", [("supplied", 2, 2, "[]")], []),
]


class TestParseLeiden:
    """Table-driven coverage of every Leiden marker form."""

    @pytest.mark.parametrize(("raw", "text", "spans", "warnings"), CASES)
    def test_case(self, raw, text, spans, warnings):
        parse = parse_leiden(raw)
        assert parse.text == text
        assert [(s.kind, s.start, s.end, s.source) for s in parse.spans] == spans
        assert list(parse.warnings) == warnings

    def test_mixed_realistic_inscription(self):
        parse = parse_leiden("mi [lar]θ̣al (clan) [...] śuθi")
        assert parse.text == "mi larθal clan  śuθi"
        assert [(s.kind, s.start, s.end) for s in parse.spans] == [
            ("supplied", 3, 6),
            ("unclear", 6, 7),
            ("expansion", 10, 14),
            ("gap", 15, 15),
        ]
        assert parse.warnings == ("unrestorable gap of width 3",)
        # Span offsets index the stripped text: slicing must recover
        # exactly what the editor annotated.
        supplied = parse.spans[0]
        assert parse.text[supplied.start : supplied.end] == "lar"

    def test_spans_never_reference_markup(self):
        """No span offset may point at a character that is itself markup."""
        parse = parse_leiden("⸢mi⸣ [larθ]al (clan) θ̣")
        assert not any(marker in parse.text for marker in "[]()⸢⸣̣")
        for span in parse.spans:
            assert 0 <= span.start <= span.end <= len(parse.text)

    def test_stray_underdot_at_start(self):
        parse = parse_leiden("̣lar")
        assert parse.text == "lar"
        assert parse.spans == ()
        assert parse.warnings == ("stray combining underdot",)


class TestGapExtent:
    def test_counted_widths(self):
        assert gap_extent("[...]") == 3
        assert gap_extent("[--]") == 2
        assert gap_extent("---") == 3
        assert gap_extent("[- - -]") == 3

    def test_unknown_width(self):
        assert gap_extent("[…]") is None


class TestEditorialSpan:
    def test_frozen(self):
        span = EditorialSpan("supplied", 0, 3, "[mi]")
        with pytest.raises(AttributeError):
            span.start = 1  # type: ignore[misc]
