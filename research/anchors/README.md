# Primary-source anchor mining (WBS P4)

This directory holds the output of the LLM-as-parser pipeline that
mines bilingual gloss equivalences from classical Greek and Latin
passages mentioning the Etruscans.

## Files

| File | Source | Role |
|---|---|---|
| `llm_anchors_raw.jsonl` | [`scripts/research/llm_extract_anchors.py`](../../scripts/research/llm_extract_anchors.py) | **Raw** Gemini 2.5 Pro extraction output. One JSON object per gloss; ~48% raw precision; needs hand-review before use. |
| `llm_anchors_raw.jsonl.passages.jsonl` | same | Per-passage status sidecar — `{passage_index, status, n_glosses}`. Lets the script resume after interruption. Also documents which passages were skipped (`api_error` / `parse_error`). |
| `llm_anchors_raw.run.log` | same | Full stderr+stdout log of the full-corpus run that produced the JSONL. Audit trail for the token-count / cost / verbatim-drop count claims. |
| `attested.jsonl` | [`scripts/research/review_anchors.py`](../../scripts/research/review_anchors.py) (T4.2 — not yet implemented) | **Hand-reviewed** keep-list. Each row has been confirmed by a human against the source passage. Dedup'd against the held-out test split. |

## Provenance of `llm_anchors_raw.jsonl`

Generated on **2026-05-11** from
`data/extracted/etruscan_passages.jsonl` (1,795 classical passages
mentioning the Etruscans, gitignored — reproducible from upstream
extractions in `scripts/research/extract_classical_etruscan.py`).

| Stat | Value |
|---|---:|
| Passages processed | 1,795 |
| Wall time | 62.3 minutes |
| Model | `gemini-2.5-pro` on Vertex AI (`europe-west1`, project `double-runway-465420-h9`) |
| Input tokens | 3,528,618 |
| Output tokens | 4,745 |
| Cost (USD) | $4.46 |
| Glosses kept (post verbatim-substring validation) | 27 |
| Verbatim-substring hallucination drops | 9 |
| Parse errors | 0 |
| API errors | 0 |

The substantial gap between "27 kept" and "13–18 likely-real" reflects
that the verbatim-substring check catches *hallucinated citations*
but cannot catch *appositive metaphors* or *Greek-glossing-Latin*
false positives — those need T4.2 hand-review.

## Re-running

```bash
# Default — reads data/extracted/etruscan_passages.jsonl, writes here:
python scripts/research/llm_extract_anchors.py

# Resume after Ctrl-C — re-reading the .passages.jsonl sidecar skips
# already-processed input:
python scripts/research/llm_extract_anchors.py
```

Estimated cost is reported at the start of every run; the full-corpus
run lands at ~$4.46 on Gemini 2.5 Pro (one-off; resume is free for
already-processed passages).
