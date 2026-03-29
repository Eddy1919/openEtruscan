export interface Inscription {
  id: string;
  canonical: string;
  phonetic: string | null;
  old_italic: string | null;
  findspot: string | null;
  findspot_lat: number | null;
  findspot_lon: number | null;
  date_approx: number | null;
  date_uncertainty: number | null;
  classification: string | null;
  medium: string | null;
  object_type: string | null;
  source: string | null;
  notes: string | null;
  pleiades_id: string | null;
  geonames_id: string | null;
  trismegistos_id: string | null;
  eagle_id: string | null;
  is_codex: boolean;
  provenance_status: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.openetruscan.com";

let _cache: Inscription[] | null = null;

export async function loadCorpus(): Promise<Inscription[]> {
  if (_cache) return _cache;
  try {
    const res = await fetch(`${API_URL}/corpus`, { next: { revalidate: 3600 } });
    if (!res.ok) throw new Error("Failed to fetch corpus");
    _cache = (await res.json()) as Inscription[];
    return _cache;
  } catch (err) {
    console.error("Corpus load error:", err);
    return [];
  }
}

export function dateDisplay(insc: Inscription): string {
  if (insc.date_approx == null) return "undated";
  const year = Math.abs(insc.date_approx);
  const era = insc.date_approx < 0 ? "BCE" : "CE";
  if (insc.date_uncertainty) {
    return `${year} ± ${insc.date_uncertainty} ${era}`;
  }
  return `${year} ${era}`;
}

export function pleiadesUrl(id: string): string {
  return `https://pleiades.stoa.org/places/${id}`;
}

export function geonamesUrl(id: string): string {
  return `https://sws.geonames.org/${id}/`;
}

export function trismegistosUrl(id: string): string {
  return `https://www.trismegistos.org/text/${id}`;
}

export function eagleUrl(id: string): string {
  return `https://www.eagle-network.eu/info/${id}`;
}

/** Classification color palette */
export const CLASS_COLORS: Record<string, string> = {
  funerary: "#c4704b",
  votive: "#6395f2",
  dedicatory: "#4ade80",
  legal: "#c084fc",
  commercial: "#fbbf24",
  boundary: "#f472b6",
  ownership: "#38bdf8",
  unknown: "#6b6962",
};

/** Canonical → Old Italic Unicode mapping (Etruscan alphabet) */
const CANONICAL_TO_OLD_ITALIC: Record<string, string> = {
  a: "𐌀", c: "𐌂", e: "𐌄", v: "𐌅", z: "𐌆", h: "𐌇",
  "θ": "𐌈", i: "𐌉", k: "𐌊", l: "𐌋", m: "𐌌", n: "𐌍",
  p: "𐌐", "ś": "𐌑", q: "𐌒", r: "𐌓", s: "𐌔", t: "𐌕",
  u: "𐌖", "φ": "𐌘", "χ": "𐌗", f: "𐌚",
};

/** Convert canonical Etruscan text to Old Italic Unicode */
export function toOldItalic(canonical: string): string {
  let result = "";
  for (const char of canonical) {
    result += CANONICAL_TO_OLD_ITALIC[char] || char;
  }
  return result;
}

