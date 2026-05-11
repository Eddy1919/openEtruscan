# Rosetta Vector Space — findings, what works, what doesn't, what's next

*Honest writeup, dated 2026-05-06. Supersedes the optimistic framing in
`ROADMAP.md` §"The Rosetta Vector Space".*

---

## TL;DR

We built a working cross-language word-vector retrieval system covering
Etruscan, Latin, and Greek (~209k vectors total) backed by `pgvector`
behind a public API. After three iterations on the embedding stack
(XLM-RoBERTa-base, then XLM-R + LoRA, then LaBSE) and two on the
metric, here's the honest read:

* **What works:** sub-word cognate retrieval (`fanu→fanum`,
  `hercle→hercules`, `menrva→minerva`), within-language semantic-field
  clustering (kinship terms cluster, theonyms cluster), and
  proper-noun / theonym alignment — the parts of the cross-language
  task where surface forms transfer.
* **What doesn't:** mapping a semantically-equivalent lexical pair
  when surface forms are unrelated (`clan→filius`, `puia→uxor`,
  `lautn→familia`). Nothing in the encoder's training set told it
  these are equivalent, and no amount of pooling or normalisation
  recovers signal that was never there.
* **Headline numbers (LaBSE, against the 62 curated Bonfante anchors):**
  * Strict-lexical precision@10: **0.071** (3/42 evaluated pairs)
  * Semantic-field precision@10: **0.119** (5/42)
  * For comparison, XLM-R baseline was 0.000 on both — LaBSE is a
    real upgrade for this task, just not enough to clear the
    publication-grade ≥0.40 gate.

The strict-lexical metric measures something the system *cannot* do
without parallel-data supervision. The semantic-field metric measures
what it *can* do, and is a more honest reflection of the system's
actual research utility.

---

## What this system is for (and isn't)

### Real, demonstrated use cases

1. **Cognate / loanword detection.** Given an Etruscan word, find
   orthographically-similar Latin/Greek words. Useful for spotting
   Etruscan→Latin borrowings (e.g. `histrio`, `popa`, `subulo`,
   `satura`) and shared Mediterranean vocabulary.
2. **Theonym + place-name alignment.** Etruscan deity and place names
   were often Latinised by Roman authors with regular sound
   correspondences. The system reliably recovers these:
   `menrva→minerva` (rank 7), `hercle→hercules` (rank 5),
   `fanu→fanum` (rank 1).
3. **Within-language semantic-field exploration.** For an Etruscan
   query, the system returns Latin words with related meanings even
   when the exact target lemma is wrong. Example: `papa→avus`
   (grandfather) returns `[papa, daddy, pater]` — `pater` (father)
   is at rank 3, semantically adjacent.
4. **Multilingual nearest-neighbour browsing.** A platform other
   ancient-language work (Phoenician, Faliscan, Oscan) could plug
   into without rebuilding the storage / API layer.

### Use cases the system does *not* support

1. **Mechanical Etruscan→Latin translation.** Lexical equivalence
   between unrelated surface forms is not in the model.
2. **Decipherment of unknown Etruscan words.** Top-k results will be
   orthographic neighbours of the source, not semantic equivalents.
3. **Replacing philological judgment.** The system produces ranked
   shortlists; a domain expert is needed to judge them.

---

## How we got here — three iterations

### v1: XLM-RoBERTa-base + LoRA fine-tune

* Embed Etruscan, Latin, Greek through XLM-R-base; mean-pool +
  L2-normalise; LoRA adapter (r=8, q+v target) fine-tuned on 6,097
  prod inscriptions over 5 epochs.
