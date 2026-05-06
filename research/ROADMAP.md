# Research Roadmap — Rosetta Vector Space

Forward-looking research plan for the multilingual-encoder strand of
OpenEtruscan. **Read [`FINDINGS.md`](FINDINGS.md) first** — that's the
honest current state. This file is about where to go next.

The discrete tasks for executing each milestone are in [`WBS.md`](WBS.md).

---

## Guiding principles

These constrain every decision below:

1. **Rigour over metric chasing.** The strict-lexical precision@k metric
   we originally gated on doesn't measure what the system actually does.
   We will not chase it with training tricks that game the metric without
   advancing the science. New work clears methodological bars (held-out
   splits, baselines, qualitative review) before we celebrate any number.
2. **Witness evidence over modern consensus.** When introducing supervised
   anchors, we draw from primary-source attestations (Festus, Macrobius,
   Hesychius, Suetonius, etc. attesting `aesar→deus`, `tinia→iuppiter`)
   rather than modern textbooks (Bonfante 2002, Wallace 2008). The latter
   is what we *evaluate* against; using it for training is circular.
3. **Discovery is the goal; verification is the gate.** A useful Rosetta
   system generates ranked candidate translations for *unknown* Etruscan
   words. The eval set verifies we're not making nonsense. Both modes
   matter; neither alone suffices.
4. **Scope honestly.** "Decipher Etruscan" was always overpromised. The
   ambition is "research-assistant browser for ancient-language
   inscriptions" — fast shortlists, semantic-field clustering, cognate
   detection. That's a real product for a real audience.

---

## Milestones

The order here is the recommended execution order.

### Milestone 1 — Make the eval scientifically defensible

**Goal:** before publishing or claiming anything from this system,
ensure the metrics we report can survive peer review.

**Deliverables:**
- Levenshtein-only retrieval baseline (rank Latin words by edit
  distance to the Etruscan source) computed against the same eval set.
  This tells us whether our model beats trivial surface-form matching.
- Random-baseline expected precision@k computed analytically.
- A held-out split of the 62 anchor pairs (e.g. 40/22) recorded in
  the eval module so any future training data never leaks to test.
- A coverage-at-cosine-threshold metric that actually uses cosines
  (currently a stub).
- A frozen reference benchmark `rosetta-eval-v1` — locked eval set,
  locked metric definitions — against which all future model
  iterations are compared.

**Acceptance:** the eval harness produces a report that includes
strict-lexical, semantic-field, Levenshtein-baseline, random-baseline,
and coverage numbers side-by-side. All committed to git, all
reproducible from a single command.

**Out of scope:** any model retraining or new vocabulary embedding.
This milestone is metric infrastructure only.

---

### Milestone 2 — Qualitative-review pipeline

**Goal:** measure the system's value for *novel* hypothesis generation
on Etruscan words *not* in any anchor set.

**Why this matters:** the eval set verifies we aren't making nonsense
for words we know. The actual research utility is for words we don't
know — and that can only be assessed by a domain expert reviewing the
system's top-k outputs.

**Deliverables:**
- A CLI / notebook that draws ~50-100 Etruscan words from the prod
  corpus, filters out those in the anchor set, queries the system
  for top-k Latin/Greek neighbours, and exports a structured review
  packet (per-word page with the inscription contexts, top-k
  candidates, confidence indicators).
- A simple scoring schema for the reviewer: per top-k entry mark
  *plausible* / *implausible* / *interesting*.
- A way to compute aggregate "qualitative novelty score" from
  reviewed outputs.

**Acceptance:** at least one round of review completed by a
collaborator with relevant philological background, with results
written up.

---

### Milestone 3 — Primary-source attested-anchor mining

**Goal:** extract bilingual attestations from the classical Latin/Greek
corpora we already have on disk, *without* recourse to modern
philological synthesis.

**Why this matters:** classical authors who lived alongside Etruscan
speakers (Livy, Cicero, Pliny) and post-Etruscan grammarians who
recorded the language (Suetonius's `aesar=deus`, Festus's loanword
glosses) are *witness evidence*. Training on these attested pairs is
methodologically clean — they are what the texts say, not what
modern scholars have inferred.

**Deliverables:**
- LLM-as-parser pipeline over the 1,795 Etruscan-mentioning passages
  already extracted (`data/extracted/etruscan_passages.jsonl`). The
  prompt is *strictly bounded*: extract bilingual equivalences
  *stated in the passage*, refuse outside knowledge, return a JSON
  list with verbatim evidence quotes.
- A reviewed subset (~30-100 attested pairs) with held-out split
  ensuring the eval set never leaks into training.
