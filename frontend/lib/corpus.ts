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

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.openetruscan.com";

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

  const res = await fetch(`${API_URL}/search?${qs.toString()}`);
  if (!res.ok) throw new Error("Search failed");
  return res.json();
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

  const res = await fetch(`${API_URL}/search/geo?${qs.toString()}`);
  if (!res.ok) throw new Error("Geo search failed");
  return res.json();
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
  const res = await fetch(`${API_URL}/ids`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error("Failed to fetch IDs");
  return res.json();
}

export async function fetchStatsSummary(): Promise<StatsSummary> {
  const res = await fetch(`${API_URL}/stats/summary`, {
    next: { revalidate: 3600 },
  });
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export async function fetchTimeline(): Promise<{
  total: number;
  items: TimelineItem[];
}> {
  const res = await fetch(`${API_URL}/stats/timeline`, {
    next: { revalidate: 3600 },
  });
  if (!res.ok) throw new Error("Failed to fetch timeline");
  return res.json();
}

export async function fetchConcordance(
  q: string,
  context: number = 40,
  limit: number = 2000
): Promise<ConcordanceResponse> {
  const qs = new URLSearchParams({
    q,
    context: String(context),
    limit: String(limit),
  });
  const res = await fetch(`${API_URL}/concordance?${qs.toString()}`);
  if (!res.ok) throw new Error("Concordance search failed");
  return res.json();
}

export async function fetchNamesNetwork(
  minCount: number = 5
): Promise<NamesNetworkResponse> {
  const res = await fetch(
    `${API_URL}/names/network?min_count=${minCount}`
  );
  if (!res.ok) throw new Error("Failed to fetch names network");
  return res.json();
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
