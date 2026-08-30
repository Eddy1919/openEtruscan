# Pelagios & Linked Open Data Integration

OpenEtruscan implements the [Pelagios](https://pelagios.org) model for ancient-world Linked Open Data, interconnecting inscriptions across **geography (Pleiades)**, **chronology (PeriodO)**, and **cross-corpus registries (Trismegistos, EAGLE)**.

The corpus is published as a Web Annotation collection at [`/pelagios.jsonld`](https://www.openetruscan.com/pelagios.jsonld) and described by a VoID dataset descriptor at [`/void.ttl`](https://www.openetruscan.com/void.ttl).

---

## 1. Spatial Axis: Pleiades Alignment

To link unstructured historical findspots (`Clusii in agro`, `Perusiae`, `Volaterris`) to stable [Pleiades](https://pleiades.stoa.org) gazetteer entities:

1. **Stemming & Latin Normalization**: The matcher (`src/openetruscan/core/gazetteer.py`) removes locative Latin case endings and administrative stopwords (`in agro`, `in museo publico`).
2. **Indexing & Proposal Generation**: Candidates are generated and filtered at a tuned precision threshold (0.90):
   ```bash
   # 1. Build local gazetteer from Pleiades dump (Etruria bounding box)
   python scripts/data_pipeline/build_pleiades_gazetteer.py

   # 2. Generate findspot -> Pleiades link proposals
   python scripts/data_pipeline/propose_pleiades_links.py --from-db

   # 3. Interactive human review
   python scripts/data_pipeline/review_pleiades_links.py
   ```
3. **Storage & Serialization**: Accepted alignments are saved to `data/pleiades_mapping.yaml` and embedded into JSON-LD annotations at render time.

---

## 2. Chronological Axis: PeriodO Alignment

Temporal estimates are mapped to formal [PeriodO](https://perio.do) period definitions via `src/openetruscan/core/periodo.py`:

- **Authority Dataset**: Uses the MAPPA Lab Tuscany chronological model (`p03dzfb`), covering Etruscan historical phases (Orientalizing → Archaic → Classical → Hellenistic) without temporal overlap.
- **Serialization**: Period URIs are serialized as `dcterms:temporal` properties and `identifying` bodies in the Web Annotation feed.
- **Timeline Integration**: `/api/stats/timeline` tags century bins with canonical PeriodO identifiers.

---

## 3. Collaborative Annotation: Recogito Round-Trip

OpenEtruscan integrates with [Recogito](https://recogito.pelagios.org) for human epigrapher curation:

```bash
# Export adjudication queue to Recogito-compatible CSV
python scripts/research/export_recogito.py \
    --queue research/v2/handoff/v2.0-etr/adjudication_queue.csv \
    --output /tmp/recogito_upload.csv

# Import adjudicated annotations back into the project
python scripts/research/import_recogito.py \
    --export /tmp/recogito_annotations.csv \
    --links-out data/pleiades_link_queue.jsonl \
    --decisions-out /tmp/adjudicated.csv
```
