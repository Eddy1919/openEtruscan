# Neural-network stack — status, location, expansion options

**Status:** survey of every neural-network workstream live or in-flight in the openEtruscan codebase as of 2026-05-11, with per-workstream "what's there", "what works", "what's stuck", and "how to expand."

**Author:** coding agent, 2026-05-11.

## TL;DR — seven workstreams

| # | Workstream | Production status | Lives at | Expansion priority |
|---:|---|---|---|---:|
| 1 | **Multilingual Rosetta retrieval** (LaBSE) | ✅ live in prod | [`src/openetruscan/ml/multilingual.py`](../../src/openetruscan/ml/multilingual.py) | **1 — semantic-field clustering is the system's actual win** |
| 2 | **etr-lora-v4 adapter** (XLM-R + LoRA on Etruscan) | ⚠ deployed but degraded | [`scripts/training/vertex/train_etruscan_lora.py`](../../scripts/training/vertex/train_etruscan_lora.py) | 5 — kept for transparency / negative-result replay; not the production path |
| 3 | **ByT5 lacunae restorer** | ✅ live in prod | [`src/openetruscan/ml/lacuna.py`](../../src/openetruscan/ml/lacuna.py) | 2 — strongest single neural product, room for scaling |
| 4 | **CharCNN + Transformer inscription classifier** | ✅ live in prod | [`src/openetruscan/ml/classifier.py`](../../src/openetruscan/ml/classifier.py) | 4 — saturated at F1=0.99, no obvious next move |
| 5 | **Char-level MLM + LoRA char-head** | ✅ trained, ❌ unused | `gs://openetruscan-rosetta/models/{char-mlm-v1, lora-char-head-v1}` | 3 — primitive for restoration + decipherment work |
| 6 | **Cross-encoder rerank** | ❌ negative result, kept for replay | [`evals/rerank.py`](../../evals/rerank.py) | 6 — won't help retrieval; reserved for re-running with a domain-pretrained reranker |
| 7 | **YOLO glyph detector (CV pipeline)** | 🟡 v0 scaffolded, no real training data | [`src/cv_pipeline/`](../../src/cv_pipeline/) | **1 — biggest leverage; gated on philologist labelling** |

The two priority-1 workstreams (LaBSE retrieval + CV glyph detection) are the system's structural growth axes. Everything else is either saturated, blocked, or a documented failure.

---

## 1. Multilingual Rosetta retrieval — LaBSE

### What's there

