# Recovered GCS buckets — inventory and salvage assessment

Two GCS buckets believed lost with the retired GCP infrastructure survive in
a live project. This is their full inventory, taken **2026-07-17** with
`gcloud storage ls -L` (read-only; sizes and MD5s below are as reported by
GCS). Access is maintainer-only, and neither bucket is a distribution
channel — the public data path remains the Zenodo deposit (see
[README.md](README.md)). Bucket names are already public in this repo's
history; the hosting project id is deliberately recorded nowhere.

| Bucket | Objects | Total size | Object creation time |
|---|---|---|---|
| `gs://openetruscan-rosetta-vai` | 138 (+21 zero-byte directory placeholders) | 16,688,282,426 B (16.69 GB) | all 2026-05-29T20:34Z |
| `gs://openetruscan-data-dvc` | 29 | 365,332,386 B (365.3 MB) | 2026-04-04 |

## `gs://openetruscan-rosetta-vai` — copy of the lost research bucket

Every object was created inside a two-second window on 2026-05-29, so the
bucket is a single bulk copy of (a subset of) `gs://openetruscan-rosetta`,
the research bucket that died with its project (it returns 404 — see
[`research/experiments/lacuna_restoration/README.md`](../research/experiments/lacuna_restoration/README.md)).
The `/gcs/openetruscan-rosetta/...` paths inside the recovered
`training_metadata.json` files show the original bucket was the one mounted
into the Vertex AI training jobs; "vai" was its Vertex-side copy. GCS
creation times therefore date the *copy*, not the artifacts — original
creation dates are known only where a repo document records them (e.g. the
run log in
[`research/notes/reproduce-rosetta-eval-v1.md`](../research/notes/reproduce-rosetta-eval-v1.md)).

### Contents by prefix

| Prefix | What it is | Referenced by | Verification status |
|---|---|---|---|
| `adapters/byt5-lacunae-{v3,v4,v5}/` | ByT5-small LoRA lacuna adapters (final adapter + tokenizer + `training_metadata.json` + two `_trainer/` checkpoints each) | [`research/experiments/byt5_v4_vs_v5/`](../research/experiments/byt5_v4_vs_v5/README.md), which expects the adapters under `data/models/byt5-v4` / `byt5-v5` | Identified by their self-describing `training_metadata.json` (v5: base `google/byt5-small`, 4,382 samples from `corpus/etruscan-prod-rawtext-v2.jsonl`). No independent hash exists. |
| `adapters/etr-lora-{v1,v2,v3,v4}/` | XLM-R-base LoRA adapters — the Etruscan encoder iterations | `research/EXECUTION_WBS.md` (T2.x), `research/FINDINGS.md`; v4 is the warm start for `lora-char-head-v1` ([lacuna experiment](../research/experiments/lacuna_restoration/README.md)) | Identified by `training_metadata.json` (v4: base `xlm-roberta-base`, 5,827 inscriptions, seed 42, corpus `etruscan-prod-rawtext-v3.jsonl`). No independent hash exists. |
| `adapters/labse-attested-v1/` | `metrics.json` **only** — no adapter weights | [`research/results/labse_hardneg_t43_FINDINGS.md`](../research/results/labse_hardneg_t43_FINDINGS.md) | Weights lost — see *Gaps and anomalies*. |
| `anchors/` | `attested.jsonl`, `hard_negatives.jsonl` | committed at [`research/anchors/`](../research/anchors/) | MD5 and size match the committed copies (checked 2026-07-17, this inventory). |
| `code/` | 12 Vertex-side training / embedding / eval scripts | `research/EXECUTION_WBS.md` (embedding and adapter jobs); `train_char_mlm.py` and `train_lora_char_head.py` are the training code for the `char_mlm` module lost in the 2026-07 history rewrite | Not in git; no independent hash. See *Notable items*. |
| `corpus/` | Prod-DB exports: CIE extraction JSONL, `etruscan-prod-rawtext-v{1,2,3}.jsonl`, `etruscan-prod-v2.jsonl`, and a full `prod-inscriptions.sql` dump | `research/v2/README.md` (corpus staging convention); the adapters' `training_metadata.json` name rawtext-v2/v3 as their training corpora | No independent hashes. See *Gaps and anomalies* (v2 ≡ v3; SQL-dump caution). |
| `embeddings/` | Vocabulary-embedding JSONLs behind Rosetta retrieval | [`research/notes/reproduce-rosetta-eval-v1.md`](../research/notes/reproduce-rosetta-eval-v1.md) (pinned manifest), [`docs/REPRODUCE.md`](../docs/REPRODUCE.md) §6, `research/FINDINGS.md` | `labse-v1` and `etr-xlmr-lora-v4` MD5-verified against the historical manifest; `lat-xlmr-lora-v4`'s hash was first recorded *from this copy* (both facts recorded in the note above, 2026-07-17). The `lat-grc-xlmr*` files have no recorded hash anywhere — unverified. |
| `eval/` | `byt5_eval_100.jsonl` (100-row masked eval set) + `byt5_v4_v5_results.json` | [`research/experiments/byt5_v4_vs_v5/`](../research/experiments/byt5_v4_vs_v5/README.md) (whose Results table is still "TBD") | No independent hash. |
| `models/` | `char-mlm-v1` and `lora-char-head-v1` checkpoints + `metadata.json` | [`research/experiments/lacuna_restoration/`](../research/experiments/lacuna_restoration/README.md) README + `eval.py` | See *Notable items* — candidate recovery for the lacuna reproducer. |

