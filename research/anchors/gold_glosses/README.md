# Gold glosses — Etruscan↔meaning pairs with a paper trail

Candidate gold-standard gloss pairs for expanding the semantic evaluation
beyond the 22-pair rosetta test set. Every record carries its citation,
confidence, source type, and adjudication status. Nothing here enters an
evaluation or a training set until a human with the sources in hand has
moved it to `verified`.

## Provenance warning

The seed batch (`adjudication.status = "seeded"`) was drafted by an LLM from
the standard philological literature. The word–meaning pairs follow the
published consensus, but **every primary-source locus must be checked
against the edition before the record is trusted** — a seeded citation is a
claim, not a fact. Verification means: locate the passage (or the modern
treatment), confirm the Etruscan form, the gloss, and the locus, then set
`status: verified`, `by`, and `date`. A record that fails checking is set to
`rejected` with the reason in `notes`, never deleted.

## Schema (`gold_glosses.jsonl`, one JSON object per line)

| field | meaning |
|---|---|
| `etr` | Etruscan form, NFC, lowercase. For glosses transmitted only in Greek/Latin garb, the transmitted form (e.g. `aesar`). |
| `gloss_en` | English meaning, lowercase, short |
| `lat` | Latin equivalent when one is attested or standard, else null |
| `source_type` | `ancient_gloss` (a Greek/Latin author states the meaning), `bilingual` (meaning fixed by a parallel text), `lexicon` (modern philological consensus), `combinatory` (contextual/formulaic inference), `loanword`, `numeral` |
| `citation_primary` | ancient locus, as precise as the seeder could defend; may be author-level pending verification |
| `citation_modern` | modern treatment (Bonfante & Bonfante 2002; Wallace 2008; Pallottino TLE 1968) |
| `confidence` | `high` / `medium` / `low` — philological confidence in the PAIR, independent of adjudication |
| `notes` | disputes, transmission problems, competing readings |
| `adjudication` | `{status: seeded|verified|rejected, by, date}` |

## Rules

1. **No use before verification.** Only `verified` records may feed an eval.
2. **Eval before training.** Verified records extend the *evaluation* first
   (a new frozen split, generated the way
   `eval/harness/_generate_eval_split.py` did it — deterministic seed,
   stratified). Only pairs assigned to a train split may ever touch training.
3. **The existing rosetta test set stays frozen.** `validate.py` marks every
   record that overlaps `eval/harness/rosetta_eval_pairs.py` (train or
   test). A record overlapping the rosetta TEST split can be verified for
   the record's own sake but is excluded from any new eval or training use —
   it is already spoken for.
4. **Rejected ≠ deleted.** Failed candidates stay, with reasons: negative
   adjudications are data.

## Source map (where the next batches come from)

- **Ancient authors' glosses** (seeded here, partially): the ~60 items
  collected in TLE and Bonfante & Bonfante 2002 (glossary chapter).
  Not yet seeded: the Dioscorides plant-name synonyms — the seeder was not
  confident enough of individual items to draft them; take them directly
  from a TLE copy.
- **Bilinguals**: Pyrgi tablets (Etruscan–Phoenician); the ~30 Latin–Etruscan
  epitaphs (CIE). Cross-referencing corpus ids against the TLE bilingual
  list is scripted work; the equations they fix are mostly onomastic and
  kinship/office.
- **Modern lexica, pair-by-pair**: Bonfante & Bonfante 2002 glossary
  (~350 entries), Wallace 2008 appendix. Copy facts with citations, not the
  compilation wholesale.
- **Combinatory candidates**: `research/anchors/attested.jsonl` (17 pairs,
  UNVERIFIED) and the IBM-1 miner output
  (`research/experiments/hybrid_embed/mine_pairs.py`) — both feed the same
  adjudication queue with `source_type: combinatory`.

## Validate

```bash
python research/anchors/gold_glosses/validate.py
```

Checks schema, enums, NFC normalization, duplicates, and rosetta overlap;
exits non-zero on violations. Run it in CI and after every edit.
