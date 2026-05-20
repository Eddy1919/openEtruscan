# Adjudication Guide

For the philologist working the queue produced by the LLM jury.

## What you're doing

You have a JSONL file of inscriptions where the 3-model jury could not agree on a single label. Your job is to make the call. The goal is *not* to defer to the models — the goal is to apply the codebook strictly and produce a gold answer.

Expected workload:
- Roughly 200–400 rows per stream (classification + lacuna)
- Average decision time: ~30 seconds per row (with the codebook open)
- Total: 2–4 hours per stream

You are paid for thinking, not speed. If a row needs 5 minutes of bibliography lookup, take it.

## Setup

1. Read [`codebooks/classification.md`](../codebooks/classification.md) end-to-end before starting. Same for `lacunae.md` when working that queue.
2. Open the queue JSONL alongside this guide. Each row carries:
   - `id` — inscription identifier
   - `raw_text` / `canonical_transliterated` — the text
   - `translation` (if any)
   - `silver_label`, `silver_confidence` — the v1 weak label
   - `jury_summary.per_model` — what each LLM proposed and why
3. Have the relevant fascicles open: Pallottino-Rix *Etruskische Texte* (ET), CIE volumes, the Larth dataset translations, and Wallace 2008 for vocabulary.

## Per-row decision

For each queue row, return one of:

| Verdict | When | Output field |
|---|---|---|
| `accept(label_X)` | The codebook's decision tree clearly produces `label_X`. The jury was wrong or split. | `gold_label = label_X`, `gold_source = "human_adjudicated"` |
| `relabel(new_label, reason)` | None of the jury proposals fits, but the codebook does specify a label. | `gold_label = new_label`, `gold_reason = "<your reason>"` |
| `unsure(reason)` | Even applying the codebook strictly, the evidence is genuinely insufficient. | `gold_label = "irreducibly_ambiguous"`, `gold_reason = "<why>"` |
| `defect` | The row's text is corrupted or non-Etruscan; remove from gold. | `gold_label = "defect"`, `gold_reason = "<why>"` |

**Do not invent classes.** If you find yourself wanting to call something "magical/curse" or "graffito", route to `unsure` instead and flag in your adjudication notes — that's input for a v3 codebook revision, not a v2 label.

## Pitfalls

1. **"It looks like a name" ≠ ownership.** A bare personal name on a tomb wall is `funerary` (decision-tree rule 1), not `ownership`. The find-context is decisive.
2. **Translation bias.** The Larth dataset's English translation can mislead — e.g., translating `cana` as "this" rather than as the dedicatory marker. Trust the Etruscan over the translation.
3. **Confirmation laziness.** If two models agreed and one dissented, your prior should be 50/50 on the agreement — not 2/3. LLMs share training data and make correlated errors.
4. **"My intuition says X."** Apply the rubric, not your gut. If your intuition disagrees with the rubric, log the case in `data/codebook_revision_proposals.md` and follow the rubric for the current row.

## Krippendorff α check (mandatory before sign-off)

Before the gold set ships, a **second philologist** independently adjudicates a 50-row sub-sample. The two adjudicators' labels are then fed to `eval/bootstrap.py::krippendorff_alpha_nominal()`. If α < 0.80:

- Identify the rows you disagreed on.
- Each adjudicator writes a 1-paragraph defense of their label.
- The codebook is revised to disambiguate (with explicit examples added to the rule that failed).
- A v2.1 codebook is published.
- The disagreement rows are re-adjudicated; if α now ≥ 0.80, ship.
- If still < 0.80 after one revision, the task is harder than this codebook supports. Document and downgrade publication claims.

## What to log

Keep a running notes file `data/adjudication_notes_<adjudicator_id>.md` with:

- Row id + your verdict + 1-sentence reason
- Any rule from the codebook you found ambiguous or contradictory
- Any new class you wished existed (input for v3)

These notes are part of the published artifact. Honest disagreement is more valuable than performative consensus.
