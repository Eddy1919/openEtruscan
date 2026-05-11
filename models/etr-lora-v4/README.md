---
language:
  - ett
  - la
license: apache-2.0
library_name: sentence-transformers
tags:
  - sentence-transformers
  - cross-lingual
  - low-resource-nlp
  - ancient-languages
  - etruscan
  - epigraphy
  - LoRA
  - LaBSE
  - XLM-R
base_model: sentence-transformers/LaBSE
datasets:
  - Eddy1919/openetruscan-corpus
metrics:
  - precision-at-k
  - cosine-similarity
model-index:
  - name: etr-lora-v4
    results:
      - task:
          type: cross-lingual-retrieval
          name: Etruscan-Latin word-vector retrieval
        dataset:
          name: rosetta-eval-v1 (test split)
          type: Eddy1919/openetruscan-rosetta-eval-v1
        metrics:
          - type: precision_at_10_semantic_field
            value: 0.1875
            name: Semantic-field precision@10 (LaBSE baseline)
            verified: false
          - type: precision_at_10
            value: 0.0625
            name: Strict-lexical precision@10 (LaBSE baseline)
            verified: false
---

# etr-lora-v4 — Etruscan-side LoRA adapter for LaBSE

> **Status note.** The numbers in the YAML frontmatter and in the
> Evaluation table below are the **LaBSE-only** column of the current
> frozen `rosetta-eval-v1` benchmark. That is what the first Hub
> deposit covers. The **v4 column** will be added after WBS tasks
> **T2.3** (ingest v4 vectors behind a feature flag) and **T2.4** (run
> the head-to-head eval) land in prod and the benchmark gains its
> fourth row.

## TL;DR

`etr-lora-v4` is a **LoRA adapter** that fine-tunes the **Etruscan-side
vocabulary projection** of a multilingual encoder (XLM-R-base, with
LaBSE as the cross-lingual anchor on the Latin/Greek side) so that
Etruscan words land in the same 768-dim semantic space as the rest of
the multilingual vocabulary. The system is evaluated against held-out
Etruscan ↔ Latin equivalences drawn from the philological literature
(Bonfante & Bonfante 2002, Wallace 2008, Pallottino 1968), exposed
through the `rosetta-eval-v1` frozen benchmark.

The pipeline is designed for **semantic-neighbourhood retrieval over a
low-resource, undeciphered ancient language**, not lexical-equivalence
translation. See *Limitations* before you cite the numbers.

## Intended use

- **Cognate / loanword detection.** Given an Etruscan word, find
  orthographically- or semantically-similar Latin or Greek words.
  Useful for spotting Etruscan→Latin borrowings (e.g. `histrio`,
  `popa`, `subulo`, `satura`).
- **Theonym and place-name alignment.** Etruscan deity and place
  names were often Latinised by Roman authors with regular sound
  correspondences. The system reliably recovers these:
  `menrva→minerva`, `hercle→hercules`, `fanu→fanum`.
- **Within-language semantic-field exploration.** For an Etruscan
  query, the system returns Latin words with related meanings even
  when the exact target lemma is wrong (e.g. `papa→[papa, daddy,
  pater]`).
- **Multilingual nearest-neighbour browsing** as a primitive other
  ancient-language work (Phoenician, Faliscan, Oscan) can plug into
  without rebuilding the storage / API layer.

## Out of scope

- **Mechanical Etruscan → Latin translation.** Lexical equivalence
  between *unrelated* surface forms (`clan → filius`, `puia → uxor`,
  `lautn → familia`) is **not** in the model, and no amount of
  pooling, centering, or LoRA fine-tuning recovers signal that was
  never in the training corpus.
- **Decipherment of unknown Etruscan words.** Top-k results will be
  orthographic and semantic neighbours of the source surface form,
  not authoritative semantic equivalents.
- **An Etruscan dictionary.** This is not a dictionary. We make no
  such claim. The output is a ranked shortlist for downstream
  philological judgement, not a translation.

## How to use