- A LaBSE contrastive fine-tune (`MultipleNegativesRankingLoss` on
  the attested pairs) if the yield is large enough to be useful
  (≥30 pairs after dedup with the eval set).
- Documented yield-per-source: did we get the expected attestations
  from each author? (Suetonius's `aesar` is the easy gold standard.)

**Acceptance:** a reviewed list of attested pairs is in
`research/anchors/attested.jsonl` (with provenance), and a fine-tuned
LaBSE adapter improves *semantic-field* @5 by at least 1.5× on the
held-out eval split.

**Out of scope:** Festus, Macrobius, Hesychius — none are in the
Perseus corpus we have on disk; pulling them from external sources
proved harder than expected. Tracked as a follow-up.

---

### Milestone 4 — Multi-language expansion

**Goal:** broaden the Rosetta space beyond Etruscan + Latin + Greek
to cover Phoenician, Oscan, Coptic, and other tier-2 languages from
the registry.

**Why this matters:** the multilingual-encoder bet (LaBSE supports
109 languages by training; the storage layer is language-agnostic)
should mean each new language is a vocab-list-and-populate exercise,
not a new model. Until we add at least one more language, that bet is
unverified.

**Deliverables:**
- Phoenician populate (KAI corpus → vocab list → LaBSE → ingest).
- Oscan populate (ImagInes Italicae → vocab → LaBSE → ingest).
- Eval extension: per-language anchor pairs (Phoenician↔Latin via
  the Pyrgi Tablets, Oscan↔Latin via cognate-pair attestations).
- Documented honest limitations per language.

**Acceptance:** the API answers `/neural/rosetta?from=phn&to=lat`
non-trivially (returns plausible neighbours, not 400-skip) for at
least 50 Phoenician query words.

---

### Milestone 5 — Discovery experiments

**Goal:** test whether the system actually generates *new* hypotheses
that survive expert review.

**Deliverables:**
- A pre-registered experiment design: pick N Etruscan words that
  modern scholarship considers contested or unknown, run them
  through the system, blind-review the top-k by an Etruscanist.
- Compare the model's blind ranking against the reviewer's
  preferences. Inter-rater agreement, novelty rate, and
  plausibility distribution as metrics.
- A short paper describing the methodology and results, suitable for
  a digital classics venue (e.g. *Digital Scholarship in the
  Humanities* or a workshop at *Classics@UMD*).

**Acceptance:** there's a reviewed list of candidate hypotheses and
either (a) the reviewer flags ≥1 plausible non-trivial candidate per
10 reviewed words, in which case we have something publishable; or
(b) reviewer feedback is overwhelmingly negative, in which case we
have an *honest negative result* worth publishing.

---

## What's NOT on this roadmap (and why)

- **Decipherment of unknown Etruscan words via the Rosetta system
  alone.** The system produces ranked candidates; calling that
  "decipherment" would overpromise. Hypothesis generation is the
  honest framing.
- **Tier-3 languages with semantic queries** (Linear A, Nuragic,
  Illyrian, Faliscan). The registry already correctly refuses
  cross-language semantic queries to/from these. Structural
  embeddings within-language might still be useful but are out of
  scope for the Rosetta strand.
- **Real-time or low-latency inference.** Current API at ~80 ms is
  good enough; further latency optimisation is out of scope until
  there's a use case that needs it.
- **Switching to a non-LaBSE base encoder.** LaBSE was a deliberate
  choice. Future "what about model X" investigations need to
  outperform LaBSE on the frozen `rosetta-eval-v1` benchmark
  (Milestone 1) before the migration cost is justified.
- **Frontier-LLM-as-translator pipelines.** The original Tier-1
  proposal of "have Claude/GPT generate alignment pairs from the
  philological literature" was rejected on circularity grounds.
  Doesn't come back unless the methodology problem is solved.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Milestone 3 yield is below threshold (< 30 attested pairs after dedup) | Documented in `notes/primary-sources.md`; pivot to expanding the eval anchor set rather than training on a too-small attested set. |
| Milestone 2 reviewer access is hard to get | Build the pipeline anyway; the *infrastructure* is the deliverable, even if review-rounds are episodic. |
| Production DB drift (someone re-ingests / partially overwrites embeddings) | Reproducibility manifest in `research/notes/reproduce-current-eval.md` (TODO) — what bucket file + what revision tag was the eval run against. |
| LaBSE deprecation by HuggingFace | LaBSE checkpoints are fully open and re-hostable; no real risk but worth noting. |

---

## Updating this document

This roadmap is *forward-looking*. If a milestone completes, mark it
done and move it to [`FINDINGS.md`](FINDINGS.md) (which is the
historical / current-state record). Don't accumulate "DONE" entries
here; that's what `git log` is for.