* **Result on first eval:** strict-lexical precision@k = 0.000 across
  the board. Investigation showed all cosines were 0.9998+ (mean-pooled
  XLM-R has severe anisotropy — Ethayarajh 2019; Mu et al 2018 "all-but-
  the-top"). Differences between hits and non-hits were sub-epsilon.

### v2: Per-language mean-centering on top of v1

* Two-pass over the JSONL: compute per-language centroid, subtract,
  re-L2-normalise.
* **Result:** cosines decompressed nicely (single-language pairs now
  span 0.42–0.81 with real spread), but cross-language semantic
  alignment remained weak — `cos(clan_ett, filius_lat)=0.73` was
  beaten by `cos(clan_ett, rege_lat)=0.97` because the encoder still
  rewarded surface-form similarity over meaning.

### v3 (current): LaBSE replaces XLM-R entirely

* `sentence-transformers/LaBSE` was *trained* with a translation-
  ranking objective on parallel sentences across 109 languages. It
  doesn't have the anisotropy of XLM-R-base because contrastive
  training spreads the manifold by construction.
* Same 768-d dimension as XLM-R; no schema migration; SBERT API
  handles pooling and normalisation correctly out-of-the-box.
* **Result:** strict-lexical @10 went from 0.000 (XLM-R) to 0.071
  (LaBSE). Semantic-field @10 from 0.000 to 0.119. Cosines now span a
  realistic range (`clan→filius=0.55`, `clan→tribe=0.88` —
  `tribe` is a real semantic neighbour the system is correctly
  surfacing).

The full per-stage comparison is in [docs/ROSETTA_FINDINGS_RAW.md](#)
once that file lands; intermediate JSONL files are in
`gs://openetruscan-rosetta/embeddings/`.

---

## Headline — rosetta-eval-v1, 4-column head-to-head

The frozen `rosetta-eval-v1` benchmark (held-out 22-pair test split;
`min_confidence=medium`; full methodology in
[`research/notes/reproduce-rosetta-eval-v1.md`](notes/reproduce-rosetta-eval-v1.md))
landed on 2026-05-11 with this table:

| Metric @10 | random | levenshtein | LaBSE (default) | v4 (xlmr-lora) |
|---|---:|---:|---:|---:|
| `precision_at_k` (strict-lexical) | 0.0002 | 0.0000 | **0.0625** | 0.0000 |
| `precision_at_k_semantic_field` | 0.0081 | 0.0000 | **0.1875** | 0.0625 |
| `coverage_at_threshold` (cos ≥ 0.85) | — | — | 0.6875 | 1.0000 |
| `n_evaluated` / 22 | 22 | 22 | 16 | 16 |

Source: [`eval/rosetta-eval-v1-20260511T080032Z.json`](../eval/rosetta-eval-v1-20260511T080032Z.json).
Earlier rows of the run-log (LaBSE-only) reproduce this LaBSE column
to four decimal places.

### What this table actually says

1. **LaBSE wins on the metric that matters (semantic-field@10).** 3× the
   v4 column (0.1875 vs 0.0625) and ~23× the random baseline (0.0081).
   The translation-ranking pre-training does the work; nothing else
   gets close.

2. **v4's high coverage@0.85 is misleading, not impressive.** v4
   returns Latin neighbours above cosine 0.85 for 100% of evaluated
   source words — but those neighbours are morphological
   rhymes (`fanu → mateu, effectu, flatu, turnu, fluxu`, all
   `-u`-suffixed Latin nouns), not semantic matches. The high
   cosines reflect XLM-R-base's known anisotropy — without contrastive
   training, all vectors crowd into a narrow cone of the embedding
   space, so "cosine 0.99" is essentially noise.

3. **Levenshtein returns nothing.** Edit-distance between Etruscan and
   Latin orthographies is uncorrelated with meaning. The expected
   baseline is exactly zero at every metric; the eval confirms it.
   (Strict-lexical Levenshtein@10 = 0 means no expected Latin lemma
   sits within the top-10 edit-closest Latin words for any
   Etruscan source.)

4. **The v4 design hypothesis (LoRA on Etruscan + base XLM-R on Latin)
   failed.** The hope was that adapter fine-tuning on the Etruscan
   corpus would teach the encoder enough Etruscan-side structure that
   the existing XLM-R Latin vectors would line up. They don't — XLM-R
   was never trained with cross-lingual alignment in mind, and a
   monolingual adapter doesn't bridge that gap.

### Decision per the WBS decision tree

```text
P3 (FINDINGS table) → look at v4 vs LaBSE field@10 number
  ├── v4 closes the gap (≥0.18)     → ship v4, skip P5+P4
  └── gap remains                   → P5
```

v4 field@10 = 0.0625 < 0.18. **Gap remains; proceed to P5** (cheap
interventions: cross-encoder rerank, cosine→confidence calibration,
dual-track loanword/semantic API). LaBSE stays the production default.

---

## P5 results so far

### T5.1 — Cross-encoder rerank (negative result)

Per the WBS decision tree, gap-remains pushed us into P5. The first
P5 lever is cross-encoder rerank: fetch top-N candidates from the
bi-encoder (LaBSE), reorder them with a transformer that scores
`(query, document)` pairs jointly, return top-k. The hope:
re-rank-aware retrieval beats pure cosine.

**Result:** rerank made `field@10` WORSE.

| Metric @10 | LaBSE (pure) | LaBSE + bge-reranker-v2-m3 |
|---|---:|---:|
| strict-lexical | 0.0625 | 0.0625 |
| **semantic-field** | **0.1875** | **0.1250** ↓ |

Source: [`eval/p5-experiments/t5-1-labse-rerank-20260511.json`](../eval/p5-experiments/t5-1-labse-rerank-20260511.json).

Rerank model: `BAAI/bge-reranker-v2-m3`, the SOTA multilingual
reranker as of mid-2025. Top-50 bi-encoder candidates fed to
cross-encoder; top-10 retained for metrics.

#### Why it failed (per-pair forensic)

Sampling the rerank-promoted top-1s:

| Etruscan | Expected Latin | Rerank top-3 |
|---|---|---|
| `apa` (father) | pater | apa, **what**, wat |
| `papa` (grandfather) | avus | papa, papas, papam |
| `lautn` (family) | familia | laute, lahn, lautus |
| `suθi` (tomb) | sepulcrum | sui, suebi, sugie |
| `flerχva` (sacred things) | sacra | plure, multi, pluresve |

The cross-encoder is treating the Etruscan source word as a sequence
of Latin-script characters and matching against orthographic
near-neighbours. It can't know `apa` is Etruscan for "father" — that
language pairing is absent from its training distribution. The
fallback behaviour is surface-form similarity, which is the opposite
of useful here: it actively promotes phonetic doppelgängers over the
semantic matches LaBSE had already retrieved.

#### What this is evidence of

Off-the-shelf multilingual cross-encoders **cannot** help low-resource
ancient-language retrieval where neither the source nor target language
sits in the cross-encoder's training distribution. The bi-encoder
gets cross-lingual signal "for free" from translation-pair
pre-training (LaBSE's strength); the cross-encoder needs supervised
examples of the specific language pair, which we don't have and the
field doesn't have for Etruscan-Latin specifically.

Implication for P5 sequencing: the *calibration* and *dual-track*
levers (T5.2 / T5.3 / T5.4) are still on the table — they don't
require cross-encoder supervision. Pivot there. T5.1's negative
result is itself publishable: "off-the-shelf MNL rerank does NOT
transfer to ancient-language IR" is a useful contribution.

---

## Why the strict-lexical metric was wrong

The original eval gate was `precision_at_5 ≥ 0.40` against the 62
curated Etruscan↔Latin pairs from Bonfante 2002, Wallace 2008,
Pallottino 1968. The metric was: *did the exact expected Latin lemma
appear in the top-5 nearest Latin neighbours?*

Three problems with this framing:

1. **Circularity.** The eval set is the philological consensus. Any
   training signal we'd add to push that metric up — short of
   genuinely parallel data we don't have — is necessarily reflecting
   that same consensus back at us. A system that "passes" by training
   on consensus-extracted anchors hasn't *learned* anything; it's
   *recovered* what the textbook already says.

2. **Metric mismatch.** Cross-language word-vector retrieval routes
   queries into semantic *neighbourhoods*, not specific lemmas. The
   eval ignored cases where the system correctly identified the
   semantic field but picked a different specific Latin word. Example
   under strict-lexical, `papa→avus` is a miss; the actual top-3 was
   `[papa, daddy, pater]` — kinship terms clustering correctly. The
   system understood the question; the metric refused partial credit.

3. **No held-out split.** All 62 pairs were train-test ambiguous in
   the philological space. There is no clean way to use any of them
   for training and any of them for honest evaluation simultaneously.

### The new metrics

[`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py) now
computes both:

* **`precision_at_k` (strict-lexical)** — the original metric.
  Retained for historical comparability and as a hard upper-bound on
  the system's lexical-equivalence capability.
* **`precision_at_k_semantic_field`** — was *any* Latin word from the
  expected category's vocabulary in top-k? Categories: `kinship`,
  `civic`, `religious`, `time`, `numeral`, `verb`, `theonym`,
  `onomastic`. Per-category Latin reference vocabularies are
  curated in
  [`evals/latin_semantic_fields.py`](../evals/latin_semantic_fields.py)
  — derived from the eval set's expected lemmas plus standard
  morphological / synonym extensions an undergrad classics student
  would unambiguously assign to the same field.

Reported side-by-side. The semantic-field metric is the honest one
for the use cases the system actually supports; the strict-lexical
one stays so we can track when (if ever) we get to a point where the
model genuinely encodes lexical equivalence.

### Per-pair examples — where field-match adds signal

| Etruscan | Expected | top-3 returned | strict | field |
|---|---|---|---|---|
| `fanu` | fanum | `fanum, fani, ...` | rank 1 | rank 1 |
| `hercle` | hercules | `hercle, hercule, herculem` | rank 5 | **rank 3** |
| `menrva` | minerva | `menrva, minerva, ...` | rank 7 | rank 7 |
| `papa` | avus (grandfather) | `papa, daddy, pater` | MISS | **rank 3** |
| `avle` | aulus | `avella, ávila, fale` | MISS | **rank 7** |

Field-match captures `papa→pater` and `avle→aulus`-adjacent forms
that strict-lexical missed.

---

## P4 results so far

### T4.1 + T4.2 — primary-source anchor mining yield

Per the WBS decision tree, the gap-still-remains verdict after P5
pushed us into P4: mine the ~1,800 classical-author passages that
mention the Etruscans for *verbatim* bilingual gloss attestations
the LLM-as-parser pipeline can extract under hallucination-defence.

**Pipeline:** [`scripts/research/llm_extract_anchors.py`](../scripts/research/llm_extract_anchors.py)
on Gemini 2.5 Pro via Vertex AI (billed to `double-runway-465420-h9`),
followed by [`scripts/research/review_anchors.py`](../scripts/research/review_anchors.py)
for keep/skip/edit triage + dedup against the rosetta-eval-v1 test
split. Originally specified for Claude Sonnet via Anthropic-on-Vertex
but the publisher hasn't been enabled in the project (manual
Terms-of-Service click) — Gemini 2.5 Pro substituted cleanly.

**Pipeline stats:**

| Stage | Stat | Value |
| --- | --- | ---: |
| T4.1 extract | passages processed | 1,795 / 1,795 |
| T4.1 extract | raw glosses kept (post verbatim-substring check) | **27** |
| T4.1 extract | hallucinated-quote drops | 9 |
| T4.1 extract | wall time | 62.3 min |
| T4.1 extract | cost (USD) | **$4.46** |
| T4.2 review | kept (`attested.jsonl`) | **17** |
| T4.2 review | rejected (skip) | 10 |
| T4.2 review | test-split collisions (`attested_eval_overlap.jsonl`) | 0 |

**Yield breakdown by author:**

* Livy (*Ab urbe condita* + variants): 7
* Strabo (*Geography*): 3
* Apollodorus (*Library*): 1
* Dionysius of Halicarnassus (*Antiquitates Romanae*): 1
* Juvenal (*Saturae*): 1
* Pliny the Elder (*Naturalis Historia*): 1
* Silius Italicus (*Punica*): 1
* Suetonius (*Divus Augustus*): 1
* Valerius Maximus (*Facta et Dicta Memorabilia*): 1

Equivalent-language split: 12 Latin, 5 Greek.

**Anchors kept** (chronologically by passage_index):

```text
ἰταλόν   → ταῦρον   (Apollodorus)            "Etruscans called the bull `italos`"
τύρσεις  → ἐντείχιοι οἰκήσεις (Dionysius)    "Etruscan name for walled dwellings"
χαῖρε    → Καῖρε    (Strabo)                 Caere/Cisra renaming etymology
Κύπραν   → Ἥραν     (Strabo)                 Cupra ≈ Hera
ἀρίμους  → πιθήκους (Strabo)                 Etruscan for "monkeys"
Nortia   → Fortuna  (Juvenal)                Etruscan goddess Nortia ≈ Fortuna
ossifragam → barbatam (Pliny)                Etruscan for "bearded vulture"
Asilos   → Aesis    (Silius)                 Aesis river → Asilos populus toponym
aesar    → deus     (Suetonius)              THE canonical Etruscan→Latin gloss
ister    → ludio    (Livy ×2 + Val. Max.)    histrio/hister actor etymology
Celeres  → bodyguards (Livy)                 Romulus's mounted bodyguard
Luceres  → tribus   (Livy)                   antiqua tribus name
Camars   → Clusium  (Livy ×2)                old Etruscan name for Clusium
Materinam → plaga   (Livy)                   Etruscan name for a region
```

### Gate check — T4.3 status

The WBS T4.3 spec requires **≥ 30 train-eligible attested pairs**
before the conditional contrastive LaBSE fine-tune runs. Current
yield is **17** — well below the gate. Per the decision tree:

```text
P4 → conditional contrastive fine-tune
  ├── yield ≥30 attested anchors AND fine-tune ≥1.5× field@5 → ship, publish
  ├── yield ≥30 but fine-tune <1.5× → publishable negative result
  └── yield <30 → documented data-limitation, hard-negative-mining
                  last-resort experiment  ← we are here
```

**This is itself a publishable result.** Two thousand years of
classical-literature treatment of the Etruscans yields **17 verbatim
bilingual gloss attestations** (and that with a state-of-the-art LLM
combing every passage exhaustively for the strict pattern). Etruscan
isn't *under-attested* — it's *unattested* in the bilingual-gloss
register Latin and Greek authors used for Greek loanwords or
technical terms. The Roman literary record knows Etruscan ritual
practice deeply but barely names a dozen Etruscan *words*.

### What's actually in the 17 anchors

Of the 17 train-eligible pairs, three structural patterns dominate:

1. **Proper-noun renamings (~7 pairs).** Etruscan place / tribe /
   goddess names that Roman authors gloss with Latin equivalents
   (Camars→Clusium, Materinam→plaga, Cupra↔Hera, Caere etymology).
   These contribute almost nothing to the *common-vocabulary*
   retrieval task that `rosetta-eval-v1` measures.

2. **Loanword etymologies (~5 pairs).** The canonical *aesar*, *ister*
   / *hister* → *ludio* / *ludius* (the actor etymology, repeated
   across Livy and Valerius Maximus), Nortia → Fortuna. These are the
   "real" Etruscan→Latin / Greek attestations the literature is
   famous for.

3. **Topographic / institutional names (~5 pairs).** Asilos / Aesis,
   Celeres bodyguard, Luceres tribe — Etruscan-origin proper nouns
   that the Roman state inherited.

Group 2 (the 5 etymological pairs) is what the WBS fine-tune
*wanted* to amplify. With LaBSE already returning *aesar* → *deus*
in its top-5 (the canonical case), the leverage from contrastive
fine-tuning on 5 examples — at most 5 — is unlikely to move the
top-line `field@10` enough to clear the 0.20 publish gate.

### Implication for sequencing

T4.3 is **gated-off**. The path forward per the decision tree is:

* **(option A) Publish the negative result.** Three lines of evidence
  now point in the same direction: P3 found v4 LoRA didn't beat LaBSE;
  P5 found cross-encoder rerank made things worse; P4 found
  primary-source mining cannot supply the data fine-tuning would
  need. Together that's a strong contribution to the
  ancient-language IR literature: the standard interventions all
  fail in low-resource settings for principled, characterisable
  reasons.
* **(option B) Hard-negative-mining last-resort.** The WBS leaves the
  door open for this — manufacture contrastive negatives from
  near-orthographic mismatches in the existing corpus and fine-tune
  on those. Cheap, but high risk of overfitting to surface form.
* **(option C) Active learning + qualitative-review track.** Document
  the 17 anchors as the seed for a community-curated extension and
  pivot the system to support **review-and-extend** workflows rather
  than translation. This aligns with the M2 qualitative-review track
  flagged in the WBS "out of scope" footnote.

T4.4 (re-eval against rosetta-eval-v1) is mechanically blocked-on
T4.3 producing a new model, so it's also out of scope until we
escalate via option B or pivot via option C.

---

## What's still missing — scientific rigour gaps

Acknowledging where we still fall short of publishable rigour:

1. ~~**No held-out anchor split.**~~ **Addressed in T1.3.** The 62
   anchors are now stratified 40/22 by `(category, confidence)` with a
   reproducible deterministic seed. The default eval grades the
   held-out 22-pair test split only.

2. ~~**No baseline comparison.**~~ **Addressed in T1.1, T1.2, T2.4.**
   The 4-column head-to-head table above includes random (analytical),
   Levenshtein (edit distance against the full Latin vocab), LaBSE,
   and v4 (xlmr-lora). LaBSE beats Levenshtein by an unambiguous
   margin (`field@10` 0.1875 vs 0.0000).

3. **No qualitative evaluation pipeline.** The system's value for
   *novel* hypothesis generation can only be assessed by domain
   experts grading top-k for words *not* in Bonfante's anchor set.
   We have no UI or workflow for that. Estimated: 2-3 days to build
   a minimal "philologist review" tool plus arrange for ~50-100 Etruscan
   words to be reviewed.

4. ~~**Reproducibility.**~~ **Addressed in T1.5 + T3.2.**
   [`bash evals/rosetta_eval_v1.sh --api-url ... --output auto`](../evals/rosetta_eval_v1.sh)
   is the single reproducer; the manifest in
   [`research/notes/reproduce-rosetta-eval-v1.md`](notes/reproduce-rosetta-eval-v1.md)
   pins commit hashes, GCS object md5s, alembic head, and the
   per-run-log entries that produced every committed `eval/*.json`.

5. ~~**Coverage metric.**~~ **Addressed in T1.4.** `coverage_at_threshold`
   reports the fraction of source words whose top-1 neighbour clears
   cosine ∈ {0.5, 0.7, 0.85}. Note the v4-column finding above: a high
   coverage@0.85 doesn't imply quality if the underlying space is
   collapsed.

6. **No statistical-significance test.** The head-to-head table
   compares point estimates on n=16 evaluated pairs. A paired
   bootstrap (10k resamples) would let us put a p-value on
   "LaBSE > v4 at field@10". Scoped in
   [`research/SOTA_ROADMAP.md`](SOTA_ROADMAP.md) as RG.8; not blocking
   for the P5 work but should land before any external publication.

---

## Reproducing the current eval

```bash
# Eval against the live API (which reads from prod corpus DB):
python evals/run_rosetta_eval.py \
  --api-url https://api.openetruscan.com \
  --json > /tmp/eval.json

# To regenerate the LaBSE embeddings from scratch (Vertex AI, ~$0.30):
bash scripts/training/vertex/submit_labse_job.sh

# To re-ingest into prod DB (run from openetruscan-eu VM via IAP):
python scripts/training/vertex/ingest_embeddings.py \
  --gcs-uri gs://openetruscan-rosetta/embeddings/labse-v1.jsonl
```

---

## Cost of the build (for the record)

* Vertex AI compute (4× LoRA training + 4× embed jobs, all on T4):
  **~$2 total**.
* GCS storage (~7 GB JSONLs + adapter): **~$0.20/month**.
* No frontier-LLM API spend (we explicitly chose not to do the
  LLM-distillation path because of methodological circularity).

---

## What we'd do with another week

In rough priority order, all aimed at *scientific defensibility* over
*chasing the strict-lexical metric*:

1. **Add Levenshtein + random baselines** to the eval harness.
   *Without these, "0.071 strict-lexical" has no context.*
2. **Build the qualitative-review pipeline** — a tiny CLI or notebook
   that pulls top-k for ~50-100 Etruscan words not in the anchor set,
   formats them as a review packet, lets a domain expert mark
   plausible / implausible / interesting. Output: a numerical
   "qualitative novelty score" alongside the strict + field metrics.
3. **Mine the Perseus primary-source corpus we already extracted** —
   1,795 Etruscan-mentioning passages from Livy / Dionysius / Cicero /
   Plutarch / Strabo / Pliny. Use an LLM **as a parser, not an oracle**
   to extract attested bilingual glosses from those passages
   (methodologically clean: the LLM reports what's in the text, doesn't
   draw on outside knowledge). Realistic yield ~30-100 attested
   anchors. Use them with proper held-out split for a contrastive
   LaBSE fine-tune. Cost ~$2-4 in LLM API.
4. **Phoenician + Oscan + Coptic populate.** Same pattern as Latin/
   Greek — base LaBSE, no adapter, vocab from external source. The
   Rosetta initiative was always supposed to span more than three
   languages.
5. **Frozen reference benchmark + leaderboard.** Lock the current
   eval set + new field metric as `rosetta-eval-v1`. Future
   architectures (multi-encoder ensembles, parallel-data fine-tunes,
   token-level contrastive losses) get evaluated against this fixed
   benchmark. Without a frozen target, "does this help?" is
   unanswerable.

---

## Bottom line

We built infrastructure that was supposed to help with the holy-grail
problem ("decipher Etruscan via geometric alignment with known
languages"). The infrastructure works. The holy-grail problem still
isn't solved, because it requires alignment supervision the encoders
don't have and the corpus can't provide.

What we *do* have is a **research-assistant browser** — fast, free,
and good at the parts of the problem where surface signal transfers
(theonyms, loanwords, semantic-field exploration). That's a real
useful product for a real audience (digital classics labs, museum
tech teams, epigraphy databases). Worth keeping. Worth being honest
about.
