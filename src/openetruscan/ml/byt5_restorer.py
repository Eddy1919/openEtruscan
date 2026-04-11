"""
ByT5 Lacunae Restorer.

Fine-tunes the `google/byt5-small` model on Etruscan texts
to restore lacunae. Operates entirely at the byte level, avoiding
the linguistic destruction caused by English-biased subword tokenizers.

Usage:
    from openetruscan.ml.byt5_restorer import ByT5Restorer
    restorer = ByT5Restorer()
    restorer.train_from_db(os.environ["DATABASE_URL"])
"""

import time
import random
import psycopg2
from typing import Any

from sklearn.model_selection import train_test_split
import torch

try:
    from transformers import (
        AutoTokenizer,
        AutoModelForSeq2SeqLM,
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
    )
    from datasets import Dataset

    _HF_AVAILABLE = True
except ImportError:
    _HF_AVAILABLE = False


class ByT5Restorer:
    def __init__(self, model_name: str = "google/byt5-small", max_length: int = 128) -> None:
        if not _HF_AVAILABLE:
            raise ImportError("Please install transformers, datasets, and accelerate.")

        # Configure hardware target
        self.device = torch.device(
            "cuda"
            if torch.cuda.is_available()
            else "mps"
            if torch.backends.mps.is_available()
            else "cpu"
        )
        self.model_name = model_name
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(self.device)
        self._trained = False

    def _corrupt_text(self, text: str) -> str:
        """
        Synthetically generate training data by blanking out characters.
        e.g., 'suθi larθal' -> 'suθ[..]arθal'
        """
        if len(text) < 5:
            return text

        # Random location to mask
        idx = random.randint(1, len(text) - 4)
        # Random mask width (1 to 3 characters)
        length = random.randint(1, min(3, len(text) - idx - 1))

        # We use standard Leiden bracket notation with dots for characters
        mask_str = f"[{'.' * length}]"

        return text[:idx] + mask_str + text[idx + length :]

    def train_from_db(
        self,
        db_url: str,
        output_dir: str = "data/models/byt5_etruscan",
        epochs: int = 3,
        batch_size: int = 8,
    ) -> dict[str, Any]:
        """Fetch canonical inscriptions and fine-tune ByT5 to denoise them."""

        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            # We want verified, clean canonical text to corrupt and learn from
            cur.execute(
                "SELECT canonical FROM inscriptions "
                "WHERE canonical != '' AND provenance_status = 'verified'"
            )
            rows = cur.fetchall()
        conn.close()

        texts = [r[0] for r in rows if r[0] and len(r[0]) >= 5]
        if len(texts) < 20:
            raise ValueError(f"Only {len(texts)} samples found. Need more for fine-tuning.")

        # 90-10 Split
        train_texts, val_texts = train_test_split(texts, test_size=0.1, random_state=42)

        print(f"  Preparing HuggingFace dataset ({len(train_texts)} train, {len(val_texts)} val)")

        def prepare_hf_dataset(raw_texts):
            # Input is the corrupted string, target is the original ground-truth string
            inputs = [self._corrupt_text(t) for t in raw_texts]
            return Dataset.from_dict({"input_text": inputs, "target_text": raw_texts})

        train_ds = prepare_hf_dataset(train_texts)
        val_ds = prepare_hf_dataset(val_texts)

        def tokenize_func(examples):
            model_inputs = self.tokenizer(
                examples["input_text"],
                max_length=self.max_length,
                padding="max_length",
                truncation=True,
            )
            labels = self.tokenizer(
                text_target=examples["target_text"],
                max_length=self.max_length,
                padding="max_length",
                truncation=True,
            )
            model_inputs["labels"] = labels["input_ids"]
            return model_inputs

        train_ds = train_ds.map(
            tokenize_func, batched=True, remove_columns=["input_text", "target_text"]
        )
        val_ds = val_ds.map(
            tokenize_func, batched=True, remove_columns=["input_text", "target_text"]
        )

        args = Seq2SeqTrainingArguments(
            output_dir=output_dir,
            eval_strategy="epoch",
            learning_rate=2e-4,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            weight_decay=0.01,
            save_total_limit=1,
            num_train_epochs=epochs,
            predict_with_generate=True,
            fp16=torch.cuda.is_available(),
            logging_steps=10,
        )

        trainer = Seq2SeqTrainer(
            model=self.model,
            args=args,
            train_dataset=train_ds,
            eval_dataset=val_ds,
            processing_class=self.tokenizer,
        )

        print("\n  🚀 Starting ByT5 Fine-tuning...\n")
        start = time.time()
        train_result = trainer.train()
        train_time = time.time() - start

        trainer.save_model(output_dir)
        self.tokenizer.save_pretrained(output_dir)
        self._trained = True

        print(f"\n  ✅ ByT5 trained in {train_time:.1f}s")
        print(f"  💾 Saved to {output_dir}")

        return {
            "arch": "byt5_small",
            "train_time_s": round(train_time, 2),
            "train_samples": len(train_texts),
            "val_samples": len(val_texts),
            "loss": train_result.metrics.get("train_loss", 0),
        }

    def predict(self, corrupted_text: str) -> str:
        """Pass a string like 'lar[..]i' through the network for restoration."""
        if not self._trained:
            raise RuntimeError("Model not trained or loaded.")

        inputs = self.tokenizer(corrupted_text, return_tensors="pt").input_ids.to(self.device)
        outputs = self.model.generate(inputs, max_length=self.max_length)
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)
