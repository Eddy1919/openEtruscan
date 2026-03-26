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
}

let _cache: Inscription[] | null = null;

export async function loadCorpus(): Promise<Inscription[]> {
  if (_cache) return _cache;
  const res = await fetch("/data/corpus.json");
  _cache = (await res.json()) as Inscription[];
  return _cache;
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
