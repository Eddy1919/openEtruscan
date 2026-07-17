# scripts

Operational and data scripts, grouped by concern. Each subdirectory has
its own README where the contents warrant one.

| Directory | Contents |
|---|---|
| [`data_pipeline/`](data_pipeline/README.md) | Reusable corpus pipeline: CIE ingestion, findspot geocoding, seeding, Pleiades linking, exports. |
| `ml/` | Neural-classifier training and Gemini embedding generation. |
| `ops/` | Deploy, geocoding, DB/extension setup, HF sync, and security-check operational scripts. |
| `research/` | Anchor extraction, corpus mining, and Recogito import/export for the research workflow. |
| [`training/`](training/vertex/README.md) | Vertex AI training and embedding job entrypoints plus their submission shells. |
| `hub/` | Hugging Face Hub push scripts for trained adapters. |
| [`attic/`](attic/README.md) | One-off scripts that already ran (corpus surgery, enrichment, training, infra migrations); retained as the build audit trail, not maintained. |
