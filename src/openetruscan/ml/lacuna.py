"""Etruscan Lacuna Restoration using contextual embeddings.

This module provides the production interface for the v3 lacuna restoration
model. It uses a validated XLM-R + etr-lora-v4 encoder to extract contextual
embeddings and a lightweight classification head to predict missing characters.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

warnings.warn(
    "openetruscan.ml.lacuna is deprecated and will be removed in 2.0",
    DeprecationWarning,
    stacklevel=2,
)

# ---------------------------------------------------------------------------
# Lazy torch import — same pattern as neural.py/embeddings.py, so importing
# this module (e.g. via the CLI) does not hard-fail without the ML extras.
# transformers/peft are imported inside LacunaRestorer.__init__.
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False

try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True
except ImportError:

    class _DummyModule:
        """Fallback for nn.Module when PyTorch is not installed."""

    class _DummyNN:
        """Fallback for torch.nn when PyTorch is not installed."""

        Module = _DummyModule

    nn = _DummyNN()


def _require_ml_extras() -> None:
    """Raise a clear error when torch is missing instead of a bare ImportError."""
    if not _TORCH_AVAILABLE:
        raise ImportError(
            "Lacuna restoration requires PyTorch, transformers, and peft. "
            "Install with: pip install openetruscan[transformers]"
        )


# Character set matching the lora-char-head-v1 model
ETRUSCAN_CHARS = (
    "abcdefghiklmnopqrstuvxyz"  # 24 Latin letters (no j/w)
    "θχσφξς"  # 6 Greek phonemes lower
    "ΘΧΣΦΞ"  # 5 Greek phonemes upper
    "śŚšń"  # 4 diacritical sibilants
    "ṛṭḥṿṣṇẹ"  # 7 IPA dot-below
    " ·•|:;"  # 6 Word separators
    "[]<>{}()?!"  # 10 Editorial markers
    "-"  # 1 Lacuna
)


class CharPredictionHead(nn.Module):
    """Linear classification head for character prediction."""

    def __init__(self, hidden_dim: int, num_classes: int):
        super().__init__()
        self.head = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, 256),
            nn.GELU(),
            nn.LayerNorm(256),
            nn.Linear(256, num_classes),
        )

    def forward(self, hidden_states: torch.Tensor, mask_positions: torch.Tensor) -> torch.Tensor:
        batch_idx = torch.arange(hidden_states.size(0), device=hidden_states.device)
        masked_hidden = hidden_states[batch_idx, mask_positions]
        return self.head(masked_hidden)


class LacunaRestorer:
    """Production interface for restoring missing characters in Etruscan inscriptions."""

    def __init__(
        self, model_dir: str | Path, base_model: str = "xlm-roberta-base", device: str = "cpu"
    ):
        _require_ml_extras()
        try:
            from peft import PeftModel
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise ImportError(
                "Lacuna restoration requires transformers and peft. "
                "Install with: pip install openetruscan[transformers]"
            ) from exc

        self.model_dir = Path(model_dir)
        self.device = device

        # Load metadata
        with open(self.model_dir / "metadata.json") as f:
            self.meta = json.load(f)

        self.char_set = self.meta.get("char_set", list(ETRUSCAN_CHARS))
        self.id_to_char = {i: c for i, c in enumerate(self.char_set)}

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(base_model)

        # Load encoder (Base + LoRA)
        base = AutoModel.from_pretrained(base_model)
        adapter_path = self.meta.get("adapter")
        if not adapter_path or not Path(adapter_path).exists():
            raise FileNotFoundError(
                f"LoRA adapter not found at {adapter_path!r} "
                f"(declared in {self.model_dir / 'metadata.json'}). "
                "Fix the 'adapter' entry to point at the etr-lora-v4 adapter "
                "directory; the ML runtime itself installs via "
                "pip install openetruscan[transformers]."
            )

        self.encoder = PeftModel.from_pretrained(base, adapter_path)
        self.encoder = self.encoder.merge_and_unload()
        self.encoder.to(self.device)
        self.encoder.eval()

        # Load classification head
        self.head = CharPredictionHead(
            hidden_dim=self.meta["hidden_dim"], num_classes=self.meta["num_classes"]
        )
        head_path = self.model_dir / "char_head_best.pt"
        self.head.load_state_dict(
            torch.load(head_path, map_location=self.device, weights_only=True)
        )
        self.head.to(self.device)
        self.head.eval()

    def predict(self, text: str, mask_pos: int, top_k: int = 5) -> list[tuple[str, float]]:
        """Predict the character at mask_pos in the given text.

        Args:
            text: The inscription text (clean).
            mask_pos: 0-indexed position of the missing character.
            top_k: Number of predictions to return.

        Returns:
            List of (character, probability) tuples.
        """
        # Insert <mask> at the lacuna position
        masked_text = text[:mask_pos] + "<mask>" + text[mask_pos + 1 :]

        encoded = self.tokenizer(masked_text, return_tensors="pt").to(self.device)

        # Find the <mask> token index
        mask_token_id = self.tokenizer.mask_token_id
        positions = (encoded.input_ids[0] == mask_token_id).nonzero(as_tuple=True)[0]

        if len(positions) == 0:
            raise ValueError("Tokenizer failed to insert <mask> token correctly.")

        idx = positions[0].item()

        with torch.no_grad():
            enc_out = self.encoder(**encoded)
            logits = self.head(enc_out.last_hidden_state, torch.tensor([idx], device=self.device))

        probs = torch.nn.functional.softmax(logits[0], dim=-1)
        topk_probs, topk_ids = torch.topk(probs, top_k)

        return [
            (self.id_to_char[int(tid)], float(tprob))
            for tid, tprob in zip(topk_ids, topk_probs, strict=True)
        ]
