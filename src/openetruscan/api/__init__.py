"""OpenEtruscan API subpackage — FastAPI server and Linked Open Data integration."""

from .lod import corpus_to_pelagios_jsonld, lod_stats, pleiades_stats
from .server import app

__all__ = [
    "app",
    "corpus_to_pelagios_jsonld",
    "lod_stats",
    "pleiades_stats",
]
