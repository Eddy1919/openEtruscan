"""
EpiDoc XML exporter — generate TEI/EpiDoc XML from inscriptions.

EpiDoc is the standard for encoding ancient texts in XML, used by:
- Papyri.info, EDH, EAGLE, I.Sicily, and virtually all digital epigraphy projects.

This module generates valid EpiDoc XML from our Inscription objects,
enabling interoperability with the entire digital classics ecosystem.

Requires: lxml (optional dependency, install with `pip install openetruscan[epidoc]`)
"""

from __future__ import annotations

import contextlib
import xml.etree.ElementTree as ET  # nosec B405
from collections.abc import Iterator

# Register the TEI namespace to avoid ns0: prefix in output
ET.register_namespace("", "http://www.tei-c.org/ns/1.0")


def inscription_to_epidoc(inscription, language: str = "xet") -> str:
    """
    Convert an Inscription to EpiDoc XML string.

    Args:
        inscription: An Inscription object from openetruscan.corpus.
        language: ISO 639-3 language code (xet = Etruscan).

    Returns:
        A string of valid EpiDoc XML.
    """
    root = ET.Element("TEI")
    root.set("xmlns", "http://www.tei-c.org/ns/1.0")

    # teiHeader
    header = ET.SubElement(root, "teiHeader")
    file_desc = ET.SubElement(header, "fileDesc")

    # titleStmt
    title_stmt = ET.SubElement(file_desc, "titleStmt")
    title = ET.SubElement(title_stmt, "title")
    title.text = f"Inscription {inscription.id}"

    # publicationStmt
    pub_stmt = ET.SubElement(file_desc, "publicationStmt")
    authority = ET.SubElement(pub_stmt, "authority")
    authority.text = "OpenEtruscan"
    idno = ET.SubElement(pub_stmt, "idno")
    idno.set("type", "OpenEtruscan")
    idno.text = inscription.id
    availability = ET.SubElement(pub_stmt, "availability")
    licence = ET.SubElement(availability, "licence")
    licence.set("target", "https://creativecommons.org/publicdomain/zero/1.0/")
    licence.text = "CC0 1.0 Universal"

    # sourceDesc
    source_desc = ET.SubElement(file_desc, "sourceDesc")
    ms_desc = ET.SubElement(source_desc, "msDesc")

    # msIdentifier
    ms_id = ET.SubElement(ms_desc, "msIdentifier")
    if inscription.findspot:
        settlement = ET.SubElement(ms_id, "settlement")
        settlement.text = inscription.findspot

    # physDesc
    if inscription.medium or inscription.object_type:
        phys_desc = ET.SubElement(ms_desc, "physDesc")
        obj_desc = ET.SubElement(phys_desc, "objectDesc")
        support_desc = ET.SubElement(obj_desc, "supportDesc")
        support = ET.SubElement(support_desc, "support")
        if inscription.medium:
            material = ET.SubElement(support, "material")
            material.text = inscription.medium
        if inscription.object_type:
            obj_type = ET.SubElement(support, "objectType")
            obj_type.text = inscription.object_type

    # history
    history = ET.SubElement(ms_desc, "history")
    origin = ET.SubElement(history, "origin")

    if inscription.date_approx is not None:
        orig_date = ET.SubElement(origin, "origDate")
        year = inscription.date_approx
        if inscription.date_uncertainty:
            orig_date.set(
                "notBefore-custom",
                str(year - inscription.date_uncertainty),
            )
            orig_date.set(
                "notAfter-custom",
                str(year + inscription.date_uncertainty),
            )
        else:
            orig_date.set("when-custom", str(year))
        orig_date.text = inscription.date_display()

    if inscription.findspot:
        orig_place = ET.SubElement(origin, "origPlace")
        orig_place.text = inscription.findspot
        if inscription.findspot_lat is not None and inscription.findspot_lon is not None:
            geo = ET.SubElement(orig_place, "geo")
            geo.text = f"{inscription.findspot_lat} {inscription.findspot_lon}"

    # text body
    text = ET.SubElement(root, "text")
    body = ET.SubElement(text, "body")
    div = ET.SubElement(body, "div")
    div.set("type", "edition")
    div.set("xml:lang", language)

    ab = ET.SubElement(div, "ab")
    ab.text = inscription.canonical

    # apparatus / translation
    if inscription.notes:
        div_translation = ET.SubElement(body, "div")
        div_translation.set("type", "translation")
        p = ET.SubElement(div_translation, "p")
        p.text = inscription.notes

    # bibliography
    if inscription.bibliography:
        div_bib = ET.SubElement(body, "div")
        div_bib.set("type", "bibliography")
        bibl = ET.SubElement(div_bib, "bibl")
        bibl.text = inscription.bibliography

    return _indent_xml(ET.tostring(root, encoding="unicode"))


