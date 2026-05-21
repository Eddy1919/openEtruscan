# Lacunae Restoration Codebook (v2)

**Task:** Given an Etruscan inscription with a marked lacuna (Leiden notation), produce the character sequence most likely to fill it. Scored against the editor's published restoration.

**Status:** frozen at 2026-05-17.

## Source of gold restorations

Every gold restoration in this benchmark comes from a **published philological edition**. The editor's restoration is treated as the gold answer because:
- It represents the consensus reading of trained classicists working from autopsy or photographs.
- It is citable and contestable; a paper can disagree with it on philological grounds.

Important: the editor's restoration is **not always correct in an absolute sense** — many readings are conjectural. The benchmark scores agreement with the editor, not agreement with reality. Authors of papers using v2 must say so explicitly.

## Leiden notation we accept

| Notation | Meaning | Width | Example |
|---|---|---|---|
| `[abc]` | editor's restoration of three lost characters | known, known | `lar[θal]` (`θal` is restored) |
| `[.]` `[..]` `[...]` | gap of n characters, no restoration proposed by editor | known, unknown | `mi tite [.] al` (1 char missing) |
| `[---]` `[− − −]` | gap of unknown length | unknown | `lar[---]nas` |
| `[abc?]` | conjectural restoration | known, doubtful | not used in v2 gold (editor flagged as uncertain) |
| `(abc)` | editor's expansion of an abbreviation | not a lacuna | NOT included in v2 |
| `<abc>` | editor's addition of omitted characters | not a lacuna | NOT included in v2 |
| `{abc}` | editor's deletion of redundant characters | not a lacuna | NOT included in v2 |

**The v2 set includes only `[abc]`-style restorations** (case 1) where the editor proposed a specific reading. Unknown-content lacunae (`[.]`, `[---]`) are **excluded** from gold because there is no editor-supplied answer to score against.

## Strata

Each gold row carries a `width_bucket`:
- `w1`: lacuna spans 1 character
- `w2_3`: 2–3 characters
- `w4_6`: 4–6 characters
- `w7_plus`: 7+ characters

Width is calculated as the number of characters inside the editor's restoration brackets, *not* counting Etruscan word-separators (`·`, `•`) inside the gap.

We expect strong width × difficulty interaction: w1 is mostly trivial (single-character disambiguation, often deducible from glyph traces); w7+ is essentially open-ended generation.

## What we score against

Each row in the gold set has the shape:

```json
{
  "id": "Ta 1.66",
  "source_edition": "CIE Vol. II Section I",
  "context_before": "larθ velus",
  "lacuna_gold": "papas",
  "context_after": "spural",
  "width": 5,
  "width_bucket": "w4_6",
  "object_type": "tomb wall",
  "inscription_type": "funerary",
  "philologist_accept": true,
  "philologist_accept_reason": "..."
}
```

A model is given the input:

```
larθ velus [?????] spural
```

…where `?????` marks a known-width gap, and asked to fill it. The model's output is then scored:

### Metric 1 — char-level top-1 accuracy

For each position in the gold restoration, the model gets credit iff its output's character at that position matches the gold's character. The score for one inscription is `n_correct_chars / n_gold_chars`. The metric over the test set is the mean across inscriptions.

### Metric 2 — span exact-match rate

Fraction of inscriptions where the model's entire output string equals the gold string. Brutal but the cleanest publication-grade metric.

### Metric 3 — hallucination rate

**Hallucination = emission of a character outside the marked lacuna span.**

Concretely: we hand the model the input `larθ velus [?????] spural`. The model returns a full output string. If the output's `context_before` portion does not equal `larθ velus`, or the `context_after` portion does not equal `spural`, the model has hallucinated. We count the row as a hallucination event regardless of how good the lacuna content itself is. We report:

- `hallucination_rate = n_hallucination_rows / n_total_rows`

This is what made v1's "Phil. Safety: High" claim vacuous — it was never quantified. v2 puts a number on it.

### Metric 4 — top-3 char accuracy

Same as metric 1 but the model's top-3 predictions per position are all scored; a hit if any of the top-3 matches gold.

## Why "philologist_accept" gates gold inclusion

The LLM-jury pipeline (`pipelines/lacuna_jury.py`) does not produce gold. It produces *candidate* gold: editor-restored rows where the LLM-jury's restoration agrees with the editor's. Disagreement rows go to the queue.

A philologist must accept each candidate before it joins the gold set, because:
1. Some editor restorations are themselves disputed; the philologist may flag them.
2. Some restorations are "obviously over-determined" (e.g., `larθ vel[us papa]s` where the next-token model basically can't lose). These rows skew metrics upward and should be marked so they can be analyzed separately.
3. The find-context may make the restoration extra-obvious in a way the text alone doesn't show.

Philologist labels on each row:
- `accept` — fair-difficulty restoration, include in primary gold set
- `accept_overdetermined` — restoration is trivially recoverable; include but report metrics separately
- `reject` — restoration is too disputed or the editor flagged uncertainty; do not include
- `unsure` — philologist cannot decide; route to second adjudicator

Two independent philologists must achieve Krippendorff α ≥ 0.80 on a 30-row spot-check before the gold set ships.

## What is NOT in v2

- Restoration of unknown-length lacunae (`[---]`). These need a separate "lacuna detection + width prediction" task.
- Restoration where the editor's reading is conjectural (`[abc?]`).
- Restoration of fragmentary words where the original was never legible.
- Multi-lacuna rows where the joint optimization matters (defer to v3).

Authors using v2 should not claim "lacuna restoration is solved." The set covers a constrained sub-problem (known-width gaps with editor-published gold restorations) and the metrics will reflect that.
