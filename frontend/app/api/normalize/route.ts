import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

interface LanguageAlphabetEntry {
  unicode: string;
  ipa: string;
  variants: string[];
}

interface LanguageData {
  alphabet: Record<string, LanguageAlphabetEntry>;
  digraphs: Record<string, string>;
}

let _lang: LanguageData | null = null;
const _variantToCanonical: Record<string, string> = {};
const _canonicalToUnicode: Record<string, string> = {};
const _canonicalToIPA: Record<string, string> = {};
const _unicodeToCanonical: Record<string, string> = {};

function ensureLoaded() {
  if (_lang) return;
  const raw = fs.readFileSync(
    path.join(process.cwd(), "public", "data", "languages.json"),
    "utf-8"
  );
  const langs = JSON.parse(raw);
  _lang = langs.etruscan;
  if (!_lang) return;

  for (const [canonical, data] of Object.entries(_lang.alphabet)) {
    const d = data as LanguageAlphabetEntry;
    _canonicalToUnicode[canonical] = d.unicode;
    _canonicalToIPA[canonical] = d.ipa;
    _unicodeToCanonical[d.unicode] = canonical;
    _variantToCanonical[canonical] = canonical;
    for (const v of d.variants) _variantToCanonical[v] = canonical;
  }
  for (const [digraph, canonical] of Object.entries(_lang.digraphs || {})) {
    _variantToCanonical[digraph] = canonical;
    _variantToCanonical[digraph.toUpperCase()] = canonical;
    _variantToCanonical[digraph.charAt(0).toUpperCase() + digraph.slice(1)] =
      canonical;
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
  const philoChars = new Set(["θ", "φ", "χ", "ś"]);
  for (const c of text) {
    if (philoChars.has(c)) return "philological";
  }
  const alpha = [...text].filter((c) => /[aldine-zA-Z]/.test(c));
  if (alpha.length > 0 && alpha.every((c) => c === c.toUpperCase()))
    return "cie";
  return "web_safe";
}

function normalize(text: string) {
  ensureLoaded();
  text = text.trim();
  if (!text) return { canonical: "", phonetic: "", old_italic: "", source_system: "", tokens: [] };

  const sourceSystem = detectSourceSystem(text);
  if (sourceSystem === "unicode") {
    let converted = "";
    for (const char of text) {
      converted += isOldItalic(char) ? (_unicodeToCanonical[char] || char) : char;
    }
    text = converted;
  }

  // Fold to canonical
  const result: string[] = [];
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
      if (/[aldine-zA-Z]/.test(char)) {
        result.push(_variantToCanonical[char.toLowerCase()] || char.toLowerCase());
      } else {
        result.push(char);
      }
      i++;
    }
  }
  const canonical = result.join("");

  // Phonetic
  const parts: string[] = [];
  for (const char of canonical) {
    const ipa = _canonicalToIPA[char];
    if (ipa) parts.push(ipa);
    else if (char === " ") parts.push(" ");
    else parts.push(char);
  }
  const phonetic = "/" + parts.join("").split(" ").filter(Boolean).join(".") + "/";

  // Old Italic
  let oldItalic = "";
  for (const char of canonical) {
    oldItalic += _canonicalToUnicode[char] || char;
  }

  return {
    canonical,
    phonetic,
    old_italic: oldItalic,
    source_system: sourceSystem,
    tokens: canonical.split(/\s+/).filter(Boolean),
  };
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const text = body.text;
    if (typeof text !== "string") {
      return NextResponse.json(
        { error: "Request body must contain a 'text' field (string)" },
        { status: 400 }
      );
    }
    const result = normalize(text);
    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    endpoint: "/api/normalize",
    method: "POST",
    body: { text: "string" },
    response: {
      canonical: "string",
      phonetic: "string",
      old_italic: "string",
      source_system: "string",
      tokens: "string[]",
    },
    example: 'curl -X POST -H "Content-Type: application/json" -d \'{"text":"MI AVILES"}\' https://www.openetruscan.com/api/normalize',
  });
}

