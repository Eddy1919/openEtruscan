"""
OpenEtruscan core subpackage — normalizer, corpus, statistics, prosopography, and adapters.
"""

from .adapter import LanguageAdapter, list_available_adapters, load_adapter
from .artifacts import InscriptionImage, list_images, store_image
from .corpus import Corpus
from .epidoc import corpus_to_epidoc, inscription_to_epidoc
from .geo import haversine
from .inscription import Inscription, SearchResults
from .normalizer import NormResult, normalize

try:
    from .statistics import (
        cluster_sites_from_texts,
        compare_frequencies,
        estimate_date,
        letter_frequencies,
    )

    _has_stats = True
except ImportError:
    _has_stats = False
from .validator import ValidationReport, validate_file

__all__ = [
    "LanguageAdapter",
    "load_adapter",
    "list_available_adapters",
    "InscriptionImage",
    "store_image",
    "list_images",
    "Corpus",
    "Inscription",
    "SearchResults",
    "corpus_to_epidoc",
    "inscription_to_epidoc",
    "haversine",
    "normalize",
    "NormResult",
    "cluster_sites_from_texts",
    "compare_frequencies",
    "estimate_date",
    "letter_frequencies",
    "ValidationReport",
    "validate_file",
]
