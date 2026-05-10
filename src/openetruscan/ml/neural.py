"""
Neural inscription classifiers — Character-level CNN & Micro-Transformer.

Two architectures for comparison:
  1. **CharCNN**: Multi-kernel 1D CNN (~50K params) — production model.
  2. **MicroTransformer**: 2-layer, 4-head attention (~500K params) — ablation.

Both return ``ClassificationResult`` from ``classifier.py``.

Usage:
    from openetruscan.ml.neural import NeuralClassifier

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

from openetruscan.ml.classifier import _KEYWORD_VOCAB, ClassificationResult
from openetruscan.core.normalizer import normalize

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

    class _DummyModule:
        """Fallback for nn.Module when PyTorch is not installed."""

        pass

    class _DummyNN:
        """Fallback for torch.nn when PyTorch is not installed."""

        Module = _DummyModule

    nn = _DummyNN()  # type: ignore


def _require_torch() -> None:
    """Check if PyTorch is available and raise an ImportError if not."""
    if not _TORCH_AVAILABLE:
        raise ImportError(
            "Neural classifiers require PyTorch. Install with: pip install openetruscan[neural]"
        )


class AlphaFocalLoss(nn.Module):
    """
    α-balanced Focal Loss: FL(pt) = -αt (1 - pt)^γ log(pt)
    Designed to address class imbalance by focusing on hard examples and weighting by rare classes.
    """
    def __init__(self, alpha: torch.Tensor, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_loss = F.cross_entropy(inputs, targets, reduction='none', weight=self.alpha)
        pt = torch.exp(-ce_loss)
        focal_loss = ((1 - pt) ** self.gamma * ce_loss).mean()
        return focal_loss


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
        """Return the number of unique tokens in the vocabulary."""
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
        """Serialize the vocabulary to a dictionary for JSON storage."""
        return {"char_to_idx": self.char_to_idx}

    @classmethod
    def from_dict(cls, d: dict) -> CharVocab:
        """De-serialize the vocabulary from a dictionary."""
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
        """Initialize the Character CNN with specified hyperparameters."""
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
        """Initialize the sinusoidal positional encoding layer."""
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
        """Add positional encoding to the input embedding tensor."""
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
        """Initialize the ablation study MicroTransformer with restricted parameter space."""
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


class IthacaMicroTransformer(nn.Module):
    """
    Ithaca-style Multi-Modal Transformer.
    Injects [lat, lon, date_approx] directly into the character embeddings
    to contextualize learning using geographical and temporal dialect cues.
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

        # Spatial/Temporal projection: [1, 3] -> [1, d_model]
        self.context_proj = nn.Linear(3, d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(d_model, num_classes)

    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        """
        x: [batch, seq_len]
        context: [batch, 3] -> (lat, lon, date_approx)
        logits: [batch, num_classes]
        """
        padding_mask = x == 0

        # Character Embedding Space
        emb = self.embedding(x)  # [batch, seq_len, d_model]
        emb = self.pos_enc(emb)

        # Context Space
        ctx_emb = self.context_proj(context).unsqueeze(1)  # [batch, 1, d_model]

        # Concatenate Context as a prefix token (like a CLS token but dense)
        # Sequence becomes [Context, Char1, Char2, ...]
        combined_emb = torch.cat([ctx_emb, emb], dim=1)  # [batch, seq_len + 1, d_model]

        # Update padding mask to account for the new context token (never padded)
        ctx_mask = torch.zeros((x.size(0), 1), dtype=torch.bool, device=x.device)
        combined_mask = torch.cat([ctx_mask, padding_mask], dim=1)

        out = self.transformer(
            combined_emb,
            src_key_padding_mask=combined_mask,
        )

        # Use only the Context token representation for classification pooling
        # (Alternatively, mean-pool across the entire sequence)
        pooled = out[:, 0, :]

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
        """Initialize the Masked Language Model Transformer."""
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
    db_url: str | Path,
) -> tuple[list[str], list[str]]:
    """
    Load inscriptions from the corpus and generate weak labels.

    Returns (texts, labels) for inscriptions that received a label.
    """
    import psycopg2
    from psycopg2.extras import DictCursor

    conn = psycopg2.connect(str(db_url))
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            "SELECT canonical, classification FROM inscriptions"
            " WHERE canonical != ''"
            " AND classification != 'unknown'"
        )
        rows = cur.fetchall()
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
        """
        Initialize the neural classifier interface for training and inference.
        Allowed archs: cnn, transformer, ithaca.
        """
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
        db_url: str | Path,
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

        texts_full, labels_full = load_training_data(db_url)

        # We also need context for Ithaca. Let's fetch context for all texts.
        import psycopg2
        from psycopg2.extras import DictCursor

        conn = psycopg2.connect(str(db_url))
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                "SELECT canonical, findspot_lat, findspot_lon, date_approx FROM inscriptions"
            )
            context_map = {
                r["canonical"]: [
                    float(r["findspot_lat"] or 0),
                    float(r["findspot_lon"] or 0),
                    float(r["date_approx"] or 0),
                ]
                for r in cur.fetchall()
            }
        conn.close()

        texts = []
        labels = []
        contexts = []
        for t, lbl in zip(texts_full, labels_full, strict=False):
            if t in context_map:
                texts.append(t)
                labels.append(lbl)
                contexts.append(context_map[t])

        if len(texts) < 20:
            raise ValueError(
                f"Only {len(texts)} labeled samples found. Need at least 20 for training."
            )

        # Filter out classes with < 2 samples to allow stratified split
        from collections import Counter
        counts = Counter(labels)
        valid_indices = [i for i, lbl in enumerate(labels) if counts[lbl] >= 2]
        
        if len(valid_indices) < len(texts):
            if verbose:
                removed = set(lbl for lbl, c in counts.items() if c < 2)
                print(f"  Warning: Dropping classes with < 2 samples: {removed}")
            texts = [texts[i] for i in valid_indices]
            labels = [labels[i] for i in valid_indices]
            contexts = [contexts[i] for i in valid_indices]

        # Stratified split
        x_train, x_val, y_train, y_val, c_train, c_val = train_test_split(
            texts,
            labels,
            contexts,
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
        def _encode_batch(txts: list[str], lbls: list[str], ctxs: list[list[float]]):
            """Encode a batch of texts, labels, and context into torch Tensors."""
            x = torch.tensor(
                [self.vocab.encode(t, self.max_len) for t in txts],
                dtype=torch.long,
            )
            y = torch.tensor(
                [label_to_idx[lbl] for lbl in lbls],
                dtype=torch.long,
            )
            c = torch.tensor(ctxs, dtype=torch.float)
            return x, y, c

        x_train_t, y_train_t, c_train_t = _encode_batch(x_train, y_train, c_train)
        x_val_t, y_val_t, c_val_t = _encode_batch(x_val, y_val, c_val)

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
        elif self.arch == "ithaca":
            self.model = IthacaMicroTransformer(
                vocab_size=len(self.vocab),
                num_classes=num_classes,
                max_len=self.max_len,
            )
        else:
            raise ValueError(f"Unknown arch: {self.arch}. Use 'cnn', 'transformer', or 'ithaca'.")

        param_count = sum(p.numel() for p in self.model.parameters())
        if verbose:
            print(f"  Model: {self.arch} — {param_count:,} parameters")

        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)

        # α-balanced Focal Loss (γ=2.0)
        class_counts = torch.bincount(y_train_t, minlength=num_classes).float()
        alpha = len(y_train_t) / (num_classes * class_counts.clamp(min=1))
        
        if verbose:
            weight_info = {self.labels[i]: f"{alpha[i]:.2f}" for i in range(num_classes)}
            print(f"  α-Weights: {weight_info}")
            
        criterion = AlphaFocalLoss(alpha=alpha.to(x_train_t.device), gamma=2.0)

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
                cb = c_train_t[batch_idx]

                optimizer.zero_grad()
                if self.arch == "ithaca":
                    logits = self.model(xb, cb)
                else:
                    logits = self.model(xb)

                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            # --- Validate ---
            self.model.eval()
            with torch.no_grad():
                if self.arch == "ithaca":
                    val_logits = self.model(x_val_t, c_val_t)
                else:
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
            if self.arch == "ithaca":
                val_logits = self.model(x_val_t, c_val_t)
            else:
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
# Lacunae Restorer
# ---------------------------------------------------------------------------
#
# Production restorer is the XLM-R + char-prediction-head model from
# research/experiments/lacuna_restoration/ (38.0% top-1 / 60.6% top-3
# on held-out masked positions; see CURATION_FINDINGS.md Finding 9).
#
# The restorer accepts Leiden bracket notation `lar[..]i` (where each
# `.` is one missing character of known width) and returns a per-mask
# probability distribution over the Etruscan character vocabulary.
# Unbounded lacunae `[...]` are rejected — width must be explicit for
# a per-position MLM.


