#!/usr/bin/env python3
"""
Build web/languages.js from all YAML adapters.

Reads src/openetruscan/adapters/*.yaml and generates a JavaScript
file that the web converter uses for the language dropdown.

Usage:
    python scripts/build_web_languages.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openetruscan.adapter import list_available_adapters, load_adapter


def build_languages_js() -> str:
    """Generate JavaScript language definitions from YAML adapters."""
    languages = {}

    for lang_id in sorted(list_available_adapters()):
        adapter = load_adapter(lang_id)

        # Build alphabet map for JS
        alphabet = {}
        for letter, info in adapter.alphabet.items():
            alphabet[letter] = {
                "unicode": info.unicode_char,
                "ipa": info.ipa,
                "variants": info.variants,
            }

        # Build digraphs from equivalence classes
        digraphs = {}
        for cls in adapter.equivalence_classes.values():
            for member in cls.members:
                if len(member) > 1 and member.lower() != cls.canonical:
                    digraphs[member.lower()] = cls.canonical

        # Build reverse map (unicode → canonical)
        unicode_map = {}
        for letter, info in adapter.alphabet.items():
            unicode_map[info.unicode_char] = letter

        languages[lang_id] = {
            "id": lang_id,
            "displayName": adapter.display_name,
            "direction": adapter.direction,
            "alphabet": alphabet,
            "digraphs": digraphs,
            "unicodeMap": unicode_map,
            "vowels": adapter.phonotactics.vowels,
        }

    js = (
        "// Auto-generated from YAML adapters — do not edit manually.\n"
        "// Run: python scripts/build_web_languages.py\n"
        "\n"
        "const LANGUAGES = " + json.dumps(languages, ensure_ascii=False, indent=2) + ";\n"
    )
    return js


def main():
    js = build_languages_js()
    out_path = Path(__file__).parent.parent / "web" / "languages.js"
    out_path.write_text(js, encoding="utf-8")
    print(f"✅ Generated {out_path} ({len(js):,} bytes)")
    for lang_id in sorted(list_available_adapters()):
        adapter = load_adapter(lang_id)
        print(f"   {lang_id}: {adapter.display_name} ({len(adapter.alphabet)} letters)")


if __name__ == "__main__":
    main()
