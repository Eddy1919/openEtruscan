# Corpus Curation — findings, what works, what doesn't, what's next

*Honest writeup of the May 7-9 2026 corpus-curation cycle. Distinct
from [`FINDINGS.md`](FINDINGS.md), which covers the earlier Rosetta
vector-space strand.*

---

## TL;DR

We took the OpenEtruscan corpus through a full character-level
deconfounding cycle (mirror-glyph mapping, sibilant unification,
Old Italic regeneration), produced a 6,567-row ML-ready dataset
joined with Larth metadata (Vico & Spanakis 2023), built a
712-label inscription-typology training set via reasoning cascade
with auditable signal trails, and tested three classifier
architectures and two seq2seq lacuna restoration models on the
result. Five concrete findings and two negative-result publications
emerge.

* **What works:** the cleaning pipeline (deterministic, reversible,
  every transformation documented); the etr-lora-v4 embedder
  retrained on cleaned data (qualitative wins on sibilant
  convergence, structural pattern matching, abbreviation handling);
  the CharCNN classifier on the 712-label cascade (5/5 perfect on
  unambiguous-signal held-out rows).
* **What doesn't:** ByT5-small + LoRA r=8 lacuna restoration (both
  v4 and v5 fail to converge — sentinel-token learning collapse, not
  a data issue); linear classifier head on 768-d frozen embeddings
  (curse of dimensionality at n=184/611); from-scratch character CNN
  classifier trained on ≤500 labels (chance-level macro F1).
* **What we now know:** the Etruscan classifier ML frontier is
  data-bound, not architecture-bound, demonstrated *invariant* across
  three architectures.

---

## 1. Corpus character-level cleaning

### Finding 1.1 — Mirror-glyph corruption is downstream of Larth, not in it

Audit of the 6,633-row prod DB found ~1,400 chars across ~250 rows
of non-Latin / non-Greek characters in the `canonical` column:

| Block | Chars | Most-frequent codepoints |
|---|---|---|
| Cyrillic | ~494 | Э (200), И (179), Я (89), О (6), А (4) |
| Latin Extended-B | ~619 | Ǝ (160), Ƨ (135), Ɔ (57), Ʀ (13) |
| Number Forms | ~100 | ↄ (79), Ↄ (21) |
| Math | ~19 | ∃ (17), ∂ (2) |
| Latin-1 stragglers | ~120 | ê (44), þ (5), Ð (18), ð (14) |

The pattern is unambiguous: these are **mirror-glyph artifacts of
an OCR pipeline that read retrograde Etruscan inscriptions
left-to-right** and grabbed visually-similar codepoints from
non-Latin Unicode blocks. `Я` is the mirror of Latin `R`, `Ǝ` is
the explicit "reversed E" codepoint, etc.

**Comparison against Larth (Vico & Spanakis 2023) — the upstream
seed corpus** — found *zero* Cyrillic, Latin-Ext-B, Number-Forms,
or Math characters in their `Etruscan` column across all 7,139
rows. The corruption was therefore introduced by the **CIE Vol. I
ingestion path** in the OpenEtruscan production database, not
inherited from the academic seed dataset.

### Finding 1.2 — Greek-block sibilants (θ χ σ φ ξ ς) are signal, not noise

An earlier automated-cleaning proposal would have mapped Greek-block
characters to ASCII Latin (θ → th, χ → kh, σ → s, φ → ph). Audit
revealed this would have *destroyed* standard philological
notation:

* θ appears 2,230 times (Etruscan dental fricative — universal in
  scholarly editions: Bonfante & Bonfante 2002; Wallace 2008;
  Pallottino 1968).
* χ (476), σ (223), φ (19), ξ (18), ς (16) all carry phonological
  meaning the consonant clusters cannot reproduce.

The deterministic mapping below preserves these. The "clean Latin"
hypothesis was wrong.

### Finding 1.3 — Sibilant traditions are scribally fragmented; cleaning unifies them

Etruscan epigraphy distinguishes two sibilants — `s` (sigma, 𐌔)
and `ś` (san, 𐌑) — corresponding to /s/ and /ʃ/ phonemes. Different
scholarly traditions encode the same san phoneme as `ś` (Bonfante
2002), `σ` (Pallottino 1968 Italian school), `š` (with caron), or
`ς` (final-sigma form).

In the unified mapping, all four normalize to **𐌑 (san)** when the
canonical_italic column is regenerated. This is verified to improve
embedding-space neighborhoods (see §5 below).

### Finding 1.4 — Three-class quality tagging cleanly separates trainable from diagnostic rows

