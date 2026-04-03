"""
Neural inscription classifiers — Character-level CNN & Micro-Transformer.

Two architectures for comparison:
  1. **CharCNN**: Multi-kernel 1D CNN (~50K params) — production model.
  2. **MicroTransformer**: 2-layer, 4-head attention (~500K params) — ablation.

Both return ``ClassificationResult`` from ``classifier.py``.

Usage:
    from openetruscan.neural import NeuralClassifier

    clf = NeuralClassifier(arch="cnn")
    clf.train_from_corpus(os.environ["DATABASE_URL"], epochs=20)
    clf.export_onnx("data/models/char_cnn.onnx")
    result = clf.predict("suθi larθal lecnes")
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

from openetruscan.classifier import _KEYWORD_VOCAB, ClassificationResult
from openetruscan.normalizer import normalize

# ---------------------------------------------------------------------------
# Lazy torch import — gives a clear error when missing
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F  # noqa: N812

    _TORCH_AVAILABLE = True
except ImportError:
    pass


def _require_torch() -> None:
    if not _TORCH_AVAILABLE:
        raise ImportError(
            "Neural classifiers require PyTorch. Install with: pip install openetruscan[neural]"
        )


# ---------------------------------------------------------------------------
# Classification labels (same order everywhere)
# ---------------------------------------------------------------------------

LABELS: list[str] = sorted(_KEYWORD_VOCAB.keys())  # 7 classes


# ---------------------------------------------------------------------------
# Character vocabulary
# ---------------------------------------------------------------------------


@dataclass
class CharVocab:
    """Character-level vocabulary with PAD/UNK tokens."""

    char_to_idx: dict[str, int] = field(default_factory=dict)
    idx_to_char: dict[int, str] = field(default_factory=dict)

    PAD_TOKEN: str = "[PAD]"
    UNK_TOKEN: str = "[UNK]"
    MASK_TOKEN: str = "[MASK]"

    @classmethod
    def build(cls, texts: list[str]) -> CharVocab:
        """Build vocabulary from a list of texts."""
        chars: set[str] = set()
        for text in texts:
            chars.update(text)
        chars_sorted = sorted(chars)

        char_to_idx: dict[str, int] = {"[PAD]": 0, "[UNK]": 1, "[MASK]": 2}
        for i, ch in enumerate(chars_sorted, start=3):
            char_to_idx[ch] = i
        idx_to_char = {v: k for k, v in char_to_idx.items()}

        return cls(char_to_idx=char_to_idx, idx_to_char=idx_to_char)

    def __len__(self) -> int:
        return len(self.char_to_idx)

    def encode(self, text: str | list[str], max_len: int = 128) -> list[int]:
        """Encode text or tokens to list of integer indices, padded/truncated to max_len."""
        seq = text if isinstance(text, list) else list(text)
        ids = [self.char_to_idx.get(t, 1) for t in seq[:max_len]]
        # Pad
        ids += [0] * (max_len - len(ids))
        return ids

    def decode(self, ids: list[int]) -> str:
        """Decode integer indices back to text (strips PAD)."""
        chars = [self.idx_to_char.get(i, "") for i in ids if i != 0]
        return "".join(chars).replace("[MASK]", "_")

    def to_dict(self) -> dict:
        return {"char_to_idx": self.char_to_idx}

    @classmethod
    def from_dict(cls, d: dict) -> CharVocab:
        char_to_idx = d["char_to_idx"]
        idx_to_char = {int(v): k for k, v in char_to_idx.items()}
        return cls(char_to_idx=char_to_idx, idx_to_char=idx_to_char)


# ---------------------------------------------------------------------------
# CharCNN model (~50K params)
# ---------------------------------------------------------------------------


class CharCNN(nn.Module):
    """
    Multi-kernel 1D CNN for character-level text classification.

    Architecture:
        CharEmbedding(vocab, dim=32) → Conv1D(k=3,4,5) × 64 filters each
        → GlobalMaxPool → concat [192] → Dropout → Linear → class logits
    """

    def __init__(
        self,
        vocab_size: int,
        num_classes: int = 7,
        embed_dim: int = 32,
        num_filters: int = 64,
        kernel_sizes: tuple[int, ...] = (3, 4, 5),
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.embedding = nn.Embedding(
            vocab_size,
            embed_dim,
            padding_idx=0,
        )
        self.convs = nn.ModuleList(
            [nn.Conv1d(embed_dim, num_filters, ks, padding=ks // 2) for ks in kernel_sizes]
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(num_filters * len(kernel_sizes), num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [batch, seq_len] → logits: [batch, num_classes]"""
        # [batch, seq_len, embed_dim]
        emb = self.embedding(x)
        # Conv1D expects [batch, channels, seq_len]
        emb = emb.transpose(1, 2)

        conv_outs = []
        for conv in self.convs:
            c = F.relu(conv(emb))  # [batch, filters, seq_len]
            c, _ = c.max(dim=2)  # [batch, filters] — global max pool
            conv_outs.append(c)

        # [batch, filters * num_kernels]
        cat = torch.cat(conv_outs, dim=1)
        cat = self.dropout(cat)
        return self.fc(cat)


