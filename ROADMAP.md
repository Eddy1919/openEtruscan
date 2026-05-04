# OpenEtruscan engineering roadmap

This document is a forward-looking plan, not a history log. The previous
incarnation tracked completed work and was deleted in `f624fef` once those
tasks shipped. Recreated here to scope the next strategic initiative.

---

## The Rosetta Vector Space

### Why this is the holy grail

Etruscan has no known living relatives. Unlike Latin — which evolved into
Italian, French, Spanish, and gave comparative linguistics centuries of
parallel data to triangulate against — Etruscan is an isolate. Traditional
comparative reconstruction hits a hard wall: there is no sister language
whose cognates can anchor the meaning of a contested word.

Geometric space doesn't care about language families.

If we build high-quality monolingual word-embedding spaces for Etruscan and
for documented neighbours (Early Latin, Oscan, Umbrian), and then align
those spaces *unsupervised* using adversarial methods, we get a shared
coordinate system where semantically equivalent words from different
languages occupy the same region. The geometry is anchored by the simple
fact that all human languages describe the same physical world: words for
*water*, *father*, *god*, *tomb* sit in similar structural relationships
to neighbouring vocabulary regardless of language family.

Successfully aligned, this is the closest computational analogue to a
Rosetta Stone for an isolate language. Every contested Etruscan word
becomes a query: *which Latin/Umbrian/Oscan words sit at the same
coordinate?* For words with strong philological consensus the alignment
*confirms* the consensus (high-confidence sanity check); for words with no
consensus it produces a ranked candidate list with quantified uncertainty.

### Phase 1 — Monolingual spaces

Each language gets its own independent geometric cloud. This phase is
boring and reproducible; it's the foundation everything else stands on.

**Etruscan cloud.** We already have ~10 000 inscriptions in the corpus.
Train a **FastText** model on the canonical column. FastText (rather than
Word2Vec) because it learns from sub-word character n-grams, which matters
for highly inflected ancient languages where suffixes change constantly —
the same root in five inflected forms gets a coherent vector even if some
forms are rare. `gensim`'s `FastText` is the obvious starting library.

Evaluation: held-out perplexity on a 10% test split, plus qualitative
inspection of nearest-neighbour clusters for known Etruscan word families
(praenomina vs. gentilicia vs. magistracy titles).

**Sabellic + Latin clouds.** Ingest open epigraphic datasets:

- Early Latin: Epigraphic Database Roma (EDR), filtered to pre-100 BCE
  inscriptions. Latin BiblIndex / PHI Latin for early texts.
- Oscan and Umbrian: ImagInes Italicae or Untermann's *Wörterbuch des
  Oskisch-Umbrischen* digitisations.

Train one FastText per language. The corpora are small (~3–5k
inscriptions per Sabellic dialect, ~50k for early Latin) so training is a
laptop-minute job, not an infrastructure problem.

**Storage.** Each model is ~50 MB. Persist as `.bin` files in a Cloud
Storage bucket; load lazily via `gensim.models.FastText.load`.

### Phase 2 — Adversarial alignment

This is where the actual research happens. Use **MUSE** (Multilingual
Unsupervised and Supervised Embeddings) or **VecMap** to align two clouds
into a shared space.

The MUSE pipeline:

1. Place the Etruscan cloud and (say) the Latin cloud in the same virtual
   space with random initial alignment.
2. Train a generative adversarial network. The **discriminator** looks at
   a coordinate and tries to predict whether it came from the Latin or
   Etruscan cloud. The **generator** is a learned linear transformation
   (rotation + scale) applied to the Etruscan cloud, optimised to fool the
   discriminator.
3. Because both clouds describe the same physical reality, structurally
   similar regions exist in both — and the generator finds the rotation
   that lines them up. The clouds eventually snap into alignment without a
   single hand-curated bilingual lexicon.
4. Refine with the Procrustes step: take the most-confidently-aligned word
   pairs, compute the closed-form orthogonal transformation, and re-align.
   Iterate until the Procrustes solution stops moving.

Sanity-check on word pairs we *do* know — the philological literature has
maybe 100 high-confidence Etruscan-Latin equivalences (`avil`/`annus`,
`zilath`/`praetor`, `clan`/`filius`, …). The aligned space should put
these pairs near each other. If it doesn't, the alignment is wrong and
we report negative results.

### Phase 3 — OpenEtruscan integration

Once aligned, freeze the shared vector space and deploy it.

**The endpoint.** A new route on the API:

```http
GET /neural/rosetta?word=zich
```

The handler finds the coordinate for the input Etruscan word in the shared
space, returns the *k* nearest neighbours from the Latin (and Sabellic)
clouds with cosine-similarity scores, plus a confidence band derived from
intra-cluster density.

For `zich`, the expected output is something like:

```json
{
  "query": "zich",
  "candidates": [
    {"word": "scribere", "lang": "lat", "cosine": 0.82, "gloss": "to write"},
    {"word": "liber",    "lang": "lat", "cosine": 0.78, "gloss": "book"}
  ],
  "confidence": "high"
}
```

