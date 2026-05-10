#!/usr/bin/env python3
"""Train a character-prediction head on top of the etr-lora-v4 XLM-R encoder.

This leverages the validated Etruscan contextual embeddings to solve
lacuna restoration as a simple classification problem: given a masked
position in an inscription, predict which of the ~35 Etruscan characters
belongs there.

Architecture:
    1. XLM-R + etr-lora-v4 encoder (frozen or fine-tuned)
    2. Extract the 768-dim hidden state at the <mask> token position
    3. Linear(768, num_etruscan_chars) → softmax → predicted character

Training data is generated on the fly: for each inscription, we
iteratively mask one character at a time and create (masked_input,
target_char) pairs.

Usage:
    python train_lora_char_head.py \
        --corpus_path /gcs/openetruscan-rosetta/corpus/etruscan-prod-rawtext-v3.jsonl \
        --adapter_path /gcs/openetruscan-rosetta/adapters/etr-lora-v4 \
        --output_dir /gcs/openetruscan-rosetta/models/lora-char-head-v1 \
        --freeze_encoder \
        --epochs 20 --batch_size 32 --learning_rate 1e-3
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import subprocess
import sys
from pathlib import Path


def _ensure_deps():
    """Install HF stack matching the etr-lora-v4 training environment."""
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torch_xla"],
        check=False,
    )
    pkgs = []
    for mod, pkg in [
        ("transformers", "transformers>=4.40,<4.47"),
        ("peft", "peft>=0.10,<0.13"),
        ("sentencepiece", "sentencepiece>=0.2"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            pkgs.append(pkg)
    if pkgs:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *pkgs]
        )


# ── Etruscan character set (same as char_mlm.py) ─────────────────────

ETRUSCAN_CHARS_RAW = (
    "abcdefghiklmnopqrstuvxyz"  # 24 Latin letters (no j/w)
    "θχσφξς"                    # 6 Greek phonemes lower
    "ΘΧΣΦΞ"                     # 5 Greek phonemes upper
    "śŚšń"                      # 4 diacritical sibilants
    "ṛṭḥṿṣṇẹ"                   # 7 IPA dot-below
    " ·•|:;"                    # 6 Word separators
    "[]<>{}()?!"                # 10 Editorial markers
    "-"                         # 1 Lacuna
)

def _build_char_set():
    seen = set()
    chars = []
    for c in ETRUSCAN_CHARS_RAW:
        if c not in seen:
            chars.append(c)
            seen.add(c)
    return chars

ETRUSCAN_CHARS = _build_char_set()
CHAR_TO_ID = {c: i for i, c in enumerate(ETRUSCAN_CHARS)}
ID_TO_CHAR = {i: c for i, c in enumerate(ETRUSCAN_CHARS)}
NUM_CHARS = len(ETRUSCAN_CHARS)


# ── Dataset ───────────────────────────────────────────────────────────

import torch
from torch.utils.data import Dataset, DataLoader


class CharPredictionDataset(Dataset):
    """Generates (masked_text, mask_char_idx) pairs from inscriptions.

    For each inscription, we randomly pick `samples_per_text` character
    positions to mask (replacing with the XLM-R <mask> token string).
    """

    def __init__(self, texts, samples_per_text=3, seed=42):
        self.samples = []
        rng = random.Random(seed)

        for text in texts:
            # Find positions of valid Etruscan characters
            valid_positions = [
                i for i, c in enumerate(text)
                if c in CHAR_TO_ID
            ]
            if len(valid_positions) < 3:
                continue

            # Sample positions to mask
            n = min(samples_per_text, len(valid_positions))
            chosen = rng.sample(valid_positions, n)

            for pos in chosen:
                target_char = text[pos]
                target_id = CHAR_TO_ID[target_char]
                # Replace single char with <mask>
                masked = text[:pos] + "<mask>" + text[pos + 1:]
                self.samples.append({
                    "masked_text": masked,
                    "target_id": target_id,
                    "target_char": target_char,
                    "original": text,
                    "mask_pos_in_text": pos,
                })

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


def collate_fn(batch, tokenizer, max_length=64):
    """Tokenize a batch and locate the <mask> token positions."""
    texts = [s["masked_text"] for s in batch]
    targets = torch.tensor([s["target_id"] for s in batch], dtype=torch.long)

    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )

    # Find the position of the <mask> token in each sequence
    mask_token_id = tokenizer.mask_token_id
    mask_positions = []
    for i in range(encoded.input_ids.size(0)):
        positions = (encoded.input_ids[i] == mask_token_id).nonzero(as_tuple=True)[0]
        if len(positions) > 0:
            mask_positions.append(positions[0].item())
        else:
            # Fallback: mask token was truncated — use position 1 (after CLS)
            mask_positions.append(1)

    return {
        "input_ids": encoded.input_ids,
        "attention_mask": encoded.attention_mask,
        "mask_positions": torch.tensor(mask_positions, dtype=torch.long),
        "targets": targets,
    }


# ── Model (thin head) ────────────────────────────────────────────────

import torch.nn as nn


class CharPredictionHead(nn.Module):
    """Linear classification head: hidden_dim → num_etruscan_chars."""

    def __init__(self, hidden_dim=768, num_classes=NUM_CHARS, dropout=0.1):
        super().__init__()
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 256),
            nn.GELU(),
            nn.LayerNorm(256),
            nn.Linear(256, num_classes),
        )

    def forward(self, hidden_states, mask_positions):
        """Extract hidden states at mask positions and classify.

        Args:
            hidden_states: (batch, seq_len, hidden_dim)
            mask_positions: (batch,) — token index of <mask> per sample
        Returns:
            logits: (batch, num_classes)
        """
        batch_idx = torch.arange(hidden_states.size(0), device=hidden_states.device)
        masked_hidden = hidden_states[batch_idx, mask_positions]  # (batch, hidden_dim)
        return self.head(masked_hidden)


# ── Training ──────────────────────────────────────────────────────────

def _read_corpus(path, log):
    texts = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = (row.get("canonical_clean") or row.get("raw_text") or "").strip()
            if len(text) >= 5:
                texts.append(text)
    log.info("Loaded %d inscriptions from %s", len(texts), path)
    return texts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_path", required=True)
    parser.add_argument("--adapter_path", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--base_model", default="xlm-roberta-base")
    parser.add_argument("--freeze_encoder", action="store_true",
                        help="Freeze the XLM-R+LoRA encoder; train only the head.")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--learning_rate", type=float, default=1e-3)
    parser.add_argument("--max_length", type=int, default=64)
    parser.add_argument("--samples_per_text", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("lora_char_head")

    _ensure_deps()

    from functools import partial
    from transformers import AutoModel, AutoTokenizer
    from peft import PeftModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("torch=%s device=%s", torch.__version__, device)

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    # Load corpus
    texts = _read_corpus(Path(args.corpus_path), log)
    random.shuffle(texts)
    split = int(len(texts) * 0.9)
    train_texts, val_texts = texts[:split], texts[split:]
    log.info("Train: %d texts, Val: %d texts", len(train_texts), len(val_texts))

    train_ds = CharPredictionDataset(train_texts, args.samples_per_text, seed=args.seed)
    val_ds = CharPredictionDataset(val_texts, args.samples_per_text, seed=args.seed + 1)
    log.info("Train samples: %d, Val samples: %d", len(train_ds), len(val_ds))

    # Load encoder
    log.info("Loading %s + LoRA from %s", args.base_model, args.adapter_path)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    base_model = AutoModel.from_pretrained(args.base_model)
    encoder = PeftModel.from_pretrained(base_model, args.adapter_path)
    encoder = encoder.merge_and_unload()  # For XLM-R (not seq2seq), this is safe
    encoder.to(device)
    encoder.eval()

    if args.freeze_encoder:
        for p in encoder.parameters():
            p.requires_grad = False
        log.info("Encoder frozen — training head only.")
    else:
        log.info("Encoder unfrozen — end-to-end fine-tuning.")

    hidden_dim = encoder.config.hidden_size
    head = CharPredictionHead(hidden_dim=hidden_dim, num_classes=NUM_CHARS).to(device)
    log.info("Head: %d params", sum(p.numel() for p in head.parameters()))
    log.info("Character classes: %d (%s)", NUM_CHARS, ETRUSCAN_CHARS)

    _collate = partial(collate_fn, tokenizer=tokenizer, max_length=args.max_length)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              collate_fn=_collate, num_workers=2)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            collate_fn=_collate, num_workers=2)

    # Optimizer: head params + (optionally) encoder params
    trainable = list(head.parameters())
    if not args.freeze_encoder:
        trainable += [p for p in encoder.parameters() if p.requires_grad]

    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = nn.CrossEntropyLoss()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0

    for epoch in range(1, args.epochs + 1):
        # Train
        head.train()
        if not args.freeze_encoder:
            encoder.train()

        total_loss = 0.0
        total_correct = 0
        total_samples = 0

        for batch in train_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            mask_positions = batch["mask_positions"].to(device)
            targets = batch["targets"].to(device)

            with torch.set_grad_enabled(not args.freeze_encoder):
                enc_out = encoder(input_ids=input_ids, attention_mask=attention_mask)
            hidden = enc_out.last_hidden_state

            if args.freeze_encoder:
                hidden = hidden.detach()

            logits = head(hidden, mask_positions)
            loss = criterion(logits, targets)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()

            total_loss += loss.item() * targets.size(0)
            total_correct += (logits.argmax(dim=-1) == targets).sum().item()
            total_samples += targets.size(0)

        scheduler.step()
        train_loss = total_loss / max(total_samples, 1)
        train_acc = total_correct / max(total_samples, 1)

        # Validate
        head.eval()
        encoder.eval()
        val_loss_sum = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                mask_positions = batch["mask_positions"].to(device)
                targets = batch["targets"].to(device)

                enc_out = encoder(input_ids=input_ids, attention_mask=attention_mask)
                logits = head(enc_out.last_hidden_state, mask_positions)
                loss = criterion(logits, targets)

                val_loss_sum += loss.item() * targets.size(0)
                val_correct += (logits.argmax(dim=-1) == targets).sum().item()
                val_total += targets.size(0)

        val_loss = val_loss_sum / max(val_total, 1)
        val_acc = val_correct / max(val_total, 1)

        log.info(
            "Epoch %d/%d — train_loss=%.4f train_acc=%.1f%% val_loss=%.4f val_acc=%.1f%% lr=%.2e",
            epoch, args.epochs, train_loss, train_acc * 100,
            val_loss, val_acc * 100, scheduler.get_last_lr()[0],
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(head.state_dict(), output_dir / "char_head_best.pt")
            log.info("  ↑ New best val_acc=%.1f%% — saved.", val_acc * 100)

    # Save final
    torch.save(head.state_dict(), output_dir / "char_head_final.pt")

    metadata = {
        "char_set": ETRUSCAN_CHARS,
        "num_classes": NUM_CHARS,
        "hidden_dim": hidden_dim,
        "encoder": args.base_model,
        "adapter": args.adapter_path,
        "freeze_encoder": args.freeze_encoder,
        "epochs": args.epochs,
        "best_val_acc": best_val_acc,
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    log.info("Done. Best val_acc=%.1f%%", best_val_acc * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
