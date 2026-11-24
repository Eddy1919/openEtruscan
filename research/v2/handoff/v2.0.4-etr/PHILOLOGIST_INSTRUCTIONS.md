# Philologist Instructions: OpenEtruscan v2.0.4 Adjudication

You are one of the two human adjudicators for the OpenEtruscan v2.0.4 classification gold set. This document is everything you need.

**Time commitment:** about 4 to 6 hours in total. Codebook read-in takes 30 to 45 min. The 30-row blind spot-check takes about 1 h at ~2 min/row, and the α check plus review 15 min. The 59-row queue takes 2 to 3 h at 2 to 3 min/row. We pay for thinking, not speed: easy rows take seconds, hard rows can take minutes. Budget more if you tend to consult the bibliography on edge cases.

## What you are doing

The OpenEtruscan corpus has 6,500+ inscriptions. A 427-row test split was drawn so that no test text repeats a training text. Three LLMs (Claude Opus 4.8, Gemini 3.1 Pro and Gemini 3.5 Flash) labelled each row independently using the codebook attached to this bundle. The outcome:

- On **167** rows all three agreed, each at confidence medium or high. Those form the candidate-gold set.
- On **201** rows all three answered `unsure`. They are recorded as irreducibly ambiguous, with no further action.
- The remaining **59 rows** are the ones where the LLMs disagreed. Those are in `adjudication_queue.csv`, and they are your job.

You are NOT being asked to re-rate the LLMs. You are being asked to apply the codebook strictly and produce the correct label where the LLMs split.

## Bundle contents

| File | What it is | What you do with it |
|---|---|---|
| `codebook_classification.md` | The 7-class decision tree + positive/negative examples per class | Read first; keep open while working |
| `PHILOLOGIST_INSTRUCTIONS.md` | This file | You're reading it |
| `adjudication_queue.csv` | The 59 rows the LLMs disagreed on | Fill in two columns (see below) |
| `spot_check_30_adjudicator_A.csv` | 30 rows spread across the classes: 9 from the queue, 21 from the candidate-gold set | Only one of you ("A") fills this in |
| `spot_check_30_adjudicator_B.csv` | Same 30 rows | The other adjudicator ("B") fills this in independently |
| `compute_alpha.py` | Computes Krippendorff α between A and B | Run after both spot-checks are complete |

The dual spot-check is the rigour gate. If A and B disagree too often (Krippendorff α < 0.80), the codebook is too ambiguous and needs revision before the queue adjudication ships.

## Workflow

### Step 1: Read the codebook end to end
Open `codebook_classification.md`. Pay particular attention to:
- The decision tree (rules 1 to 8).
- The tie-breaking rules (object > text, find-context > formula, etc.).
- The 7 positive and negative examples per class.
- The `unsure` route: you may mark a row `unsure` if even strict application of the codebook cannot decide.

### Step 2: Do the spot-check first (30 rows)

Open your assigned CSV (`spot_check_30_adjudicator_A.csv` OR `spot_check_30_adjudicator_B.csv`). For each row:

- Read the inscription text and translation.
- Apply the decision tree.
- Fill the `adjudicator_decision` column with one of:
  `funerary`, `ownership`, `dedicatory`, `votive`, `legal`, `boundary`, `commercial`, `unsure`, `reject`
- Optionally add a short note in `adjudicator_notes` (a single sentence is plenty).

`reject` means "the text is corrupted, non-Etruscan, or the inscription should not be in the corpus at all". Reserve it for genuine defects, not for difficulty.

The CSV also shows each LLM's label and rationale. Decide from the codebook first, and read the LLM columns only afterwards, if at all.

**Do NOT** look at the other adjudicator's choices. The blind comparison is the point.

### Step 3: Run the α check

Once both A and B have completed their spot-check CSVs, run:

```bash
python compute_alpha.py spot_check_30_adjudicator_A.csv spot_check_30_adjudicator_B.csv
```

It prints Krippendorff's α between you, with a 95% bootstrap interval. The target is a point estimate of **α ≥ 0.80**.

- **α ≥ 0.80**: you're aligned on the codebook; proceed to Step 4.
- **0.60 ≤ α < 0.80**: look at the rows where you disagreed. Identify the codebook rule that failed to disambiguate and add a note for the project lead. The codebook may need a revision before you proceed.
- **α < 0.60**: the codebook is too ambiguous in its current form. Stop and contact the project lead. Do not proceed to Step 4.

Thirty rows give a wide interval: if your true agreement is α = 0.85, a 30-row estimate can land anywhere from about 0.69 to 0.96. A result near the threshold is a reason to look at the disagreements together, not a verdict on either of you.

### Step 4: Adjudicate the 59-row queue

Once the α check passes, open `adjudication_queue.csv` and fill in `adjudicator_decision` + `adjudicator_notes` for ALL 59 rows. Nine of them you have already seen in the spot-check; keep your spot-check decision unless the second look changes your mind, and say so in the notes if it does. You can split the work (for example A does even-indexed rows, B odd-indexed) or both do all 59 and reconcile. Either is fine, but record which.

### Step 5: Return

Send the filled CSVs back to the project lead. The ratified labels promote the v2.0.4 candidate-gold set to the **v2.0.4 gold classification dataset**, citable in publications without the LLM-consensus caveat.

## How to make calls

- **Apply the rubric, not your gut.** If your intuition disagrees with the codebook, log the case in `adjudicator_notes` ("Codebook rule 5 says ownership but the find-context strongly suggests funerary; followed the rubric") and follow the rubric for the current row. These notes feed codebook revisions.
- **`mi` formulas are tricky.** Per the codebook tie-breaking rules: bare name on tomb wall = funerary (rule 1). `mi` + name on portable object = ownership. `mi` + verb of giving = dedicatory.
- **Trust the find-context over the text.** A simple personal name on a cippus is `boundary` if the cippus shape and findspot are diagnostic, even if no `tular`/`spural` appears in the text.
- **Don't invent classes.** If nothing fits, mark `unsure`. The seven classes are closed; new ones go in v3.

## Quality bar

This dataset will appear in academic publications. The point of the pipeline is v2 labels that are *demonstrably* more rigorous than the v1 baseline of "0.28 macro F1 on 29 rows". Adjudication quality is the bottleneck.

If you find the codebook ambiguous, that is important data: file a note. We would rather discover an ambiguity here than after we publish.
