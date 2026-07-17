"""Tests for Leiden apparatus markup in the EpiDoc exporter.

The exporter must turn editorial spans into real TEI elements — <supplied>,
<ex>, <gap/>, <unclear> — instead of dumping bracket characters into <ab>,
and must produce byte-for-byte the old output when an inscription carries no
markup at all.
"""

import xml.etree.ElementTree as ET

from openetruscan.core.corpus import Inscription
from openetruscan.core.epidoc import inscription_to_epidoc, results_to_epidoc
from openetruscan.core.normalizer import normalize

TEI_NS = "{http://www.tei-c.org/ns/1.0}"


def _make_inscription(raw_text: str, insc_id: str = "T1") -> Inscription:
    """Build an Inscription the way ingestion does: canonical via normalize."""
    result = normalize(raw_text)
    return Inscription(
        id=insc_id,
        raw_text=raw_text,
        canonical=result.canonical,
        phonetic=result.phonetic,
        old_italic=result.old_italic,
    )


class TestInscriptionToEpidoc:
    def test_marked_input_emits_apparatus_elements(self):
        insc = _make_inscription("mi [lar]θ̣al (clan) [...] śuθi")
        xml = inscription_to_epidoc(insc)
        root = ET.fromstring(xml)
        ab = root.find(f".//{TEI_NS}div[@type='edition']/{TEI_NS}ab")
        assert ab is not None

        supplied = ab.find(f"{TEI_NS}supplied")
        assert supplied is not None
        assert supplied.get("reason") == "lost"
        assert supplied.text == "lar"

        unclear = ab.find(f"{TEI_NS}unclear")
        assert unclear is not None
        assert unclear.text == "θ"

        ex = ab.find(f"{TEI_NS}ex")
        assert ex is not None
        assert ex.text == "clan"

        gap = ab.find(f"{TEI_NS}gap")
        assert gap is not None
        assert gap.get("reason") == "lost"
        assert gap.get("quantity") == "3"
        assert gap.get("unit") == "character"

        # No literal Leiden markup anywhere in the edition text.
        edition_text = "".join(ab.itertext())
        assert not set("[]()̣") & set(edition_text)

    def test_unknown_width_gap_uses_extent(self):
        insc = _make_inscription("mi […] lar")
        xml = inscription_to_epidoc(insc)
        root = ET.fromstring(xml)
        gap = root.find(f".//{TEI_NS}ab/{TEI_NS}gap")
        assert gap is not None
        assert gap.get("extent") == "unknown"
        assert gap.get("quantity") is None

    def test_clean_input_unchanged(self):
        """No markup → the exact plain <ab> dump we shipped before."""
        insc = _make_inscription("mi larθal śuθi")
        xml = inscription_to_epidoc(insc)
        assert "<ab>mi larθal śuθi</ab>" in xml
        for tag in ("<supplied", "<gap", "<unclear", "<ex>"):
            assert tag not in xml


class TestResultsToEpidoc:
    def test_marked_input_emits_apparatus_elements(self):
        insc = _make_inscription("[mi] lar(θal) [...] θ̣i")
        xml = results_to_epidoc([insc])
        assert '<supplied reason="lost">mi</supplied>' in xml
        assert "<ex>θal</ex>" in xml
        assert '<gap reason="lost" quantity="3" unit="character"/>' in xml
        assert "<unclear>θ</unclear>" in xml
        assert "[" not in xml.split("<body>")[1]

    def test_clean_input_unchanged(self):
        insc = _make_inscription("mi larθal")
        xml = results_to_epidoc([insc])
        assert "    mi larθal" in xml
        for tag in ("<supplied", "<gap", "<unclear", "<ex>"):
            assert tag not in xml

    def test_legacy_bracketed_canonical_falls_back_to_plain_dump(self):
        """Rows ingested before the Leiden fix may store literal brackets in
        canonical; their raw_text no longer re-normalizes to that string, so
        the exporter must not attach mismatched span offsets — it keeps the
        old verbatim dump instead."""
        insc = Inscription(id="L1", raw_text="[mi] lar", canonical="[mi] lar")
        xml = results_to_epidoc([insc])
        assert "[mi] lar" in xml
        assert "<supplied" not in xml
