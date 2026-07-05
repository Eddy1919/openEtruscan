# Registering OpenEtruscan with Pelagios / Peripleo

Getting into the Pelagios graph is a **community / hosting action**, not a code
change — and it has hard prerequisites that are **not yet met**. This page is the
honest runbook: what's missing, in what order to fix it, and how to submit.

> **Status (2026-06): NOT yet registerable.** The Pelagios artifacts are
> generated correctly by this repo but are **not served on the live site**, so
> there is nothing for Peripleo to crawl. Fix the prerequisites below first.

## What works today

`openetruscan.api.lod` renders the corpus as valid **W3C Web Annotation**
JSON-LD. Regenerate and inspect the full dump from the live corpus with:

```bash
python - <<'PY'   # (see git history of this doc for the full snippet)
# pages /api/search and runs lod.inscription_to_jsonld over every row
PY
```

A run on 2026-06-20 produced 5,932 annotations (~2.9 MB); every item had
`type` + `target` + `body`; 301 carried a PeriodO `dcterms:temporal`, 307 a
GeoJSON point. The pipeline is sound.

## Prerequisites (blockers, in order)

1. **Serve the discovery artifacts on the live origin.** Today these all 404:
   - `https://openetruscan.com/void.ttl` (the dataset description)
   - `https://openetruscan.com/pelagios.jsonld` (the annotation dump named by
     `void:dataDump` in [`void.ttl`](../void.ttl))
   - a SPARQL endpoint (optional)

   The live API is the **Vercel/TypeScript** app in the `openEtruscan-frontend`
   repo; the `/pelagios.jsonld` route in *this* repo's FastAPI is not deployed.
   Port the feed to a Vercel function (or publish the dump as a static file).

2. **Make item URIs dereference to JSON-LD.** `…/api/inscription/100` with
   `Accept: application/ld+json` currently returns plain JSON. Peripleo and LOD
   consumers expect content negotiation to JSON-LD on each `id`.

3. **Populate the place links the feed under-reports.** The generated dump had
   **0 Pleiades bodies** even though the DB reports 408 linked, because
   `inscription_to_jsonld` resolves Pleiades only from `data/pleiades_mapping.yaml`
   and **ignores the `inscriptions.pleiades_id` column**. Two fixes:
   - have `lod.get_pleiades_uri` fall back to the row's `pleiades_id`;
   - run the (now tuned) Pleiades review pipeline to grow the mapping — see
     [`PELAGIOS.md`](PELAGIOS.md).

4. **Reconcile `void.ttl` with reality.** It currently advertises 11,361
   entities / 34,477 triples; the live corpus is 5,932 inscriptions. Regenerate
   it (`api/void_gen.py`) so the counts, `void:dataDump`, and licence are
   accurate before anyone crawls it.

## Submitting (once the prerequisites are met)

The Pelagios discovery mechanism has changed across Peripleo versions, so
**confirm the current path with the community** rather than assuming — start at
<https://pelagios.org> and the Pelagios Network GitHub org. As of writing the
route is roughly:

1. **Join the Pelagios Network** (it's an association of projects) via the
   "Get involved" / membership path on pelagios.org.
2. **Announce the dataset** on the community channels (the mailing list / Slack)
   and at a **Linked Pasts** event — this is how new gazetteer-linked corpora
   are surfaced.
3. **Make it Peripleo-ingestable.** Current Peripleo builds ingest a dataset by
   pointing a config at a stable dump URL (the `void:dataDump`). Provide the
   served `pelagios.jsonld` + `void.ttl` URLs.
4. **Contribute place records upstream** where Etruscan findspots are thin in
   Pleiades — the highest-value, most-welcomed contribution.

## What I could not do

The submission itself is an external, authenticated community process and
depends on the live feed existing first — it is **not** something this repo can
complete on its own. Everything code-side that *can* be prepared is prepared;
the remaining steps are deploy-and-submit, listed above.
