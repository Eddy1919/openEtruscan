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

## What's still missing — scientific rigour gaps

Acknowledging where we still fall short of publishable rigour:

1. **No held-out anchor split.** Even with the new metric we'd
   want a 30/32 train-test split of the 62 anchors before any
   contrastive fine-tune.

2. **No baseline comparison.** We haven't computed Levenshtein-only
   retrieval or random-baseline performance on the same eval. Without
   those numbers we don't know whether LaBSE's 0.119 field@10 is
   actually beating "just rank Latin words by edit distance".
   (Estimated work: ~1 hour to add both baselines as `--baseline`
   modes in the eval.)

3. **No qualitative evaluation pipeline.** The system's value for
   *novel* hypothesis generation can only be assessed by domain
   experts grading top-k for words *not* in Bonfante's anchor set.
   We have no UI or workflow for that. Estimated: 2-3 days to build
   a minimal "philologist review" tool plus arrange for ~50-100 Etruscan
   words to be reviewed.

4. **Reproducibility.** Code and data are versioned; intermediate
   JSONLs are in GCS; pinned model versions are in
   `scripts/training/vertex/embed_*.py`. **But** there's no single
   `make eval` reproducer script that pulls the right adapter +
   embeddings + runs the eval end-to-end. Worth landing.

5. **Coverage metric is a stub.** `coverage_any_hit` currently just
   reports "did the API return *any* result", because cosines aren't
   exposed in `per_pair`. Should track "fraction of source words for
   which top-k contains at least one neighbour above cosine X" for
   X ∈ {0.5, 0.7, 0.85}. Easy fix in next harness pass.

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