### Notable items

**`models/char-mlm-v1/` and `models/lora-char-head-v1/`** — the two
checkpoints the lacuna-restoration experiment declared "unrecoverable, no
archived copy known". Both survive here, in exactly the
checkpoint-plus-`metadata.json` layout the adapted `eval.py` documents.
What the recovered metadata settles, and what it does not:

- `char-mlm-v1/metadata.json` carries the **full ordered 68-symbol
  vocabulary** (with `<BOS>` at index 3), `d_model=256`, 4 layers,
  `best_val_loss=1.5269`, train/val 4,991/555. The ordered id→char mapping
  the experiment README feared was undetectable is therefore on record —
  but the vocabulary confirms the checkpoint was trained BOS-aware, so the
  encode-offset caveat (the adapted script encodes without BOS) is live,
  not hypothetical.
- `lora-char-head-v1/metadata.json` pins encoder `xlm-roberta-base`
  (frozen), warm-start adapter `/gcs/openetruscan-rosetta/adapters/etr-lora-v4`
  (also recovered in this bucket), 63 classes, `best_val_acc=0.4421`.
- The state-dict-compatibility caveat (weights saved from the lost
  `CharTransformerMLM` class vs. the surviving strict-loading `CharMLM`)
  is untested and stands until a load is attempted.

Salvage path: copy to `data/models/` in the layout the experiment README
documents; per that README, no historical metric counts as reproduced until
the vocabulary-alignment and state-dict caveats are cleared.

**`corpus/prod-inscriptions.sql`** — a 61.4 MB full dump of the prod
database. Not inspected in this pass. It must be audited for credentials
and personal data (AGENTS.md rule 9) before it leaves the bucket in any
form; the JSONL exports beside it cover the training-data use cases.

**`code/train_char_mlm.py` and `code/train_lora_char_head.py`** — the
training code whose in-repo module (`openetruscan.ml.char_mlm`) was lost in
the 2026-07 history rewrite. Candidates for re-import into git (Pod B
decision).

### Gaps and anomalies

- `embeddings/etr-xlmr-lora-v3.jsonl` has the same size and MD5 as
  `etr-xlmr-lora-v4.jsonl` — the two objects are copies of one file. Since
  the v4 MD5 independently matches the historical manifest, the object
  *named* v3 is a mislabeled v4 copy; the true v3 vectors survive here only
  in mean-centered form (`etr-xlmr-lora-v3-centered.jsonl`, no recorded
  hash to check against).
- `corpus/etruscan-prod-rawtext-v3.jsonl` ≡ `-v2.jsonl` (same size and
  MD5). Possibly a genuine no-change re-export — v3 is what `etr-lora-v4`
  trained on, v2 what `byt5-lacunae-v5` trained on — but whether a distinct
  v3 ever existed is unknown.
- `adapters/labse-attested-v1/` holds only `metrics.json`.
  `research/results/labse_hardneg_t43_FINDINGS.md` states the adapter is
  "on GCS as audit"; with the original bucket gone, the weights are lost.
- No `byt5-lacunae-v1` or `-v2` copies exist here; only v3–v5 survive.

### Full object listing

