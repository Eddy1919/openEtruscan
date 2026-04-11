"""
Linked Open Data — Pelagios / Pleiades / Trismegistos / EAGLE integration.

Generates JSON-LD feeds compatible with the Pelagios ecosystem,
linking our corpus inscriptions to Pleiades ancient place URIs,
Trismegistos text records, and EAGLE network inscriptions.

See: https://pelagios.org, https://pleiades.stoa.org,
     https://www.trismegistos.org, https://www.eagle-network.eu
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

PLEIADES_BASE = "https://pleiades.stoa.org/places/"
TRISMEGISTOS_BASE = "https://www.trismegistos.org/text/"
EAGLE_BASE = "https://www.eagle-network.eu/resource/inscriptions/"
OPENETRUSCAN_BASE = "https://openetruscan.com"

_mapping_cache: dict[str, str] | None = None
_tm_mapping_cache: dict[str, str] | None = None
_eagle_mapping_cache: dict[str, str] | None = None


def _load_yaml_mapping(filename: str) -> dict[str, str]:
    """Load a YAML mapping file from the data directory."""
    mapping_path = Path(__file__).parent.parent.parent / "data" / filename
    if not mapping_path.exists():
        return {}
    with open(mapping_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {str(k): str(v) for k, v in raw.items() if v}


def _load_pleiades_mapping() -> dict[str, str]:
    """Load the findspot → Pleiades ID mapping from YAML."""
    global _mapping_cache
    if _mapping_cache is not None:
        return _mapping_cache

    mapping_path = Path(__file__).parent.parent.parent / "data" / "pleiades_mapping.yaml"
    if not mapping_path.exists():
        _mapping_cache = {}
        return _mapping_cache

    with open(mapping_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Filter out empty values
    _mapping_cache = {k: v for k, v in raw.items() if v}
    return _mapping_cache


def _load_trismegistos_mapping() -> dict[str, str]:
    """Load the inscription_id → TM ID mapping from YAML."""
    global _tm_mapping_cache
    if _tm_mapping_cache is not None:
        return _tm_mapping_cache
    _tm_mapping_cache = _load_yaml_mapping("trismegistos_mapping.yaml")
    return _tm_mapping_cache


def _load_eagle_mapping() -> dict[str, str]:
    """Load the inscription_id → EAGLE ID mapping from YAML."""
    global _eagle_mapping_cache
    if _eagle_mapping_cache is not None:
        return _eagle_mapping_cache
    _eagle_mapping_cache = _load_yaml_mapping("eagle_mapping.yaml")
    return _eagle_mapping_cache


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


def get_trismegistos_uri(inscription_id: str) -> str | None:
    """
    Get the Trismegistos URI for an inscription ID.

    Returns None if no TM mapping exists.
    """
    mapping = _load_trismegistos_mapping()
    tm_id = mapping.get(inscription_id)
    if tm_id:
        return f"{TRISMEGISTOS_BASE}{tm_id}"
    return None


def get_eagle_uri(inscription_id: str) -> str | None:
    """
    Get the EAGLE network URI for an inscription ID.

    Returns None if no EAGLE mapping exists.
    """
    mapping = _load_eagle_mapping()
    eagle_id = mapping.get(inscription_id)
    if eagle_id:
        return f"{EAGLE_BASE}{eagle_id}"
    return None


def inscription_to_jsonld(inscription, language: str = "ett") -> dict:
    """
    Convert an Inscription to a Pelagios-compatible JSON-LD annotation.

    Includes Pleiades, Trismegistos, and EAGLE URIs when available.
    """
    pleiades_uri = None
    if inscription.findspot:
        pleiades_uri = get_pleiades_uri(inscription.findspot)

    tm_uri = get_trismegistos_uri(inscription.id)
    eagle_uri = get_eagle_uri(inscription.id)

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

    if tm_uri:
        annotation["body"].append(
            {
                "type": "SpecificResource",
                "source": tm_uri,
                "purpose": "identifying",
            }
        )

    if eagle_uri:
        annotation["body"].append(
            {
                "type": "SpecificResource",
                "source": eagle_uri,
                "purpose": "identifying",
            }
        )

    # 4. Handle Spatial selectors if coordinates are present
    # Pelagios uses SVG selectors or WKT for identifying regions of interest
    if inscription.findspot_lat is not None and inscription.findspot_lon is not None:
        annotation["target"]["selector"] = {
            "type": "SvgSelector",
            "value": (
                f"<svg><circle cx='{inscription.findspot_lon}' "
                f"cy='{inscription.findspot_lat}' r='0.01'/></svg>"
            ),
        }

    return annotation


def corpus_to_pelagios_jsonld(
    search_results,
    language: str = "ett",
) -> str:
    """
    Export search results as a Pelagios-compatible JSON-LD collection.

    Args:
        search_results: A SearchResults instance containing inscriptions.
        language: ISO 639-3 language code.

    Returns:
        JSON-LD string with all annotations.
    """
    inscriptions = getattr(search_results, "inscriptions", search_results)

    annotations = []
    for inscription in inscriptions:
        ann = inscription_to_jsonld(inscription, language=language)
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


def pleiades_stats(search_results) -> dict[str, int]:
    """
    Get statistics on Pleiades coverage in the results.

    Returns a dict of {pleiades_uri: count}.
    """
    inscriptions = getattr(search_results, "inscriptions", search_results)
    stats: dict[str, int] = {}
    for inscription in inscriptions:
        if inscription.findspot:
            uri = get_pleiades_uri(inscription.findspot)
            if uri:
                stats[uri] = stats.get(uri, 0) + 1
    return dict(sorted(stats.items(), key=lambda x: -x[1]))


def lod_stats(search_results) -> dict:
    """
    Get coverage statistics for all three LOD systems.

    Returns:
        dict with keys "pleiades", "trismegistos", "eagle",
        each containing {"mapped": int, "total": int, "coverage": float}.
    """
    inscriptions = getattr(search_results, "inscriptions", search_results)
    total = len(inscriptions)

    pleiades_count = 0
    tm_count = 0
    eagle_count = 0

    for inscription in inscriptions:
        if inscription.findspot and get_pleiades_uri(inscription.findspot):
            pleiades_count += 1
        if get_trismegistos_uri(inscription.id):
            tm_count += 1
        if get_eagle_uri(inscription.id):
            eagle_count += 1

    def _coverage(mapped: int, tot: int) -> dict:
        """Helper to calculate coverage ratio for a specific LOD dataset mapping."""
        return {
            "mapped": mapped,
            "total": tot,
            "coverage": round(mapped / tot, 4) if tot > 0 else 0.0,
        }

    return {
        "pleiades": _coverage(pleiades_count, total),
        "trismegistos": _coverage(tm_count, total),
        "eagle": _coverage(eagle_count, total),
    }


# ---------------------------------------------------------------------------
# Live API Reconciliation
# ---------------------------------------------------------------------------

TRISMEGISTOS_API = "https://www.trismegistos.org/dataservices/texrelations/search"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Rate limiting: minimum seconds between API calls
_MIN_API_INTERVAL = 1.0


def _get_httpx():
    """Import httpx or raise a helpful error."""
    try:
        import httpx

        return httpx
    except ImportError as exc:
        raise ImportError(
            "Live LOD reconciliation requires httpx. Install with: pip install openetruscan[lod]"
        ) from exc


def reconcile_trismegistos(
    inscription_id: str,
    text: str = "",
    timeout: float = 10.0,
) -> str | None:
    """
    Search the Trismegistos API for a matching text record.

    Tries static YAML mapping first, then queries the TM API
    using the inscription text content for fuzzy matching.

    Args:
        inscription_id: Local inscription ID.
        text: Canonical inscription text for search.
        timeout: HTTP request timeout in seconds.

    Returns:
        TM text ID if found, None otherwise.
    """
    # 1. Try static mapping first
    mapping = _load_trismegistos_mapping()
    if inscription_id in mapping:
        return mapping[inscription_id]

    if not text or not text.strip():
        return None

    # 2. Query TM API
    httpx = _get_httpx()
    try:
        response = httpx.get(
            TRISMEGISTOS_API,
            params={
                "text": text[:100],  # TM API has query length limits
                "language": "ett",  # Etruscan ISO 639-3
            },
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()

        data = response.json()

        # TM API returns a list of text records
        if isinstance(data, list) and len(data) > 0:
            # Take the first (best) match
            tm_id = str(data[0].get("tm_id", data[0].get("id", "")))
            if tm_id:
                return tm_id
        elif isinstance(data, dict):
            # Some endpoints return a dict with 'results'
            results = data.get("results", data.get("data", []))
            if results and len(results) > 0:
                tm_id = str(results[0].get("tm_id", results[0].get("id", "")))
                if tm_id:
                    return tm_id

    except Exception as e:  # noqa: BLE001
        # Network errors or API timeouts are handled gracefully to prevent
        # blocking the ingestion pipeline during bulk reconciliation.
        logger.warning(f"TM reconciliation failed for {inscription_id}: {e}")
        return None

    return None


def reconcile_wikidata(
    findspot: str,
    timeout: float = 10.0,
) -> str | None:
    """
    Query Wikidata SPARQL for the Q-ID of an ancient site.

    Searches for entities that are instances of ancient settlements
    (or subclasses) matching the findspot name.

    Args:
        findspot: Name of the findspot (e.g., "Caere", "Tarquinii").
        timeout: HTTP request timeout in seconds.

    Returns:
        Wikidata Q-ID (e.g., "Q202210") if found, None otherwise.
    """
    if not findspot or not findspot.strip():
        return None

    httpx = _get_httpx()

    # SPARQL query: find items labeled with the findspot name
    # that are instances of (or subclass of) archaeological site, ancient city, etc.
    query = f"""
    SELECT ?item ?itemLabel WHERE {{
      ?item rdfs:label "{findspot}"@en .
      ?item wdt:P31/wdt:P279* ?type .
      VALUES ?type {{
        wd:Q839954    # archaeological site
        wd:Q515       # city
        wd:Q3957      # town
        wd:Q56061     # administrative territorial entity
        wd:Q486972    # human settlement
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }}
    LIMIT 1
    """

    try:
        response = httpx.get(
            WIKIDATA_SPARQL,
            params={"query": query, "format": "json"},
            timeout=timeout,
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "OpenEtruscan/0.4 (https://openetruscan.com)",
            },
        )
        response.raise_for_status()

        data = response.json()
        bindings = data.get("results", {}).get("bindings", [])
        if bindings:
            uri = bindings[0].get("item", {}).get("value", "")
            # Extract Q-ID from URI: http://www.wikidata.org/entity/Q123
            if "/entity/" in uri:
                return uri.split("/entity/")[-1]

    except Exception:  # noqa: BLE001
        pass  # Network error — fall through  # nosec B110

    return None


def reconcile_and_cache(
    corpus,
    timeout: float = 10.0,
    max_requests: int = 50,
) -> dict:
    """
    Bulk-reconcile corpus inscriptions against TM and Wikidata APIs.

    Results are cached to local YAML files for offline use.
    Respects rate limiting and caps at ``max_requests`` API calls.

    Args:
        corpus: A Corpus instance.
        timeout: HTTP request timeout per request.
        max_requests: Maximum total API calls (to avoid abuse).

    Returns:
        Dict with counts: {tm_new, wikidata_new, tm_cached, wikidata_cached}.
    """
    import time

    results = corpus.search(limit=999999)

    # Load existing caches
    tm_mapping = dict(_load_trismegistos_mapping())
    pleiades_mapping = dict(_load_pleiades_mapping())

    tm_new = 0
    wd_new = 0
    api_calls = 0

    # Reconcile Trismegistos
    for inscription in results:
        if api_calls >= max_requests:
            break
        if inscription.id in tm_mapping:
            continue
        if not inscription.canonical:
            continue

        try:
            tm_id = reconcile_trismegistos(inscription.id, inscription.canonical, timeout=timeout)
            if tm_id:
                tm_mapping[inscription.id] = tm_id
                tm_new += 1
            api_calls += 1
            time.sleep(_MIN_API_INTERVAL)
        except ImportError:
            break  # httpx not installed

    # Reconcile Wikidata for findspots not in Pleiades
    seen_findspots: set[str] = set()
    wikidata_cache: dict[str, str] = {}

    for inscription in results:
        if api_calls >= max_requests:
            break
        if not inscription.findspot:
            continue
        if inscription.findspot in seen_findspots:
            continue
        if inscription.findspot in pleiades_mapping:
            seen_findspots.add(inscription.findspot)
            continue

        seen_findspots.add(inscription.findspot)

        try:
            qid = reconcile_wikidata(inscription.findspot, timeout=timeout)
            if qid:
                wikidata_cache[inscription.findspot] = qid
                wd_new += 1
            api_calls += 1
            time.sleep(_MIN_API_INTERVAL)
        except ImportError:
            break

    # Save updated TM mapping
    if tm_new > 0:
        _save_yaml_mapping("trismegistos_mapping.yaml", tm_mapping)
        # Invalidate cache
        global _tm_mapping_cache
        _tm_mapping_cache = None

    # Save Wikidata results alongside Pleiades
    if wd_new > 0:
        wikidata_path = Path(__file__).parent.parent.parent / "data" / "wikidata_mapping.yaml"
        existing_wd = {}
        if wikidata_path.exists():
            with open(wikidata_path, encoding="utf-8") as f:
                existing_wd = yaml.safe_load(f) or {}
        existing_wd.update(wikidata_cache)
        with open(wikidata_path, "w", encoding="utf-8") as f:
            yaml.dump(existing_wd, f, allow_unicode=True, sort_keys=True)

    return {
        "tm_new": tm_new,
        "wikidata_new": wd_new,
        "tm_total": len(tm_mapping),
        "api_calls": api_calls,
    }


def _save_yaml_mapping(filename: str, mapping: dict[str, str]) -> None:
    """Save a mapping dict to a YAML file in the data directory."""
    mapping_path = Path(__file__).parent.parent.parent / "data" / filename
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mapping_path, "w", encoding="utf-8") as f:
        yaml.dump(dict(mapping), f, allow_unicode=True, sort_keys=True)


def get_wikidata_uri(findspot: str) -> str | None:
    """
    Get the Wikidata URI for a findspot from the local cache.

    Returns None if not in the cache.
    """
    wd_path = Path(__file__).parent.parent.parent / "data" / "wikidata_mapping.yaml"
    if not wd_path.exists():
        return None
    with open(wd_path, encoding="utf-8") as f:
        mapping = yaml.safe_load(f) or {}
    qid = mapping.get(findspot)
    if qid:
        return f"https://www.wikidata.org/entity/{qid}"
    return None
