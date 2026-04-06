---
language:
  - ett
license: mit
tags:
  - etruscan
  - epigraphy
  - inscription-classification
  - character-level
  - onnx
  - digital-humanities
pipeline_tag: text-classification
library_name: onnxruntime
datasets:
  - custom
metrics:
  - f1
model-index:
  - name: openetruscan-cnn
    results:
      - task:
          type: text-classification
          name: Inscription Classification
        metrics:
          - type: f1
            value: 0.72
            name: Macro F1
---

# OpenEtruscan Neural Inscription Classifier

## Model Description

Character-level CNN and Micro-Transformer models for **automated classification of Etruscan inscriptions** into 7 categories:

| Category | Description |
|---|---|
| **funerary** | Tomb inscriptions, epitaphs, death/life formulae |
| **votive** | Offerings to deities, dedication verbs |
| **boundary** | Territorial markers, civic designations |
| **ownership** | Object ownership marks ("mi" = I am) |
| **legal** | Administrative texts, magistrate titles |
| **commercial** | Trade records, numerals, vessel terms |
| **dedicatory** | Temple dedications, deity names |

## Architecture

- **CharCNN** (recommended): 27,943 parameters, F1=0.72
- **MicroTransformer**: 273,159 parameters, F1=0.64

Both models operate at the **character level** - no tokenizer needed. Input is a raw Etruscan inscription string.

## Training Data

1,050 weakly-labeled Etruscan inscriptions bootstrapped via **keyword-based weak supervision** from the OpenEtruscan corpus (4,728 inscriptions from the Larth dataset + Burman concordance enrichment).

## Usage

### Python (PyTorch)
```python
from openetruscan.neural import NeuralClassifier

clf = NeuralClassifier()
clf.load("path/to/models", model_type="cnn")
print(clf.predict("mi araθia velθurus"))  # → "ownership"
```

### ONNX Runtime (lightweight inference)
```python
import onnxruntime as ort
import numpy as np
import json

with open("cnn.json") as f:
    meta = json.load(f)

session = ort.InferenceSession("cnn.onnx")
# Tokenize: map each character to vocab index
text = "mi araθia velθurus"
ids = [meta["vocab"]["char_to_idx"].get(c, 1) for c in text.lower()]
ids = ids[:128] + [0] * max(0, 128 - len(ids))  # pad to 128

logits = session.run(None, {"input": np.array([ids], dtype=np.int64)})[0]
label = meta["labels"][logits.argmax()]
print(label)  # → "ownership"
```

### In-Browser (onnxruntime-web)
The ONNX model runs directly in the browser via WebAssembly. See the [OpenEtruscan web app](https://eddy1919.github.io/openEtruscan/) Classifier tab for a live demo.

## Files

| File | Description |
|---|---|
| `cnn.onnx` | CNN model in ONNX format (production) |
| `cnn.json` | Vocabulary + label metadata for CNN |
| `cnn.pt` | CNN PyTorch weights |
| `transformer.onnx` | Transformer model in ONNX format |
| `transformer.json` | Vocabulary + label metadata for Transformer |
| `transformer.pt` | Transformer PyTorch weights |
| `metrics.json` | Training metrics and per-class F1 scores |

## Citation

If you use these models in your research, please cite:

```
@software{openetruscan_neural,
  title = {OpenEtruscan Neural Inscription Classifier},
  author = {Panichi, Edoardo},
  year = {2024},
  url = {https://github.com/Eddy1919/openEtruscan},
  license = {MIT}
}
```

## License

MIT
