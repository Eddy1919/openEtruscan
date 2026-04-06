export interface Inscription {
  id: string;
  canonical: string;
  phonetic: string | null;
  old_italic: string | null;
  raw_text: string | null;
  findspot: string | null;
  findspot_lat: number | null;
  findspot_lon: number | null;
  date_display: string;
  date_approx: number | null;
  date_uncertainty: number | null;
  classification: string | null;
  medium: string | null;
  object_type: string | null;
  source: string | null;
  notes: string | null;
  language: string | null;
  gens: string | null;
  pleiades_id: string | null;
  geonames_id: string | null;
  trismegistos_id: string | null;
  eagle_id: string | null;
  is_codex: boolean;
  provenance_status: string;
}

export interface SearchResponse {
  total: number;
  count: number;
  results: Inscription[];
}

export interface KWICRow {
  inscId: string;
  left: string;
  keyword: string;
  right: string;
}

export interface ConcordanceResponse {
  total: number;
  unique_inscriptions: number;
  rows: KWICRow[];
}

export interface NameNode {
  id: string;
  count: number;
  inscriptions: string[];
}

export interface NameEdge {
  source: string;
  target: string;
  weight: number;
}

export interface NamesNetworkResponse {
  nodes: NameNode[];
  edges: NameEdge[];
}

export interface TimelineItem {
  id: string;
  findspot: string;
  findspot_lat: number;
  findspot_lon: number;
  date_approx: number;
  classification: string;
}

export interface StatsSummary {
  total: number;
  with_coords: number;
  pleiades_linked: number;
  classified: number;
  classification_counts: [string, number][];
  top_sites: [string, number][];
  text_length_buckets: [string, number][];
  distinct_sites: string[];
  distinct_classifications: string[];
}

