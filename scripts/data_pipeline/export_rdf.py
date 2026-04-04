"""Export the OpenEtruscan corpus as RDF/Turtle (Linked Open Data).

Ontologies used:
- LAWD (Linked Ancient World Data) for inscriptions
- Dublin Core (dc/dcterms) for metadata
- GeoSPARQL / WGS84 for spatial data
- CRMtex / CiTO for epigraphic references

Usage: .venv/bin/python scripts/export_rdf.py [--db data/corpus.db] [-o data/rdf/corpus.ttl]
"""

import argparse
import sqlite3
from pathlib import Path

# ── Namespace prefixes ──────────────────────────────────────────────
PREFIXES = """\
@prefix rdf:      <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:     <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:      <http://www.w3.org/2001/XMLSchema#> .
@prefix dc:       <http://purl.org/dc/elements/1.1/> .
@prefix dcterms:  <http://purl.org/dc/terms/> .
@prefix foaf:     <http://xmlns.com/foaf/0.1/> .
@prefix geo:      <http://www.w3.org/2003/01/geo/wgs84_pos#> .
@prefix lawd:     <http://lawd.info/ontology/> .
@prefix skos:     <http://www.w3.org/2004/02/skos/core#> .
@prefix pleiades: <https://pleiades.stoa.org/places/> .
@prefix gn:       <https://sws.geonames.org/> .
@prefix oe:       <https://openetruscan.com/inscription/> .
@prefix oeplace:  <https://openetruscan.com/place/> .
@prefix oevocab:  <https://openetruscan.com/vocabulary/> .

"""

# ── Helpers ─────────────────────────────────────────────────────────


def _escape_turtle(s: str) -> str:
    """Escape a string for Turtle literal format."""
    if s is None:
        return ""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _safe_uri(s: str) -> str:
    """Make a string safe for use in a URI local name."""
    return (
        s.replace(" ", "_")
        .replace("'", "")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .replace("'", "")
    )


# ── Main RDF generation ────────────────────────────────────────────


def export_rdf(db_path: str, output_path: str) -> None:
    """Export corpus to Turtle RDF."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all inscriptions
    rows = cursor.execute(
        "SELECT * FROM inscriptions WHERE canonical IS NOT NULL AND canonical != ''"
    ).fetchall()

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [PREFIXES]

    # ── Vocabulary: classification types ──
    lines.append("# === Classification Vocabulary ===\n")
    classifications = [
        "funerary",
        "votive",
        "dedicatory",
        "legal",
        "commercial",
        "boundary",
        "ownership",
    ]
    for cls in classifications:
        lines.append(f"oevocab:{cls} a skos:Concept ;")
        lines.append(f'    skos:prefLabel "{cls}"@en ;')
        lines.append("    skos:inScheme oevocab:InscriptionClassification .")
        lines.append("")

    lines.append("oevocab:InscriptionClassification a skos:ConceptScheme ;")
    lines.append('    dc:title "OpenEtruscan Inscription Classification"@en .')
    lines.append("")

    # ── Places ──
    lines.append("# === Places ===\n")
    place_rows = cursor.execute(
        "SELECT DISTINCT findspot, findspot_lat, findspot_lon, pleiades_id, geonames_id "
        "FROM inscriptions "
        "WHERE findspot IS NOT NULL AND findspot != '' "
        "ORDER BY findspot"
    ).fetchall()

    seen_places: set[str] = set()
    for p in place_rows:
        fs = p["findspot"]
        if fs in seen_places:
            continue
        seen_places.add(fs)
        uri = _safe_uri(fs)

        lines.append(f"oeplace:{uri} a lawd:Place ;")
        lines.append(f'    rdfs:label "{_escape_turtle(fs)}"@la ;')

        if p["pleiades_id"]:
            lines.append(f"    skos:closeMatch pleiades:{p['pleiades_id']} ;")
        if p["geonames_id"]:
            lines.append(f"    skos:closeMatch gn:{p['geonames_id']}/ ;")
        if p["findspot_lat"] is not None and p["findspot_lon"] is not None:
            lines.append(f'    geo:lat "{p["findspot_lat"]}"^^xsd:float ;')
            lines.append(f'    geo:long "{p["findspot_lon"]}"^^xsd:float ;')
        # Remove trailing semicolon and close
        if lines[-1].endswith(" ;"):
            lines[-1] = lines[-1][:-2] + " ."
        else:
            lines.append("    .")
        lines.append("")

    # ── Inscriptions ──
    lines.append("# === Inscriptions ===\n")
    count = 0
    for row in rows:
        iid = row["id"]
        canonical = _escape_turtle(row["canonical"])
        uri = _safe_uri(iid)

        lines.append(f"oe:{uri} a lawd:WrittenWork ;")
        lines.append(f'    dc:identifier "{_escape_turtle(iid)}" ;')
        lines.append(f'    lawd:hasText "{canonical}"@xet ;')
        lines.append('    dc:language "ett" ;')

        if row["findspot"]:
            place_uri = _safe_uri(row["findspot"])
            lines.append(f"    dcterms:spatial oeplace:{place_uri} ;")

        if row["date_approx"] is not None:
            lines.append(f'    dcterms:date "{row["date_approx"]}"^^xsd:integer ;')

        if row["classification"] and row["classification"] != "unknown":
            lines.append(f"    dcterms:type oevocab:{row['classification']} ;")

        if row["medium"]:
            lines.append(f'    dcterms:medium "{_escape_turtle(row["medium"])}" ;')

        if row["object_type"]:
            lines.append(f'    dc:type "{_escape_turtle(row["object_type"])}" ;')

        if row["pleiades_id"]:
            lines.append(f"    dcterms:spatial pleiades:{row['pleiades_id']} ;")

        if row["source"]:
            lines.append(f'    dc:source "{_escape_turtle(row["source"])}" ;')

        if row["bibliography"]:
            lines.append(
                f'    dcterms:bibliographicCitation "{_escape_turtle(row["bibliography"])}" ;'
            )

        # Close triple block
        if lines[-1].endswith(" ;"):
            lines[-1] = lines[-1][:-2] + " ."
        else:
            lines.append("    .")
        lines.append("")
        count += 1

    # Write file
    content = "\n".join(lines)
    out.write_text(content, encoding="utf-8")

    conn.close()

    size_kb = len(content.encode("utf-8")) / 1024
    print(f"  ✅ Exported {count} inscriptions + {len(seen_places)} places")
    print(f"  📁 {output_path} ({size_kb:.0f} KB)")
    print(f"  🔗 {sum(1 for r in rows if r['pleiades_id'])} Pleiades links")


def main():
    parser = argparse.ArgumentParser(description="Export corpus as RDF/Turtle")
    parser.add_argument("--db", default="data/corpus.db", help="Database path")
    parser.add_argument("-o", "--output", default="data/rdf/corpus.ttl", help="Output Turtle file")
    args = parser.parse_args()

    print("OpenEtruscan — RDF Export")
    print("=" * 50)
    export_rdf(args.db, args.output)


if __name__ == "__main__":
    main()
