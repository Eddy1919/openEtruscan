"""
OpenEtruscan — CLTK Integration Module
=======================================

Provides Etruscan NLP pipeline components for the
Classical Language Toolkit (cltk.org).

Usage with CLTK::

    from cltk import NLP
    cltk_nlp = NLP(language="ett")  # after this module is registered

    doc = cltk_nlp.analyze(text="mi larθal lecnes")
    for word in doc.words:
        print(word.string, word.phonetic, word.ner_tag)

Standalone usage (without CLTK installed)::

    from openetruscan.cltk_module import EtruscanPipeline
    pipe = EtruscanPipeline()
    result = pipe.analyze("mi larθal lecnes")
    print(result)
"""

from openetruscan.cltk_module.language import ETRUSCAN_LANGUAGE
from openetruscan.cltk_module.pipeline import EtruscanPipeline

__all__ = ["EtruscanPipeline", "ETRUSCAN_LANGUAGE"]
