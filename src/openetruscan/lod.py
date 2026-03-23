"""
Linked Open Data — Pelagios / Pleiades integration for OpenEtruscan.

Generates JSON-LD feeds compatible with the Pelagios ecosystem,
linking our corpus inscriptions to Pleiades ancient place URIs.

See: https://pelagios.org and https://pleiades.stoa.org
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

PLEIADES_BASE = "https://pleiades.stoa.org/places/"
OPENETRUSCAN_BASE = "https://openetruscan.com"

_mapping_cache: dict[str, str] | None = None


def _load_pleiades_mapping() -> dict[str, str]:
    """Load the findspot → Pleiades ID mapping from YAML."""
    global _mapping_cache
    if _mapping_cache is not None:
        return _mapping_cache

    mapping_path = (
        Path(__file__).parent.parent.parent / "data" / "pleiades_mapping.yaml"
    )
    if not mapping_path.exists():
        _mapping_cache = {}
        return _mapping_cache

    with open(mapping_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Filter out empty values
    _mapping_cache = {
        k: v for k, v in raw.items() if v
    }
    return _mapping_cache


def get_pleiades_uri(findspot: str) -> str | None:
    """
    Get the Pleiades URI for a findspot name.

    Returns None if the findspot is not in the mapping.
    """
    mapping = _load_pleiades_mapping()
    pleiades_id = mapping.get(findspot)
    if pleiades_id:
        return f"{PLEIADES_BASE}{pleiades_id}"
    return None


def inscription_to_jsonld(inscription, language: str = "ett") -> dict:
    """
    Convert an Inscription to a Pelagios-compatible JSON-LD annotation.

    Follows the Pelagios Annotation model:
    https://github.com/pelagios/pelagios-cookbook/wiki
    """
    pleiades_uri = None
    if inscription.findspot:
        pleiades_uri = get_pleiades_uri(inscription.findspot)

    annotation = {
        "@context": "http://www.w3.org/ns/anno.jsonld",
        "id": f"{OPENETRUSCAN_BASE}/inscriptions/{inscription.id}",
        "type": "Annotation",
        "body": [
            {
                "type": "TextualBody",
                "value": inscription.canonical or inscription.raw_text,
                "language": language,
                "format": "text/plain",
            }
        ],
        "target": {
            "source": f"{OPENETRUSCAN_BASE}/inscriptions/{inscription.id}",
            "type": "Text",
        },
    }

    if pleiades_uri:
        annotation["body"].append(
            {
                "type": "SpecificResource",
                "source": pleiades_uri,
                "purpose": "identifying",
            }
        )

    if (
        inscription.findspot_lat is not None
        and inscription.findspot_lon is not None
    ):
        annotation["target"]["selector"] = {
            "type": "SvgSelector",
            "value": (
                f"<svg><circle cx='{inscription.findspot_lon}' "
                f"cy='{inscription.findspot_lat}' r='0.01'/></svg>"
            ),
        }

    return annotation


def corpus_to_pelagios_jsonld(
    corpus, language: str = "ett", limit: int = 0,
) -> str:
    """
    Export the entire corpus as a Pelagios-compatible JSON-LD collection.

    Args:
        corpus: A Corpus instance.
        language: ISO 639-3 language code.
        limit: Max inscriptions (0 = all).

    Returns:
        JSON-LD string with all annotations.
    """
    search_limit = limit if limit > 0 else 999999
    results = corpus.search(limit=search_limit)

    annotations = []
    for inscription in results:
        ann = inscription_to_jsonld(inscription, language=language)
        # Only include if we have a Pleiades link
        has_pleiades = any(
            b.get("purpose") == "identifying"
            for b in ann.get("body", [])
            if isinstance(b, dict)
        )
        if has_pleiades:
            annotations.append(ann)

    collection = {
        "@context": "http://www.w3.org/ns/anno.jsonld",
        "id": f"{OPENETRUSCAN_BASE}/pelagios.jsonld",
        "type": "AnnotationCollection",
        "label": "OpenEtruscan Inscriptions",
        "total": len(annotations),
        "first": {
            "type": "AnnotationPage",
            "items": annotations,
        },
    }

    return json.dumps(collection, ensure_ascii=False, indent=2)


def pleiades_stats(corpus) -> dict[str, int]:
    """
    Get statistics on Pleiades coverage in the corpus.

    Returns a dict of {pleiades_uri: count}.
    """
    results = corpus.search(limit=999999)
    stats: dict[str, int] = {}
    for inscription in results:
        if inscription.findspot:
            uri = get_pleiades_uri(inscription.findspot)
            if uri:
                stats[uri] = stats.get(uri, 0) + 1
    return dict(sorted(stats.items(), key=lambda x: -x[1]))
