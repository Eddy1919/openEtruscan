# OpenEtruscan engineering roadmap

Forward-looking plan, not a history log. The previous FastText + Procrustes
prototype was nuked when we pivoted to the 2026 SOTA architecture below.

---

## The Rosetta Vector Space

### Why this is the holy grail

Etruscan has no known living relatives. Unlike Latin — which evolved into
Italian, French, Spanish, and gave comparative linguistics centuries of
parallel data to triangulate against — Etruscan is an isolate. Traditional
comparative reconstruction hits a hard wall: there is no sister language
whose cognates can anchor the meaning of a contested word.

Geometric space doesn't care about language families.

If we embed Etruscan and its documented neighbours (Latin, Greek,
Phoenician, Oscan, Coptic, Egyptian, modern-Basque-as-Aquitanian-proxy)
into a single shared coordinate system, every contested Etruscan word
becomes a query: *which Latin / Greek / Phoenician words sit at the same
coordinate?* For words with strong philological consensus the geometry
*confirms* the consensus (high-confidence sanity check); for contested
words it produces a ranked candidate list with quantified uncertainty.

### Architecture (2026 SOTA)

A multilingual transformer encoder — **XLM-RoBERTa-base** by default,
with optional **LoRA-adapter fine-tuning** on the Etruscan corpus —
produces contextual word vectors. The encoder's pretraining covers 100+
languages, so cross-language retrieval works **without** any explicit
Procrustes alignment step. Every language we care about already lives
in the same vector space because the encoder put it there.

```
                     ┌────────────────────────────┐
                     │ XLM-RoBERTa-base (frozen)  │
                     │  100+ languages, 768d      │
                     └────────┬───────────────────┘
                              │
                              │  LoRA adapter (~5 MB,
                              │  fine-tuned on the
                              │  Etruscan corpus)
                              ▼
        ┌───────────────────────────────────────────┐
        │   Embedder — emits 768-d contextual       │
        │   word vectors for ANY input string       │
        └───┬──────────┬──────────┬──────────┬──────┘
            │          │          │          │
         Etruscan    Latin     Greek    Phoenician  …
            │          │          │          │
            └──────────┴──────────┴──────────┘
                          │
                          ▼
        ┌────────────────────────────────────────────┐
        │ pgvector table `language_word_embeddings`  │
        │  (language, word, vector(768)) HNSW idx    │
        └─────────────────┬──────────────────────────┘
                          │
                          ▼
        GET /neural/rosetta?word=zich&from=ett&to=lat
```

### Why this beats the alternatives we tried

A pre-pivot FastText-and-Procrustes prototype shipped briefly to a side
branch then got nuked. Three things FastText fundamentally couldn't do
that this architecture gives us for free:

1. **Cosine spread.** Our ~15k-token Etruscan corpus collapsed FastText's
   manifold (mean top-N spread ≈ 0.003). XLM-R's manifold was set by
   trillions of tokens during pretraining; the LoRA adapter inherits
   that structure rather than competing with it.
2. **Contextual disambiguation.** `larθ` as a praenomen is a different
   vector from `larθ` in compound terms. FastText averages across uses;
   transformers don't.
3. **Sub-word vocabulary across languages.** XLM-R's SentencePiece
   tokeniser shares pieces across 100+ languages, so an Etruscan word
   gets a sensible vector even if the surface form is rare, *and* it
   automatically lives in the same space as Latin / Greek / Coptic.

The tradeoff (cost):

| | shipped pre-pivot | XLM-R + LoRA |
|---|---:|---:|
| training compute | seconds on a laptop | ~30 min on one A10/T4 GPU |
| model storage | 50 MB | 1.1 GB base + 5 MB LoRA |
| inference latency | <1 ms | ~80 ms CPU / ~10 ms GPU |
| api cost on €50/mo | already paid | +€0–10 if Cloud Run min=0 |
| pgvector dim | 100 | 768 |

The €50/mo budget allows for a Cloud Run GPU job at min-instances=0
(~€0–5/mo for inference traffic) plus offline GPU rental for the
fine-tune (~$1–3 per training run on Lambda/Vast/Modal).

### What's in main today

* **Schema** — migration `i4d5e6f7a8b9_resize_embeddings_to_768`. The
  `language_word_embeddings` pgvector table is sized at vector(768),
  has an HNSW index on the vector column, and records each row's
  source encoder + revision.
* **Embedder abstraction** — `src/openetruscan/ml/embeddings.py`:
  `Embedder` ABC, `XLMREmbedder` (production), `MockEmbedder`
  (tests, deterministic SHA-256-derived vectors).
* **LoRA fine-tuning** — `src/openetruscan/ml/finetune.py`. CLI:
  `python -m openetruscan.ml.finetune train --output models/etr-lora-v1`.
  Pulls the corpus from the inscriptions table, runs MLM with a LoRA
  adapter on XLM-R, writes a PEFT-compatible adapter directory.
* **Multilingual storage + lookup** — `src/openetruscan/ml/multilingual.py`:
  `populate_language()` writes vectors via any `Embedder`,
  `find_cross_language_neighbours()` does the SQL-side cosine search,
  `LANGUAGE_TIERS` registry honestly classifies every language.
* **API endpoint** — `GET /neural/rosetta?word=&from=&to=&k=`,
  `GET /neural/rosetta/languages`. Tier-3 languages refuse cross-language
  semantic queries (`HTTP 400`) but their structural embeddings can
  still be stored and queried within-language.
