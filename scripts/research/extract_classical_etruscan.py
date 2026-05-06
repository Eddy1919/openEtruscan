"""Mine the Perseus classical-texts corpus for Etruscan-mentioning passages.

Walks every Latin/Greek primary source in
``data/classical_texts/formatted/`` (Perseus TEI XML), extracts paragraphs
that mention Etruscan/Tyrrhenian, and emits structured JSONL with the
cleaned passage + locus metadata.

The downstream consumer (a contrastive fine-tune of LaBSE) will:
  1. Mine explicit bilingual gloss patterns (Etruscan word → Latin/Greek
     equivalent attested in a primary source).
  2. Use the rest as contextual semantic enrichment for Etruscan tokens.

Two output streams:
  --bilingual_glosses_path   regex-extracted (Etruscan, Latin/Greek)
                             pairs with attribution (~tens to hundreds)
  --passages_path            full Etruscan-mentioning passages (~1500-2000)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger("extract_classical")

NS = {"tei": "http://www.tei-c.org/ns/1.0"}

# Match anything Etruscan-related across Latin and Greek.
ETRUSCAN_RE = re.compile(
    r"Etrusc|Tusc[oaeisu]|Tyrrhen|Τυρρην|Τυρσην|Ἐτρουσκ|Ἐτρυσκ|Τυρρηνί",
    re.UNICODE | re.IGNORECASE,
)

# Bilingual gloss patterns — these are the GOLD: ancient grammarians or
# historians explicitly mapping a foreign word to its Latin/Greek equivalent.
LATIN_GLOSS_PATTERNS = [
    # "X — quod Etrusci Y vocant/dicunt/appellant"
    re.compile(
        r"\b(?P<lat>[a-z]{3,20})\b[^.]{0,80}?\b(?:quod|quem|quam)\b[^.]{0,40}?"
        r"(?:Etrusc[ioa]|Tusc[ioa])[^.]{0,80}?\b(?P<etr>[a-zθχσφ]{2,30})\b",
        re.IGNORECASE,
    ),
    # "Etrusci [linguā [suā]] X [appellant/dicunt/vocant] [Y]"
    re.compile(
        r"(?:Etrusc[ioa]|Tusc[ioa])\b[^.]{0,40}?\b(?P<etr>[a-zθχσφ]{2,30})\b"
        r"[^.]{0,40}?\b(?:appellant|appellatur|dicunt|dicitur|vocant|vocatur|uocant|uocatur)\b"
        r"[^.]{0,40}?\b(?P<lat>[a-z]{3,20})\b",
        re.IGNORECASE,
    ),
    # "X enim ... lingua Tusca Y dicitur" (Suetonius pattern for "aesar")
    re.compile(
        r"\b(?P<etr>[a-zθχσφ]{2,30})\b[^.]{0,40}?\blingua\s+Tusca\b[^.]{0,40}?"
        r"\b(?P<lat>[a-z]{3,20})\b",
        re.IGNORECASE,
    ),
]

GREEK_GLOSS_PATTERNS = [
    # "Τυρρηνοὶ ... X καλοῦσι ... Y"
    re.compile(
        r"Τυρρην\w+[^.]{0,80}?\b(?P<etr>[\w]{2,30})\b[^.]{0,40}?"
        r"\bκαλο(?:υσι|ῦσι|ύμενον|υμένη)\b[^.]{0,40}?\b(?P<grc>[\w]{2,30})\b",
        re.UNICODE,
    ),
    # "ὃν|ἣν|ὃ Ἕλληνες X καλοῦσι(ν)"
    re.compile(
        r"(?:ὃν|ἣν|ὃ)\s+Ἕλλην\w+[^.]{0,40}?\b(?P<grc>[\w]{2,30})\b[^.]{0,40}?"
        r"\bκαλο(?:υσι|ῦσι)\b",
        re.UNICODE,
    ),
]

# Editorial / apparatus noise we strip from cleaned passages
APPARATUS_NOISE = re.compile(
    r"(?:\s\b[A-Z]\s\b\d+\b|\s\b[A-Z]{1,3}\s+[a-z]{1,3}\b|"
    r"\s\b[A-Z][12]\b|\s\bcod\.?\b)",
    re.UNICODE,
)


def _clean_text(t: str) -> str:
    """Collapse whitespace and strip the most obvious editorial apparatus."""
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_paragraphs(xml_path: Path) -> list[str]:
    """Return the textual paragraphs from a TEI XML file."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        logger.warning("XML parse error in %s: %s", xml_path, e)
        return []
    root = tree.getroot()
    body = root.find(".//tei:text/tei:body", NS)
    if body is None:
        return []
    paras: list[str] = []
    # Try <p> first (most prose), fall back to <div>/<l> if absent
    for tag in ("tei:p", "tei:div", "tei:l"):
        for elem in body.findall(f".//{tag}", NS):
            text = " ".join(elem.itertext())
            text = _clean_text(text)
            if len(text) >= 20:
                paras.append(text)
        if paras:
            break
    return paras


