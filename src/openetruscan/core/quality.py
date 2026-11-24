"""Ingest-time quality checks: automatic provenance flags and near-duplicate detection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from openetruscan.core.inscription import Inscription

if TYPE_CHECKING:
    from openetruscan.core.corpus import Corpus

# Geographic bounds for Etruscan cultural area (used by provenance checks)
_ETRUSCAN_LAT_RANGE = (35.0, 48.0)
_ETRUSCAN_LON_RANGE = (5.0, 18.0)


def auto_flag_inscription(
    inscription: Inscription,
    language: str = "etruscan",
    corpus: Corpus | None = None,
    similarity_threshold: float = 0.9,
) -> list[str]:
    """
    Auto-detect potential issues in an inscription for the provenance pipeline.

    Checks:
      - Non-alphabet characters (potential OCR errors)
      - Out-of-range coordinates (outside Etruscan cultural area)
      - Near-duplicate texts (TF-IDF cosine similarity > threshold)

    Args:
        inscription: The inscription to check.
        language: Language adapter to use.
        corpus: If provided, checks for near-duplicates against existing texts.
        similarity_threshold: Cosine similarity threshold for duplicate flagging (0-1).

    Returns:
        List of flag strings describing detected issues.
    """
    from openetruscan.core.adapter import load_adapter

    flags: list[str] = []

    # Check for non-alphabet characters
    if inscription.canonical:
        try:
            adapter = load_adapter(language)
            alphabet_set = set(adapter.alphabet.keys())
            unknown_chars = set()
            for ch in inscription.canonical:
                if ch not in alphabet_set and ch != " ":
                    unknown_chars.add(ch)
            if unknown_chars:
                flags.append(f"non_alphabet_chars: {', '.join(sorted(unknown_chars))}")
        except Exception:  # noqa: BLE001
            pass  # Adapter not found — skip check  # nosec B110

    # Check coordinate range
    if inscription.findspot_lat is not None and inscription.findspot_lon is not None:
        lat, lon = inscription.findspot_lat, inscription.findspot_lon
        if not (_ETRUSCAN_LAT_RANGE[0] <= lat <= _ETRUSCAN_LAT_RANGE[1]):
            flags.append(
                f"lat_out_of_range: {lat} "
                f"(expected {_ETRUSCAN_LAT_RANGE[0]}-"
                f"{_ETRUSCAN_LAT_RANGE[1]})"
            )
        if not (_ETRUSCAN_LON_RANGE[0] <= lon <= _ETRUSCAN_LON_RANGE[1]):
            flags.append(
                f"lon_out_of_range: {lon} "
                f"(expected {_ETRUSCAN_LON_RANGE[0]}-"
                f"{_ETRUSCAN_LON_RANGE[1]})"
            )

    # TF-IDF near-duplicate detection
    if corpus is not None and inscription.canonical:
        flags.extend(_check_near_duplicates(inscription, corpus, similarity_threshold))

    return flags


# Above this many stored inscriptions the near-duplicate check is skipped:
# every call fetches the whole corpus and refits a TF-IDF vectorizer, so
# flagging n inserts against an m-row corpus costs O(n·m) — quadratic during
# a bulk import. Overridable via the OPENETRUSCAN_NEAR_DUP_MAX_CORPUS env var
# or the max_corpus_size parameter.
_NEAR_DUP_MAX_CORPUS_DEFAULT = 5000


def _near_dup_corpus_limit() -> int:
    """Resolve the near-duplicate corpus-size gate from the environment."""
    raw = os.environ.get("OPENETRUSCAN_NEAR_DUP_MAX_CORPUS", "")
    try:
        return int(raw)
    except ValueError:
        return _NEAR_DUP_MAX_CORPUS_DEFAULT


def _check_near_duplicates(
    inscription: Inscription,
    corpus: Corpus,
    threshold: float = 0.9,
    max_corpus_size: int | None = None,
) -> list[str]:
    """
    Check for near-duplicate texts using TF-IDF cosine similarity.

    Uses character n-gram TF-IDF (2-4 grams) to detect texts that are
    suspiciously similar, which may indicate OCR duplicates or transcription
    errors from the same source.

    The check is skipped when the corpus exceeds ``max_corpus_size`` rows
    (default from OPENETRUSCAN_NEAR_DUP_MAX_CORPUS, falling back to
    ``_NEAR_DUP_MAX_CORPUS_DEFAULT``): it refits a corpus-wide vectorizer per
    call, which is O(n²) across a bulk import.
    """
    by_id = _check_near_duplicates_batch(
        [inscription], corpus, threshold=threshold, max_corpus_size=max_corpus_size
    )
    return by_id.get(inscription.id, [])


def _check_near_duplicates_batch(
    inscriptions: list[Inscription],
    corpus: Corpus,
    threshold: float = 0.9,
    max_corpus_size: int | None = None,
) -> dict[str, list[str]]:
    """
    Near-duplicate scan for a whole batch with a single TF-IDF fit.

    Fetches the existing corpus once, fits the vectorizer once, and transforms
    every batch text against it — instead of refitting per inserted row.

    Returns a mapping of inscription id → flag strings (ids without
    near-duplicates are omitted).
    """
    empty: dict[str, list[str]] = {}
    if not inscriptions:
        return empty

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return empty  # sklearn not installed — skip check

    # Size gate: see _check_near_duplicates docstring for the O(n²) rationale.
    limit = max_corpus_size if max_corpus_size is not None else _near_dup_corpus_limit()
    if corpus.count() > limit:
        return empty

    batch_ids = {insc.id for insc in inscriptions}
    candidates = [insc for insc in inscriptions if insc.canonical]
    if not candidates:
        return empty

    # Fetch existing canonical texts once for the whole batch
    results = corpus.search(limit=999999)
    existing = [
        (insc.id, insc.canonical) for insc in results if insc.canonical and insc.id not in batch_ids
    ]

    if not existing:
        return empty

    existing_ids, existing_texts = zip(*existing, strict=True)

    # Build TF-IDF matrix with character n-grams
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=5000,
    )

    try:
        corpus_matrix = vectorizer.fit_transform(list(existing_texts))
        new_vectors = vectorizer.transform([insc.canonical for insc in candidates])
        similarities = cosine_similarity(new_vectors, corpus_matrix)
    except ValueError:
        return empty  # Empty vocabulary or other vectorizer issue

    # Flag high-similarity matches per batch member
    flags_by_id: dict[str, list[str]] = {}
    for row_idx, insc in enumerate(candidates):
        for col_idx, sim in enumerate(similarities[row_idx]):
            if sim >= threshold:
                flags_by_id.setdefault(insc.id, []).append(
                    f"near_duplicate: {existing_ids[col_idx]} (similarity={sim:.3f})"
                )

    return flags_by_id