_LACUNA_MODEL_PATHS = {
    "local://default": ("data/models/lora-char-head-v1", "data/models/v4"),
    "local://lora-char-head-v1": ("data/models/lora-char-head-v1", "data/models/v4"),
}


class LacunaeRestorer:
    """XLM-R + char-prediction-head Etruscan lacuna restorer.

    Uses the etr-lora-v4-warm-started encoder + a small MLP head over
    the ~50-class Etruscan character vocabulary. For each `[..]`
    bracket-notation mask in the input, replaces the bracketed span
    with the encoder's native ``<mask>`` token (one mask per missing
    character) and returns top-k character predictions per position.
    """

    def __init__(self, model_uri: str = "local://default", max_len: int = 128) -> None:
        _require_torch()
        self.model_uri = model_uri
        self.max_len = max_len

        if model_uri not in _LACUNA_MODEL_PATHS:
            raise ValueError(
                f"Unknown lacunae model_uri {model_uri!r}. "
                f"Known: {list(_LACUNA_MODEL_PATHS)}"
            )
        head_dir, adapter_dir = _LACUNA_MODEL_PATHS[model_uri]

        from transformers import AutoModel, AutoTokenizer
        from peft import PeftModel

        head_path = Path(head_dir)
        meta_path = head_path / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"Lacunae model not found at {head_path}. Sync from "
                f"gs://openetruscan-rosetta/models/lora-char-head-v1 first."
            )
        meta = json.loads(meta_path.read_text())

        self.char_set: list[str] = meta["char_set"]
        self.id_to_char = {i: c for i, c in enumerate(self.char_set)}
        self.num_classes = meta["num_classes"]
        self.hidden_dim = meta["hidden_dim"]

        self.tokenizer = AutoTokenizer.from_pretrained(meta["encoder"])
        base = AutoModel.from_pretrained(meta["encoder"])
        encoder = PeftModel.from_pretrained(base, adapter_dir)
        self.encoder = encoder.merge_and_unload()
        self.encoder.eval()

        self.head = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(self.hidden_dim, 256),
            nn.GELU(),
            nn.LayerNorm(256),
            nn.Linear(256, self.num_classes),
        )
        self.head.load_state_dict(
            torch.load(head_path / "char_head_best.pt", map_location="cpu", weights_only=True)
        )
        self.head.eval()

    def _expand_lacunae(self, text: str) -> tuple[str, list[int]]:
        """Replace each `[.+]` span with one ``<mask>`` per dot.

        Returns the expanded text and a list of original-string indices
        (relative to the cleaned text, with masks counted as one char
        each) for every mask, so callers can map predictions back to
        their input positions.
        """
        import re

        if "[...]" in text:
            raise ValueError(
                "Cannot predict unbounded lacunae `[...]`. Specify width with `[..]`."
            )

        out_chars: list[str] = []
        mask_positions: list[int] = []
        i = 0
        while i < len(text):
            m = re.match(r"\[(\.+)\]", text[i:])
            if m:
                for _ in m.group(1):
                    mask_positions.append(len(out_chars))
                    out_chars.append("\x00")  # placeholder, swapped to <mask> at lookup
                i += m.end()
            else:
                out_chars.append(text[i])
                i += 1
        return "".join(out_chars), mask_positions

    def predict(self, text_with_lacunae: str, top_k: int = 5) -> list[dict]:
        """Return top-k char distributions for every `[..]`-marked position."""
        _require_torch()
        expanded, mask_positions = self._expand_lacunae(text_with_lacunae)
        if not mask_positions:
            return []

        results: list[dict] = []
        mask_token = self.tokenizer.mask_token  # "<mask>"

        for pos in mask_positions:
            # Replace exactly the target placeholder with <mask>; leave
            # other placeholders as-is so we predict one position at a
            # time conditioned on the surrounding visible context.
            chars = list(expanded)
            chars[pos] = mask_token
            # Other placeholders are unknown to the model — strip them
            # so they don't poison the context.
            masked = "".join(c for c in chars if c != "\x00")

            encoded = self.tokenizer(masked, return_tensors="pt", truncation=True, max_length=self.max_len)
            mask_idx_tensor = (encoded.input_ids[0] == self.tokenizer.mask_token_id).nonzero(as_tuple=True)[0]
            if len(mask_idx_tensor) == 0:
                results.append({"position": pos, "predictions": {}})
                continue
            mask_idx = mask_idx_tensor[0].item()

            with torch.no_grad():
                hidden = self.encoder(**encoded).last_hidden_state
                logits = self.head(hidden[0, mask_idx])
            probs = F.softmax(logits, dim=-1)
            top_probs, top_ids = torch.topk(probs, min(top_k, self.num_classes))

            char_dist = {
                self.id_to_char[int(i)]: round(float(p), 4)
                for p, i in zip(top_probs, top_ids, strict=False)
            }
            results.append({"position": pos, "predictions": char_dist})

        return results
