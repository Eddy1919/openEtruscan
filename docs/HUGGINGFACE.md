# Hugging Face Model Deployment

This document specifies the deployment roadmap, artifact formats, and release procedures for publishing OpenEtruscan models to the [Hugging Face Hub](https://huggingface.co/Eddy1919).

---

## 1. Planned Hub Artifacts

Models will be released under the `Eddy1919` namespace once curatorial review is complete:

| Artifact | Source / Architecture | Validated Benchmark |
|---|---|---|
| `openetruscan-classifier` | `src/openetruscan/ml/` (CharCNN & TF-IDF+NB) | v2.0.4 text-disjoint split (n=167): CharCNN **Macro F1 0.399** (95% CI: 0.353 – 0.435); TF-IDF+NB **Macro F1 0.293** (95% CI: 0.255 – 0.329). |
| `openetruscan-lacuna-restorer` | Neural character-level restoration models | v2.0.3 protocol (n=66 clean-gold tasks): evaluated for exact-match and hallucination containment. |

---

## 2. Standards for Model Cards

All published models include structured [Model Cards](https://arxiv.org/abs/1810.03993) covering:
- **Intended Epigraphic Use**: Classification boundaries and historical language scope.
- **Training Data Composition**: Provenance and class distribution of the training split.
- **Evaluated Performance**: Bootstrap confidence intervals on out-of-distribution held-out data.
- **Known Limitations**: Imbalanced tail categories (`boundary`, `legal`, `votive`, `commercial`).
- **Licensing**: Apache 2.0.

---

## 3. Hub Upload Procedure

```bash
# Authenticate with Hugging Face Hub
huggingface-cli login

# Push classifier weights and model card
huggingface-cli upload Eddy1919/openetruscan-classifier \
    models/openetruscan-classifier/ .
```
