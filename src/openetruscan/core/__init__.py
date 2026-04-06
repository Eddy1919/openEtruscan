"""
OpenEtruscan core subpackage — normalizer, corpus, statistics, prosopography, and adapters.
"""

from .adapter import LanguageAdapter, load_adapter, list_available_adapters
from .artifacts import InscriptionImage, store_image, list_images
from .corpus import Corpus, Inscription, SearchResults
from .epidoc import corpus_to_epidoc, inscription_to_epidoc
from .geo import haversine
from .normalizer import normalize, NormResult
from .statistics import cluster_sites_from_texts, compare_frequencies, estimate_date, letter_frequencies
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
