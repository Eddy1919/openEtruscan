# ByT5 v4 vs v5 — Lacuna Restoration

## Question

Did training ByT5-small + LoRA on the *cleaned* corpus (`canonical_clean`) produce measurably better lacuna restoration than training on the pre-cleaning corpus?

## Dataset

- **100 clean inscriptions** drawn deterministically from the prod DB (`md5(id)` ordering, seed=42).
- Filter: `data_quality = clean ∧ intact_token_ratio = 1.0 ∧ length(canonical_clean) > 20 ∧ multi-word`.
- Per row: one random word is masked with `<extra_id_0>`; the model must restore it.

## Protocol

For each adapter version (`data/models/byt5-v4`, `data/models/byt5-v5`):

1. Load fresh `google/byt5-small` base in fp32.
2. Attach the LoRA adapter via `PeftModel.from_pretrained`.
3. Call `merge_and_unload()` so inference goes through a plain `T5ForConditionalGeneration` forward (avoids PEFT routing edge cases on CPU).
4. For each of the 100 masked rows, generate (`num_beams=1`, greedy, `max_new_tokens=32`).
5. Extract the span between `<extra_id_0>` and `<extra_id_1>` from the raw decode.
6. Compute exact-match accuracy and character-level edit distance vs. the held-out target word.

CPU-runnable in ~3 minutes for 100 examples × 2 models. Tested on CUDA.

## Run

```bash
python research/experiments/byt5_v4_vs_v5/eval.py
```

## Results

To be filled in after the next run.

| Model | Exact-match | CER |
|---|---|---|
| ByT5 v4 (pre-cleaning corpus) | TBD | TBD |
| ByT5 v5 (post-cleaning corpus) | TBD | TBD |
| **Δ (v5 − v4)** | TBD | TBD |
