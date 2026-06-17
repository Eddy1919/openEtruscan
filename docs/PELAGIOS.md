# Pelagios alignment

OpenEtruscan participates in the [Pelagios](https://pelagios.org) model of
*linking the past through places*: inscriptions are published as Web Annotation
JSON-LD whose targets are gazetteer URIs (Pleiades for places, Trismegistos and
EAGLE for cross-corpus identity), described by a [`void.ttl`](../void.ttl)
dataset record. The LOD emission lives in
[`src/openetruscan/api/lod.py`](../src/openetruscan/api/lod.py).

This page documents the workflows that *grow* that linked data. The triad
Pelagios cares about is **place + time + people**; we already emit people
(SNAP prosopography, [`snap_exporter.py`](../src/openetruscan/api/snap_exporter.py)).

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

## Next steps (planned)

- **Time axis — PeriodO.** Map the period labels from
  `openetruscan.core.statistics` (`archaic` / `classical` / `late`) to
  [PeriodO](https://perio.do) period URIs and emit them alongside the place
  links, completing place + time + people.
- **Recogito round-trip.** Export the v2 LLM-jury adjudication queue to
  [Recogito](https://recogito.pelagios.org)-importable annotations so human
  philologists adjudicate in the community's own tool, then re-import decisions.