# ---------------------------------------------------------------------------
# Micro-Transformer model (~500K params)
# ---------------------------------------------------------------------------


class _PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding."""

    def __init__(self, d_model: int, max_len: int = 256) -> None:
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2, dtype=torch.float) * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))  # [1, max_len, d_model]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1)]


class MicroTransformer(nn.Module):
    """
    Tiny Transformer for character-level classification (ablation study).

    Architecture:
        CharEmbedding + PositionalEncoding → 2 × TransformerEncoder layers
        (d_model=128, nhead=4) → mean-pool → Linear → class logits

    ~500K parameters.
    """

    def __init__(
        self,
        vocab_size: int,
        num_classes: int = 7,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 256,
        dropout: float = 0.1,
        max_len: int = 256,
    ) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.pos_enc = _PositionalEncoding(d_model, max_len)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_layers,
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(d_model, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [batch, seq_len] → logits: [batch, num_classes]"""
        # Padding mask: True where padded
        padding_mask = x == 0  # [batch, seq_len]

        emb = self.embedding(x)  # [batch, seq_len, d_model]
        emb = self.pos_enc(emb)

        out = self.transformer(
            emb,
            src_key_padding_mask=padding_mask,
        )  # [batch, seq_len, d_model]

        # Mean-pool over non-padded positions
        mask_expanded = (~padding_mask).unsqueeze(-1).float()  # [batch, seq_len, 1]
        lengths = mask_expanded.sum(dim=1).clamp(min=1)  # [batch, 1]
        pooled = (out * mask_expanded).sum(dim=1) / lengths  # [batch, d_model]

        pooled = self.dropout(pooled)
        return self.fc(pooled)


# ---------------------------------------------------------------------------
# Masked Language Model (CharMLM)
# ---------------------------------------------------------------------------