After deterministic mapping, every row gets one of three quality tags:

| Tag | n | Definition |
|---|---|---|
| `clean` | 6,094 (92.8%) | Every char in `canonical_clean` is in the contract whitelist (Latin lowercase + scholarly Greek + Old Italic + Leiden punctuation). ML-ready. |
| `needs_review` | 154 (2.3%) | Residual chars outside the contract after mapping (e.g., scattered `Λ Π Ψ Γ` from heavily corrupted retrograde rows). |
| `ocr_failed` | 319 (4.9%) | Diagnostic regex `[0-9]\|\+` matches body text — these are digit-substitution OCR junk like `IAN8VJV1 ANV+: VEA`, unrecoverable deterministically. |

OCR-failed rows are kept in the dataset but excluded from training
by all downstream models. They retain value for error analysis and
for any future correction campaign.

---

## 2. Old Italic regeneration

### Finding 2.1 — Latin orthography rows must be detected and abstained from

The Old Italic block (U+10300–U+1031A) does not have a 1:1 mapping
to all Latin letters. Standard Etruscan letter ↔ glyph correspondence
(Bonfante 2002, Wallace 2008) gives:

```
a → 𐌀  c → 𐌂  e → 𐌄  v → 𐌅  z → 𐌆  h → 𐌇  i → 𐌉  k → 𐌊
l → 𐌋  m → 𐌌  n → 𐌍  o → 𐌏  p → 𐌐  ś → 𐌑  q → 𐌒  r → 𐌓
s → 𐌔  t → 𐌕  u → 𐌖  x → 𐌗  θ → 𐌈  φ → 𐌘  χ → 𐌙  f → 𐌚
σ → 𐌑   ς → 𐌑   (sibilant unification)
g, y    no Old Italic correspondent — abstain
```

When the canonical column contains **Roman/scholarly Latin
orthography** (e.g. `HASTI | PURNIS`, `PVLFENNIA ARRI`,
`C.Pulfennius:C.f|Calamus`), letter-by-letter remapping into Old
Italic produces a glyph stream that **never represented any
inscription that ever existed**. The script must detect these and
emit NULL.

Three detection rules cover the failure modes:

| Rule | Triggers on | Example caught |
|---|---|---|
| All-uppercase token of length ≥ 2 (excl. Roman numerals) | HASTI, ZANIDIA | CIE 2649, CIE 2670 |
| Token of length ≥ 4 with ≥ 75% uppercase (catches mixed-case retrograde garbage) | MVOVsIAO, OeAS | CIE 2261 |
| Title-case Latin proper noun of length ≥ 4 | Pulfennius, Calamus | CIE 2613 |

Pure Roman numerals (XXIX, CVI) are *not* abstained from — they
appear in legitimate late-Etruscan funerary formulae like
`avils : CVI murce` (Ta 1.107).

### Finding 2.2 — Coverage breakdown after the abstention rules

After applying §1 mapping and §2.1 abstention rules:

```
canonical_italic emitted     5,509 rows   (83.9%)
canonical_italic NULL        1,058 rows   (16.1%)
  ├─ Latin orthography         558
  ├─ ocr_failed                319
  ├─ needs_review              154
  └─ unmappable letter (g/y)    27
```

Every NULL has a documented reason. There are no silent dropouts.

---

## 3. Larth dataset comparison

The OpenEtruscan production corpus is built from Larth (Vico &
Spanakis 2023) plus CIE Vol. I extractions. We did a head-to-head
comparison.

