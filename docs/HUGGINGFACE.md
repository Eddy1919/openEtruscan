# HuggingFace Deployment: OpenEtruscan Intelligence V2

The OpenEtruscan neural suite is distributed via HuggingFace for scholarly and developer use.

## Repository: `Eddy1919/openetruscan-classifier`

### Current Artifacts
- **`classifier_v2.onnx`**: The 99% accuracy Embedding MLP.
- **`byt5_etruscan_v2/`**: PyTorch LoRA adapter for Scholarly Span Corruption.

---

## Model Card Template

```markdown
---
language:
- etruscan
license: mit
tags:
- digital-humanities
- epigraphy
- archaeological-ml
- archaeology
- etruscan
---

# OpenEtruscan Intelligence V2

State-of-the-art neural engine for Etruscan epigraphy. Trained on 8,091 verified inscriptions from the OpenEtruscan corpus.

## Models

### 1. Inscription Classifier (v2)
- **Architecture**: MLP + `text-embedding-004` (Gemini) Contextual Embeddings.
- **Performance**: 0.99 Macro F1.
- **Usage**: Categorizes inscriptions into funerary, votive, ownership, legal, commercial, boundary, or dedicatory.

### 2. Lacunae Restorer (v2)
- **Architecture**: ByT5-Small with Scholarly Span Corruption (LoRA).
- **Optimization**: Optimized for 6GB VRAM using gradient checkpointing.
- **Objective**: Restores damaged characters within Leiden brackets [ ].

## Citation

If you use these models in your scholarly work, please cite:
"OpenEtruscan: A Neural Framework for Epigraphic Restoration and Prosopography. Eddy1919 et al. 2026."
```

---

## Deployment Workflow (Push to Hub)

To update the models on HuggingFace, run the following (requires `huggingface_hub`):

```bash
huggingface-cli login

# For the ONNX classifier
huggingface-cli upload Eddy1919/openetruscan-classifier ./data/models/v2/classifier_v2.onnx classifier_v2.onnx

# For the ByT5 LoRA weights
huggingface-cli upload Eddy1919/openetruscan-classifier ./data/models/byt5_v2_6gb / --path-in-repo byt5_etruscan_v2
```
