/**
 * Etruscan Script Normalizer Engine — ported from web/app.js
 *
 * Full multi-language normalizer supporting:
 * - Canonical → Old Italic Unicode
 * - Canonical → Phonetic (IPA)
 * - Digraph resolution (th→θ, ph→φ, ch→χ, sh→ś)
 * - Source system detection (Old Italic, CIE, philological, web-safe)
 */

export interface LanguageAlphabetEntry {
  unicode: string;
  ipa: string;
  variants: string[];
}

export interface LanguageData {
  id: string;
  displayName: string;
  direction: string;
  alphabet: Record<string, LanguageAlphabetEntry>;
  digraphs: Record<string, string>;
  unicodeMap: Record<string, string>;
  vowels: string[];
}

export interface NormalizeResult {
  canonical: string;
  phonetic: string;
  old_italic: string;
  source_system: string;
  tokens: string[];
  confidence: number;
  warnings: string[];
}

let _languages: Record<string, LanguageData> | null = null;
let _currentLang: LanguageData | null = null;
let _variantToCanonical: Record<string, string> = {};
let _canonicalToUnicode: Record<string, string> = {};
let _canonicalToIPA: Record<string, string> = {};
let _unicodeToCanonical: Record<string, string> = {};

export async function loadLanguages(): Promise<
  Record<string, LanguageData>
> {
  if (_languages) return _languages;
  const res = await fetch("/data/languages.json");
  _languages = await res.json();
  buildLookupTables("etruscan");
  return _languages!;
}

function buildLookupTables(langId: string) {
  if (!_languages) return;
  const lang = _languages[langId];
  if (!lang) return;

  _currentLang = lang;
  _variantToCanonical = {};
  _canonicalToUnicode = {};
  _canonicalToIPA = {};
  _unicodeToCanonical = {};

  for (const [canonical, data] of Object.entries(lang.alphabet)) {
    _canonicalToUnicode[canonical] = data.unicode;
    _canonicalToIPA[canonical] = data.ipa;
    _unicodeToCanonical[data.unicode] = canonical;
    _variantToCanonical[canonical] = canonical;
    for (const v of data.variants) {
      _variantToCanonical[v] = canonical;
    }
  }

  // Digraph mappings
  for (const [digraph, canonical] of Object.entries(lang.digraphs || {})) {
    _variantToCanonical[digraph] = canonical;
    _variantToCanonical[digraph.toUpperCase()] = canonical;
    _variantToCanonical[
      digraph.charAt(0).toUpperCase() + digraph.slice(1)
    ] = canonical;
  }
}

function isOldItalic(char: string): boolean {
  const cp = char.codePointAt(0);
  return cp !== undefined && cp >= 0x10300 && cp <= 0x1032f;
}

function detectSourceSystem(text: string): string {
  for (const char of text) {
    if (isOldItalic(char)) return "unicode";
  }
  const philoChars = new Set([
    "θ", "φ", "χ", "ś", "Θ", "Φ", "Χ", "Ś", "í", "ú", "Í", "Ú",
  ]);
  for (const c of text) {
    if (philoChars.has(c)) return "philological";
  }
  const alpha = [...text].filter((c) => /[a-zA-Z]/.test(c));
  if (alpha.length > 0 && alpha.every((c) => c === c.toUpperCase()))
    return "cie";
  return "web_safe";
}

function unicodeToCanonicalText(text: string): string {
  let result = "";
  for (const char of text) {
    if (isOldItalic(char)) {
      result += _unicodeToCanonical[char] || char;
    } else {
      result += char;
    }
  }
  return result;
}

function foldToCanonical(text: string): {
  canonical: string;
  warnings: string[];
} {
  const result: string[] = [];
  const warnings: string[] = [];
  let i = 0;

  while (i < text.length) {
    let matched = false;

    for (let len = Math.min(3, text.length - i); len > 0; len--) {
      const chunk = text.substring(i, i + len);
      const resolved = _variantToCanonical[chunk];
      if (resolved !== undefined) {
        result.push(resolved);
        i += len;
        matched = true;
        break;
      }
    }

    if (!matched) {
      const char = text[i];
      if (/[a-zA-Z]/.test(char)) {
        const lower = char.toLowerCase();
        const resolved = _variantToCanonical[lower];
        if (resolved !== undefined) {
          result.push(resolved);
        } else {
          warnings.push(`Unknown '${char}'`);
          result.push(lower);
        }
      } else if (" .,-;:'[]()•|\n\t".includes(char)) {
        result.push(char);
      } else {
        warnings.push(`Unknown '${char}'`);
        result.push(char);
      }
      i++;
    }
  }

  return { canonical: result.join(""), warnings };
}

function toPhonetic(canonical: string): string {
  const parts: string[] = [];
  for (const char of canonical) {
    const ipa = _canonicalToIPA[char];
    if (ipa) parts.push(ipa);
    else if (char === " ") parts.push(" ");
    else parts.push(char);
  }
  const words = parts
    .join("")
    .split(" ")
    .filter(Boolean);
  return "/" + words.join(".") + "/";
}

function toOldItalic(canonical: string): string {
  let result = "";
  for (const char of canonical) {
    const uc = _canonicalToUnicode[char];
    if (uc) result += uc;
    else if (char === " ") result += " ";
    else result += char;
  }
  return result;
}

export function normalize(text: string): NormalizeResult {
  text = text.trim();
  if (!text) {
    return {
      canonical: "",
      phonetic: "",
      old_italic: "",
      source_system: "",
      tokens: [],
      confidence: 1.0,
      warnings: [],
    };
  }

  const sourceSystem = detectSourceSystem(text);

  if (sourceSystem === "unicode") {
    text = unicodeToCanonicalText(text);
  }

  const { canonical, warnings } = foldToCanonical(text);
  const phonetic = toPhonetic(canonical);
  const oldItalic = toOldItalic(canonical);
  const tokens = canonical.split(/\s+/).filter(Boolean);
  const confidence = Math.max(0, 1.0 - warnings.length * 0.15);

  return {
    canonical,
    phonetic,
    old_italic: oldItalic,
    source_system: sourceSystem,
    tokens,
    confidence,
    warnings,
  };
}

export function switchLanguage(langId: string) {
  buildLookupTables(langId);
}

export function getLanguages(): Record<string, LanguageData> | null {
  return _languages;
}

export const SOURCE_SYSTEM_NAMES: Record<string, string> = {
  cie: "CIE Standard",
  philological: "Philological",
  unicode: "Old Italic Unicode",
  web_safe: "Web-safe",
  latex: "LaTeX",
};