### From `sentence-transformers`

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("Eddy1919/etr-lora-v4")
embeddings = model.encode(["fanu", "avil", "clan"])
# embeddings.shape == (3, 768)
```

### Through the hosted API

```bash
curl 'https://api.openetruscan.com/neural/rosetta?word=fanu&from=ett&to=lat&embedder=xlmr-lora-v4'
```

The default `embedder` is `LaBSE`; passing `embedder=xlmr-lora-v4`
routes the query through the v4 adapter. The route currently returns
LaBSE results until T2.3 lands the v4 partition in prod.

## Training data

Derived from the **OpenEtruscan corpus v1** (Zenodo DOI
[10.5281/zenodo.20075836](https://doi.org/10.5281/zenodo.20075836)):

- **6,633 unified inscriptions**, drawn primarily from the *Larth
  Dataset* (Vico & Spanakis 2023; ~71% of rows) and the *Corpus
  Inscriptionum Etruscarum* Vol. I extractions (~29%).
- **~8,905 unique Etruscan tokens** on the source side after
  divider-normalisation (see *Training procedure* below).
- No primary-source-attested anchors are used in training — only the
  raw transcriptions. The Bonfante / Wallace / Pallottino
  equivalences are held out for evaluation in `rosetta-eval-v1`.

Upstream provenance chain is documented in
[`research/BIBLIOGRAPHY.md`](https://github.com/Eddy1919/openEtruscan/blob/main/research/BIBLIOGRAPHY.md).

## Training procedure

LoRA over **XLM-R-base** (768-dim hidden), trained on Vertex AI in
the `openetruscan-rosetta` GCP project.

- **Output adapter:** `gs://openetruscan-rosetta/adapters/etr-lora-v4/`
- **Re-embedded Etruscan vocabulary:**
  `gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl`
  (8,905 rows × 768 dim).
- **Etruscan-side preprocessing:** word-divider normalisation
  (`:` and `·` → space, per Bonfante 2002 §10), preserving `.`
  (intra-word phonological marker) and `-` (compounding marker).

Hyperparameters (matching the v3 → v4 recipe in
`scripts/training/vertex/submit_etr_lora_v4.sh`):

| Hyperparameter | Value |
|---|---|
| Base model | `xlm-roberta-base` |
| Epochs | 5 |
| Learning rate | 5e-4 |
| Batch size | 16 |
| Max length | 64 tokens |
| LoRA r | 8 |
| LoRA alpha | 16 |
| LoRA dropout | 0.1 |
| Target modules | `q_proj`, `v_proj` |
| Seed | 42 |
| Hardware | 1× NVIDIA T4 (Vertex AI `n1-standard-8`) |
| Wall time | ~30–60 min |
| Compute cost | ~$0.40 USD |

