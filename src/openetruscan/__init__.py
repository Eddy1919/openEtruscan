"""
OpenEtruscan — Open-source tools for ancient epigraphy.

Built for Etruscan, designed to be copied.
"""

from openetruscan.normalizer import normalize, NormResult
from openetruscan.converter import to_old_italic, to_latin, to_phonetic

__version__ = "0.1.0"
__all__ = ["normalize", "NormResult", "to_old_italic", "to_latin", "to_phonetic"]
