"""
OpenEtruscan — Open-source tools for ancient epigraphy.

Built for Etruscan, designed to be copied.
"""

from importlib.metadata import version as _get_version

from openetruscan.core.converter import to_latin, to_old_italic, to_phonetic
from openetruscan.core.normalizer import NormResult, normalize

try:
    __version__ = _get_version("openetruscan")
except Exception:
    __version__ = "unknown"

__all__ = [
    "normalize",
    "NormResult",
    "to_old_italic",
    "to_latin",
    "to_phonetic",
    "__version__",
]