The training recipe (and divider-normalisation function) is in
[`scripts/training/vertex/train_etruscan_lora.py`](https://github.com/Eddy1919/openEtruscan/blob/main/scripts/training/vertex/train_etruscan_lora.py).
The only delta from v3 is the corpus input
(`etruscan-prod-rawtext-v3.jsonl`, the cleaner V3 corpus produced
after `normalize_inscriptions.py` removed Cyrillic / Latin-Ext-B
mirror-glyph corruption and unified sibilant variants σ/ś/š/ς → SAN).

## Evaluation

All numbers below are from the first frozen run of `rosetta-eval-v1`,
committed at
[`eval/rosetta-eval-v1-20260510T210124Z.json`](https://github.com/Eddy1919/openEtruscan/blob/main/eval/rosetta-eval-v1-20260510T210124Z.json).
**The `model` column reflects the LaBSE baseline that prod was serving
at the time of the run.** The v4 column will be added when T2.3 lands
v4 vectors in prod and T2.4 runs the head-to-head.

### Headline numbers — 22-pair test split

| Metric | random | Levenshtein | LaBSE (current prod) | v4 (after T2.3 / T2.4) |
|---|---:|---:|---:|---:|
| Strict-lexical precision@10           | 0.0002 | 0.000 | **0.0625** | _to be added_ |
| Semantic-field precision@10           | 0.0081 | 0.000 | **0.1875** | _to be added_ |
| Coverage@cos≥0.50                     | 0.000  | 0.955 | **1.000**  | _to be added_ |
| Coverage@cos≥0.70                     | 0.000  | 0.273 | **1.000**  | _to be added_ |
| Coverage@cos≥0.85                     | 0.000  | 0.091 | **0.6875** | _to be added_ |
| n evaluated (of 22)                   | 22     | 22    | 16         | _to be added_ |
| n skipped (OOV on the source side)    | 0      | 0     | 6 (27.3%)  | _to be added_ |

### Per-confidence breakdown (LaBSE column)

| Confidence | n | strict @10 | field @10 |
|---|---:|---:|---:|
| high   | 10 | 0.100 | 0.200 |
| medium | 6  | 0.000 | 0.167 |

### Per-category breakdown (LaBSE column, field@10)

| Category   | n | field @10 |
|---|---:|---:|
| kinship    | 3 | 0.333 |
| theonym    | 3 | 0.333 |
| onomastic  | 2 | 0.500 |
| religious  | 2 | 0.000 |
| time       | 2 | 0.000 |
| numeral    | 3 | 0.000 |
| verb       | 1 | 0.000 |

The strict-lexical metric measures something the system *cannot* do
without parallel-data supervision; the semantic-field metric measures
what it *can* do, and is the honest reflection of the system's actual
research utility. Both are reported side-by-side for historical
comparability.

For the full reproducibility manifest (pinned commit hashes, Latin
vocab snapshot, baseline math), see
[`research/notes/reproduce-rosetta-eval-v1.md`](https://github.com/Eddy1919/openEtruscan/blob/main/research/notes/reproduce-rosetta-eval-v1.md).

## Limitations

Honesty matters more here than marketing:

1. **Small held-out test split (n=22 pairs).** Confidence intervals
   are correspondingly wide. RG.4 in the SOTA roadmap adds
   95%-bootstrap CIs to every reported number; until that lands,
   treat single-decimal-point differences between models as noise.
2. **27% OOV rate on the source side.** 6 of the 22 test-split pairs
   are skipped by the model because the Etruscan token has no vector
   in `language_word_embeddings`. The other two baselines (random,
   Levenshtein) evaluate all 22. Comparisons are accordingly *not*
   apples-to-apples without per-pair pairing.
3. **No primary-source-attested anchors used in training.** The
   evaluation set is itself the philological consensus. Any training
   signal that pushed precision up — short of genuinely parallel data
   we do not have — would be reflecting that same consensus back at
   us. Work-package P4 (primary-source mining) is the route out.
4. **Philological consensus reflects a school.** The Bonfante &
   Bonfante / Wallace / Pallottino reading is one school's best
   reading. Categories like `verb` (n=1) and `time` (n=2) are
   under-represented; the per-category breakdown above is indicative,
   not authoritative.
5. **Cross-language semantic alignment for unrelated surface forms
   remains weak.** `clan → filius`, `puia → uxor`, `lautn → familia`
   are misses by design; there is no signal in the training corpus
   that these are equivalent.

## Citation

If you use this model, please cite both the software/dataset DOI and
the model directly:

```bibtex
@software{openetruscan_2026,
  author    = {OpenEtruscan Contributors},
  title     = {{OpenEtruscan: open-source digital corpus platform for Etruscan epigraphy}},
  year      = {2026},
  version   = {0.5.0},
  doi       = {10.5281/zenodo.20075836},
  url       = {https://doi.org/10.5281/zenodo.20075836},
  publisher = {Zenodo}
}

@misc{openetruscan_etr_lora_v4_2026,
  author       = {OpenEtruscan Contributors},
  title        = {{etr-lora-v4: Etruscan-side LoRA adapter for LaBSE / XLM-R}},
  year         = {2026},
  publisher    = {Hugging Face},
  howpublished = {\url{https://huggingface.co/Eddy1919/etr-lora-v4}},
  note         = {Evaluated against the rosetta-eval-v1 frozen benchmark.}
}
```

The frozen reference benchmark is `rosetta-eval-v1`; full reproduction
instructions live in
[`research/notes/reproduce-rosetta-eval-v1.md`](https://github.com/Eddy1919/openEtruscan/blob/main/research/notes/reproduce-rosetta-eval-v1.md).

## License

**Apache 2.0** — matches the model-artifact licensing scheme of the
OpenEtruscan repository (code: MIT, data: CC0 1.0, models:
Apache 2.0).

## Acknowledgements

- Vico, A. and Spanakis, G. (2023). *Larth Dataset* — primary source
  for ~71% of the unified corpus.
- Compilers of the *Corpus Inscriptionum Etruscarum* (CIE Vol. I),
  source of the remaining ~29%.
- Bonfante, G. and Bonfante, L. (2002). *The Etruscan Language: An
  Introduction*, 2nd edition.
- Wallace, R. E. (2008). *Zikh Rasna: A Manual of the Etruscan
  Language and Inscriptions*.
- Pallottino, M. (1968). *Testimonia Linguae Etruscae*.
- Feng et al. (2020). *LaBSE: Language-agnostic BERT Sentence
  Embedding* — the cross-lingual anchor.
- The Pelagios Network, the EpiDoc community, and the Classical
  Language Toolkit.
