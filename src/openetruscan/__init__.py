"""
OpenEtruscan — Open-source tools for ancient epigraphy.

Built for Etruscan, designed to be copied.
"""

from openetruscan.converter import to_latin, to_old_italic, to_phonetic
from openetruscan.normalizer import NormResult, normalize

__version__ = "0.1.0"
__all__ = ["normalize", "NormResult", "to_old_italic", "to_latin", "to_phonetic"]
