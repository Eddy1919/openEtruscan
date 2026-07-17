# Registering OpenEtruscan with Pelagios / Peripleo

Getting into the Pelagios graph is a **community / hosting action**, not a code
change. The discovery artifacts a Peripleo ingester needs are now live on the
public origin, so this is an execution runbook, not a list of blockers.

> **Status (verified 2026-07-17): registerable.** The two discovery artifacts
> resolve on the live site and are mutually consistent (the VoID `void:dataDump`
> names the feed, and both report the same corpus size). The operator is a
> Pelagios Network member; the remaining work is the submission itself.

Every URL and number below was confirmed with `curl` against the live origin on
2026-07-17. The public origin is the **Next.js frontend on Vercel** (repo
`openEtruscan-frontend`); both artifacts are per-request route handlers rendered
from live corpus counts (`app/void.ttl/route.ts`, `app/pelagios.jsonld/route.ts`).
The FastAPI backend in *this* repo is not the public origin — do not point a
crawler at it.

## Verified live endpoints

| URL (as curled) | Result |
| --- | --- |
| `https://www.openetruscan.com/void.ttl` | `200`, `text/turtle` — the dataset description |
| `https://www.openetruscan.com/pelagios.jsonld` | `200`, `application/ld+json` — the annotation dump |
| `https://openetruscan.com/void.ttl` (apex) | `307` → `https://www.openetruscan.com/void.ttl` |
| `https://openetruscan.com/pelagios.jsonld` (apex) | `307` → www, then `200` |
| `https://www.openetruscan.com/.well-known/void.ttl` | `404` — no well-known alias is served |

The canonical host is **`www.openetruscan.com`**; the apex `openetruscan.com`
`307`-redirects to it (verified on `/`, `/void.ttl`, `/pelagios.jsonld`).

## What the live artifacts contain (verified)

**`void.ttl`** (`text/turtle`) describes one `void:Dataset`,
`:OpenEtruscanInscriptions`, licensed CC-BY-4.0, and names the dump:

- `void:dataDump <https://openetruscan.com/pelagios.jsonld>`
- `void:entities 5932`
- linksets: `:PleiadesLinks void:triples 408`, `:TrismegistosLinks void:triples
  135`, `:EagleLinks void:triples 0`, and `:PeriodoLinks` (a temporal linkset
  via `dcterms:temporal`, no triple count declared)

**`pelagios.jsonld`** is a W3C Web Annotation `AnnotationCollection`:

- `"id": "https://openetruscan.com/pelagios.jsonld"`, `"total": 5932`, with a
  flat `items` array of 5932 annotations (one per inscription — count matches
  `void:entities`)
- each annotation carries a `TextualBody`, `dcterms:license`, and, where the row
  has them, Pleiades / Trismegistos / EAGLE / PeriodO bodies plus a
  `GeoJSONSelector` point target

## Submitting (operator is a Network member)

The single artifact to hand Pelagios is the **VoID URL** — it self-describes the
dump and the linksets:

```
https://www.openetruscan.com/void.ttl
```

1. The Pelagios homepage does not expose a self-serve dataset form; the current
   path is via the community. Contact the Network (`officers@pelagios.org`) or
   the relevant LOD/Peripleo working channel linked from <https://pelagios.org>,
   and provide the VoID URL above.
2. For a Peripleo ingest config, the dataset dump is the `void:dataDump` target
   inside that VoID: `https://openetruscan.com/pelagios.jsonld`. **Point strict
   (non-redirect-following) ingesters at the `www` form**
   `https://www.openetruscan.com/pelagios.jsonld` directly, because the
   advertised apex form `307`-redirects (see caveat below).
3. Highest-value upstream contribution: add or correct **Pleiades** place
   records where Etruscan findspots are thin — only 408 of 5,932 inscriptions
   currently carry a Pleiades body.

## Honest caveats (verified, not blockers)

- **The advertised dump URL is the apex form and redirects.** `void:dataDump`
  names `https://openetruscan.com/pelagios.jsonld`, which `307`s to the `www`
  host; `curl -L` and browsers follow it, but an ingester that refuses
  cross-host redirects should be given the `www` URL explicitly. (The redirect
  is same-registrable-domain apex→www.)
- **Annotation target URIs do not dereference.** Each annotation's `id` /
  `target.source` is `https://openetruscan.com/inscriptions/{id}` (plural),
  which returns `404`. The human-readable page lives at the **singular**
  `https://www.openetruscan.com/inscription/{id}` (`200`, HTML with embedded
  JSON-LD), and `https://www.openetruscan.com/api/inscription/{id}` returns
  `200 application/json` (not `application/ld+json`). Peripleo ingests the dump,
  so this does not block registration, but aligning the emitted target URI with
  a route that resolves would let LOD consumers follow the link.
- **EAGLE linkset is empty** (`void:triples 0`); the subset is declared but
  carries no links yet.

## Re-verifying before you submit

```bash
# Dataset description (small) — check counts and the dataDump target
curl -sSL https://www.openetruscan.com/void.ttl

# Feed size (multi-MB) — confirm the collection total
curl -sSL https://www.openetruscan.com/pelagios.jsonld | grep -o '"total":[0-9]*' | head -1
```

The counts are rendered live from the corpus (`getVoidStats` /
`getPelagiosFeedRows` in `openEtruscan-frontend/lib/db/queries.ts`), so they
track the database and will change as the corpus grows — re-run the checks and
update this page's numbers when you submit.