Zero-byte directory-placeholder objects are omitted. MD5s are base64, as
GCS reports them.

| Object (under `gs://openetruscan-rosetta-vai/`) | Bytes | MD5 (base64) |
|---|---|---|
| `adapters/byt5-lacunae-v3/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-517/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-517/adapter_config.json` | 635 | `OTvqNWdFVdeif8DiOt//kw==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-517/adapter_model.safetensors` | 2,386,768 | `akiqYCBt+HHQMEQrL+vNBg==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-517/optimizer.pt` | 4,818,810 | `UV32nl25LQof+beUt06rbg==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-517/rng_state.pth` | 14,244 | `cYxbocAFZ28Lk+JjH+jEBw==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-517/scheduler.pt` | 1,064 | `iKhU1AI6nG9SFrJ/u7GaZw==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-517/trainer_state.json` | 10,655 | `7OZHRad33uj61qdQEpv57Q==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-517/training_args.bin` | 5,560 | `HI0ohWaTlYB+7NtIjawbzw==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-645/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-645/adapter_config.json` | 635 | `OTvqNWdFVdeif8DiOt//kw==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-645/adapter_model.safetensors` | 2,386,768 | `Y161lXr6tsdnusNA23aAFw==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-645/optimizer.pt` | 4,818,810 | `BqrnbiXeo3hM1vmA3u+GRg==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-645/rng_state.pth` | 14,244 | `ZZVg3xDg4oRM/juTgqXwng==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-645/scheduler.pt` | 1,064 | `SYqc50HXo89jNu0qym9Pqg==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-645/trainer_state.json` | 13,091 | `IbKLHr3zKdJsKpfwUHOyNQ==` |
| `adapters/byt5-lacunae-v3/_trainer/checkpoint-645/training_args.bin` | 5,560 | `HI0ohWaTlYB+7NtIjawbzw==` |
| `adapters/byt5-lacunae-v3/adapter_config.json` | 635 | `OTvqNWdFVdeif8DiOt//kw==` |
| `adapters/byt5-lacunae-v3/adapter_model.safetensors` | 2,386,768 | `Y161lXr6tsdnusNA23aAFw==` |
| `adapters/byt5-lacunae-v3/added_tokens.json` | 3,018 | `PL4/dQVVYPf5fW+i8hNS0Q==` |
| `adapters/byt5-lacunae-v3/special_tokens_map.json` | 3,090 | `kdJjvzCp9z4kE88naKh3Ig==` |
| `adapters/byt5-lacunae-v3/tokenizer_config.json` | 25,572 | `wUM5jP7zafWx5XntfMP+6g==` |
| `adapters/byt5-lacunae-v3/training_args.bin` | 5,560 | `HI0ohWaTlYB+7NtIjawbzw==` |
| `adapters/byt5-lacunae-v3/training_metadata.json` | 692 | `Fu/BFuS25PibnrhF79gqZg==` |
| `adapters/byt5-lacunae-v4/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-707/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-707/adapter_config.json` | 635 | `Z8sr8aIQpiPnnbW79QUKLw==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-707/adapter_model.safetensors` | 2,386,768 | `FnVahjcNFDAFhS3lXcatcA==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-707/optimizer.pt` | 4,818,810 | `mAlhbePtp3mADUF88RwXNw==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-707/rng_state.pth` | 14,244 | `yh0AlWGexprRemwyzsOqPA==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-707/scheduler.pt` | 1,064 | `L3wV5uSx/zWZj9q6U2QJJA==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-707/trainer_state.json` | 15,407 | `bJaBISugt+PJ62KgBdg+OA==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-707/training_args.bin` | 5,560 | `cUAaeCvAKS4VvPJbfSKTrQ==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-768/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-768/adapter_config.json` | 635 | `Z8sr8aIQpiPnnbW79QUKLw==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-768/adapter_model.safetensors` | 2,386,768 | `AnON/th6kn558kr9tZY+rw==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-768/optimizer.pt` | 4,818,810 | `OtK6r6v9Otj8i1YoElBgng==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-768/rng_state.pth` | 14,244 | `5hngdPF9w6NHYwFAkXMSXw==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-768/scheduler.pt` | 1,064 | `ejMNJ3BhCsYFgmYQPC7tqg==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-768/trainer_state.json` | 16,661 | `BKNfrg/qA4UKh+U1RsY3lw==` |
| `adapters/byt5-lacunae-v4/_trainer/checkpoint-768/training_args.bin` | 5,560 | `cUAaeCvAKS4VvPJbfSKTrQ==` |
| `adapters/byt5-lacunae-v4/adapter_config.json` | 635 | `Z8sr8aIQpiPnnbW79QUKLw==` |
| `adapters/byt5-lacunae-v4/adapter_model.safetensors` | 2,386,768 | `AnON/th6kn558kr9tZY+rw==` |
| `adapters/byt5-lacunae-v4/added_tokens.json` | 3,018 | `PL4/dQVVYPf5fW+i8hNS0Q==` |
| `adapters/byt5-lacunae-v4/special_tokens_map.json` | 3,090 | `kdJjvzCp9z4kE88naKh3Ig==` |
| `adapters/byt5-lacunae-v4/tokenizer_config.json` | 25,572 | `wUM5jP7zafWx5XntfMP+6g==` |
| `adapters/byt5-lacunae-v4/training_args.bin` | 5,560 | `cUAaeCvAKS4VvPJbfSKTrQ==` |
| `adapters/byt5-lacunae-v4/training_metadata.json` | 693 | `PKrRidOwQ8C/I8UBVUelSg==` |
| `adapters/byt5-lacunae-v5/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-673/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-673/adapter_config.json` | 635 | `OTvqNWdFVdeif8DiOt//kw==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-673/adapter_model.safetensors` | 2,386,768 | `UEjI6AwwGvfFWLnqU7OM1Q==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-673/optimizer.pt` | 4,818,810 | `+Cobza/0p3Um69blKALaLg==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-673/rng_state.pth` | 14,244 | `Vc5as72bz/xg2HnwbHj1Ow==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-673/scheduler.pt` | 1,064 | `Q7ah33xMxVDA3y/mjG4rhg==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-673/trainer_state.json` | 14,860 | `xw2RxExhaf/b7gIm7UXDag==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-673/training_args.bin` | 5,560 | `gW/u/I2eE/E7h2jsl91IjQ==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-915/README.md` | 5,091 | `lqR7I6Y1MtV4fc29REdG9w==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-915/adapter_config.json` | 635 | `OTvqNWdFVdeif8DiOt//kw==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-915/adapter_model.safetensors` | 2,386,768 | `+deuMghYIrszhzI2Esq9+A==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-915/optimizer.pt` | 4,818,810 | `VyZGME0xxorK7pHGomAK+g==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-915/rng_state.pth` | 14,244 | `bKR1WepqWLMJnWj0JZpLaw==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-915/scheduler.pt` | 1,064 | `V5oKzJPla+BclycgsyoiXg==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-915/trainer_state.json` | 19,848 | `7ZM+beF6aJBKzv2tq6sEew==` |
| `adapters/byt5-lacunae-v5/_trainer/checkpoint-915/training_args.bin` | 5,560 | `gW/u/I2eE/E7h2jsl91IjQ==` |
| `adapters/byt5-lacunae-v5/adapter_config.json` | 635 | `OTvqNWdFVdeif8DiOt//kw==` |
| `adapters/byt5-lacunae-v5/adapter_model.safetensors` | 2,386,768 | `UEjI6AwwGvfFWLnqU7OM1Q==` |
| `adapters/byt5-lacunae-v5/added_tokens.json` | 3,018 | `PL4/dQVVYPf5fW+i8hNS0Q==` |
| `adapters/byt5-lacunae-v5/special_tokens_map.json` | 3,090 | `kdJjvzCp9z4kE88naKh3Ig==` |
| `adapters/byt5-lacunae-v5/tokenizer_config.json` | 25,572 | `wUM5jP7zafWx5XntfMP+6g==` |
| `adapters/byt5-lacunae-v5/training_args.bin` | 5,560 | `gW/u/I2eE/E7h2jsl91IjQ==` |
| `adapters/byt5-lacunae-v5/training_metadata.json` | 693 | `FnBVPTWgJnYz43tS7GRYkA==` |
| `adapters/etr-lora-v1/README.md` | 5,090 | `aylmLW35cslMleU3yK7AbA==` |
| `adapters/etr-lora-v1/adapter_config.json` | 647 | `MDy5DmuYRayHkXZVrTHJYA==` |
| `adapters/etr-lora-v1/adapter_model.safetensors` | 1,186,472 | `Is0l88ED/9DIizsDUto+Qw==` |
| `adapters/etr-lora-v1/special_tokens_map.json` | 280 | `e0mjE+rSPK1+MfQU/OR/kQ==` |
| `adapters/etr-lora-v1/tokenizer.json` | 17,082,997 | `bSyGa3J20kXe34GAMnLmYQ==` |
| `adapters/etr-lora-v1/tokenizer_config.json` | 1,148 | `Jp6HO0WmLu3qdIMirLkq1g==` |
| `adapters/etr-lora-v1/training_metadata.json` | 413 | `icFhqJoRdx6g5Lt9B++XiQ==` |
| `adapters/etr-lora-v2/README.md` | 5,090 | `aylmLW35cslMleU3yK7AbA==` |
| `adapters/etr-lora-v2/adapter_config.json` | 647 | `KKrhXR9NpATLScJDYqnc9w==` |
| `adapters/etr-lora-v2/adapter_model.safetensors` | 1,186,472 | `fw4qQ4SZG+SCJn6R5nw2gw==` |
| `adapters/etr-lora-v2/special_tokens_map.json` | 280 | `e0mjE+rSPK1+MfQU/OR/kQ==` |
| `adapters/etr-lora-v2/tokenizer.json` | 17,082,997 | `bSyGa3J20kXe34GAMnLmYQ==` |
| `adapters/etr-lora-v2/tokenizer_config.json` | 1,148 | `Jp6HO0WmLu3qdIMirLkq1g==` |
| `adapters/etr-lora-v2/training_metadata.json` | 414 | `BoY4WAKHNn0QnHTOS8U/rw==` |
| `adapters/etr-lora-v3/README.md` | 5,090 | `aylmLW35cslMleU3yK7AbA==` |
| `adapters/etr-lora-v3/adapter_config.json` | 647 | `KKrhXR9NpATLScJDYqnc9w==` |
| `adapters/etr-lora-v3/adapter_model.safetensors` | 1,186,472 | `HYy15Tjyk1BI7pYLz3w2iw==` |
| `adapters/etr-lora-v3/special_tokens_map.json` | 280 | `e0mjE+rSPK1+MfQU/OR/kQ==` |
| `adapters/etr-lora-v3/tokenizer.json` | 17,082,997 | `bSyGa3J20kXe34GAMnLmYQ==` |
| `adapters/etr-lora-v3/tokenizer_config.json` | 1,148 | `Jp6HO0WmLu3qdIMirLkq1g==` |
| `adapters/etr-lora-v3/training_metadata.json` | 414 | `2/7w6TRiYVykfLKimi2Z9Q==` |
| `adapters/etr-lora-v4/README.md` | 5,090 | `aylmLW35cslMleU3yK7AbA==` |
| `adapters/etr-lora-v4/adapter_config.json` | 647 | `MDy5DmuYRayHkXZVrTHJYA==` |
| `adapters/etr-lora-v4/adapter_model.safetensors` | 1,186,472 | `NovIAUQ5xXQlJ6jC7dcbnA==` |
| `adapters/etr-lora-v4/special_tokens_map.json` | 280 | `e0mjE+rSPK1+MfQU/OR/kQ==` |
| `adapters/etr-lora-v4/tokenizer.json` | 17,082,997 | `bSyGa3J20kXe34GAMnLmYQ==` |
| `adapters/etr-lora-v4/tokenizer_config.json` | 1,148 | `Jp6HO0WmLu3qdIMirLkq1g==` |
| `adapters/etr-lora-v4/training_metadata.json` | 422 | `pGvqXD3rKuTMoqS/+7qsGA==` |
| `adapters/labse-attested-v1/metrics.json` | 22,533 | `Pv8GrH2vpv2fV1Pjc2fxQA==` |
| `anchors/attested.jsonl` | 8,713 | `LQTrzeXUR0gAl0UzMM+bbg==` |
| `anchors/hard_negatives.jsonl` | 15,042 | `kk0Tg/JJio0q8hOlL+ybTg==` |
| `code/embed_etruscan.py` | 7,914 | `gFMHKsqtud8qfkzr3ww2Rg==` |
| `code/embed_labse.py` | 7,926 | `5p2rMIi/XO/r3tgvNiJz3A==` |
| `code/embed_lat_grc.py` | 6,903 | `K1Qfc5K8Isb/c4aGaeD/xw==` |
| `code/embed_lat_xlmr_v4.py` | 7,503 | `WrFeL3laNAjYbNjiwGj3Kg==` |
| `code/embed_vocab.py` | 9,110 | `IwRoj9LBBmUnIcKlOxYxqg==` |
| `code/eval_byt5_v4_v5.py` | 5,612 | `z7nIb69h8fDrN3DGMYwNAw==` |
| `code/finetune_labse_hardneg.py` | 23,195 | `9RYD6GkhjcVmzj5O7G64Ig==` |
| `code/mean_center_embeddings.py` | 6,701 | `kXtACLvQN0ntmNzSDH6e2Q==` |
| `code/train_byt5_v3.py` | 13,172 | `wiM/JLnoWowvkWU2SDxK2Q==` |
| `code/train_char_mlm.py` | 12,686 | `8/xbGq4F1xMv1KnMYLIyaQ==` |
| `code/train_etruscan_lora.py` | 8,288 | `JU/xC2ILP4S4oAT4iBbqdg==` |
| `code/train_lora_char_head.py` | 14,563 | `krRczWCVI0o04+xRkBrerA==` |
| `corpus/etruscan-cie-v1.jsonl` | 156,372 | `e6szW9pIeeNk9Ehd4NzpKw==` |
| `corpus/etruscan-prod-rawtext-v1.jsonl` | 711,446 | `+h2jJsNUar2F4CjLya8LTA==` |
| `corpus/etruscan-prod-rawtext-v2.jsonl` | 1,350,570 | `C8WSwMaMtLCuMRBE2irkmw==` |
| `corpus/etruscan-prod-rawtext-v3.jsonl` | 1,350,570 | `C8WSwMaMtLCuMRBE2irkmw==` |
| `corpus/etruscan-prod-v2.jsonl` | 280,829 | `4HmZhElkrmxmUNiT3Ei8xg==` |
| `corpus/prod-inscriptions.sql` | 61,392,049 | `XTBNAAot43JxE+nUjmQzMg==` |
| `embeddings/etr-xlmr-lora-v3-centered.jsonl` | 152,721,844 | `5UwSXE9IM4z5echqPen7SA==` |
| `embeddings/etr-xlmr-lora-v3.jsonl` | 158,234,414 | identical to `etr-xlmr-lora-v4.jsonl` (same size and MD5) — see anomalies |
| `embeddings/etr-xlmr-lora-v4.jsonl` | 158,234,414 | recorded in [reproduce-rosetta-eval-v1](../research/notes/reproduce-rosetta-eval-v1.md) — matches |
| `embeddings/labse-v1.jsonl` | 3,566,650,280 | recorded in [reproduce-rosetta-eval-v1](../research/notes/reproduce-rosetta-eval-v1.md) — matches |
| `embeddings/lat-grc-xlmr-v2.jsonl` | 3,555,298,235 | `yD9MG5fXiyDFHw9/ZnlYkA==` |
| `embeddings/lat-grc-xlmr-v3-centered.jsonl` | 3,428,617,918 | `snL+Zm0T2yIU4I9zYgfF3w==` |
| `embeddings/lat-grc-xlmr-v3.jsonl` | 3,555,661,693 | `ffteLeH743R5l4lXZPjy6Q==` |
| `embeddings/lat-grc-xlmr.jsonl` | 126,959,493 | `XGTnFUu0GRpGhRR0GxxSbA==` |
| `embeddings/lat-xlmr-lora-v4.jsonl` | 1,776,864,468 | recorded in [reproduce-rosetta-eval-v1](../research/notes/reproduce-rosetta-eval-v1.md) (taken from this copy) |
| `eval/byt5_eval_100.jsonl` | 16,380 | `0ApniBvP/+Kg0ybajp1jPg==` |
| `eval/byt5_v4_v5_results.json` | 31,861 | `Wn9sA+Lk/8GY0alDqwcyLQ==` |
| `models/char-mlm-v1/char_mlm_best.pt` | 8,990,230 | `IPHmxnpLOj4MTrEXDiydYg==` |
| `models/char-mlm-v1/char_mlm_final.pt` | 8,990,290 | `AJu2BqXHUX1t237wv8xbAA==` |
| `models/char-mlm-v1/metadata.json` | 986 | `+2KuQIpQFg+jZ0acuLeHtw==` |
| `models/lora-char-head-v1/char_head_best.pt` | 857,102 | `+GSbSf9eELRClbCCsQ6VPg==` |
| `models/lora-char-head-v1/char_head_final.pt` | 857,112 | `sLRJ4yaJNN5+UuHWxfQ+lg==` |
| `models/lora-char-head-v1/metadata.json` | 976 | `5OpPPdBGGx0H07fCA1MgHQ==` |