def _file_meta(xml_path: Path, formatted_root: Path) -> dict[str, str]:
    """{author, work, language} derived from the path under formatted/."""
    rel = xml_path.relative_to(formatted_root)
    parts = rel.parts
    # formatted/<Latin|Greek>/<Author>/<Work_..._lang.xml>
    if len(parts) >= 3:
        language = parts[0]  # "Latin" or "Greek"
        author = parts[1]
        # Strip CTS suffix: "Naturalis Historia_phi0978.phi001.perseus-lat2.xml"
        work = parts[-1].split("_")[0]
        return {"author": author, "work": work, "language": language}
    return {"author": "?", "work": xml_path.stem, "language": "?"}


def _is_target_lang(xml_path: Path) -> bool:
    """Keep only the *original-language* edition (lat or grc), not English."""
    name = xml_path.name.lower()
    return "perseus-lat" in name or "perseus-grc" in name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--formatted-root", default=str(
            Path(__file__).resolve().parent.parent.parent.parent
            / "data" / "classical_texts" / "formatted"
        ),
    )
    parser.add_argument(
        "--passages-path", required=True,
        help="JSONL output: every Etruscan-mentioning paragraph",
    )
    parser.add_argument(
        "--bilingual-glosses-path", required=True,
        help="JSONL output: regex-extracted attested bilingual pairs",
    )
    parser.add_argument(
        "--include-authors", default=None,
        help="Comma-separated substring filter for author dirs (default: all)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    formatted_root = Path(args.formatted_root)
    if not formatted_root.exists():
        logger.error("formatted root %s not found", formatted_root)
        return 2

    include = None
    if args.include_authors:
        include = [s.strip() for s in args.include_authors.split(",")]

    xml_files = [
        p for p in formatted_root.rglob("*.xml")
        if _is_target_lang(p)
        and (include is None or any(s in str(p) for s in include))
    ]
    logger.info("Will scan %d original-language XML files", len(xml_files))

    passages_path = Path(args.passages_path)
    glosses_path = Path(args.bilingual_glosses_path)
    passages_path.parent.mkdir(parents=True, exist_ok=True)
    glosses_path.parent.mkdir(parents=True, exist_ok=True)

    n_passages = n_glosses = 0
    n_files_with_match = 0
    by_author: dict[str, int] = {}

    with passages_path.open("w", encoding="utf-8") as f_pass, \
         glosses_path.open("w", encoding="utf-8") as f_gl:
        for x in sorted(xml_files):
            meta = _file_meta(x, formatted_root)
            paras = _extract_paragraphs(x)
            file_had_match = False
            for para in paras:
                if not ETRUSCAN_RE.search(para):
                    continue
                f_pass.write(json.dumps({**meta, "text": para}, ensure_ascii=False) + "\n")
                n_passages += 1
                file_had_match = True
                by_author[meta["author"]] = by_author.get(meta["author"], 0) + 1
                # Probe gloss patterns
                patterns = (
                    LATIN_GLOSS_PATTERNS if meta["language"] == "Latin"
                    else GREEK_GLOSS_PATTERNS
                )
                for pat in patterns:
                    for m in pat.finditer(para):
                        gd = m.groupdict()
                        f_gl.write(json.dumps(
                            {**meta, "match": m.group(0)[:300], **gd},
                            ensure_ascii=False,
                        ) + "\n")
                        n_glosses += 1
            if file_had_match:
                n_files_with_match += 1

    logger.info("DONE: %d passages, %d gloss-pattern hits, %d files contributing",
                n_passages, n_glosses, n_files_with_match)
    logger.info("Top contributing authors:")
    for author, n in sorted(by_author.items(), key=lambda x: -x[1])[:15]:
        logger.info("  %s: %d", author, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
