# Philologist Instructions — OpenEtruscan v2.0 Adjudication

You are one of the human adjudicators for the OpenEtruscan v2.0 classification gold set. This document is everything you need.

**Time commitment:** ~3–4 hours, paid for thinking, not speed.

## What you are doing

The OpenEtruscan corpus has 6,500+ inscriptions. A 400-row stratified test split was created, and two LLMs (Google Gemini 2.5 Pro and Meta Llama 4 Maverick) independently labelled each row using the codebook attached to this bundle. On **159** rows they agreed unanimously at high confidence → those go straight to candidate-gold. On **162** rows both refused (`unsure`) → they are recorded as "irreducibly ambiguous" without further action. The remaining **79 rows** are the ones where the two LLMs disagreed. Those are in `adjudication_queue.csv` and they are your job.

You are NOT being asked to re-rate the LLMs. You are being asked to apply the codebook strictly and produce the correct label, in the cases where the LLMs split.

## Bundle contents

| File | What it is | What you do with it |
|---|---|---|
| `codebook_classification.md` | The 7-class decision tree + positive/negative examples per class | Read first; keep open while working |
| `PHILOLOGIST_INSTRUCTIONS.md` | This file | You're reading it |
| `adjudication_queue.csv` | 79 rows for you to adjudicate | Fill in two columns (see below) |
| `spot_check_30_adjudicator_A.csv` | 30 rows (subset of the 79) | Only one of you (let's say "A") fills this in |
| `spot_check_30_adjudicator_B.csv` | Same 30 rows | The other adjudicator ("B") fills this in independently |
| `compute_alpha.py` | Script that computes Krippendorff α between A and B | Run after both spot-checks are complete |

The dual spot-check is the rigor gate: if A and B disagree too often (Krippendorff α < 0.80), the codebook is too ambiguous and needs revision before the full 79-row adjudication ships.

## Workflow

### Step 1 — Read the codebook end-to-end
Open `codebook_classification.md`. Pay particular attention to:
- The decision tree (rules 1–8).
- The tie-breaking rules (object > text, find-context > formula, etc.).
- The 7 positive and negative examples per class.
- The `unsure` route (you are allowed to mark a row `unsure` if even strict application of the codebook cannot decide).

### Step 2 — Do the spot-check first (30 rows)

Open your assigned CSV (`spot_check_30_adjudicator_A.csv` OR `spot_check_30_adjudicator_B.csv`). For each row:

- Read the inscription text and translation.
- Apply the decision tree.
- Fill the `adjudicator_decision` column with one of:
  `funerary`, `ownership`, `dedicatory`, `votive`, `legal`, `boundary`, `commercial`, `unsure`, `reject`
- Optionally add a short note in `adjudicator_notes` (a single sentence is plenty).

`reject` means "the text is corrupted, non-Etruscan, or the inscription should not be in the corpus at all". Reserve this for genuine defects, not for difficulty.

**Do NOT** look at the other adjudicator's choices. The blind comparison is the point.

### Step 3 — Run the α check

Once both A and B have completed their spot-check CSVs, run:

```bash
python compute_alpha.py spot_check_30_adjudicator_A.csv spot_check_30_adjudicator_B.csv
```

It will print Krippendorff's α between you. The target is **α ≥ 0.80**.

- **α ≥ 0.80** → you're aligned on the codebook; proceed to Step 4.
- **0.60 ≤ α < 0.80** → look at the rows where you disagreed. Identify the codebook rule that failed to disambiguate. Add a note for the project lead; possibly the codebook needs a v2.0.1 revision before proceeding.
- **α < 0.60** → the codebook is too ambiguous in its current form. Stop and contact the project lead. Do not proceed to Step 4.

### Step 4 — Adjudicate the full 79-row queue

Once the α check passes, open `adjudication_queue.csv` and fill in `adjudicator_decision` + `adjudicator_notes` for ALL 79 rows. You can split the work (e.g., A does even-indexed rows, B does odd-indexed) or both do all 79 and average — your call, but document which.

### Step 5 — Return

Send the filled CSVs back to the project lead. The ratified labels join the v2 candidate-gold set and become the **v2.0 gold classification dataset**, citable in publications.

## How to make calls

- **Apply the rubric, not your gut.** If your intuition disagrees with the codebook, log the case in `adjudicator_notes` ("Codebook rule 5 says ownership but the find-context strongly suggests funerary; followed the rubric") and follow the rubric for the current row. These notes feed v2.0.1 codebook revisions.
- **`mi` formulas are tricky.** Per the codebook tie-breaking rules: bare name on tomb wall = funerary (rule 1). `mi` + name on portable object = ownership. `mi` + verb of giving = dedicatory.
- **Trust the find-context over the text.** A simple personal name on a cippus is `boundary` if the cippus shape and findspot are diagnostic — even if no `tular`/`spural` appears in the text.
- **Don't invent classes.** If nothing fits, mark `unsure`. The seven classes are closed; new ones go in v3.

## Quality bar

This dataset will appear in academic publications. The point of this whole pipeline is to have v2 labels that are *demonstrably* more rigorous than the v1 "0.28 macro F1 on 29 rows" baseline. Adjudication quality is the bottleneck.

If you find the codebook ambiguous, that's important data: file a note. We'd rather discover an ambiguity here than after we publish.