That happens to align with the existing philological hypothesis that
`zich` means "to write / writing", which is the kind of result we want as
a sanity check.

**The discovery tool.** A cron job that systematically maps every word in
the corpus currently classified as `unknown` (or every hapax legomenon)
against the Latin space, producing a ranked report of the top-50
high-confidence candidate translations. That report is publishable.

**Cost shape.** The aligned vector space is ~200 MB on disk, served from
the existing api container or (cheaper) from a Cloud Run sidecar with
min-instances=0 like the byt5 service. Inference is a single matrix
multiply + nearest-neighbour lookup; sub-50 ms even on CPU.

### Open questions and risks

Honest list. These determine whether the project is publishable or just
a toy demo:

- **Corpus size — confirmed problem.** MUSE was developed on Wikipedia-
  scale data (≥10⁸ tokens). Our corpus yields **15,022 training tokens
  / 1,306 unique tokens after `min_count=2`** — five orders of magnitude
  smaller than MUSE's training regime. The Etruscan baseline now lives
  on prod (commit 919d9e5) and the manifold is **collapsed**: mean top-1
  cosine ≈ 0.998, top-10 spread ≈ 0.0028 across every probe word.
  Rankings remain meaningful (Larth-family praenomina cluster correctly,
  kinship terms cluster, magistracy vocab clusters); absolute distances
  do not. Sweeps tried and rejected:
  - `vector_size` ∈ {30, 50, 75, 100}: identical top-N spread.
  - `negative` ∈ {5, 15, 20} + `sample=1e-4` (subsample frequent words):
    spread cosines but destroyed semantic cohesion.
  - **Character-level pretraining** (Word2Vec on glyph streams →
    seed FastText word vectors → continue training): seeding succeeded
    mechanically (1306/1306 word vectors initialised), but final spread
    was identical to baseline (0.0028 vs 0.0028) and neighbour orderings
    were nearly unchanged. **The collapse is data-bound, not
    initialisation-bound** — same 15k tokens, same ceiling regardless of
    where you start the gradient descent.
  Tooling for the char-init path is shipped (`train_model_with_char_init`,
  CLI `--char-init`) so future experiments can re-run it against a
  larger corpus without rewriting the wiring. **Conclusion**: vanilla
  unsupervised MUSE is unlikely to work at this scale. Phase 2 should
  pursue **supervised** alignment using the ~100 known Etruscan-Latin
  equivalences from the philological literature, or **expand the
  corpus** by ingesting CIE volumes II-III and other epigraphic
  sources not yet in the database.
- **Inflection density.** Etruscan inflection patterns may break FastText's
  sub-word assumption; the language might need a custom morpheme tokeniser
  before training. This is a 1–2 week side project on its own.
- **Reproducibility for publication.** Any paper coming out of this needs
  the exact corpus snapshot (with provenance metadata), the seed and
  hyperparameters of the training runs, and the bilingual sanity-check
  set committed to git. Plan a `data/rosetta/` directory that's
  release-tagged.

### First technical step

Before any of the alignment work, set up the data pipeline + baseline
Etruscan FastText. Concretely:

1. New module `src/openetruscan/ml/rosetta.py` with:
   - `extract_training_corpus(min_tokens=2)` — pulls canonical strings
     from the corpus, normalises to NFC, drops fragments below the token
     threshold, returns an iterator of token lists.
   - `train_etruscan_model(out_path, vector_size=100, window=5,
     min_count=2)` — trains a `gensim.models.FastText` on the iterator,
     persists the binary, returns a metadata dict (vocab size, total
     tokens, training-loss curve).
   - `nearest(word, k=10)` — load + query helper.
2. CLI entry point: `python -m openetruscan.ml.rosetta train`.
3. A `tests/test_rosetta.py` that trains on a 100-row synthetic corpus
   (no external deps), confirms the model serialises/loads, and asserts
   that a known pair like `larθ` / `larθal` are within the top-5
   neighbours of each other (basic morphology sanity check).
4. ~30 MB Etruscan model checked into Cloud Storage (NOT git; too big and
   regeneratable). README explains how to download it.

That's a self-contained ~2-day chunk of work that produces an artifact
(the Etruscan model) we can poke at and decide whether Phase 2 is worth
pursuing. If FastText loss is poor or the morphology tokeniser becomes
the long pole, we know before sinking time into alignment.

---

## Other open initiatives

These are tracked elsewhere but listed for completeness:

- **`place_findspot` retrieval gap** — current NDCG@10 is 0.39 because
  PostgreSQL FTS doesn't stem across Latin morphological variants. Three
  remediation paths in `evals/README.md`. Low priority: existing
  `place_pleiades` (0.80) covers most user-visible queries.
- **Prosopography category for the eval** — deferred until entity
  extraction is cleaned up. The existing graph is dominated by
  punctuation parsing artefacts; needs an entity-extractor rewrite first.
- **More period vocabulary** — `archaic`, `classical`, `late`,
  `orientalising`, `hellenistic` parse. `villanovan` would be the next
  natural addition once we have any rows that early; currently zero rows
  are dated `<= -720`.
