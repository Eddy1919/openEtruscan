# Frozen classification split (Stream A) — superseded 2026-08-08 (text-disjoint)

## Current state (2026-08-08)

The committed split is the **text-disjoint** regeneration: 427 test / 285
train, produced by the exact pre-registered invocation below after
`classify_split.py` learned to sample text groups instead of rows
(PRE_REGISTRATION.md Deviation §D). Three properties, all verified
programmatically at regeneration time:

1. **The old 400-row test pool is a strict subset of the new 427.** Same
   seed, same sampling path; the only change is that 27 train rows whose
   normalized text matched a test row were pulled across. Every id the
   v2.0.2 jury scored, all 79 adjudication-queue ids, and the philologist
   handoff CSVs therefore remain valid references into the current test pool.
2. **The new 285-row train pool is a strict subset of the old 312.** No row
   entered training that was not already there; 27 left.
3. **Zero normalized-text overlap between pools** (`split_contamination.py`
   reports 0/427).

Superseded hashes, for the record: test
`7df5e46c7d8b26df000b87bd125ef8049e3822ce7c008f76c6a5a8cb0cc75f61` (400 rows),
train `8a8b83fb0d48139d52b38b0e42a7c772723d41e3581460551272d9e6556c25bb`
(312 rows). Any historical number citing those hashes was measured against a
train pool now known to leak 25 test texts.

---

## Prior repair — 2026-07-17

## What happened

The previously committed `classify_test_v2.jsonl` (99 rows) and
`classify_train_pool.jsonl` (613 rows) had **empty text fields on every row**
and did not match the pre-registered n=400 test-pool size. They were a corrupt
export (id-only extract, text join never written back) and were **not** the
artifact the v2.0.2 jury ran on.

## The repair

Both files were regenerated deterministically on 2026-07-17 with the exact
pre-registered invocation (`research/v2/Makefile` → `classify-split`):

```bash
python -m research.v2.pipelines.classify_split \
    --corpus research/data/openetruscan_clean.csv \
    --silver research/data/openetruscan_labels.csv \
    --out-train research/v2/data/classify_train_pool.jsonl \
    --out-test  research/v2/data/classify_test_v2.jsonl \
    --n-test 400 --seed 42
```

`openetruscan_clean.csv` is the public Zenodo deposit
([10.5281/zenodo.20075836](https://doi.org/10.5281/zenodo.20075836)),
SHA256 `4fc09af94005655bfe26affeeb48295c88606ae23c8dbc33ff5436f9083f69f8`
(recorded in `SHA256SUMS`; the CSV itself stays out of git — fetch it with
`scripts/ops/fetch_data.py` or from the DOI).

## Verification that this is the split the jury ran on

- All **79** adjudication-queue IDs in
  `research/v2/handoff/v2.0-etr/adjudication_queue.csv` (produced by the
  actual jury run) are contained in the regenerated 400-row test pool, and
  their `canonical_transliterated` text matches the handoff CSVs byte-for-byte
  (e.g. id 1085 `arnt ziχn(i)al`).
- The 99 IDs of the old corrupt test file are a strict subset of the
  regenerated 400 (same seed, deterministic generator).
- 0/400 test rows and 0/312 train rows have empty text; train∩test = ∅.

## Known open delta

The regenerated train pool holds **312** silver-labelled rows;
`docs/INTELLIGENCE_V2.md` §2 reports **282** training rows for the v2.0.2
classifier. The 30-row difference is not explained by any filter in
`train_classifier.py` and most likely reflects a small difference between the
corpus state at jury time and the published Zenodo CSV. Until that is
reconciled, treat 312 as the canonical pool and 282 as the historically
reported training count. Tracked as an open reproducibility item in
`PRE_REGISTRATION.md` Deviation §C.

## Signal-source rename (same day)

Immediately after the repair, the label provenance tag
`gold:claude_hand_label` was renamed to `silver:claude_hand_label` in
`research/data/openetruscan_labels.csv` (184 rows) — those labels are
LLM-derived, not philologist-validated, and the word "gold" invited
miscitation. The split was regenerated after the rename; membership, row
order, and silver labels are byte-identical — only the
`silver_signal_source` strings changed (verified programmatically).

`SHA256SUMS` pins all four artifacts; verify with `shasum -a 256 -c SHA256SUMS`
(the corpus line requires the CSV fetched to `research/data/`).
