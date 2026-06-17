"""
Unit tests for the Recogito round-trip (openetruscan.core.recogito).

No network: fixtures are small Recogito-shaped CSV strings.
"""

from openetruscan.core.recogito import (
    UploadRow,
    build_upload_table,
    extract_pleiades_links,
    extract_tag_decisions,
    parse_recogito_csv,
    pleiades_id_from_uri,
)

# A Recogito-2-style annotation export.
RECOGITO_CSV = (
    "UUID,FILE,TYPE,QUOTE_TRANSCRIPTION,LABEL,TAGS,COMMENTS,URI,LAT,LNG,VERIFICATION_STATUS\n"
    "u1,AT 1.1,PLACE,Tarchna,Tarquinii,funerary,,"
    "https://pleiades.stoa.org/places/413332,42.25,11.76,VERIFIED\n"
    "u2,AT 1.2,PLACE,Clusii,Clusium,ownership|votive,note,"
    "https://pleiades.stoa.org/places/413047,43.0,11.9,VERIFIED\n"
    "u3,AT 1.3,PLACE,Nowhere,,,,,,,REJECTED\n"
    "u4,AT 1.4,PERSON,Larth,,,,https://www.wikidata.org/entity/Q1,,,\n"
)


class TestParse:
    def test_parses_all_rows(self):
        anns = parse_recogito_csv(RECOGITO_CSV)
        assert len(anns) == 4

    def test_normalises_fields(self):
        anns = parse_recogito_csv(RECOGITO_CSV)
        a = anns[0]
        assert a.file == "AT 1.1"
        assert a.ann_type == "PLACE"
        assert a.quote == "Tarchna"
        assert a.tags == ("funerary",)
        assert a.lat == 42.25 and a.lng == 11.76

    def test_tag_splitting(self):
        anns = parse_recogito_csv(RECOGITO_CSV)
        assert anns[1].tags == ("ownership", "votive")

    def test_rejected_flag(self):
        anns = parse_recogito_csv(RECOGITO_CSV)
        assert anns[2].is_rejected is True
        assert anns[0].is_rejected is False

    def test_tolerant_header_aliases(self):
        # Different but recognised header names should still map.
        csv_alt = (
            "id,document,entity_type,transcription,place_uri,status\n"
            "x,DOC,PLACE,Perusiae,https://pleiades.stoa.org/places/393839,VERIFIED\n"
        )
        [a] = parse_recogito_csv(csv_alt)
        assert a.uuid == "x" and a.file == "DOC" and a.quote == "Perusiae"
        assert a.uri.endswith("393839")

    def test_empty_input(self):
        assert parse_recogito_csv("") == []


class TestPleiadesExtraction:
    def test_id_from_uri(self):
        assert pleiades_id_from_uri("https://pleiades.stoa.org/places/413332") == "413332"
        assert pleiades_id_from_uri("https://www.wikidata.org/entity/Q1") is None
        assert pleiades_id_from_uri("") is None

    def test_harvest_links(self):
        links = extract_pleiades_links(parse_recogito_csv(RECOGITO_CSV))
        assert links == {"Tarchna": "413332", "Clusii": "413047"}

    def test_rejected_place_excluded(self):
        links = extract_pleiades_links(parse_recogito_csv(RECOGITO_CSV))
        assert "Nowhere" not in links

    def test_person_excluded(self):
        # u4 is a PERSON with a non-Pleiades URI — must not appear.
        links = extract_pleiades_links(parse_recogito_csv(RECOGITO_CSV))
        assert "Larth" not in links


class TestTagDecisions:
    def test_per_document_tags(self):
        decisions = extract_tag_decisions(parse_recogito_csv(RECOGITO_CSV))
        assert decisions["AT 1.1"] == ["funerary"]
        assert decisions["AT 1.2"] == ["ownership", "votive"]

    def test_untagged_documents_absent(self):
        decisions = extract_tag_decisions(parse_recogito_csv(RECOGITO_CSV))
        assert "AT 1.3" not in decisions


class TestUploadTable:
    def test_round_trips_through_parse(self):
        rows = [
            UploadRow(id="1085", text="arnt ziχn(i)al", extra={"jury": "funerary/unsure"}),
            UploadRow(id="1154", text="miaratiaialtamenei", extra={"jury": "ownership"}),
        ]
        csv_text = build_upload_table(rows, extra_columns=["jury"])
        # First line is the header.
        header = csv_text.splitlines()[0]
        assert header == "id,text,jury"
        # And it parses back as a normal CSV with our two rows.
        import csv as _csv
        import io as _io

        parsed = list(_csv.DictReader(_io.StringIO(csv_text)))
        assert [r["id"] for r in parsed] == ["1085", "1154"]
        assert parsed[0]["text"] == "arnt ziχn(i)al"
        assert parsed[1]["jury"] == "ownership"

    def test_missing_extra_is_blank(self):
        rows = [UploadRow(id="1", text="x")]
        csv_text = build_upload_table(rows, extra_columns=["jury"])
        import csv as _csv
        import io as _io

        [parsed] = list(_csv.DictReader(_io.StringIO(csv_text)))
        assert parsed["jury"] == ""
