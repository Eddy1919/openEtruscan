# Vertex AI training & embedding scripts

All Vertex AI custom-job entrypoints + their submission shells live
here. Each `*.py` is a self-contained job script that runs inside a
Vertex AI prebuilt PyTorch container; each `submit_*.sh` is the
gcloud invocation that uploads the script to GCS and launches the
job.

## Why this structure

- Vertex prebuilt images don't have the HuggingFace stack, and the
  `pytorch-gpu.2-2.py310` image's preinstalled `torch_xla` interferes
  with HF Trainer's `nested_gather` (slows training to one step every
  several minutes — see commit history). Every script here applies the
  same bootstrap: `pip uninstall torch_xla` + `pip install
  transformers<4.47, datasets<3, peft<0.13, accelerate<1.0`.
- Output goes to GCS via the auto-mounted `/gcs/` fuse, which the
  scripts use directly (`/gcs/openetruscan-rosetta/...` paths).
- All `submit_*.sh` scripts target project `double-runway-465420-h9`
  region `us-central1` — change via env vars if needed.

## Files

### Embedding (the current-state-of-the-art path)

| File | Purpose |
|---|---|
| [`embed_labse.py`](embed_labse.py) + [`submit_labse_job.sh`](submit_labse_job.sh) | **Primary embedding pipeline.** Builds Latin + Greek vocab from Wikipedia, plus Etruscan vocab from the prod corpus dump. Embeds all three through `sentence-transformers/LaBSE`. Writes one combined JSONL (`labse-v1.jsonl`) per run. This is what the current production embeddings come from. |
| [`ingest_embeddings.py`](ingest_embeddings.py) | Streams a JSONL from GCS into the prod `language_word_embeddings` Postgres table. Idempotent (`ON CONFLICT (language, word) DO UPDATE`). Run from a host that can reach the prod DB (the openetruscan-eu VM via IAP). |

### Earlier-iteration scripts (kept for reproducibility / future work)

These produced the XLM-R-based embeddings that the LaBSE pipeline
superseded. They still work and are kept because:

1. Future research might revisit XLM-R + LoRA with a parallel-data
   contrastive head or a different base encoder.
2. They document the iteration history that's referenced in
   [`research/FINDINGS.md`](../../../research/FINDINGS.md).

| File | Purpose |
|---|---|
| [`train_etruscan_lora.py`](train_etruscan_lora.py) + [`submit_job.sh`](submit_job.sh) | LoRA fine-tune of XLM-R-base on the Etruscan corpus. Output: PEFT adapter directory (`etr-lora-v3` is the latest version; in `gs://openetruscan-rosetta/adapters/`). |
| [`embed_vocab.py`](embed_vocab.py) + [`submit_embed_job.sh`](submit_embed_job.sh) | XLM-R vocabulary embedding for Latin + Greek (Wikipedia top-N). Superseded by `embed_labse.py`. |
| [`embed_etruscan.py`](embed_etruscan.py) + [`submit_etruscan_embed.sh`](submit_etruscan_embed.sh) | XLM-R + LoRA Etruscan vocabulary embedding. Superseded by `embed_labse.py` for the live API path. |
| [`mean_center_embeddings.py`](mean_center_embeddings.py) + [`submit_mean_center.sh`](submit_mean_center.sh) | Per-language mean-subtraction + L2-renormalisation pass. Was a partial fix for XLM-R's anisotropy ("all-but-the-top" lite). LaBSE doesn't suffer from the same anisotropy by training; the script remains in case future encoder choices revive the issue. |

## Typical operations

**Re-embed everything** with the current pipeline:

```bash
# (1) Train Etruscan LoRA on Vertex AI (currently UNUSED in the live path
#     because LaBSE is the encoder of record, but kept for future work)
bash submit_job.sh

# (2) Embed all three languages with LaBSE
bash submit_labse_job.sh

# (3) From the openetruscan-eu VM (IAP tunnel into prod DB):
python ingest_embeddings.py \
  --gcs-uri gs://openetruscan-rosetta/embeddings/labse-v1.jsonl
```

**Run the eval** (no compute, just hits the public API):

```bash
python evals/run_rosetta_eval.py \
  --api-url https://api.openetruscan.com --json
```

## Cost reference (T4 GPU, all CPU-light operations)

| Job | Wall time | $ |
|---|---|---|
| LoRA fine-tune (5 epochs, 6k inscriptions) | ~7 min | ~$0.05 |
| LaBSE embed (200k Wikipedia + 8k Etruscan) | ~12 min | ~$0.07 |
| XLM-R Wikipedia embed | ~12 min | ~$0.07 |
| Mean-centering (lat-grc + ett, two-pass over JSONL) | ~10 min | ~$0.05 |
| Ingest into prod DB | ~30 min | (egress only, ~negligible) |

Across the whole research effort (4× LoRA + 4× embed + 1× mean-center)
total Vertex spend was **~$2**. The *iteration cost* for this kind of
work is in human time, not compute.
