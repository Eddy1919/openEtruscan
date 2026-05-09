"""LoRA fine-tuning of the multilingual encoder on Etruscan inscriptions.

This is the second half of the Rosetta architecture:

  Phase A (this file): take a pretrained multilingual encoder
  (XLM-R-base by default), continue masked-LM pretraining on the
  Etruscan corpus with a LoRA adapter (~1% of parameters trainable).
  The adapter learns Etruscan-specific morphology and onomastic
  patterns without overwriting the encoder's existing 100+ language
  representations.

  Phase B (embeddings.py): load the same base + the adapter, take
  contextual embeddings out of the encoder, store in pgvector.

Why LoRA, not full fine-tuning
------------------------------
* **Cost**: a full fine-tune of XLM-R-base on 15k tokens needs ~16 GB
  VRAM and takes ~30 min on an A100. LoRA needs ~6 GB and 5 min on a
  T4. Both produce comparable downstream quality on this corpus size
  (Hu et al, *LoRA*, 2021; Pfeiffer et al, *MAD-X*, 2020).
* **Safety**: full fine-tuning at 15k tokens overfits the encoder and
  destroys the pretrained multilingual structure (catastrophic
  forgetting). LoRA freezes the base weights and only learns
  low-rank updates, so the cross-language alignment stays intact.
* **Storage**: the LoRA adapter is ~5 MB, vs. ~1.1 GB for the full
  model. Multiple adapters (one per fine-tune experiment) cost almost
  nothing to keep around.

This module ships:
  * ``train_etruscan_adapter`` — runs the MLM training loop, writes a
    PEFT-compatible adapter directory.
  * CLI: ``python -m openetruscan.ml.finetune train --output models/etr-lora-v1``.

What this DOESN'T do:
  * Run on the api VM. LoRA still wants a GPU; use Lambda Cloud / AWS /
    Cloud Run GPU jobs / a personal workstation. Cost: ~$1-3 per run.
  * Auto-download the corpus. Pass an inscription file or hit the DB.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger("openetruscan.finetune")


def _require_transformers() -> None:
    """Hard-fail with a clear message when the [transformers] extra is missing."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        import peft  # noqa: F401
        import datasets  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "Fine-tuning requires the [transformers] extra: "
            "pip install -e '.[transformers]'\n"
            f"Missing: {e}"
        ) from e


def _load_etruscan_inscriptions() -> Iterator[str]:
    """Pull canonical Etruscan strings from the corpus DB.

    Mirrors ``rosetta_v1.extract_training_corpus`` but yields raw strings
    rather than tokenised lists — the transformer tokeniser handles
    sub-word splitting itself, so we feed it whole sentences.
    """
    import asyncio

    from sqlalchemy import select

    from openetruscan.db.models import Inscription
    from openetruscan.db.session import get_engine

    async def _pull() -> list[str]:
        _, session_maker = get_engine()
        async with session_maker() as session:
            stmt = select(Inscription.canonical).where(Inscription.language == "etruscan")
            result = await session.execute(stmt)
            return [c for (c,) in result.all() if c]

    yield from asyncio.run(_pull())


def train_etruscan_adapter(
    *,
    output_dir: Path,
    base_model: str = "xlm-roberta-base",
    inscriptions: list[str] | None = None,
    epochs: int = 5,
    learning_rate: float = 5e-4,
    batch_size: int = 16,
    max_length: int = 64,
    lora_r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.1,
    seed: int = 42,
) -> dict[str, Any]:
    """Run masked-LM fine-tuning of ``base_model`` on Etruscan inscriptions
    with a LoRA adapter, writing the result to ``output_dir``.

    ``inscriptions`` may be passed in directly (used by tests with a
    synthetic corpus). When ``None`` we pull from the live DB.

    Returns a metadata dict that mirrors ``rosetta_v1``'s training-run
    metadata: input parameters, corpus size, adapter location.
    """
    _require_transformers()

    import numpy as np
    import torch
    from datasets import Dataset
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForMaskedLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if inscriptions is None:
        inscriptions = list(_load_etruscan_inscriptions())
    if not inscriptions:
        raise ValueError("Refusing to train on an empty corpus.")

    logger.info(
        "Loaded %d inscriptions; tokenising with %s",
        len(inscriptions), base_model,
    )

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForMaskedLM.from_pretrained(base_model)

    # XLM-R has target modules query/key/value/output in each attention
    # block. The standard LoRA config for it touches just q + v (Hu
    # et al's sweet spot for parameter-efficient fine-tuning).
    lora_config = LoraConfig(
        task_type=TaskType.FEATURE_EXTRACTION,
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=["query", "value"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    def _tokenise(batch: dict[str, list[str]]) -> dict[str, list[Any]]:
        return tokenizer(
            batch["text"],
            truncation=True,
            padding="max_length",
            max_length=max_length,
        )

    dataset = Dataset.from_dict({"text": inscriptions})
    dataset = dataset.map(_tokenise, batched=True, remove_columns=["text"])

    collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer, mlm=True, mlm_probability=0.15
    )

    training_args = TrainingArguments(
        output_dir=str(output_dir / "_trainer"),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=learning_rate,
        save_strategy="no",
        logging_steps=10,
        report_to=[],
        seed=seed,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        data_collator=collator,
        train_dataset=dataset,
    )

    logger.info("Starting LoRA fine-tune (%d epochs)", epochs)
    trainer.train()

    # Save just the adapter — the base weights are not modified.
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    metadata: dict[str, Any] = {
        "base_model": base_model,
        "n_inscriptions": len(inscriptions),
        "epochs": epochs,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "max_length": max_length,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "lora_dropout": lora_dropout,
        "seed": seed,
        "torch_version": str(torch.__version__),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "adapter_path": str(output_dir),
    }
    (output_dir / "training_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )
    logger.info("Wrote adapter + metadata to %s", output_dir)
    np.random.seed(seed)  # touch numpy too so any downstream RNGs are deterministic
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_train = sub.add_parser(
        "train",
        help="Run LoRA fine-tuning of XLM-R on the Etruscan corpus",
    )
    p_train.add_argument("--output", required=True, help="Directory to write the adapter into")
    p_train.add_argument("--base-model", default="xlm-roberta-base")
    p_train.add_argument("--epochs", type=int, default=5)
    p_train.add_argument("--learning-rate", type=float, default=5e-4)
    p_train.add_argument("--batch-size", type=int, default=16)
    p_train.add_argument("--max-length", type=int, default=64)
    p_train.add_argument("--lora-r", type=int, default=8)
    p_train.add_argument("--lora-alpha", type=int, default=16)
    p_train.add_argument("--lora-dropout", type=float, default=0.1)
    p_train.add_argument("--seed", type=int, default=42)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.cmd == "train":
        meta = train_etruscan_adapter(
            output_dir=Path(args.output),
            base_model=args.base_model,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            batch_size=args.batch_size,
            max_length=args.max_length,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            seed=args.seed,
        )
        print(json.dumps(meta, indent=2, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