## `gs://openetruscan-data-dvc` — orphaned DVC store, salvage by hash only

29 objects created 2026-04-04 under `files/md5/<aa>/<rest>`, where the
object path is the hex MD5 of the content (verified against the
GCS-reported MD5 for all 29). No `.dvc` pointer files survive in the tree
(the DVC config was removed 2026-07-17 and git history was squashed), so
this cannot be used as a DVC remote — treat it as content-addressed
salvage.

The store does, however, contain its own index: the DVC directory manifest
`files/md5/c1/25c84364630881b2f40d3b061ce717.dir` (a JSON list of
`{md5, relpath}` pairs) maps 31 relpaths onto 28 unique blobs (three small
JSONs appear under two names each), and those 28 blobs plus the manifest
itself account for **every object in the bucket**. The store is a complete
DVC snapshot of the pre-squash `data/` directory as of 2026-04-04. To
salvage a file, look up its relpath below and fetch
`files/md5/<first two hex chars>/<remaining 30>`.

MD5 is the only checksum DVC stored — adequate for identification, weak as
an integrity guarantee; no SHA-256 of these files exists anywhere.

### Salvage map (from the `.dir` manifest, sizes from GCS)

| Relpath in the 2026-04-04 `data/` snapshot | Content MD5 (hex = blob path) | Bytes |
|---|---|---|
| `Dockerfile.db` | `e751b37c127cd35ab6afe98c56830672` | 501 |
| `cie/CIE-II.2.2_Indices-et-Tabulae.pdf` | `26bb8b504ebdecee6f03902faf993546` | 51,578,086 |
| `cie/CIE-I_Additamentum.pdf` | `67df03c7258a1b5764209f969f4b3a3e` | 29,600,354 |
| `cie/CIE-I_Clusium-cum-agro-Clusino-tit.-1743-3306.pdf` | `bcf681f3dcf0a635a933a7656e3a862e` | 121,200,895 |
| `cie/CIE-I_Clusium-cum-agro-Clusino-tit.-475-1742.pdf` | `fbf3c00b4c36fbba030861eb4af94dde` | 13,299,712 |
| `cie/CIE-I_Introduzione.pdf` | `4106c807cf93ea97ca99953a87d1ea6f` | 10,516,752 |
| `cie/CIE-I_Perusia-tit.-3307-4612.pdf` | `2fda7613ef69840aa4ffd509136a2edc` | 77,852,672 |
| `cie/CIE-I_tit.1_474.pdf` | `bc54b9644c8381cfc8ff806189850a73` | 55,698,253 |
| `cie/download_cie.sh` | `aa1e2504bdd992c8812139380d8c8eed` | 1,115 |
| `cie/sample_extraction.json` | `3f973282db3083832becee0b1b765724` | 23,158 |
| `codex_texts.yaml` | `9fd3e2f3328c54736de5e04f8d409fbe` | 14,178 |
| `contributions/.gitkeep` | `d41d8cd98f00b204e9800998ecf8427e` | 0 |
| `contributions/burman_concordance.csv` | `3f62f212a4ade548c672a2e3e7b95ae8` | 1,080,727 |
| `eagle_mapping.yaml` | `b3a8eecd510904f06d24d2c02e72f4d3` | 915 |
| `models/README.md` | `e9710b76d07d1afe5947f5aebe62fefd` | 3,311 |
| `models/cnn.json` | `9d754277388f01a3d2ead2574f065740` | 2,421 |
| `models/cnn.onnx` | `989186d6bb89cb64bc28c16faaf845d4` | 123,767 |
| `models/cnn_config.json` | `5f49d3325dc1b7c5551c858bca685861` | 2,104 |
| `models/cnn_meta.json` | `9d754277388f01a3d2ead2574f065740` | 2,421 |
| `models/cnn_weights.pt` | `860e6f21a9278e263f1f05120d7bfa17` | 125,957 |
| `models/config.json` | `5f49d3325dc1b7c5551c858bca685861` | 2,104 |
| `models/metrics.json` | `ee6f70a4278a5f1eaf8001528c020f33` | 2,147 |
| `models/transformer.json` | `8b7ccb24b99e3a722898f22879bd1092` | 2,429 |
| `models/transformer.onnx` | `32364312c5b96f14fa320691896aac48` | 1,273,966 |
| `models/transformer_config.json` | `3fcce3d4daf972829a294d938e01cb2d` | 2,112 |
| `models/transformer_meta.json` | `8b7ccb24b99e3a722898f22879bd1092` | 2,429 |
| `models/transformer_weights.pt` | `9a0151171031086bcc44a88924011d9c` | 1,209,895 |
| `pleiades_mapping.yaml` | `69fb92a4d55851c7ebb35f37bbd7c50c` | 1,472 |
| `rdf/corpus.ttl` | `85a644ce1f306e744fab0739d82ee157` | 1,658,360 |
| `rejected_inscriptions.csv` | `2f65021248672385b6806e5f9783d5e9` | 51,280 |
| `trismegistos_mapping.yaml` | `b6a6a3271082f6b8c8e89f88d3326e6b` | 3,220 |

