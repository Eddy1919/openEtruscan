# Pelagios alignment

OpenEtruscan participates in the [Pelagios](https://pelagios.org) model of
*linking the past through places*: inscriptions are published as Web Annotation
JSON-LD whose bodies carry gazetteer URIs (Pleiades for places, Trismegistos and
EAGLE for cross-corpus identity) plus PeriodO period URIs for time. The corpus
is described by a live VoID record at
<https://www.openetruscan.com/void.ttl>, whose `void:dataDump` names the
annotation feed at <https://www.openetruscan.com/pelagios.jsonld> — both served
by the frontend. The JSON-LD builder lives in
[`src/openetruscan/api/lod.py`](../src/openetruscan/api/lod.py).

This page documents the workflows that *grow* that linked data. Of the triad
Pelagios cares about — **place + time + people** — the live feed emits place
(Pleiades bodies) and time (PeriodO, below). The prosopography ("people") is
modeled in the corpus but is **not** currently emitted as Pelagios/SNAP Linked
Data: the standalone SNAP exporter was removed in the 2.0 surface cleanup as an
unwired backend duplicate. To join the Pelagios graph, see the runbook in
the maintainer-held registration runbook.

## Raising Pleiades coverage (place axis)

Most inscriptions carry a findspot string but no Pleiades ID. These strings are
messy Latin surface forms — `Clusii in agro`, `Perusiae`, `Volaterris`,
`Tarchna` — so the link can't be a dict lookup; it needs fuzzy matching with
Latin-aware normalisation. The matcher is
[`openetruscan.core.gazetteer`](../src/openetruscan/core/gazetteer.py) (pure,
unit-tested in [`tests/test_gazetteer.py`](../tests/test_gazetteer.py)); the
network and human steps are three scripts:

```bash
# 1. Build a local gazetteer from the Pleiades places + names dumps
#    (filtered to the Etruria / expansion bbox). Network required.
python scripts/data_pipeline/build_pleiades_gazetteer.py
#    → data/pleiades_gazetteer.json

# 2. Propose findspot → Pleiades links for everything not yet linked.
python scripts/data_pipeline/propose_pleiades_links.py --from-db
#    (or --findspots-file findspots.txt for an offline dry run)
#    → data/pleiades_link_queue.jsonl   (only candidates ≥ --threshold, default 0.84)

# 3. Review the queue with a human. Accepted links are appended to
#    data/pleiades_mapping.yaml — the file lod.py already reads — so each
#    approval immediately becomes Pelagios-emittable.
python scripts/data_pipeline/review_pleiades_links.py
```

Design notes:

- **Why a file queue, not a DB table.** This is offline maintainer curation, not
  public submission, so it mirrors the existing `human_review.py` file-queue
  pattern rather than the user-facing `ProposedAnchor` table + API.
- **Why `difflib`, not `rapidfuzz`.** The matcher is in the always-importable
  package core and takes no new dependency. The real signal is the
  normalisation (stripping Latin case endings and locative scaffolding so
  `Clusium`/`Clusii`/`Clusii in agro` collapse to one stem), not the metric.
  Swapping in `rapidfuzz` is a drop-in upgrade if recall needs it.
- **Promotion to the DB.** `pleiades_mapping.yaml` resolves at JSON-LD render
  time. To also populate the `inscriptions.pleiades_id` column (so
  `?has_provenance` / the search facets see it), run the existing reconcile/
  enrichment path.

### Tuning (against the live corpus, 838 distinct findspots / 5,932 inscriptions)

The default threshold is **0.90**, chosen from a coverage/precision sweep:

| threshold | findspots matched | inscriptions covered |
| --- | --- | --- |
| 1.00 (exact stem) | 57 | 1,174 (53%) |
| 0.90 (default) | 75 | 1,280 (58%) |
| 0.84 (old default) | 90 | 1,328 (60%) |

The extra recall below 0.90 is mostly *wrong*: `Clusino GA.` → the lake
*Clusinus* instead of the city, modern museum cities (`Parisiis` → `Parsiana`),
and position descriptors (`in fronte DA.`). Since this is a review queue, a
higher threshold keeps reviewer signal-to-noise high; lower it with
`--threshold` if you want to sweep the long tail by hand.

Two findings fed back into the matcher: adding `cum` and museum/collection words
(`in museo publico`, `cum agro`) to the stopword set recovered ~70 inscriptions
that were scoring just under threshold; and matching is **stem-prefix indexed**
(`prefix_len`) because a full O(findspots·places) `difflib` pass over the ~11k
gazetteer places does not finish — the indexed path runs in ~2s.

Known precision gaps still open (not threshold-fixable): **place-type
disambiguation** (prefer settlements over lakes/rivers — the gazetteer carries
feature types) and **non-findspot strings** (catalogue sigla like `GA.`/`FA.`,
pure museum provenance) that should be filtered before matching.

## Time axis — PeriodO (done)

Every dated inscription now links to a [PeriodO](https://perio.do) period
definition, completing the time axis. The mapping lives in
[`openetruscan.core.periodo`](../src/openetruscan/core/periodo.py) (pure,
unit-tested in [`tests/test_periodo.py`](../tests/test_periodo.py)) and is wired
into `inscription_to_jsonld`.

- **Authority.** We link against the MAPPA Lab Tuscany data model (PeriodO
  authority `p03dzfb`), whose Etruscan-era periods (Orientalizing → Archaic →
  Classical → Hellenistic) *tile* the timeline with no gaps or overlaps and are
  spatially scoped to Etruria. Pinning one coherent authority keeps the links
  joinable.
- **Linking by date.** `period_for_year(date_approx)` picks the period whose
  interval contains the inscription's signed-year estimate — the most defensible
  path. `period_for_label("archaic"|"classical"|"late")` is a fallback for rows
  with only a feature-based label (from `core.statistics`).
- **Emission.** The period URI appears both as an `identifying` body (so
  Peripleo ingests it next to the gazetteer refs) and as a `dcterms:temporal`
  property (`{"id": "<ark>", "label": ...}`) for plain RDF consumers. URIs are
  canonical PeriodO ARKs (`http://n2t.net/ark:/99152/<id>`).
- **Timeline.** `/stats/timeline` tags each century bucket with the PeriodO
  period for its midpoint (`period_id` / `period_label` / `period_uri`), so the
  timeline UI is joinable on chronology too. The enrichment
  (`enrich_timeline_buckets`) is pure and unit-tested; the DB layer just calls it.

## Recogito round-trip (done)

[Recogito](https://recogito.pelagios.org) is Pelagios's collaborative annotation
tool. The v2 LLM-jury adjudication queue can now go out to it and come back. The
parse/harvest core is [`openetruscan.core.recogito`](../src/openetruscan/core/recogito.py)
(pure, unit-tested in [`tests/test_recogito.py`](../tests/test_recogito.py)).

```bash
# Out: jury split-decisions → a CSV a philologist uploads to Recogito.
python scripts/research/export_recogito.py \
    --queue research/v2/handoff/v2.0-etr/adjudication_queue.csv \
    --output /tmp/recogito_upload.csv

# In: Recogito's annotation export → harvest two things.
python scripts/research/import_recogito.py --export /tmp/recogito_annotations.csv \
    --links-out data/pleiades_link_queue.jsonl \
    --decisions-out /tmp/adjudicated.csv
```

What the import harvests:

- **Place links** — PLACE annotations resolved to a Pleiades URI become
  findspot → Pleiades proposals, written in the *same queue format*
  `propose_pleiades_links.py` emits (tagged `source: recogito`). They flow
  straight through `review_pleiades_links.py` into `pleiades_mapping.yaml` — so
  Recogito is a second, human-curated source for the place axis above. The loop
  closes.
- **Classification decisions** — per-document TAGS become the philologist's
  adjudication decision (`id, decision_tags` CSV), to fold back into the v2
  gold set.

CSV parsing is tolerant of Recogito's cross-version header naming
(case-insensitive alias map), so an export from any recent Recogito version
parses.