`sentence-transformers/LaBSE` embedded with mean-pooling + L2-norm into a `pgvector` `vector(768)` column, served via [`/neural/rosetta`](https://api.openetruscan.com/neural/rosetta?word=apa&from=ett&to=lat) on the API. The embedding pipeline lives in [`scripts/training/vertex/embed_labse.py`](../../scripts/training/vertex/embed_labse.py); the Postgres-side query and the `?embedder=`, `?min_margin=`, `?track=` query-parameter surface is in [`src/openetruscan/api/server.py`](../../src/openetruscan/api/server.py).

Three partitions of vectors coexist behind the same table thanks to the T2.3 PK extension `(language, word, embedder, embedder_revision)`:

- `(LaBSE, v1)` — Latin + Greek + Etruscan; the production default.
- `(xlmr-lora, v4)` — Etruscan-side only (the etr-lora-v4 adapter, workstream #2).
- `(xlm-roberta-base, v4)` — Latin-side complement to v4.

### What works

**Semantic-field retrieval against held-out anchors:** `field@10 = 0.1875` on rosetta-eval-v1 (vs 0.0625 strict-lexical, vs 0.0081 random). The system reliably returns Latin words from the *same semantic field* as a queried Etruscan word, even when the exact target lemma isn't in top-10. See [`research/FINDINGS.md > Headline`](../FINDINGS.md#headline--rosetta-eval-v1-4-column-head-to-head) for the full table.

**Margin-calibrated retention** (T5.2): per-query `top1_margin = cos1 − cos2` is a real precision lever. At `margin ≥ 0.05`, precision@5 lifts 2.7× at the cost of half the queries returning empty. Production surfaces this via `?min_margin=τ`.

**Dual-track API** (T5.4): `?track=semantic` drops the loanword leak (where an Etruscan word matches itself in the target language because of cross-language vocabulary), `?track=loanword` returns only those; `?track=all` is the legacy behaviour.

### What's stuck

- Strict-lexical retrieval against unattested-pair anchors. LaBSE's pretraining doesn't include Etruscan; the model is essentially returning semantic-field-clustered near-neighbours via the shared multilingual manifold. See [`research/FINDINGS.md > P5 results`](../FINDINGS.md#p5-results-so-far) and [P4 results](../FINDINGS.md#p4-results-so-far) for the diagnosis.
- The 0.40 publish-grade gate is incompatible with the data regime (~17 verifiable bilingual gloss attestations across 2,000 years of literary witnesses).

### How to expand

**Track 1 — contrastive fine-tune of LaBSE on attested anchors.** Gated on yield ≥ 30 attested pairs (current: 17). The community-curation pipeline (Option C, see [`community-curation-design.md`](community-curation-design.md)) is the realistic data-source.

**Track 2 — domain-adaptive pretraining of LaBSE on Etruscan + classical-Latin corpus.** Cheaper than full retraining, but requires ~1M sentences of "Latin near Etruscan" text. The Pelagios-aligned Roman literary corpus might be enough; need to check.

**Track 3 — distillation to a smaller multilingual encoder for edge inference.** LaBSE is 470M params; for the browser-side retrieval surface (the frontend `/normalizer` page already runs a 1.2 MB transformer client-side), distilling to a ~50 MB student would unlock real-time autocomplete.

---

## 2. etr-lora-v4 adapter — XLM-R + LoRA on Etruscan-side only

### What's there

LoRA adapter (r=8, q+v target, 5 epochs) trained on 6,097 prod inscriptions via XLM-RoBERTa-base. Adapter weights at `gs://openetruscan-rosetta/adapters/etr-lora-v4/`. Published to HF Hub as [`Eddy1919/etr-lora-v4`](https://huggingface.co/Eddy1919/etr-lora-v4). Training recipe in [`scripts/training/vertex/train_etruscan_lora.py`](../../scripts/training/vertex/train_etruscan_lora.py).

### What works

The training pipeline. The adapter loads, embeds prod vocab through `embed_etruscan.py`, lands in the database under partition `(xlmr-lora, v4)`. The `?embedder=xlmr-lora-v4` query param routes to it.

### What's stuck — and why

**v4 lost to LaBSE on rosetta-eval-v1.** Semantic-field precision@10 = 0.0625 vs LaBSE's 0.1875. Diagnosis ([`research/FINDINGS.md`](../FINDINGS.md#what-this-table-actually-says)): XLM-R-base wasn't pre-trained with cross-lingual alignment; a one-sided adapter (Etruscan-only) can't bridge that. v4's high `coverage@cos≥0.85 = 1.0` is anisotropy artefact, not retrieval quality.

This is **documented as a negative result** and kept in the codebase for reproducibility. It will not be the default embedder.

### How to expand

Don't, in this direction. The right next adapter target is **LaBSE itself** (Track 1 under workstream #1) when attested-anchor yield clears the threshold. The XLM-R+LoRA approach is methodologically dead-ended for retrieval; might still be useful as a feature extractor for downstream classifier work (workstream #4).

---

## 3. ByT5 lacunae restorer

### What's there

[`src/openetruscan/ml/lacuna.py`](../../src/openetruscan/ml/lacuna.py) wraps a ByT5-small encoder-decoder with LoRA adapters (versions v3, v4, v5 on GCS at `gs://openetruscan-rosetta/adapters/byt5-lacunae-v*`). The model takes a partially-broken Etruscan inscription with `[…]` lacuna placeholders and predicts the missing characters using **Scholarly Span Corruption** — a training objective that masks contiguous spans the way real lacunae appear in the corpus, rather than the standard ByT5 random-token MLM.

The latest published model is `byt5-lacunae-v3` (HF Hub repo card lives at `models/byt5-lacunae-v3/` — that's the model card the README references when users land on the [`/lacunae`](https://www.openetruscan.com/lacunae) frontend page). v4 and v5 are experimental and not in prod.

### What works

The "Philological Safety" benchmark — production v3 produces sentinel tokens (`<extra_id_N>`) instead of hallucinating real words when the lacuna context is too sparse to commit to a prediction. This is a published win in [`research/experiments/lacuna_restoration/README.md`](../experiments/lacuna_restoration/README.md): pre-Scholarly-Span-Corruption training, the model would confabulate plausible-looking-but-wrong reconstructions; with SSC, it knows to abstain.

### What's stuck

- ByT5-small (~300M params) is the maximum size that fits the inference latency budget on the API VM. Larger models exist (ByT5-base ~580M, ByT5-large ~1.2B) but would need GPU inference, which the current GCE n1-standard-4 VM doesn't have.
- The training set is limited by the number of *complete* inscriptions (no lacunae) the model can pretrain on. That's ~4,200 of the 6,633 unified inscriptions.

### How to expand

**Track 1 — Cloud Run + GPU for ByT5-base inference.** Move the lacuna predictor off the main API VM onto a Cloud Run service with a T4 attached. Cost: ~$50/month at modest traffic. Unlocks ByT5-base, which on internal tests gives ~3 BLEU point improvement on the SSC eval.

**Track 2 — Multi-task with classifier head.** The CharCNN + Transformer classifier (workstream #4) and the ByT5 restorer both consume inscription text. Joint training (encoder shared between the two tasks) might lift both via cross-task regularisation. Cost: 1 Vertex training run, ~$2.

**Track 3 — Beam-search-with-philological-priors.** The current ByT5 inference uses greedy decoding. Adding a beam search where the score function weights candidates by their classifier-predicted compatibility with the surrounding inscription's epigraphic genre would improve "stylistically plausible" reconstructions. Zero training cost; pure inference-time engineering.

---

## 4. CharCNN + Transformer inscription classifier

### What's there

Two classifiers in [`src/openetruscan/ml/classifier.py`](../../src/openetruscan/ml/classifier.py):

- **CharCNN** — small (111 KB ONNX), runs client-side in the browser via ONNX Runtime Web. 7-way classification (funerary, votive, legal, …).
- **Transformer** — larger (1.2 MB ONNX), same task, marginally better F1 in exchange for ~10× inference cost.

The frontend [`/classifier`](https://www.openetruscan.com/classifier) page renders both side-by-side as a "see how the architectures differ" demo.

### What works

**F1-macro = 0.99 on the 7-way task** on the held-out test split. This is the strongest single number in the system, and it's the one the README features front-and-centre. The task IS relatively easy (epigraphic genre clusters tightly by lexicon — funerary inscriptions contain `larθal`, votive ones contain theonyms, legal ones contain magistracies). But 0.99 is 0.99.

### What's stuck

The task is genuinely saturated. The held-out test split is small (~660 inscriptions) and the remaining errors are mostly genuine class-boundary cases (a "votive funerary" donation inscription that legitimately belongs in two classes).

### How to expand

**Track 1 — Finer-grained classes.** The 7-way "type" classification could be subdivided into ~25 sub-types (e.g. funerary → epitaph / sarcophagus-label / cinerary-urn-label). Limiting factor: per-sub-type training data; some cells would have < 20 examples. Risk: chase finer F1 numbers that don't matter to users.

**Track 2 — Inscription dating from text alone.** A regression head over the same encoder, predicting `date_approx` (in centuries BCE). Cross-validate against the 2,317 dated inscriptions; if the eval converges, replace the current heuristic dating in the corpus with model predictions for the undated 4,316. This is real research, ~1 week of work.

**Track 3 — Multi-task with the lacuna restorer (workstream #3).** See above.

---

## 5. Char-level MLM + LoRA char-head (currently unused)

### What's there

Two artefacts on GCS, no API surface yet:

- `gs://openetruscan-rosetta/models/char-mlm-v1/` — a character-level masked-language-model trained on the full 6,633-inscription corpus. Vocabulary = 26 Old-Italic letters + word-dividers + lacuna sentinels.
- `gs://openetruscan-rosetta/models/lora-char-head-v1/` — a LoRA adapter on top of the char-MLM, fine-tuned for classification of held-out character positions.

Vertex training jobs that produced these (the `char-mlm-v1-*` and `lora-char-head-v1-*` runs in `gcloud ai custom-jobs list`).

### What works

The char-MLM itself converged cleanly. Perplexity on the held-out 10% of inscriptions is ~3.2 (random baseline at 26 chars = 26). The lora-char-head reaches ~85% accuracy on a leave-one-character-out task.

### What's stuck

**No production application has been hooked up to it.** It was scaffolded during the v3-→v4 etr-lora exploration as a "what if we go character-level instead of word-level" experiment. The retrieval task pulled us back to word-level (which is where rosetta-eval-v1 measures); char-level fell out of the critical path.

### How to expand — and this is where there's real opportunity

**Track 1 — Use as the byt5-lacunae backbone.** The char-MLM is essentially a domain-pretrained encoder for the lacuna task. Starting ByT5 fine-tuning from the char-MLM checkpoint instead of generic ByT5-small would be a substantial improvement. Cost: 1 Vertex run, ~$2.

**Track 2 — Hard-negative-mining feature extractor.** The Option-B fine-tune (see [`research/FINDINGS.md > P4 > option B`](../FINDINGS.md#implication-for-sequencing)) needs hard negatives. The char-MLM scores how "Etruscan-like" a string looks; we can filter the negative pool to retain only strings the char-MLM rates highly (i.e. orthographically-plausible Etruscan that LaBSE confuses with the positive). This makes the hard negatives genuinely hard.

**Track 3 — Decipherment primitive.** For unseen Etruscan strings (e.g., the few inscriptions still partially-undeciphered), the char-MLM gives a per-position probability distribution. A philologist tooling around with hypothetical readings can use the model as a "does this string look Etruscan?" oracle. Frontend `/decipherment` page (greenfield).

This workstream is the **highest-leverage piece of dormant work in the codebase.**

---

## 6. Cross-encoder rerank (negative result)

### What's there

[`evals/rerank.py`](../../evals/rerank.py) — wraps `BAAI/bge-reranker-v2-m3` (sentence-transformers `CrossEncoder`), reorders the top-N LaBSE candidates per query, returns top-k by cross-encoder score. Wired into the eval harness via `--rerank`.

### What works

The pipeline. The model loads, runs, produces scores.

### What's stuck

**Field@10 dropped from 0.1875 → 0.1250** when applied over LaBSE's top-50 ([T5.1 negative result](../FINDINGS.md#t51--cross-encoder-rerank-negative-result)). The cross-encoder never saw Etruscan in its training distribution; it falls back to orthographic neighbour matching, which is precisely what we don't want.

### How to expand

**Track 1 — Domain-pretrained reranker.** Train a cross-encoder from scratch (or fine-tune from `BAAI/bge-reranker-v2-m3`) on (Etruscan, Latin) pairs from the attested-anchor set. With only 17 pairs, this is **at high risk of the same overfitting problem the Option-B fine-tune scaffold guards against**. Reserved for after community curation produces ≥ 100 attested pairs.

**Track 2 — Cross-encoder with a *different* signal.** Instead of textual cross-encoding (which fails on Etruscan), the reranker could score (etr-vector, lat-vector) pairs over an *image-text* cross-encoder if the inscription photographs are in the loop. This is genuinely speculative.

---

## 7. YOLO glyph detector (CV pipeline)

### What's there

[`src/cv_pipeline/`](../../src/cv_pipeline/) — a complete YOLOv11-nano training pipeline:

- [`generate_synthetic_data.py`](../../src/cv_pipeline/generate_synthetic_data.py) — font-rasterised synthetic training images
- [`font_similarity_labeler.py`](../../src/cv_pipeline/font_similarity_labeler.py) — bootstrap bounding boxes via feature similarity
- [`yolo_pseudo_labeler.py`](../../src/cv_pipeline/yolo_pseudo_labeler.py) — iterative pseudo-labelling
- [`convert_to_ls_json.py`](../../src/cv_pipeline/convert_to_ls_json.py) — Label Studio export/import
- [`train_yolo.py`](../../src/cv_pipeline/train_yolo.py) — Ultralytics trainer + HF push

### What works

The scaffolding. A v0 detector trains on synthetic data and detects rasterised Old-Italic Unicode glyphs.

### What's stuck

**No real training data.** The v0 detector doesn't generalise to actual stone / bronze / ceramic Etruscan epigraphy because the training distribution is wrong (clean font glyphs, not 2,000-year-old worn surfaces).

### How to expand

See the **dedicated plan in [`cv-detector-plan-etruscan-glyphs.md`](cv-detector-plan-etruscan-glyphs.md)**. Summary: collect ~800 real inscription photographs from CIE / Trismegistos / EAGLE / Pleiades, hand-label ~500 via Label Studio, pseudo-label the rest, train YOLOv11-small, ship as ONNX to the frontend `/explorer/cv` page. Estimated $3 Vertex spend; bottleneck is ~80 hours of philologist labelling time.

---

## Cross-cutting themes

### Where the structural opportunity is

Three of the seven workstreams are saturated (#1 LaBSE retrieval is plateaued by data; #4 classifier is at F1=0.99; #6 cross-encoder is a confirmed negative result). Three are stuck on external resources (#3 ByT5 needs GPU inference; #5 char-MLM needs an integration target; #7 CV needs photograph collection + labelling). Only one — **#2 etr-lora-v4** — is in active production decline and has been kept around as documented-negative-result for transparency.

The two genuine growth axes:

1. **#5 char-MLM as a primitive.** Plug it into #3 (ByT5 backbone), #6 (hard-negative scoring), or a new decipherment surface. Cheap, fast, high leverage.

2. **#7 CV detector + #1 retrieval composed.** A future system reads a photograph of an inscription via the CV detector, OCRs to a string via the CharCNN (#4), looks up that string in the LaBSE retrieval (#1), and presents the philologist with semantic-field neighbours. The whole-stack composition is what makes openEtruscan more than the sum of individually-modest neural components.

### What we'd commit to next

In rough order of leverage (and assuming community-curation Option C produces gross anchors):

1. **CV labelling sprint** — collect + hand-label ~800 inscriptions for the v1 glyph detector. Single biggest unlock for the system. ~80 human hours + $3 Vertex.
2. **char-MLM as ByT5 backbone (#5 → #3).** Domain-pretrained backbone for the lacuna restorer. ~$2 Vertex; ~1 day engineering. Probably the highest leverage cheap move.
3. **Community curation pipeline (Option C).** Re-opens the data tap for retrieval fine-tuning. ~1 day engineering; success measured at 30-day yield.
4. **Inscription dating from text (extension of #4).** Real research; ~1 week. Replaces the heuristic dating for 4,316 currently-undated inscriptions.

Items 1 and 2 are the highest cost / leverage ratio. Items 3 and 4 are 1-day investments that compound if Option C produces audience-fit.

### What we should NOT do

- Retrain etr-lora-v4 in another variant. The negative result is structural, not hyperparameter-driven.
- Apply off-the-shelf cross-encoders to ancient-language IR. Same answer as the T5.1 negative result — characterised, published, move on.
- Scale up LaBSE to a larger encoder without attested-anchor data. Bigger models don't manufacture supervised signal; they amplify whatever signal exists, and we've shown the signal is structurally absent for unattested-source IR.
