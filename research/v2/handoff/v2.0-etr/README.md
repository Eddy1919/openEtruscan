# Philologist handoff bundle — OpenEtruscan v2.0 (Etruscan classification)

This directory packages everything two human adjudicators need to ratify the v2.0 classification gold set. Generated automatically from the v2 jury outputs at `gs://long-facet-427508-j2_cloudbuild/openetruscan-v2/classify/20260520T205613Z/`.

## Source provenance
- Codebook version: v2.0 (frozen 2026-05-17)
- Jury models: Gemini 2.5 Pro + Llama 4 Maverick (both on Vertex AI)
- Jury run: 2026-05-20, build `4242b290-9de7-46b5-8e19-a118bd1e1a2d`
- 400-row stratified test split, seed=42
- Jury outcome: 159 candidate-gold (unanimous agreement) | 79 adjudication queue (disagreement) | 162 all-unsure

## Files

| File | Purpose |
|---|---|
| [`PHILOLOGIST_INSTRUCTIONS.md`](PHILOLOGIST_INSTRUCTIONS.md) | Read this first. End-to-end workflow. |
| [`codebook_classification.md`](codebook_classification.md) | The frozen v2.0 codebook (7-class decision tree + examples). |
| [`adjudication_queue.csv`](adjudication_queue.csv) | The 79 rows the LLMs disagreed on. Open in any spreadsheet. |
| [`spot_check_30_adjudicator_A.csv`](spot_check_30_adjudicator_A.csv) | 30-row sub-sample for adjudicator A's blind pass. |
| [`spot_check_30_adjudicator_B.csv`](spot_check_30_adjudicator_B.csv) | Same 30 rows for adjudicator B's blind pass. |
| [`compute_alpha.py`](compute_alpha.py) | Computes Krippendorff α between A and B once both spot-checks are complete. |

## Handoff workflow (recruiter view)

1. Send this directory to two Etruscologists. Pair them so they don't discuss the rubric beforehand.
2. They each read the codebook + instructions, fill in the appropriate spot-check CSV, and run `compute_alpha.py`.
3. If α ≥ 0.80 → both proceed to fill in `adjudication_queue.csv`. Otherwise the codebook needs revision before going further.
4. Returned CSVs land back here; the ratified labels join the v2 candidate-gold set as `v2.0 gold` (citable in publications).

## What this fixes about v1

The v1 dataset reported "0.28 macro F1 on 29 held-out rows" with **silver labels only** (no human ratification, no inter-rater α). v2.0 will ship with:
- 5× larger held-out test (400 vs 29)
- 159 candidate-gold rows with 100% LLM-jury agreement at high confidence
- 79 human-adjudicated rows with measured inter-rater α
- Bootstrap 95% CIs on every reported metric (no point estimates without uncertainty)
- Pre-registered eval protocol ([`research/v2/PRE_REGISTRATION.md`](../../PRE_REGISTRATION.md))

That's the gap between "publishable methodology" and what v1 shipped.
