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
| `adjudication` | `{status: seeded|llm_checked|verified|rejected, by, date}` |
| `check_url` | required for `llm_checked`: the online edition/page the locus was corroborated against |

## Adjudication ladder

`seeded` (drafted from literature, unchecked) → `llm_checked` (an LLM with
web access corroborated the locus against an online edition; `check_url`
required; still not trusted) → `verified` (a human checked form, gloss, and
locus against the sources) or `rejected` (reason in notes).

## Rules

1. **No use before verification.** Only `verified` records may feed an eval.
   `llm_checked` shortens the human's work; it never substitutes for it.
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

## Source map and batch status (2026-08-30)

- **Ancient authors' glosses** — SEEDED and web-checked: the classic items
  (Suetonius aesar, Varro subulo, Livy ister, Hesychius entries, Servius
  capys/lucumo, Paul. ex Festo falado + arseverse, Liber glossarum months)
  plus the full Dioscorides "nomina Tusca" set (16 forms, Wellmann loci,
  TLE 808–853) with Briquel 2018's caveat recorded: those forms are Latin
  in morphology and their Etruscan-language status is contested.
- **Bilinguals** — the Benelli corpus (27 items + 4 related) is in
  `bilinguals.jsonl` with ET/TLE/CIE numbers, texts, and the equation each
  fixes. `crossref_bilinguals.py` matches them against the published corpus
  (report: `crossref_report.csv`); the lautni = libertus urn (Pe 1.211) and
  the Pesaro haruspex stone (Um 1.7) are corpus rows.
- **Modern lexica, pair-by-pair** — SEEDED via `seed_lexicon_batch.py`:
  ~195 records, each carrying its sources (Bonfante 2002 glossary via the
  Wiktionary appendix; Steinbauer etruskisch.de; the Mc Callister glossary
  with Pallottino/Bonfante codes; Liber Linteus/Pyrgi/numerals pages) and
  its disputes (Steinbauer's shifted numeral row, leine, etera, cepen, meχ,
  cilθ, tamera, ziva-). Wallace 2008 appendix remains to be mined
  page-by-page from a physical/scanned copy.
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