Notable in the snapshot:

- **`cie/*.pdf`** — the seven CIE source scans of the
  [README.md](README.md) layout table (six Vol. I fascicles + the Vol. II
  indices), the only known surviving copies besides studietruschi.org
  itself. `cie/download_cie.sh` records the exact source URLs
  (`studietruschi.org/wp-content/uploads/...`), which the provenance
  manifest in [README.md](README.md) now cites.
- **`models/`** — the v1 character-CNN / micro-transformer inscription
  classifiers (ONNX + PyTorch weights + metrics), with a complete HF-style
  model card (`models/README.md` in the snapshot, MIT). Superseded by the
  v2 classifier work but part of the project's audit trail.
- The rest is pre-squash working state: `rdf/corpus.ttl`, the
  Trismegistos/EAGLE/Pleiades mapping YAMLs, `rejected_inscriptions.csv`,
  `contributions/burman_concordance.csv`, `Dockerfile.db`.

## Proposed citable Zenodo copies

Priority order. Items 1–4 are project-produced (trained or exported by this
project), so publication is the project's call; the corpus deposit's
CC-BY-4.0 is the default unless the lead decides otherwise.

1. **rosetta-eval-v1 embeddings** — `embeddings/labse-v1.jsonl`,
   `etr-xlmr-lora-v4.jsonl`, `lat-xlmr-lora-v4.jsonl` (~5.5 GB): exactly
   the artifacts `docs/REPRODUCE.md` §6 flags as not publicly reproducible;
   a deposit unblocks the historical-column re-run for anyone.
