"""Vertex AI custom-training entrypoint for the Etruscan LoRA adapter.

Self-contained — no openetruscan package import. Runs inside the
prebuilt ``us-docker.pkg.dev/vertex-ai/training/pytorch-gpu.2-2.py310``
image, which ships PyTorch 2.2 + transformers + datasets + accelerate.
PEFT is pip-installed at startup if missing.

Inputs (via Vertex GCS fuse-mount under /gcs/<bucket>):
    --corpus_path  e.g. /gcs/openetruscan-rosetta/corpus/etruscan-cie-v1.jsonl
    --output_dir   e.g. /gcs/openetruscan-rosetta/adapters/etr-lora-v1

Mirrors openetruscan.ml.finetune.train_etruscan_adapter — kept in
lockstep (same LoRA config, same MLM probability, same target_modules).
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path


def _ensure_hf_stack() -> None:
    """The Vertex prebuilt pytorch-gpu image ships PyTorch 2.2 + CUDA but
    NOT the HuggingFace stack. Install what's missing at startup. ~30 s.

    Transformers >=4.47 requires PyTorch >=2.4, which the prebuilt image
    doesn't have. Pin to the last 4.46.x release that still supports
    torch 2.2. Same constraint cascades to peft (0.13+ tracks newer
    transformers) — pin to 0.12.x.

    CRITICAL: the prebuilt image preinstalls torch_xla. HF Trainer
    auto-detects it and routes distributed-training calls (incl. the
    no-op nested_gather on a single GPU) through XLA's CPU rendezvous,
    which makes each training step take *minutes* instead of seconds.
    We force pure CUDA by uninstalling torch_xla at startup.
    """
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torch_xla"],
        check=False,  # ok if not present (idempotent)
    )
    pkgs = []
    for mod, pkg in [
        ("transformers", "transformers>=4.40,<4.47"),
        ("datasets", "datasets>=2.18,<3"),
        ("peft", "peft>=0.10,<0.13"),
        ("accelerate", "accelerate>=0.27,<1.0"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            pkgs.append(pkg)
    if pkgs:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *pkgs]
        )


def _normalise_etruscan_dividers(text: str) -> str:
    """Convert Etruscan word-divider punctuation to spaces.

    Etruscan epigraphy (per Bonfante 2002 §10) uses `:` and `·` as word
    dividers — many inscriptions are written with NO spaces, only colons.
    Feeding such strings to the tokeniser as-is wastes capacity learning
    representations for these dividers (which are pure typography). The
    XLM-R subword tokeniser handles the resulting whitespace cleanly.

    Kept as-is:
      * `.` (period) — intra-word phonological marker, e.g. `ve.i.tule`,
        DOES NOT separate words.
      * `-` (hyphen) — compounding marker, e.g. `velxiti-leθes` joins
        praenomen and gentilicium.
    """
    return text.translate(str.maketrans({":": " ", "·": " "}))


def _read_corpus(path: Path) -> list[str]:
    out: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = (row.get("text") or "").strip()
            if not text:
                continue
            text = _normalise_etruscan_dividers(text)
            # Collapse the runs of whitespace the divider replacement may have
            # introduced (e.g. " : " → "  ").
            text = " ".join(text.split())
            if text:
                out.append(text)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_path", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--base_model", default="xlm-roberta-base")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--learning_rate", type=float, default=5e-4)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--max_length", type=int, default=64)
    parser.add_argument("--lora_r", type=int, default=8)
    parser.add_argument("--lora_alpha", type=int, default=16)
    parser.add_argument("--lora_dropout", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("train_lora")

    _ensure_hf_stack()

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

    log.info("torch=%s cuda_available=%s", torch.__version__, torch.cuda.is_available())
    if torch.cuda.is_available():
        log.info("device=%s", torch.cuda.get_device_name(0))

    corpus_path = Path(args.corpus_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    inscriptions = _read_corpus(corpus_path)
    if not inscriptions:
        raise ValueError(f"Empty corpus at {corpus_path}")
    log.info("Loaded %d inscriptions; tokenising with %s", len(inscriptions), args.base_model)

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForMaskedLM.from_pretrained(args.base_model)

    lora_config = LoraConfig(
        task_type=TaskType.FEATURE_EXTRACTION,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["query", "value"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    def _tokenise(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            padding="max_length",
            max_length=args.max_length,
        )

    dataset = Dataset.from_dict({"text": inscriptions})
    dataset = dataset.map(_tokenise, batched=True, remove_columns=["text"])

    collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer, mlm=True, mlm_probability=0.15
    )

    # /tmp keeps the trainer's intermediate files off the GCS fuse mount —
    # GCS doesn't support fast random writes and the trainer would thrash.
    # disable_tqdm + logging_first_step force the trainer to emit
    # newline-delimited metrics that Cloud Logging actually flushes;
    # without these the carriage-return progress bar is invisible from
    # outside the container.
    training_args = TrainingArguments(
        output_dir="/tmp/_trainer",
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        save_strategy="no",
        logging_steps=5,
        logging_first_step=True,
        disable_tqdm=True,
        report_to=[],
        seed=args.seed,
        fp16=torch.cuda.is_available(),
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        data_collator=collator,
        train_dataset=dataset,
    )
    log.info("Starting LoRA fine-tune (%d epochs)", args.epochs)
    trainer.train()

    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    metadata = {
        "base_model": args.base_model,
        "n_inscriptions": len(inscriptions),
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "batch_size": args.batch_size,
        "max_length": args.max_length,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_dropout": args.lora_dropout,
        "seed": args.seed,
        "torch_version": str(torch.__version__),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "corpus_path": str(corpus_path),
        "output_dir": str(output_dir),
    }
    (output_dir / "training_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )
    log.info("Wrote adapter + metadata to %s", output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
