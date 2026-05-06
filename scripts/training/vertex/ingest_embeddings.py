"""Stream embedding JSONL files from GCS into ``language_word_embeddings``.

Run from a host that can reach the prod Postgres (e.g. inside the
openetruscan-eu VM via IAP — same path you used for the inscriptions
dump). Reads ``{language, word, vector}`` JSONL, upserts in batches.

Usage::

    python scripts/training/vertex/ingest_embeddings.py \\
        --gcs-uri gs://openetruscan-rosetta/embeddings/lat-grc-xlmr-v3.jsonl \\
        --gcs-uri gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v3.jsonl \\
        --etr-embedder-tag "xlm-roberta-base+etr-lora-v3"

Idempotent: ``ON CONFLICT (language, word) DO UPDATE`` so re-runs replace
prior vectors. Accepts both ``language`` and ``lang`` JSON keys for
compat with the older v2 file format.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import subprocess
import sys
from collections.abc import AsyncIterator

from sqlalchemy import text

from openetruscan.db.session import get_engine

logger = logging.getLogger("ingest_embeddings")


async def _stream_gcs_jsonl(uri: str) -> AsyncIterator[dict]:
    """Stream a JSONL file from GCS via ``gcloud storage cat``. Avoids
    landing the 3.3 GB lat-grc file on disk."""
    proc = await asyncio.create_subprocess_exec(
        "gcloud", "storage", "cat", uri,
        stdout=subprocess.PIPE,
    )
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        line = line.decode("utf-8").strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue
    await proc.wait()


def _vector_to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def _ingest_one_file(
    session_maker,
    uri: str,
    base_embedder: str,
    etr_embedder: str,
    revision: str,
    chunk_size: int,
) -> dict[str, int]:
    """Stream + batch-upsert one JSONL file."""
    insert_query = text(
        """
        INSERT INTO language_word_embeddings
            (language, word, vector, source, embedder, embedder_revision)
        VALUES
            (:language, :word, :vector, :source, :embedder, :embedder_revision)
        ON CONFLICT (language, word) DO UPDATE SET
            vector = EXCLUDED.vector,
            source = EXCLUDED.source,
            embedder = EXCLUDED.embedder,
            embedder_revision = EXCLUDED.embedder_revision
        """
    )

    by_lang: dict[str, int] = {}
    chunk: list[dict] = []
    total = 0

    async with session_maker() as session:
        async for row in _stream_gcs_jsonl(uri):
            lang = row.get("language") or row.get("lang")
            word = row.get("word")
            vec = row.get("vector")
            if not (lang and word and isinstance(vec, list)):
                continue
            embedder = etr_embedder if lang == "ett" else base_embedder
            chunk.append({
                "language": lang,
                "word": word.lower(),
                "vector": _vector_to_pgvector(vec),
                "source": embedder,
                "embedder": embedder,
                "embedder_revision": revision,
            })
            by_lang[lang] = by_lang.get(lang, 0) + 1
            total += 1
            if len(chunk) >= chunk_size:
                await session.execute(insert_query, chunk)
                await session.commit()
                chunk.clear()
                if total % 10_000 == 0:
                    logger.info("  %s: inserted %d (by_lang=%s)", uri, total, by_lang)
        if chunk:
            await session.execute(insert_query, chunk)
            await session.commit()

    logger.info("DONE %s: %d rows; by_lang=%s", uri, total, by_lang)
    return by_lang


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gcs-uri", action="append", required=True,
        help="May be repeated; one or more gs://... JSONL files",
    )
    parser.add_argument(
        "--base-embedder", default="xlm-roberta-base",
        help="Stored as `embedder` for lat/grc rows (vanilla XLM-R)",
    )
    parser.add_argument(
        "--etr-embedder-tag", default="xlm-roberta-base+etr-lora-v3",
        help="Stored as `embedder` for ett rows so the eval can tell "
             "adapter-vs-base apart in the same table",
    )
    parser.add_argument("--revision", default="v3")
    parser.add_argument("--chunk-size", type=int, default=500)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    _, session_maker = get_engine()

    grand_total: dict[str, int] = {}
    for uri in args.gcs_uri:
        logger.info("Streaming %s", uri)
        per_file = await _ingest_one_file(
            session_maker, uri,
            args.base_embedder, args.etr_embedder_tag,
            args.revision, args.chunk_size,
        )
        for k, v in per_file.items():
            grand_total[k] = grand_total.get(k, 0) + v

    logger.info("GRAND TOTAL by_lang=%s", grand_total)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
