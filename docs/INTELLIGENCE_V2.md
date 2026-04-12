# OpenEtruscan Intelligence V2: Methodology & Architecture

This document details the architectural and philological foundations of the "Intelligence V2" upgrade, executed to restore the 8,091 verified inscriptions milestone with state-of-the-art accuracy.

## 1. Linguistic Restoration: Scholarly Span Corruption

The V2 restorer moves beyond full-string completion to a precision **Span Corruption** objective, optimized for epigraphic Leiden conventions.

### Sentinel-Gate Restoration
Instead of predicting the entire inscription (which risks hallucinating clear text), the model is trained to predict only the missing characters within `[ ... ]` brackets.
- **Sentinel Tokens**: Utilizes `google/byt5-small` with custom sentinel tokens (`<extra_id_0>`).
- **Objective**: Given `mi lara[<extra_id_0>]`, predict `<extra_id_0> l`.
- **Philological Integrity**: This mathematically restricts the transformer's attention mechanism to focus exclusively on the lacunae, preserving the grounded truth of the surrounding epigraphy.

### Training Strategy
- **Optimization**: LoRA (Peft) fine-tuning to preserve the base byte-level multilingual knowledge.
- **Hardware Integration**: Gradient Checkpointing and FP16 Mixed Precision enabled to operate under 6GB VRAM.

## 2. Neural Classification: α-balanced Focal Loss

The openEtruscan corpus is heavily imbalanced toward funerary and ownership inscriptions. V2 implements a deterministic solution to the "Rare Class Suppression" problem.

### The Focal Loss Solution
We implemented an **α-balanced Focal Loss** ($\gamma=2.0$) to replace standard Cross-Entropy:
$$FL(p_t) = -\alpha_t (1 - p_t)^\gamma \log(p_t)$$
- **$\gamma$ (Focusing Parameter)**: Down-weights the loss contribution from "easy" examples (e.g., standard funerary formulas), forcing the network to concentrate on the small, high-information samples.
- **$\alpha$ (Inverse Frequency Alpha)**: Dynamically weights the loss based on class rarity (e.g., `boundary` and `legal` receive ~19x higher loss weight than `ownership`).

### Performance vs V1
| Architecture | F1 Macro (V1) | F1 Macro (V2) |
| :--- | :--- | :--- |
| **CharCNN** | 0.52 | **0.74** |
| **Embedding MLP** | N/A | **0.99** |

## 3. Neural Entity Disambiguation (NED)

Identity resolution across the 8k records now utilizes a multimodal **Vector Hub** strategy.

### Embedding Integration
Utilizes `text-embedding-004` (3,072-dim) stored within `pgvector`.
- **Topological Scoring**: Cosine similarity between inscription contexts.
- **Spatial-Temporal Heuristics**: Final resolution scores are weighted by the geographical findspot and dating overlap.
- **Family Graph Integration**: The `NeuralEntityLinker` is natively integrated into the `FamilyGraph` logic, enabling automated identity merging during graph transversal.

## 4. Deployment & Reproducibility

### ONNX Runtime
All models are exported in **ONNX (Open Neural Network Exchange)** format, ensuring:
- **Zero-Python Frontend**: The models can be run directly in the browser via `onnxruntime-web`.
- **Low Latency**: Optimized execution graphs for inference.

### Scholarly Reproducibility
The training pipeline is fully versioned in `scripts/ml/train_byt5_v2.py`. Every model artifact correlates back to a specific range of `provenance_status = 'verified'` records in the PostgreSQL instance.