const isServer = typeof window === "undefined";
export const API_URL = isServer 
  ? (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") 
  : "/api";

// ── Fetch helpers ──────────────────────────────────────────────────────────

export async function searchCorpus(params: {
  text?: string;
  findspot?: string;
  classification?: string;
  limit?: number;
  offset?: number;
  sort_by?: string;
}): Promise<SearchResponse> {
  const qs = new URLSearchParams();
  if (params.text) qs.set("text", params.text);
  if (params.findspot) qs.set("findspot", params.findspot);
  if (params.classification) qs.set("classification", params.classification);
  if (params.sort_by) qs.set("sort_by", params.sort_by);
  qs.set("limit", String(params.limit ?? 100));
  qs.set("offset", String(params.offset ?? 0));

  try {
    const res = await fetch(`${API_URL}/search?${qs.toString()}`);
    if (!res.ok) return { total: 0, count: 0, results: [] };
    return res.json();
  } catch (e) {
    return { total: 0, count: 0, results: [] };
  }
}

export async function semanticSearchCorpus(
  q: string,
  limit: number = 20
): Promise<SearchResponse> {
  const qs = new URLSearchParams({
    q,
    limit: String(limit),
  });
  try {
    const res = await fetch(`${API_URL}/semantic-search?${qs.toString()}`);
    if (!res.ok) return { total: 0, count: 0, results: [] };
    return res.json();
  } catch (e) {
    return { total: 0, count: 0, results: [] };
  }
}

export async function fetchGeoInscriptions(params: {
  text?: string;
  findspot?: string;
  classification?: string;
  limit?: number;
}): Promise<SearchResponse> {
  const qs = new URLSearchParams();
  if (params.text) qs.set("text", params.text);
  if (params.findspot) qs.set("findspot", params.findspot);
  if (params.classification) qs.set("classification", params.classification);
  qs.set("limit", String(params.limit ?? 2000));

  try {
    const res = await fetch(`${API_URL}/search/geo?${qs.toString()}`);
    if (!res.ok) return { total: 0, count: 0, results: [] };
    return res.json();
  } catch (e) {
    return { total: 0, count: 0, results: [] };
  }
}

export async function fetchInscription(id: string): Promise<Inscription | null> {
  const res = await fetch(`${API_URL}/inscription/${encodeURIComponent(id)}`, {
    next: { revalidate: 3600 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to fetch inscription");
  return res.json();
}

export async function fetchIds(): Promise<string[]> {
  try {
    const res = await fetch(`${API_URL}/ids`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    return res.json();
  } catch (e) {
    return [];
  }
}

export async function fetchStatsSummary(): Promise<StatsSummary> {
  try {
    const res = await fetch(`${API_URL}/stats/summary`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return getFallbackStats();
    return res.json();
  } catch (e) {
    return getFallbackStats();
  }
}

function getFallbackStats(): StatsSummary {
  return {
    total: 4728,
    with_coords: 4728,
    pleiades_linked: 41,
    classified: 4728,
    classification_counts: [],
    top_sites: [],
    text_length_buckets: [],
    distinct_sites: [],
    distinct_classifications: [],
  };
}

export async function fetchTimeline(): Promise<{
  total: number;
  items: TimelineItem[];
}> {
  try {
    const res = await fetch(`${API_URL}/stats/timeline`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return { total: 0, items: [] };
    return res.json();
  } catch (e) {
    return { total: 0, items: [] };
  }
}

export async function fetchConcordance(
  q: string,
  context: number = 40,
  limit: number = 2000,
  signal?: AbortSignal
): Promise<ConcordanceResponse> {
  const qs = new URLSearchParams({
    q,
    context: String(context),
    limit: String(limit),
  });
  try {
    const res = await fetch(`${API_URL}/concordance?${qs.toString()}`, { signal });
    if (!res.ok) return { total: 0, unique_inscriptions: 0, rows: [] };
    return res.json();
  } catch (e: any) {
    if (e.name === 'AbortError') throw e;
    return { total: 0, unique_inscriptions: 0, rows: [] };
  }
}

export async function fetchNamesNetwork(
  minCount: number = 5
): Promise<NamesNetworkResponse> {
  try {
    const res = await fetch(
      `${API_URL}/names/network?min_count=${minCount}`,
      { next: { revalidate: 3600 } }
    );
    if (!res.ok) return { nodes: [], edges: [] };
    return res.json();
  } catch (e) {
    return { nodes: [], edges: [] };
  }
}

// ── Display helpers ────────────────────────────────────────────────────────

export function dateDisplay(insc: Inscription): string {
  if (insc.date_approx == null) return insc.date_display || "undated";
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

/** Classification color palette (Aldine Design System) */
export const CLASS_COLORS: Record<string, string> = {
  funerary: "#A2574B",
  votive: "#6B5A53",
  dedicatory: "#8E706A",
  legal: "#2B211E",
  commercial: "#CD7F32",
  boundary: "#433522",
  ownership: "#A2574B",
  unknown: "#8c6b5d",
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
  // Tokenize Leiden bracket notation, punctuation dots/dashes, and individual graphemes.
  // Preserves exact spacing and punctuation while strictly mapping Etruscan letters.
  return canonical.replace(/(?:\[.*?\])|[\.•\-]|([a-zθśφχ])/gi, (match, letter) => {
    if (letter) {
      return CANONICAL_TO_OLD_ITALIC[letter.toLowerCase()] || letter;
    }
    return match;
  });
}

// ── ML Helpers ─────────────────────────────────────────────────────────────

export interface LacunaePrediction {
  position: number;
  predictions: Record<string, number>;
}

export interface RestoreResponse {
  text: string;
  predictions: LacunaePrediction[];
}

export async function restoreLacunae(text: string, top_k: number = 5): Promise<RestoreResponse> {
  const res = await fetch(`${API_URL}/neural/restore`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text, top_k }),
  });
  if (!res.ok) {
    let errMsg = "Failed to restore lacunae";
    try {
      const errorData = await res.json();
      if (errorData.detail) errMsg = errorData.detail;
    } catch (e) {
      // Ignore JSON parse error if response is not JSON
    }
    throw new Error(errMsg);
  }
  return res.json();
}

export async function searchRadius(lat: number, lon: number, radiusKm: number): Promise<SearchResponse> {
  const qs = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    radius_km: String(radiusKm),
  });
  const res = await fetch(`${API_URL}/radius?${qs.toString()}`);
  if (!res.ok) throw new Error("Radius search failed");
  return res.json();
}