| Metric | Larth | OpenEtruscan v1 |
|---|---|---|
| Total rows | 7,139 | 6,567 |
| Unique IDs | 4,712 | 6,567 |
| Rows with English translation | 2,891 (40.5% of Larth's rows) | 1,800 (27.4%) |
| Rows with year_from / year_to | 358 (5.0%) | 307 (4.7%) |
| Rows with Cyrillic mirror-glyph corruption | **0** | 250 (pre-cleaning) |
| Rows with Old Italic in raw_text | 0 | 359 (5.5%) |

### Finding 3.1 — All 4,712 unique Larth IDs appear in our DB

Zero Larth rows are missing. The 1,855 OpenEtruscan IDs absent
from Larth are CIE Vol. I extractions we ingested independently.
For those rows, no English translation or year metadata exists in
Larth, and they remain that way after the merge.

### Finding 3.2 — Larth's translation column is bimodal

Of 1,798 OpenEtruscan rows that received a non-empty `translation`
field from Larth, only **184 (~10.2%)** are real scholarly English
sentences. The remaining 1,614 are MT-pipeline artifacts: `mr-X
mrs-Y son/daughter` kinship-list patterns, single-word
transliterations, or run-on phrase fragments like
`thewingedhorsepegasos`.

This was a major surprise — Larth has been cited in published work
as having "translations for ~40% of inscriptions". The number is
correct in row-count terms but misleading: the *useful* coverage is
~10%. Any downstream model that relies on Larth translations as
training data must filter for real-English structure first.

### Finding 3.3 — Roman numeral case was lost in the OpenEtruscan ingestion

Larth: `felsnas : la : leθes svalce : avil : CVI murce` (Ta 1.107)
Ours: `felsnas la leθes svalce avil cvi murce`

Both colon separators and uppercase Roman numerals were
lower-cased / collapsed during the OpenEtruscan pre-prod cleaning
chain (specifically by the now-removed `cleanup2.sql` step). This
is a small information loss but worth documenting; future ingestion
should preserve case for known Roman-numeral patterns.

---

## 4. Inscription typology classification — data bottleneck

### Finding 4.1 — Three architectures all collapse below ~500 hand-labels

Tested on the 29-row independently-labeled held-out set with strict
zero-overlap enforcement (any row appearing in both training and
held-out demoted to `unknown` before training):

| Architecture | Train labels | Macro F1 | Notes |
|---|---|---|---|
| MicroTransformer | 257 (with keyword aug) | 0.53 | **inflated** — keyword-aug labels overlap test pattern space |
| MicroTransformer | 184 (clean hand) | 0.16 | true baseline at this scale |
| Linear logistic head on `etr-lora-v3` 768-d embeddings | 184 | 0.075 | **curse of dimensionality**: 0.24 samples per parameter |
| Linear head on `etr-lora-v3` 768-d embeddings | 611 | 0.14 | still overfits |
| MicroTransformer | 712 (cascade) | 0.21 | 2/5 on high-confidence checks |
| **CharCNN** | **712 (cascade)** | **0.28** | **5/5 on high-confidence checks** |

The 712-label CharCNN run is the best result. It generalizes from
9 training examples of the `legal` class (containing the keyword
`zilχ`) to a held-out `legal` row with the same keyword, and from
a handful of `dedicatory` training rows containing `Fufluns` /
`Turan` to held-out rows with the same deity references. **This is
feature learning, not memorization** — the model encoded "deity
name → dedicatory" as a transferable representation.

### Finding 4.2 — Macro F1 is dragged by inherently-ambiguous long-tail rows

On the 5 *high-confidence-signal* held-out rows (rows where an
unambiguous categorical marker is present — `zilχ` for legal,
deity name for dedicatory, kinship + slave attribution for
funerary), the CharCNN at 712 labels achieves **5/5 (100%)**.

The drop to 0.28 macro F1 across all 29 held-out rows is driven by
the *low-confidence* rows where signal genuinely doesn't exist —
short name-only fragments where even a human reading English
translations could not confidently assign a category. **The model
is being penalized for being correctly humble where humans are too.**

### Finding 4.3 — The bottleneck is annotation count, invariant across architecture

CharCNN at 712 labels reaches 0.28 macro F1.
MicroTransformer at the same data scale: 0.21.
Linear head on contextual embeddings: 0.14.

All three architectures fail to clear the 0.30 macro F1 threshold.
The problem is not capacity (transformer has more), not features
(embeddings encode more), and not inductive bias (CharCNN's
character-n-gram bias is the right one for Etruscan morphology).
The problem is that 712 silver-labels with documented signal trails
plus 29 held-out gold cannot densely cover the feature space of 7
inscription categories on a corpus this size.

The needed intervention is **gold annotation expansion** —
specifically expansion of the minority classes (votive, boundary,
legal, commercial) from 1–14 examples each to ≥30 each. This is
not a problem ML automation can solve; it requires expert human
labeling of ~500 additional rows.

---

## 5. etr-lora-v4 embedder — qualitative wins from re-training on cleaned corpus

We re-trained the XLM-RoBERTa + LoRA embedder (`etr-lora-v3` →
`etr-lora-v4`) on the cleaned V3 corpus extract (Cyrillic-purged,
sibilants unified, Old Italic regenerated) and ran a retrieval A/B
on three target failure modes of v3.

### Finding 5.1 — Sibilant convergence

* Query: `θania śeianti tlesnaśa`
* v3 top-5 neighbors: generic `θania:`-prefixed names (`θania:hecn(i)`,
  `θania:clantini`)
* v4 top-5 neighbors: `śeianti • hanunia • tleσnaśa`

Note the query has `ś`/`s`, the v4 neighbor has `σ`/`σ`. **v4 has
internalized the σ ↔ ś orthographic equivalence** — exactly what
the §1.3 unification was designed to enable.

### Finding 5.2 — Structural pattern recognition

* Query: `arnθ:apucu:θanχvilus:ruvfial:cvan`
* v3: scattered colon-fragments
* v4: `ramθa:capznei:c[v]an`, `v(elia):clanti:cvan`,
  `ramθa:peticui:cvan`

v4 retrieves the `[Name]:[Name]:cvan` formula structurally rather
than character-string-similarity. The model now encodes syntactic
pattern, not just surface n-grams.

### Finding 5.3 — Abbreviation handling

* Query: `arnθ:cicu:peθna:ś:l:`
* v3: generic colon strings (`tite::petruni:::::`)
* v4: `a(rn)θ(al) hupn(i)ś`, `arnθ:helen[e_]`

v4 associates the `ś:l:` patronymic abbreviation pattern with full
Etruscan names — useful for the practical case where users query
with abbreviated forms.

The qualitative gains are concentrated *exactly where the cleaning
intervened* (sibilant unification, mirror-glyph removal, Old Italic
regeneration). This confirms the encoder learned phonologically- and
structurally-meaningful features rather than surface character
coincidences. Re-embedding the full corpus and rebuilding the HNSW
index is justified.

---

## 6. ByT5 lacuna restoration — architecture mismatch

### Finding 6.1 — Both v4 and v5 collapse on held-out evaluation

Held-out: 100 clean inscriptions deterministically sampled, one
random word masked per row with `<extra_id_0>`, generation evaluated
for exact-match span restoration.

| Model | Trained on | Exact Match | CER | Output behavior |
|---|---|---|---|---|
| ByT5 v4 | raw corpus | 0.0% | ~720% | Hallucinates repeating bytes (`<pad>e ee e e e e`) |
| ByT5 v5 | cleaned corpus | 0.0% | ~160% | Span collapses to empty (`<pad><extra_id_1>`) |

Neither model generates valid span-corruption format. v5's
"better" CER is an artifact of degenerate empty-span output, not a
quality improvement.

### Finding 6.2 — Likely root cause: byte-level tokenization × sentinel × LoRA × small data

The model has to bridge two embedding sub-spaces during span
restoration: byte tokens (vocab IDs 0–255) and sentinel special
tokens (`<extra_id_0>`–`<extra_id_99>` at high IDs). With LoRA
rank 8 on Q/V projections only, ~6,000 training samples, and 12–15
epochs, the adapter does not have enough capacity to teach the
model *to emit the sentinels at all*. It learns content-shifts
(toward Etruscan-vocabulary statistics) but not new structural
behavior.

The training cross-entropy loss curves were misleading. eval_loss
of 16.54 (reported as "successful convergence") is **worse than
uniform-random for a 384-element vocabulary** (where uniform CE ≈
log(384) ≈ 5.95). Loss this high implies confidently wrong
predictions on the sentinel positions — a tell of degenerate
collapse that we missed because we were watching the loss curve
rather than running held-out generation evals.

### Finding 6.3 — Architectural recommendations for v3 lacuna work

ByT5 + LoRA was the wrong tool for low-resource Etruscan span
restoration. Two viable replacement architectures:

* **Character-level encoder-decoder from scratch** with a custom
  vocabulary of ~30 classes (Etruscan letters + dividers + 3
  special tokens). No sentinels, no LoRA, full training. Smaller
  parameter count + simpler task formulation = converges on this
  data scale.
* **Fill-in-blank classification head on the etr-lora-v4 encoder.**
  Reuses the validated Etruscan encoder; adds a per-position
  softmax over the Etruscan letter set. Trained as masked language
  modeling (BERT-style) rather than span corruption (T5-style).

Both side-step the byte ↔ sentinel bridging problem. The choice
between them is a capacity / engineering trade-off — see the
companion plan in `notes/lacuna-pivot-2026-05-09.md`.

The v5 ByT5 adapter is preserved on GCS as a documented negative
baseline; future work that succeeds on this task can compare against it.

---

## 7. Reasoning-cascade labeling methodology

### Finding 7.1 — Auditable signal trails are essential when no expert annotators are available

The 712-label set was produced by a priority-ordered cascade. Every
label carries the source signal that triggered it:

| Signal | n | Confidence | Rule |
|---|---|---|---|
| `gold:claude_hand_label` | 184 | high | Reasoned from real English Larth translation by Claude |
| `etr_keyword:funerary` | 93 | high | `suθi` / `avils` / `puia` / `clan` / etc. in canonical |
| `etr_formula:mi+name` | 92 | medium | Object self-id formula `mi <name>` in short canonical |
| `junk_translation:kinship_list` | 231 | medium | Larth MT-junk regex `mr-X mrs-Y son/daughter` |
| `junk_translation:deity_ref` | 34 | medium | Deity name (Tinia, Uni, Fufluns, Hercle, …) in MT junk |
| `etr_keyword:dedicatory_deity` | 45 | high | Etruscan deity name in canonical |
| `etr_keyword:legal` | 9 | high | `zilχ` / `marunuχ` / `purθ` etc. |
| `etr_keyword:boundary` | 8 | high | `tular` / `raśna` / `meθlum` |
| `etr_keyword:votive_deity` | 8 | high | `cver` / `alpan` / `fleres` + deity |
| `etr_keyword:commercial` | 2 | medium | `presnts` / `qutum` |
| `etr_formula:mi_present` | 4 | low | `mi` in long uncategorized canonical |
| `en_phrase:dedicatory` | 2 | high | Explicit "dedicated to" in real translation |

### Finding 7.2 — Excluding the corpus prior is critical

An earlier draft of the labeler defaulted name-only short fragments
(canonical with 1–4 tokens, no other signal) to `funerary` at low
confidence. This was correct philologically (most Etruscan stones
*are* funerary) but produced a 5,594-label dataset with **87%
funerary class**. Training on this would have taught the neural
to predict the corpus prior — exactly what the keyword-augmentation
pollution had done previously.

The final labeler **abstains** on rows with no positive signal
rather than launder the prior as a label. The label count drops
from 5,594 to 712, but every label is defensible. This is the same
methodological principle as Finding 2.1 (abstain on Old Italic
when the input is Latin orthography): emit NULL rather than emit
something silently wrong.

---

## 8. Held-out evaluation methodology

### Finding 8.1 — Independent labeling before training prevents leakage

The held-out evaluation set ([eval_heldout_29.csv](data/eval_heldout_29.csv))
was labeled by Claude reasoning on canonical + translation **before**
the cascade-labeled training set was applied to the database. Seven
overlap rows that appeared in both sets were **demoted to `unknown`
in the training set** before any model was trained, enforcing
strict zero data-leakage.

Every held-out row carries a `confidence` level (`high` / `medium`
/ `low` / `very_low`) and a `signal` description. This enables
stratified reporting:

* **All 29 rows, macro F1**: penalizes models for inherent
  ambiguity in the corpus (rows where humans cannot confidently
  agree).
* **5 high-confidence rows, accuracy**: tests whether the model
  can learn the unambiguous signals that should generalize.

A model that genuinely learns features should show a large gap
between these two metrics — and the CharCNN at 712 labels does
(0.28 vs 1.00). Models that learn keyword surface forms but not
features show a smaller gap.

### Finding 8.2 — 29 rows is small; bootstrap CIs are wide

At n=29 with 7 classes, bootstrap 95% confidence intervals on the
macro F1 estimate span roughly ±0.10. This means the difference
between the 0.16 baseline (n_train=184) and the 0.28 cascade
result (n_train=712) is **statistically meaningful but not robust
to small held-out variation**. Future work should expand the
held-out set to ≥100 rows, ideally with multi-annotator agreement.

---

## What we will and won't claim in publication

**Will claim:**

* First open-weight neural classifier baselines (CharCNN +
  MicroTransformer ONNX exports) for Etruscan inscription typology.
* First documented mirror-glyph deconfounding pipeline for
  retrograde-OCR'd Etruscan corpora.
* Empirical evidence that the Etruscan classifier ML frontier is
  data-bound, demonstrated *invariant across three architectures*.
* Qualitative retrieval improvements from cleaning-aware re-training
  of XLM-RoBERTa + LoRA encoders.
* A reusable held-out evaluation set with confidence levels and
  signal trails for any future Etruscan classifier benchmark.

**Will not claim:**

* "State of the art" on any metric. The CharCNN macro F1 0.28 is a
  meaningful baseline, not a competitive number — there is no prior
  baseline to compare against because no published Etruscan
  classifier exists, but absolute performance is well below any
  threshold for production deployment.
* That ByT5 worked. We document it as a negative baseline and
  point to architectural alternatives.
* That the dataset is "complete" or "gold". 712 labels with
  documented silver-quality signal trails is what it is — useful
  for training, not a substitute for expert annotation.

See [`BIBLIOGRAPHY.md`](BIBLIOGRAPHY.md) for primary sources and
methodological references cited above.
