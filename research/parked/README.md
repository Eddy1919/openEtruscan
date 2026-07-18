# Parked research strands

Everything in this directory is deliberately **on hold**, moved here on
2026-07-17 so the live tree only contains work that serves the current
priority: closing the Etruscan gold-label and evidence chain (philologist
adjudication, frozen splits, Leiden-aware corpus). Attention is the scarce
resource on a one-maintainer project; scaffolding for future strands was
competing with unfinished core science.

Parked ≠ deleted. Each strand keeps its files intact and can be promoted
back with a `git mv` when its prerequisite lands.

| Strand | Contents | Prerequisite for un-parking |
|---|---|---|
| `cv_pipeline/` | YOLO glyph-detection experiments: synthetic data generator, pseudo-labelers, training scripts, texture assets (moved from `src/cv_pipeline/` — it was never part of the installed package). | Human-ratified classification gold ships; imaging work gets its own evaluation protocol. |
| Neurosymbolic strand | Work plan is maintainer-held (WP1 was built — see `research/experiments/vsa_role_filler/`). | Same as above; the experiment stays where it is, only the forward plan is parked. |
| `v2-multilang/` | Oscan / Faliscan / Rhaetic annotation-protocol stubs (configs + codebook placeholders). No corpus is ingested for any of these languages; the stubs implied a readiness that did not exist. | An actual non-Etruscan corpus ingestion, plus the Etruscan protocol reaching human-ratified gold first. |

The Etruscan protocol (`research/v2/configs/etr.yaml`, `research/v2/codebooks/etr/`)
is live and unaffected.
