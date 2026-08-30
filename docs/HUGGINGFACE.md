# Hugging Face Models

Two model repositories are published under the [`Eddy1919`](https://huggingface.co/Eddy1919) namespace. Their model cards are mirrored in this repo under `models/` so card edits go through the same review as code.

---

## 1. Published Repositories

| Repository | Contents | Status |
|---|---|---|
| [`openetruscan-classifier`](https://huggingface.co/Eddy1919/openetruscan-classifier) | `cnn.onnx` / `transformer.onnx` (7-class inscription typology) and a ByT5-small LoRA adapter for lacuna restoration | Live since 2026-05-02. Carries a retraction notice (see below). |
| [`etr-lora-v4`](https://huggingface.co/Eddy1919/etr-lora-v4) | LoRA adapter over XLM-R-base for Etruscan-Latin cross-lingual retrieval | Live. Only the LaBSE baseline column of `rosetta-eval-v1` is populated; the v4 column is pending tasks T2.3/T2.4. |

Both cards report benchmarks under [`docs/INTELLIGENCE_V2.md`](INTELLIGENCE_V2.md)'s v2.0.4 protocol, but as **architecture-level** results: the deposited weights predate that protocol and have not themselves been re-scored against the frozen v2.0.4 split. The card is explicit about this gap — treat the reported numbers as the expected range for this model class, not a certificate for the exact uploaded files.

## 2. The Retraction

An earlier revision of the classifier card claimed 99% Macro F1. That number came from scoring the model on data it was trained on, using labels the pipeline had assigned to itself — never a held-out result. The card now states the corrected range (0.12–0.37 macro F1 depending on architecture and split) and links back to `release-manifest.json` as the source of truth. `metrics.json` and `v2/metadata.json` in the repository are kept for provenance but should not be cited.

## 3. Updating a Card

Edit the mirror under `models/<repo>/README.md`, then push:

```bash
huggingface-cli login

huggingface-cli upload Eddy1919/openetruscan-classifier \
    models/openetruscan-classifier/README.md README.md

huggingface-cli upload Eddy1919/etr-lora-v4 \
    models/etr-lora-v4/README.md README.md
```

Verify the push against the live raw file before considering it done:

```bash
diff models/openetruscan-classifier/README.md \
    <(curl -fsSL https://huggingface.co/Eddy1919/openetruscan-classifier/raw/main/README.md)
```

Weight uploads (`huggingface-cli upload <repo> <local-dir>/ .`) follow the same pattern; there is no automated CI step that re-uploads model weights.
