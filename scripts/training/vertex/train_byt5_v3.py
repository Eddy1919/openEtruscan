"""ByT5-small + LoRA fine-tune for Etruscan lacuna restoration. v3.

Replaces the v2 trainer (scripts/ml/train_byt5_v2.py) which diverged
catastrophically — final eval_loss was nan, intermediate train_loss
hit 6.22e14 at step 680 before the gradient norm went nan at step 688.
Root cause was a combination of an aggressive learning rate (2e-4) and
fp16 underflow on ByT5's byte-level operations.

This run is designed to be numerically stable on the same task with
the same architecture. Specific changes from v2:

  | param                  | v2 (diverged)     | v3 (this script)   |
  |------------------------|-------------------|--------------------|
  | learning_rate          | 2e-4              | 5e-5               |
  | mixed precision        | fp16=True         | bf16=True          |
  | warmup_ratio           | 0 (no warmup)     | 0.1                |
  | max_grad_norm          | implicit (1.0)    | 1.0 (explicit)     |
  | weight_decay           | 0                 | 0.01               |
  | predict_with_generate  | True (slow)       | False              |
  | early-stop on nan      | n/a               | yes (custom hook)  |

The dataset is read from a JSONL exported from the prod inscriptions
table (see scripts/training/vertex/submit_byt5_v3.sh for upload). We
no longer connect to the DB at training time — Vertex's network egress
is firewalled from the prod DB anyway, so the dump-driven path is the
only viable one.

Span-corruption strategy is unchanged from v2: real bracketed lacunae
become the supervised target where present (~281 of 6,567 inscs), and
the remaining ~96 % get synthetic span masking. Both go through the
same `<extra_id_0>` sentinel pattern that ByT5 was pretrained on.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import subprocess
import sys
from pathlib import Path


def _ensure_hf_stack() -> None:
    """Vertex prebuilt pytorch-gpu image ships PyTorch + CUDA; HF stack
    needs to be installed at startup. Same constraints as the prior
    training scripts: transformers>=4.47 requires torch>=2.4, but the
    prebuilt image has torch 2.2; pin to <4.47. peft 0.13+ tracks
    transformers >=4.47, so pin <0.13. Also remove torch_xla so the
    Trainer doesn't route gradient sync through XLA's CPU rendezvous
    (we hit that bug during the LoRA work)."""
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torch_xla"],
        check=False,
    )
    pkgs = []
    for mod, pkg in [
        ("transformers", "transformers>=4.40,<4.47"),
        ("datasets", "datasets>=2.18,<3"),
        ("peft", "peft>=0.10,<0.13"),
        ("accelerate", "accelerate>=0.27,<1.0"),
        ("sklearn", "scikit-learn>=1.3"),
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


def _read_corpus(path: Path, log: logging.Logger) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("raw_text"):
                rows.append(row)
    n_brackets = sum(1 for r in rows if r.get("has_brackets"))
    log.info(
        "Corpus: %d inscs, %d with attested [...] lacunae (%.1f%%)",
        len(rows), n_brackets, 100 * n_brackets / max(1, len(rows)),
    )
    return rows


def _make_span_corruption_sample(text: str, rng: random.Random) -> dict[str, str] | None:
    """Mirror v2's strategy. If the text has bracketed lacunae, mask
    those (real signal). Otherwise create a synthetic 2-4 char span
    mask. Returns None if the text is too short to mask meaningfully."""
    if "[" in text and "]" in text:
        start = text.find("[")
        end = text.find("]", start + 1)
        if end > start:
            inner = text[start + 1 : end].replace(".", "").replace("-", "").strip()
            if not inner:
                inner = "?"
            return {
                "input": text[:start] + "<extra_id_0>" + text[end + 1 :],
                "target": f"<extra_id_0> {inner} <extra_id_1>",
            }
    if len(text) < 8:
        return None
    start = rng.randint(1, len(text) - 5)
    length = rng.randint(2, 4)
    return {
        "input": text[:start] + "<extra_id_0>" + text[start + length :],
        "target": f"<extra_id_0> {text[start : start + length]} <extra_id_1>",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_path", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--base_model", default="google/byt5-small")
    parser.add_argument("--max_input_length", type=int, default=128)
    parser.add_argument("--max_target_length", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--accumulation_steps", type=int, default=16)
    parser.add_argument("--learning_rate", type=float, default=5e-5)
    parser.add_argument("--warmup_ratio", type=float, default=0.1)
    parser.add_argument("--weight_decay", type=float, default=0.01)
    parser.add_argument("--max_grad_norm", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("byt5_v3")

    _ensure_hf_stack()

    import torch
    from datasets import Dataset
    from peft import LoraConfig, TaskType, get_peft_model
    from sklearn.model_selection import train_test_split
    from transformers import (
        AutoModelForSeq2SeqLM,
        AutoTokenizer,
        DataCollatorForSeq2Seq,
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        TrainerCallback,
    )

    log.info("torch=%s cuda=%s", torch.__version__, torch.cuda.is_available())
    if torch.cuda.is_available():
        log.info("device=%s", torch.cuda.get_device_name(0))
        bf16_ok = torch.cuda.is_bf16_supported()
        log.info("bf16 supported on this GPU: %s", bf16_ok)
    else:
        bf16_ok = False

    rng = random.Random(args.seed)

    rows = _read_corpus(Path(args.corpus_path), log)
    samples: list[dict[str, str]] = []
    for r in rows:
        s = _make_span_corruption_sample(r["raw_text"], rng)
        if s is not None and s["target"]:
            samples.append(s)
    log.info("Generated %d span-corruption samples", len(samples))

    train_data, val_data = train_test_split(
        samples, test_size=0.1, random_state=args.seed,
    )
    train_ds = Dataset.from_list(train_data)
    val_ds = Dataset.from_list(val_data)

    log.info("Loading base=%s tokeniser+model", args.base_model)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.base_model)

    def tokenize_fn(batch):
        ins = tokenizer(
            batch["input"],
            max_length=args.max_input_length,
            truncation=True,
            padding="max_length",
        )
        labels = tokenizer(
            text_target=batch["target"],
            max_length=args.max_target_length,
            truncation=True,
            padding="max_length",
        )
        ins["labels"] = labels["input_ids"]
        return ins

    train_ds = train_ds.map(tokenize_fn, batched=True, remove_columns=["input", "target"])
    val_ds = val_ds.map(tokenize_fn, batched=True, remove_columns=["input", "target"])

    # Same LoRA shape as v2 (r=8, alpha=32, q+v target). The hyperparam
    # bug was in the *training* config, not the adapter shape.
    lora_cfg = LoraConfig(
        r=8,
        lora_alpha=32,
        target_modules=["q", "v"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.SEQ_2_SEQ_LM,
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()
    # PEFT + Trainer interaction fix: PEFT marks only LoRA params as
    # `requires_grad=True`. With gradient checkpointing on, the backward
    # pass receives input tensors that don't track grad, and dies with
    # "element 0 of tensors does not require grad and does not have a
    # grad_fn". `enable_input_require_grads()` propagates the requirement
    # up to the encoder inputs so the graph is well-formed. (PEFT docs
    # call this out in the LoRA quickstart.)
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = Seq2SeqTrainingArguments(
        output_dir=str(output_dir / "_trainer"),
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.accumulation_steps,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        warmup_ratio=args.warmup_ratio,
        max_grad_norm=args.max_grad_norm,
        num_train_epochs=args.epochs,
        # T4 (Turing, sm_75) supports fp16 but NOT bf16. We started v3
        # wanting bf16 because fp16 underflow was suspected as a v2
        # contributor — but the v2 actual culprit was lr=2e-4, not fp16.
        # On T4 the only options are fp16 or fp32. fp32 is slower but
        # numerically safest for a 300M-param ByT5-small at batch=2;
        # there's plenty of memory headroom.
        bf16=bf16_ok,
        fp16=False,
        # Gradient checkpointing was triggering the PEFT-input-no-grad
        # error above. ByT5-small + LoRA fits in 16 GB without it; drop.
        gradient_checkpointing=False,
        # Generate-during-eval is slow + not needed for picking a
        # checkpoint; we'll generate offline if needed.
        predict_with_generate=False,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        label_smoothing_factor=0.1,
        logging_steps=10,
        logging_first_step=True,
        disable_tqdm=True,
        report_to=[],
        seed=args.seed,
    )

    class NaNGuard(TrainerCallback):
        """Stop training the moment loss goes non-finite. Saves us from
        burning compute after the run has already broken — which is what
        happened with v2 (it ran for ~80 steps after the loss exploded
        before the gradient finally went nan)."""

        def on_log(self, _args, state, _control, logs=None, **_kw):
            if not logs:
                return
            for k in ("loss", "eval_loss", "grad_norm"):
                v = logs.get(k)
                if v is None:
                    continue
                if isinstance(v, (int, float)) and (math.isnan(v) or math.isinf(v) or v > 1e8):
                    log.error(
                        "Numerical instability: %s=%s at step %d. Aborting.",
                        k, v, state.global_step,
                    )
                    raise RuntimeError(
                        f"Training diverged: {k}={v} at step {state.global_step}"
                    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=DataCollatorForSeq2Seq(tokenizer, model=model),
        callbacks=[NaNGuard()],
    )

    log.info("Starting ByT5 v3 LoRA fine-tune (%d epochs, lr=%g, bf16=%s)",
             args.epochs, args.learning_rate, bf16_ok)
    trainer.train()
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    metadata = {
        "base_model": args.base_model,
        "n_samples": len(samples),
        "n_train": len(train_data),
        "n_val": len(val_data),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "accumulation_steps": args.accumulation_steps,
        "effective_batch": args.batch_size * args.accumulation_steps,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "warmup_ratio": args.warmup_ratio,
        "max_grad_norm": args.max_grad_norm,
        "label_smoothing": 0.1,
        "max_input_length": args.max_input_length,
        "max_target_length": args.max_target_length,
        "lora_r": 8,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "lora_target_modules": ["q", "v"],
        "bf16": bf16_ok,
        "torch_version": str(torch.__version__),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "corpus_path": str(args.corpus_path),
        "output_dir": str(output_dir),
    }
    (output_dir / "training_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )
    log.info("Wrote adapter + metadata to %s", output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