def results_to_epidoc(
    results: Iterator | list,
    language: str = "xet",
) -> str:
    """
    Export an iterable of Inscription objects as a multi-document EpiDoc collection.
    """
    # handle both SearchResults and simple lists
    inscriptions = results.inscriptions if hasattr(results, "inscriptions") else results

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">',
        "<teiHeader>",
        "  <fileDesc>",
        "    <titleStmt>",
        "      <title>OpenEtruscan Corpus</title>",
        "    </titleStmt>",
        "    <publicationStmt>",
        "      <authority>OpenEtruscan</authority>",
        "      <licence target="
        '"https://creativecommons.org/publicdomain/zero/1.0/">'
        "CC0 1.0</licence>",
        "    </publicationStmt>",
        "    <sourceDesc><p>Aggregated corpus</p></sourceDesc>",
        "  </fileDesc>",
        "</teiHeader>",
        "<text>",
        "<body>",
    ]

    for inscription in inscriptions:
        parts.append(f'<div type="textpart" n="{inscription.id}">')
        parts.append(f'  <ab xml:lang="{language}">')
        parts.append(f"    {_escape_xml(inscription.canonical)}")
        parts.append("  </ab>")
        if inscription.notes:
            parts.append('  <div type="translation">')
            parts.append(f"    <p>{_escape_xml(inscription.notes)}</p>")
            parts.append("  </div>")
        parts.append("</div>")

    parts.extend(["</body>", "</text>", "</TEI>"])
    return "\n".join(parts)


def corpus_to_epidoc(
    corpus,
    language: str = "xet",
    limit: int = 0,
) -> str:
    """
    Export an entire corpus as a multi-document EpiDoc collection.

    Args:
        corpus: A Corpus instance.
        language: ISO 639-3 language code.
        limit: Max inscriptions (0 = all).

    Returns:
        EpiDoc XML string with all inscriptions.
    """
    results = corpus.search(limit=limit if limit > 0 else 999999)
    return results_to_epidoc(results, language=language)


def epidoc_iterator(
    corpus,
    language: str = "xet",
) -> Iterator[str]:
    """
    Yield individual EpiDoc XML strings, one per inscription.

    Memory-efficient for large corpora.
    """
    results = corpus.search(limit=999999)
    for inscription in results:
        yield inscription_to_epidoc(inscription, language=language)


def _indent_xml(xml_str: str) -> str:
    """Simple XML indentation."""
    try:
        root = ET.fromstring(xml_str)  # nosec B314
        ET.indent(root)
        return ET.tostring(root, encoding="unicode")
    except Exception:
        return xml_str


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def parse_epidoc(xml_str: str):
    """
    Parse an EpiDoc XML string into an Inscription object.

    Args:
        xml_str: EpiDoc TEI XML string.

    Returns:
        An Inscription object populated with parsed data.
    """
    from openetruscan.corpus import Inscription

    try:
        from defusedxml.ElementTree import fromstring as safe_fromstring

        root = safe_fromstring(xml_str)
    except Exception as e:
        raise ValueError(f"Invalid XML: {e}")

    ns = {"tei": "http://www.tei-c.org/ns/1.0"}

    def get_text(xpath: str, element=root) -> str | None:
        el = element.find(xpath, ns)
        return el.text.strip() if el is not None and el.text else None

    id_val = get_text(".//tei:publicationStmt/tei:idno")
    if not id_val:
        import hashlib

        id_val = f"tei_{hashlib.md5(xml_str.encode(), usedforsecurity=False).hexdigest()[:8]}"

    findspot = (
        get_text(".//tei:origin/tei:origPlace")
        or get_text(".//tei:msIdentifier//tei:settlement")
        or ""
    )

    date_approx = None
    date_uncertainty = None
    orig_date = root.find(".//tei:origin/tei:origDate", ns)
    if orig_date is not None:
        when = orig_date.get("when-custom")
        if when:
            with contextlib.suppress(ValueError):
                date_approx = int(when)
        else:
            nb = orig_date.get("notBefore-custom")
            na = orig_date.get("notAfter-custom")
            if nb and na:
                try:
                    n_b = int(nb)
                    n_a = int(na)
                    date_approx = (n_b + n_a) // 2
                    date_uncertainty = abs(n_a - n_b) // 2
                except ValueError:
                    pass

    findspot_lat = None
    findspot_lon = None
    geo = get_text(".//tei:origin/tei:origPlace/tei:geo")
    if geo:
        parts = geo.split()
        if len(parts) >= 2:
            try:
                findspot_lat = float(parts[0])
                findspot_lon = float(parts[1])
            except ValueError:
                pass

    medium = get_text(".//tei:supportDesc//tei:material") or ""
    object_type = get_text(".//tei:supportDesc//tei:objectType") or ""

    canonical = get_text(".//tei:body//tei:div[@type='edition']//tei:ab") or ""
    raw_text = canonical

    notes = get_text(".//tei:body//tei:div[@type='translation']//tei:p") or ""
    bibliography = get_text(".//tei:body//tei:div[@type='bibliography']//tei:bibl") or ""

    return Inscription(
        id=id_val,
        raw_text=raw_text,
        canonical=canonical,
        findspot=findspot,
        findspot_lat=findspot_lat,
        findspot_lon=findspot_lon,
        date_approx=date_approx,
        date_uncertainty=date_uncertainty,
        medium=medium,
        object_type=object_type,
        notes=notes,
        bibliography=bibliography,
    )