* **Operator scripts** — `scripts/ops/populate_language.py` drives the
  full populate path with `--vocab-from-corpus` / `--vocab-from-file` /
  `--use-mock-embedder` / `--dry-run` flags.
* **Tests** — 31 fast tests using `MockEmbedder` plus 3 real-model
  tests gated behind the `real_model` pytest marker. The real-model
  tests confirm that **even without LoRA fine-tuning**, XLM-R-base
  places Etruscan `clan` closer to Latin `filius` than to an unrelated
  word — the multilingual sub-word vocabulary alone gives us
  measurable cross-language structure.
* **CI** — fast tests run on every push (excluding `slow` and
  `real_model` markers); a separate `real-model-tests` job runs on
  demand when `vars.ENABLE_REAL_MODEL_TESTS == 'true'`, with HF
  model cache reused between runs.

### Honest registry

| code   | name                              | tier | deciphered | alignable | corpus status |
|--------|-----------------------------------|:----:|:----------:|:---------:|---|
| `lat`  | Latin                             | 1 | ✓ | ✓ | in encoder pretraining |
| `grc`  | Ancient Greek                     | 1 | ✓ | ✓ | in encoder pretraining |
| `ett`  | Etruscan (anchor)                 | 2 | ✓ | ✓ | LoRA fine-tune pending |
| `phn`  | Phoenician                        | 2 | ✓ | ✓ | KAI ingest pending |
| `osc`  | Oscan                             | 2 | ✓ | ✓ | ImagInes pending |
| `cop`  | Coptic                            | 2 | ✓ | ✓ | ingest pending |
| `egy`  | Egyptian (Old/Middle/Late)        | 2 | ✓ | ✓ | hieroglyphic — substantial work |
| `eus`  | Modern Basque (Aquitanian proxy)  | 2 | ✓ | ✓ | in encoder pretraining (proxy caveat) |
| `lin_a`| Linear A / Minoan                 | 3 | ✗ | ✗ | structurally embeddable, not alignable |
| `xnu`  | Nuragic / pre-Roman Sardic        | 3 | ✗ | ✗ | corpus too thin |
| `xil`  | Illyrian                          | 3 | – | ✗ | onomastic-only |
| `xfa`  | Faliscan                          | 3 | ✓ | ✗ | corpus < 1k tokens |

`alignable` gates cross-language semantic queries. Tier-3 languages
return HTTP 400 with the registry's note as `detail`.

### Next steps to ship a publishable cross-language eval

1. **LoRA fine-tune Etruscan.** Run `scripts/ops/finetune_etruscan.py`
   on a rented GPU (~$1–3, ~30 min). Push the adapter to Cloud Storage.
2. **Populate Etruscan vectors.**
   `python scripts/ops/populate_language.py --language ett --base-model xlm-roberta-base --adapter <path> --vocab-from-corpus`
3. **Populate Latin.** No fine-tune needed — Latin is in XLM-R's
   pretraining. Pull a vocab list (top 100k words by frequency from
   any reasonable Latin corpus) and call populate_language with the
   base model alone.
4. **Run the held-out eval.** `evals/rosetta_eval_pairs.py` has the
   62 curated equivalences from Bonfante 2002 / Wallace 2008 /
   Pallottino 1968. After populate, query each Etruscan word and check
   whether its known Latin equivalent lands in the top-k neighbours.
   Target: precision@5 ≥ 0.4 (Procrustes-on-FastText was 0.07).
5. **Add Greek + Coptic + Phoenician** the same way. Each is a
   new vocab list + a populate run. No alignment step required because
   they all share the encoder's pretrained space.
6. **Discovery cron.** `scripts/ops/rosetta_discovery.py` (TODO):
   for every Etruscan word currently classified as `unknown` or
   appearing fewer than 3 times in the corpus, query the top-k Latin
   neighbours and emit a CSV of the highest-confidence candidate
   translations. The output is the artefact that turns the alignment
   from a tool into a research finding.

### Risks and open questions

* **Etruscan in XLM-R's pretraining is essentially zero.** The encoder
  has *some* Etruscan pieces in its sub-word vocabulary because
  Wikipedia/CommonCrawl have a few Etruscan-Wikipedia pages, but the
  representation is thin. The LoRA adapter compensates — but how well
  it compensates is the central open question. The held-out
  precision@k against Bonfante's anchor pairs is the empirical answer.
* **Reproducibility for publication.** Any paper coming out of this
  needs the exact corpus snapshot, the seed and hyperparameters, the
  saved LoRA adapter, and the bilingual eval set committed to git.
  Plan a release-tagged `models/` directory in Cloud Storage with the
  adapter artefacts.
* **Hieroglyphic Egyptian.** Out of scope for now. Coptic (`cop`) is
  reachable via XLM-R's pretraining; Old/Middle/Late Egyptian (`egy`)
  needs Manuel-de-Codage transliteration before any encoder will see
  it. Tracked as a separate strand.

### Other open initiatives

These are tracked elsewhere but listed for completeness:

- **`place_findspot` retrieval gap** — current NDCG@10 is 0.39 because
  PostgreSQL FTS doesn't stem across Latin morphological variants.
  Three remediation paths in `evals/README.md`. Low priority: existing
  `place_pleiades` (0.80) covers most user-visible queries.
- **Prosopography category for the eval** — deferred until entity
  extraction is cleaned up. The existing graph is dominated by
  punctuation parsing artefacts.
- **More period vocabulary** — `archaic`, `classical`, `late`,
  `orientalising`, `hellenistic` parse. `villanovan` would be the next
  natural addition once we have any rows that early; currently zero
  rows are dated `<= -720`.
