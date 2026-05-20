# Rosetta Pair Codebook (v2)

**Task:** Define what counts as a valid (Etruscan, Latin/Greek) lexical equivalence pair for the Rosetta-eval-v2 benchmark.

**Status:** frozen at 2026-05-17.

## What is a pair?

A pair is a tuple `(etr, equiv, equiv_lang, evidence_quote, source, category)` where:

- `etr`: the Etruscan word, in canonical philological transliteration (Bonfante & Bonfante 2002 convention; θ χ σ φ ξ for Greek-block sibilants).
- `equiv`: the Latin or Greek word equated to it.
- `equiv_lang`: ISO-639-3 code, one of `lat` or `grc`.
- `evidence_quote`: the verbatim sentence from the classical author that asserts the equivalence.
- `source`: full bibliographic citation (author, work, passage index — book/chapter/section).
- `category`: one of the closed set below.

A pair is valid for the benchmark iff:
1. The classical author **explicitly asserts** the equivalence using a verb of equation (Greek: `ὀνομάζονται`, `ἐκάλεσαν`, `λέγουσι`; Latin: `appellare`, `vocare`, `dicere`).
2. The Etruscan word appears **verbatim** in the source passage (not paraphrased; substring-validated).
3. The pair survives the LLM-jury substring-validation step (Gemini 2.5 Pro + Claude Opus 4.7 + GPT-5 all confirm the cited evidence is a verbatim substring of the named source).
4. A human philologist accepts the pair.

Pairs that fail any test are **rejected** and listed in `data/rosetta_rejected_pairs.jsonl` with the reason. Rejection logs are part of the published artifact.

## Categories

Closed set, frozen:

| Category | Description | Example |
|---|---|---|
| `kinship` | Family relation terms | `puia` ↔ `uxor` (wife) |
| `theonym` | Names of deities | `nethuns` ↔ `Neptūnus` |
| `place` | Toponyms and ethnonyms | `cisra` ↔ `Caere` |
| `civic` | Civic/political titles | `zilath` ↔ `praetor` |
| `funerary` | Death-cult terms | `suθina` ↔ "for the tomb" |
| `cognate` | Identifiable Indo-European cognates or surface look-alikes | `sech` ↔ `secus` (daughter) |
| `gloss_only` | Hapax / single-attestation gloss from a classical author with no corpus parallel | `ἰταλὸν` ↔ `ταῦρον` (Apollodorus) |

The taxonomy is informed by Bonfante & Bonfante (2002), Wallace (2008), and Adiego (2003). Edge cases (e.g., a kinship term that is also a deity name) are routed to the philologist; the philologist picks the **most specific** category that fits.

## Why categorization matters for evaluation

The pre-registered primary metric is `P@10` (does the gold equivalent appear in the model's top-10 retrieval?). But P@10 is brutal on `gloss_only` pairs whose Latin/Greek equivalent is a rare word, so the secondary `semantic_field@10` metric uses the category to score "near miss" hits. The semantic-field vocabularies are frozen in [`eval/semantic_fields.json`](../eval/semantic_fields.json) at the freeze commit.

A pair's category cannot be changed after results are seen. If you realize a pair was miscategorized, log the correction in `data/rosetta_corrections.jsonl` and re-run; do not retroactively edit the frozen pair file.

## Train/test contamination — formal definition

A test pair `(etr, equiv, ...)` is **contaminated** with respect to a training corpus if any inscription in the training corpus contains the lemma `etr` (after canonical normalization). The contamination check is binary at the lemma level; you do not need to check `equiv` because the embedding model has not been fine-tuned on Latin/Greek corpora in this project.

The exclusion filter (`pipelines/verify_lemma_exclusion.py`):
1. Loads all pairs from `data/rosetta_eval_v2.jsonl`.
2. For each pair, extracts the Etruscan lemma after normalization.
3. Scans the entire training corpus for occurrences of that lemma (whole-word match against tokenized text).
4. Outputs a list of training inscription ids to exclude.

Models fine-tuned without honoring the exclusion list are **disqualified** from the benchmark.

## Provenance of the v1 seed pairs

The initial 22-pair eval set in v1 was bootstrapped from:
- 17 attested glosses mined via Gemini 2.5 Pro from the classical corpus (research/anchors/attested.jsonl)
- 5 cognate / theonym pairs hand-picked

For v2, we expand to ≥100 pairs by:
1. Re-running the Greek extraction over a broader passage set (Strabo, Dionysius of Halicarnassus, Diodorus Siculus, Plutarch, Lycophron, Apollodorus, Hesychius lexicon).
2. Adding a Latin extraction pass over Varro (*De lingua Latina*), Festus (*De verborum significatione*), Pliny (*Naturalis Historia*), and Servius's commentary on the *Aeneid*.
3. Adding theonym pairs from the Piacenza Liver, the Capua tile, and the Zagreb mummy bands where the deity name has a Roman interpretatio.
4. Adding kinship terms from Pallottino's *Testimonia Linguae Etruscae*.

Each addition is run through the same substring-validation gate. The expected post-validation yield is roughly 50% of raw candidates.
