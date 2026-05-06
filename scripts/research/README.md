# Research scripts

Tools that support the research strand documented in
[`/research/`](../../research/). Distinct from
[`scripts/training/vertex/`](../training/vertex/) (production
training/embedding pipelines) — these are exploratory tools that
produce *research-time* artefacts: extracted corpora, candidate
anchor sets, sample selections for review, and so on.

## Files

| File | Purpose |
|---|---|
| [`extract_classical_etruscan.py`](extract_classical_etruscan.py) | Walks `data/classical_texts/formatted/` (Perseus TEI XML), extracts every paragraph mentioning Etruscan/Tyrrhenian, and emits two JSONL outputs: full passages (~1,795) and regex-extracted bilingual gloss candidates (~29, mostly noise). Underpins [Milestone 3](../../research/WBS.md#milestone-3--primary-source-attested-anchor-mining). |

## Typical use

Run the extractor against the on-disk Perseus mirror (already populated
under `data/classical_texts/`):

```bash
python scripts/research/extract_classical_etruscan.py \
  --passages-path data/extracted/etruscan_passages.jsonl \
  --bilingual-glosses-path data/extracted/etruscan_glosses.jsonl
```

Outputs are gitignored under `data/extracted/`. See
[`/research/notes/primary-sources.md`](../../research/notes/primary-sources.md)
for what's in those outputs and how the yield breaks down by author.

## When you'd add a script here

If it's:
- An LLM-as-parser pipeline (M3.1)
- A review-packet generator (M2.2)
- A frozen-benchmark reproducer (M1.5)
- Anything else research-y rather than production-ingest-y

it goes here, not in `scripts/training/vertex/` or `scripts/ops/`.
