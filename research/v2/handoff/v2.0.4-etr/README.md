# Philologist handoff bundle: OpenEtruscan v2.0.4 (Etruscan classification)

Everything two human adjudicators need to ratify the v2.0.4 classification
gold set. Unlike the superseded [`../v2.0-etr/`](../v2.0-etr/) bundle, which
was built ad hoc from GCS files that died with a retired GCP project, this
one regenerates deterministically from committed evidence:

```bash
make -C research/v2 classify-handoff
```

## Source provenance

- Codebook version: v2.0 (frozen 2026-05-17; unchanged, only the jury and
  the split changed at v2.0.4)
- Test pool: the **text-disjoint** frozen split, 427 rows, seed=42
  (`research/v2/data/classify_test_v2.jsonl`; PRE_REGISTRATION.md Deviation
  §D; a strict superset of the pre-registered 400)
- Jury: **Claude Opus 4.8 + Gemini 3.1 Pro + Gemini 3.5 Flash**, all via
  Vertex AI, run 2026-08-08, 427×3 ratings, zero API errors
- Jury outcome: **167 candidate-gold** (unanimous, confidence ≥ medium) |
  **59 adjudication queue** (disagreement) | **201 all-unsure**
- Krippendorff α = **0.8557** overall; read it with the lineage caveat:
  two of three raters share the Gemini lineage, which inflates agreement
  (same caveat as the v2.0.3 lacuna panel, PRE_REGISTRATION.md §B)
- Raw evidence: [`../../results/classify/`](../../results/classify/)
  (committed, SHA256-pinned)

## Files

| File | Purpose |
|---|---|
| [`PHILOLOGIST_INSTRUCTIONS.md`](PHILOLOGIST_INSTRUCTIONS.md) | Read this first. End-to-end workflow. |
| [`codebook_classification.md`](codebook_classification.md) | The frozen v2.0 codebook (7-class decision tree + examples). |
| [`adjudication_queue.csv`](adjudication_queue.csv) | The 59 rows the LLMs disagreed on, one label/confidence/rationale column set per rater. |
| [`spot_check_30_adjudicator_A.csv`](spot_check_30_adjudicator_A.csv) | 30-row stratified sub-sample for adjudicator A's blind pass. |
| [`spot_check_30_adjudicator_B.csv`](spot_check_30_adjudicator_B.csv) | Same 30 rows for adjudicator B. |
| [`compute_alpha.py`](compute_alpha.py) | Krippendorff α between A and B once both spot-checks are done. |

## Workflow

1. Two Etruscologists, paired so they don't discuss the rubric beforehand.
2. Each reads codebook + instructions, fills in their spot-check CSV; run
   `compute_alpha.py`.
3. α ≥ 0.80 → both fill in `adjudication_queue.csv`. Below that, the
   codebook needs revision first.
4. Returned CSVs land back here; ratified labels promote the v2.0.4
   candidate-gold to **v2.0.4 gold** (citable without the LLM-consensus
   caveat).
