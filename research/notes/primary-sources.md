# Primary-source corpus — what's there, what we extracted

What we have on disk and what we got out of it. Used to drive
[Milestone 3](../ROADMAP.md) (primary-source attested-anchor mining).

## On-disk corpus

The Perseus Digital Library `canonical-latinLit` and `canonical-greekLit`
TEI XML mirrors are cloned (gitignored) at:

```
data/classical_texts/canonical-latinLit/   # ~1075 XML files
data/classical_texts/canonical-greekLit/   # ~similar size
data/classical_texts/formatted/Latin/      # cleaner per-author layout
data/classical_texts/formatted/Greek/      # cleaner per-author layout
```

The `formatted/` subtree is the easier path — author names are human-
readable directories, and each work is a single XML file with the
language code in the filename (`*-lat*.xml`, `*-grc*.xml`).

## Yield from the first extraction pass

[`scripts/research/extract_classical_etruscan.py`](../../scripts/research/extract_classical_etruscan.py)
walks the formatted tree, parses TEI XML, extracts every paragraph
containing Etruscan/Tyrrhenian terms, and emits two JSONL files:

| Output | Path | Rows |
|---|---|---|
| Etruscan-mentioning passages | `data/extracted/etruscan_passages.jsonl` | **1,795** |
| Regex-extracted bilingual gloss candidates | `data/extracted/etruscan_glosses.jsonl` | 29 (mostly false positives — see below) |

Top contributing authors (Latin):

| Author | Passages |
|---|---|
| Livy (Ab urbe condita) | 557 |
| Cicero | 191 |
| Pliny the Elder | 58 |
| Virgil | 51 |
| Aulus Gellius (Noctes Atticae) | 21 |
| Horace | 27 |
| Tacitus | 13 |
| Suetonius | 7 |

Top contributing authors (Greek):

| Author | Passages |
|---|---|
| Dionysius of Halicarnassus (Roman Antiquities) | 244 |
| Plutarch | 83 |
| Strabo | 50 |
| Polybius | 46 |
| Athenaeus | 45 |
| Diodorus Siculus | 41 |

## The regex approach failed (mostly)

The first pass tried Latin/Greek regex patterns for explicit bilingual
gloss statements:

```
Etrusci/Tusci [linguā suā] X dicunt/uocant Y
X qui apud Etruscos Y dicitur
quod aesar ... Etrusca lingua deus uocaretur
```

29 hits, of which only one is an unambiguously real bilingual
attestation: **Suetonius, *Divus Augustus* — `aesar = deus`**.

> *"…quod aesar, id est reliqua pars e Caesaris nomine, Etrusca
> lingua deus uocaretur."*
>
> "…because 'aesar' — the remaining part of the name 'Caesar' — is
> called 'god' in the Etruscan language."

The other 28 are false positives. Free word order in classical prose
plus paraphrased equivalences (as opposed to formulaic gloss patterns)
make regex too brittle for this task at scale.

## What we don't have on disk

The high-yield bilingual-gloss sources are *not* in the Perseus formatted
subset:

- **Festus / Sextus Pompeius Festus**, *De Verborum Significatu* — the
  ancient Latin grammarian's lexicon. Defines dozens of Etruscan
  loanwords (`histrio`, `popa`, `subulo`, `lanista`, `satura`, etc.).
  *thelatinlibrary.com* has a different *Festus* (Rufius Festus, 4th-
  century historian). Reach via Project Schmidt or Brepols.
- **Macrobius**, *Saturnalia* III — preserves the standard theonym
  equivalences (`Tinia → Iuppiter`, `Uni → Iuno`, `Menrva → Minerva`)
  with explicit attribution in classical prose.
- **Hesychius of Alexandria**'s lexicon — Greek lexicon of obscure
  words including a small set of Etruscan-glossed entries.

These are tracked under [Milestone 3.4](../WBS.md) as a discrete
follow-up. None are paywalled in principle; all are bounded by
"how much effort to find a clean digital edition".

## Path forward

[Milestone 3 of the WBS](../WBS.md) sketches the LLM-as-parser approach
on the existing 1,795 passages. The argument for it:

- **The primary text exists**. We have 1,795 paragraphs of Latin /
  Greek prose mentioning Etruscan.
- **Regex is too rigid** to recover paraphrased glosses from those
  paragraphs.
- **An LLM is a good parser**, *if used as a parser* — i.e. asked to
  extract what's stated in the text, not to volunteer what it knows
  about Etruscan from training data.
- The output is **traceable**: every extracted pair carries an
  `evidence_quote` from the source passage.

Cost: ~$2-4 for one full sweep with Claude Haiku. Expected yield:
30-100 attested anchor pairs after manual review.

## Evidence quality tiers (proposed for M3.2 review)

When we review the LLM-extracted candidates:

- **Tier A — Direct equivalence statement.** The author says
  explicitly "X means Y in Etruscan/Latin/Greek". Suetonius's
  `aesar = deus` is the prototype. These should be the highest-
  confidence training anchors.
- **Tier B — Paraphrased equivalence.** Author describes a thing in
  Latin/Greek and notes the Etruscan name. Not a 1:1 lemma map but
  close.
- **Tier C — Contextual adjacency.** Author uses the Etruscan word
  in Latin/Greek text and the surrounding context constrains the
  meaning. Useful for *semantic-field* training but not for
  lexical-equivalence training.

Tier A + B feed into the M3.3 contrastive fine-tune positives. Tier C
is reserved for follow-up work on context-augmented embeddings.