2. **Lacuna-reproducer checkpoints** — `models/char-mlm-v1/`,
   `models/lora-char-head-v1/`, plus their dependency
   `adapters/etr-lora-v4/` (~38 MB): makes
   `research/experiments/lacuna_restoration/` re-runnable.
3. **ByT5 v4-vs-v5 kit** — `adapters/byt5-lacunae-v4/`, `-v5/`,
   `eval/byt5_eval_100.jsonl`, `eval/byt5_v4_v5_results.json` (~34 MB):
   completes the documented negative-result experiment.
4. **Training-corpus exports** — `corpus/etruscan-cie-v1.jsonl`,
   `etruscan-prod-rawtext-v{1,2,3}.jsonl`, `etruscan-prod-v2.jsonl`
   (~3.9 MB): the corpora the adapters' training metadata points at.
   Derived from Larth (CC-BY-4.0) + CIE (public domain); needs an
   attribution check before deposit.

Not proposed:

- `corpus/prod-inscriptions.sql` — not before the credentials/PII audit
  above, and probably not at all (the JSONL exports supersede it).
- The CIE PDFs (DVC store) — public-domain text, but studietruschi.org's
  terms for its scans were never recorded and the files are re-downloadable
  from the source; no redistribution until licensing is cleared
  (AGENTS.md rule 6).
- `embeddings/lat-grc-xlmr*` (~10.7 GB) — no committed result depends on
  them and they carry no recorded hashes; archive only if the full
  iteration history is wanted.
- `code/*.py` — belongs in git, not Zenodo (see *Notable items*).
