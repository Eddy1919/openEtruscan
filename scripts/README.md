# scripts

Operational and data scripts, grouped by concern. Each subdirectory has
its own README where the contents warrant one.

| Directory | Contents |
|---|---|
| [`data_pipeline/`](data_pipeline/README.md) | Reusable corpus pipeline: CIE ingestion, findspot geocoding, seeding, Pleiades linking, migrations, exports. |
| `ml/` | Model training, embedding generation, classification, and dataset-enrichment scripts. |
| `ops/` | Deploy, geocoding, DB/extension setup, HF sync, and security-check operational scripts. |
| `research/` | Anchor extraction, corpus mining, and Recogito import/export for the research workflow. |
| [`training/`](training/vertex/README.md) | Vertex AI training and embedding job entrypoints plus their submission shells. |
| `hub/` | Hugging Face Hub push scripts for trained adapters. |
| [`attic/`](attic/README.md) | One-off corpus-surgery scripts that already ran; retained as the build audit trail, not maintained. |

`docs/` holds a generated OpenAPI snapshot; `add_docs.py` is a loose
top-level helper.