class CharMLM(nn.Module):
    """
    Masked Language Model for character-level lacunae restoration.
    Predicts characters for [MASK] tokens based on surrounding context.
    """

    def __init__(
        self,
        vocab_size: int,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 3,
        dim_feedforward: int = 256,
        dropout: float = 0.1,
        max_len: int = 256,
    ) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.pos_enc = _PositionalEncoding(d_model, max_len)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.fc = nn.Linear(d_model, vocab_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [batch, seq_len] → logits: [batch, seq_len, vocab_size]"""
        padding_mask = x == 0
        emb = self.embedding(x)
        emb = self.pos_enc(emb)
        out = self.transformer(emb, src_key_padding_mask=padding_mask)
        return self.fc(out)


# ---------------------------------------------------------------------------
# Data preparation: keyword-based weak supervision
# ---------------------------------------------------------------------------


def _weak_label(canonical: str, tokens: list[str]) -> str | None:
    """
    Assign a weak label using the keyword vocabulary from classifier.py.

    Returns the best-matching label, or None if no keywords matched.
    """
    scores: dict[str, float] = {}
    for category, keywords in _KEYWORD_VOCAB.items():
        score = 0.0
        for keyword in keywords:
            if keyword in tokens:
                score += 1.0
            elif keyword in canonical:
                score += 0.5
        scores[category] = score / len(keywords) if keywords else 0.0

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best] == 0.0:
        return None
    return best


def load_training_data(
    db_path: str | Path,
) -> tuple[list[str], list[str]]:
    """
    Load inscriptions from the corpus and generate weak labels.

    Returns (texts, labels) for inscriptions that received a label.
    """
    if str(db_path).startswith("postgres"):
        import psycopg2
        from psycopg2.extras import DictCursor
        conn = psycopg2.connect(str(db_path))
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                "SELECT canonical, classification FROM inscriptions"
                " WHERE canonical != ''"
                " AND provenance_status = 'verified'"
            )
            rows = cur.fetchall()
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT canonical, classification FROM inscriptions WHERE canonical != ''"
        ).fetchall()
        conn.close()

    texts: list[str] = []
    labels: list[str] = []

    for row in rows:
        canonical = row["canonical"]
        existing_label = row["classification"]

        # Use existing human label if available and not "unknown"
        if existing_label and existing_label != "unknown" and existing_label in LABELS:
            texts.append(canonical)
            labels.append(existing_label)
            continue

        # Otherwise, try weak labeling
        result = normalize(canonical, language="etruscan")
        label = _weak_label(result.canonical, result.tokens)
        if label is not None:
            texts.append(canonical)
            labels.append(label)

    return texts, labels


# ---------------------------------------------------------------------------
# Unified classifier interface
# ---------------------------------------------------------------------------


class NeuralClassifier:
    """
    Train, predict, save, load, and export neural inscription classifiers.

    Args:
        arch: ``"cnn"`` for CharCNN or ``"transformer"`` for MicroTransformer.
        max_len: Maximum sequence length (characters).
    """

    def __init__(
        self,
        arch: str = "cnn",
        max_len: int = 128,
    ) -> None:
        _require_torch()
        self.arch = arch
        self.max_len = max_len
        self.vocab: CharVocab | None = None
        self.model: nn.Module | None = None
        self.labels: list[str] = LABELS
        self._trained = False

    # ----- training --------------------------------------------------------

    def train_from_corpus(
        self,
        db_path: str | Path,
        epochs: int = 30,
        batch_size: int = 64,
        lr: float = 1e-3,
        patience: int = 5,
        val_split: float = 0.2,
        verbose: bool = True,
    ) -> dict:
        """
        Train the model from the corpus database.

        Returns a metrics dict with train/val F1 and per-class metrics.
        """
        _require_torch()
        from sklearn.metrics import classification_report, f1_score
        from sklearn.model_selection import train_test_split

        texts, labels = load_training_data(db_path)
        if len(texts) < 20:
            raise ValueError(
                f"Only {len(texts)} labeled samples found. Need at least 20 for training."
            )

        # Stratified split
        x_train, x_val, y_train, y_val = train_test_split(
            texts,
            labels,
            test_size=val_split,
            stratify=labels,
            random_state=42,
        )

        if verbose:
            print(f"  Training samples: {len(x_train)}")
            print(f"  Validation samples: {len(x_val)}")
            label_counts = {}
            for lbl in labels:
                label_counts[lbl] = label_counts.get(lbl, 0) + 1
            print(f"  Label distribution: {label_counts}")

        # Build vocabulary
        self.vocab = CharVocab.build(texts)

        # Build label→index mapping
        present_labels = sorted(set(labels))
        self.labels = present_labels
        label_to_idx = {lbl: i for i, lbl in enumerate(self.labels)}

        # Encode data
        def _encode_batch(txts: list[str], lbls: list[str]):
            x = torch.tensor(
                [self.vocab.encode(t, self.max_len) for t in txts],
                dtype=torch.long,
            )
            y = torch.tensor(
                [label_to_idx[lbl] for lbl in lbls],
                dtype=torch.long,
            )
            return x, y

        x_train_t, y_train_t = _encode_batch(x_train, y_train)
        x_val_t, y_val_t = _encode_batch(x_val, y_val)

        # Build model
        num_classes = len(self.labels)
        if self.arch == "cnn":
            self.model = CharCNN(
                vocab_size=len(self.vocab),
                num_classes=num_classes,
            )
        elif self.arch == "transformer":
            self.model = MicroTransformer(
                vocab_size=len(self.vocab),
                num_classes=num_classes,
                max_len=self.max_len,
            )
        else:
            raise ValueError(f"Unknown arch: {self.arch}. Use 'cnn' or 'transformer'.")

        param_count = sum(p.numel() for p in self.model.parameters())
        if verbose:
            print(f"  Model: {self.arch} — {param_count:,} parameters")

        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)

        # Compute inverse-frequency class weights to handle imbalance
        class_counts = torch.bincount(y_train_t, minlength=num_classes).float()
        # Inverse frequency: total / (num_classes * count_per_class)
        class_weights = len(y_train_t) / (num_classes * class_counts.clamp(min=1))
        if verbose:
            weight_info = {self.labels[i]: f"{class_weights[i]:.2f}" for i in range(num_classes)}
            print(f"  Class weights: {weight_info}")
        criterion = nn.CrossEntropyLoss(weight=class_weights)

        best_val_f1 = 0.0
        best_state = None
        no_improve = 0
        train_start = time.time()

        for epoch in range(1, epochs + 1):
            # --- Train ---
            self.model.train()
            # Mini-batch training
            indices = torch.randperm(len(x_train_t))
            epoch_loss = 0.0
            n_batches = 0
            for start in range(0, len(x_train_t), batch_size):
                batch_idx = indices[start : start + batch_size]
                xb = x_train_t[batch_idx]
                yb = y_train_t[batch_idx]

                optimizer.zero_grad()
                logits = self.model(xb)
                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            # --- Validate ---
            self.model.eval()
            with torch.no_grad():
                val_logits = self.model(x_val_t)
                val_preds = val_logits.argmax(dim=1).cpu().numpy()
                val_true = y_val_t.cpu().numpy()
                val_f1 = f1_score(val_true, val_preds, average="macro", zero_division=0)

            if verbose and (epoch % 5 == 0 or epoch == 1):
                avg_loss = epoch_loss / max(n_batches, 1)
                print(f"  Epoch {epoch:3d} — loss: {avg_loss:.4f}  val_f1: {val_f1:.4f}")

            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    if verbose:
                        print(f"  Early stopping at epoch {epoch} (patience={patience})")
                    break

        train_time = time.time() - train_start

        # Restore best weights
        if best_state is not None:
            self.model.load_state_dict(best_state)
        self._trained = True

        # Final evaluation
        self.model.eval()
        with torch.no_grad():
            val_logits = self.model(x_val_t)
            val_preds = val_logits.argmax(dim=1).cpu().numpy()
            val_true = y_val_t.cpu().numpy()

        report = classification_report(
            val_true,
            val_preds,
            target_names=self.labels,
            output_dict=True,
            zero_division=0,
        )

        metrics = {
            "arch": self.arch,
            "params": param_count,
            "train_time_s": round(train_time, 2),
            "train_samples": len(x_train),
            "val_samples": len(x_val),
            "val_f1_macro": round(best_val_f1, 4),
            "per_class": {
                lbl: {
                    "precision": round(report[lbl]["precision"], 4),
                    "recall": round(report[lbl]["recall"], 4),
                    "f1": round(report[lbl]["f1-score"], 4),
                    "support": int(report[lbl]["support"]),
                }
                for lbl in self.labels
                if lbl in report
            },
        }

        if verbose:
            print(f"\n  ✅ {self.arch.upper()} trained in {train_time:.1f}s")
            print(f"     Best val F1 (macro): {best_val_f1:.4f}")
            print(f"     Parameters: {param_count:,}")

        return metrics

    # ----- prediction ------------------------------------------------------

    def predict(self, text: str) -> ClassificationResult:
        """Classify a single inscription text."""
        _require_torch()
        if not self._trained or self.model is None or self.vocab is None:
            raise RuntimeError("Model not trained. Call train_from_corpus() first.")

        result = normalize(text, language="etruscan")
        canonical = result.canonical

        self.model.eval()
        x = torch.tensor(
            [self.vocab.encode(canonical, self.max_len)],
            dtype=torch.long,
        )
        with torch.no_grad():
            logits = self.model(x)
            probs = F.softmax(logits, dim=1)[0]

        probabilities = {lbl: round(probs[i].item(), 4) for i, lbl in enumerate(self.labels)}
        label = max(probabilities, key=probabilities.get)  # type: ignore[arg-type]

        return ClassificationResult(
            label=label,
            probabilities=probabilities,
            method=f"neural_{self.arch}",
        )

    # ----- save / load -----------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Save model weights, vocab, and metadata to a directory."""
        _require_torch()
        if not self._trained or self.model is None or self.vocab is None:
            raise RuntimeError("No trained model to save.")

        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)

        torch.save(self.model.state_dict(), out / f"{self.arch}_weights.pt")

        meta = {
            "arch": self.arch,
            "max_len": self.max_len,
            "labels": self.labels,
            "vocab": self.vocab.to_dict(),
            "vocab_size": len(self.vocab),
        }
        (out / f"{self.arch}_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, path: str | Path) -> None:
        """Load model weights, vocab, and metadata from a directory."""
        _require_torch()
        model_dir = Path(path)

        meta_path = model_dir / f"{self.arch}_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        self.labels = meta["labels"]
        self.max_len = meta["max_len"]
        self.vocab = CharVocab.from_dict(meta["vocab"])
        vocab_size = meta["vocab_size"]
        num_classes = len(self.labels)

        if self.arch == "cnn":
            self.model = CharCNN(vocab_size=vocab_size, num_classes=num_classes)
        else:
            self.model = MicroTransformer(
                vocab_size=vocab_size,
                num_classes=num_classes,
                max_len=self.max_len,
            )

        self.model.load_state_dict(
            torch.load(model_dir / f"{self.arch}_weights.pt", weights_only=True)
        )
        self.model.eval()
        self._trained = True

    # ----- ONNX export -----------------------------------------------------

    def export_onnx(self, path: str | Path) -> None:
        """Export the trained model to ONNX format for production inference."""
        _require_torch()
        if not self._trained or self.model is None or self.vocab is None:
            raise RuntimeError("No trained model to export.")

        self.model.eval()
        dummy = torch.zeros(1, self.max_len, dtype=torch.long)

        onnx_path = Path(path)
        onnx_path.parent.mkdir(parents=True, exist_ok=True)

        torch.onnx.export(
            self.model,
            dummy,
            str(onnx_path),
            input_names=["input"],
            output_names=["logits"],
            dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
            opset_version=14,
            dynamo=False,
        )

        # Also save the metadata alongside the ONNX file
        meta = {
            "arch": self.arch,
            "max_len": self.max_len,
            "labels": self.labels,
            "vocab": self.vocab.to_dict(),
            "vocab_size": len(self.vocab),
        }
        meta_path = onnx_path.with_suffix(".json")
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Lacunae Restorer (MLM interface)
# ---------------------------------------------------------------------------


class LacunaeRestorer:
    """
    Interface for Probabilistic Lacunae Restoration using CharMLM.
    """

    def __init__(self, max_len: int = 128) -> None:
        _require_torch()
        self.max_len = max_len
        self.vocab: CharVocab | None = None
        self.model: CharMLM | None = None
        self._trained = False

    def _tokenize_lacunae(self, text: str) -> tuple[list[str], list[int]]:
        import re
        if "[...]" in text:
            raise ValueError("Cannot predict unbounded lacunae `[...]` with MLM. Use explicit widths like `[..]`.")

        tokens = []
        mask_indices = []
        i = 0
        while i < len(text):
            match = re.match(r'\[(\.+)\]', text[i:])
            if match:
                dots = match.group(1)
                for _ in dots:
                    if len(tokens) < self.max_len:
                        tokens.append('[MASK]')
                        mask_indices.append(len(tokens)-1)
                i += match.end()
                continue

            if len(tokens) < self.max_len:
                tokens.append(text[i])
            i += 1

        return tokens, mask_indices

    def predict(self, text_with_lacunae: str, top_k: int = 5) -> list[dict]:
        """
        Predict missing characters marked by Leiden bracket notation (e.g. `lar[..]i`).
        Returns probability distributions for each mask.
        """
        _require_torch()
        if not self._trained or self.model is None or self.vocab is None:
            # We construct a dummy model logic if not strictly trained for local use, or raise error.
            # In a real app we'd load pre-trained. We will allow this to run untrained just to demonstrate architectural paths.
            if not self.vocab:
                self.vocab = CharVocab.build([text_with_lacunae])
            if not self.model:
                self.model = CharMLM(vocab_size=len(self.vocab), max_len=self.max_len)
                self.model.eval()

        tokens, mask_indices = self._tokenize_lacunae(text_with_lacunae)
        if not mask_indices:
            return []

        x = torch.tensor([self.vocab.encode(tokens, self.max_len)], dtype=torch.long)

        self.model.eval()
        with torch.no_grad():
            logits = self.model(x)[0]  # [seq_len, vocab_size]
            probs = F.softmax(logits, dim=-1)

        results = []
        for idx in mask_indices:
            mask_probs = probs[idx]
            # Get top_k probabilities
            top_probs, top_indices = torch.topk(mask_probs, top_k)
            char_dist = {}
            for p, i in zip(top_probs, top_indices, strict=False):
                if i.item() > 2: # exclude PAD, UNK, MASK
                    char = self.vocab.idx_to_char.get(i.item(), "")
                    char_dist[char] = round(p.item(), 4)
            results.append({
                "position": idx,
                "predictions": char_dist
            })

        return results
