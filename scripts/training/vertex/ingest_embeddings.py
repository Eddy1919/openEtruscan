"""Stream embedding JSONL files from GCS into ``language_word_embeddings``.

Run from a host that can reach the prod Postgres (e.g. inside the
openetruscan-eu VM via IAP — same path you used for the inscriptions
dump). Reads ``{language, word, vector}`` JSONL, upserts in batches.

Usage (v3 + v4-style coexist after T2.3 lands)::

    # Original v3 ingest path (still works):
    python scripts/training/vertex/ingest_embeddings.py \\
        --gcs-uri gs://openetruscan-rosetta/embeddings/lat-grc-xlmr-v3.jsonl \\
        --gcs-uri gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v3.jsonl \\
        --etr-embedder-tag "xlm-roberta-base+etr-lora-v3" \\
        --revision v3

    # T2.3 v4 ingest path (ett-only file, new embedder partition):
    python scripts/training/vertex/ingest_embeddings.py \\
        --gcs-uri gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl \\
        --embedder xlmr-lora --revision v4

Idempotent on the new 4-column PK: ``ON CONFLICT (language, word,
embedder, embedder_revision) DO UPDATE``. Re-running this script with
identical args replaces just the v4 partition's vectors; LaBSE rows are
untouched.

If you see ``RuntimeError: PRIMARY KEY does not yet include (embedder,
embedder_revision)``, run alembic upgrade head first (migration
``b7e6f7a8b9c1_extend_embedding_pk``).
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
    """Stream a JSONL file from either GCS (``gs://``) or a local path.

    GCS URIs invoke ``gcloud storage cat`` so the 3.3 GB lat-grc file
    never lands on disk. Local file paths (anything that doesn't
    match the ``gs://`` prefix) are read line-by-line via a worker
    thread, so the same script works in environments without
    ``gcloud`` installed — notably the Container-Optimized-OS VM
    that pre-stages JSONLs via a sidecar ``google/cloud-sdk`` docker
    container before the openetruscan-api image processes them.
    """
    if uri.startswith("gs://"):
        proc = await asyncio.create_subprocess_exec(
            "gcloud", "storage", "cat", uri,
            stdout=subprocess.PIPE,
        )
        assert proc.stdout is not None
        try:
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
        finally:
            await proc.wait()
        return

    # Local file path. Reading via run_in_executor keeps the event
    # loop responsive on large files; line-by-line, no in-memory
    # buffering.
    loop = asyncio.get_event_loop()
    f = await loop.run_in_executor(None, lambda: open(uri, encoding="utf-8"))  # noqa: SIM115
    try:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    finally:
        f.close()


def _vector_to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def _assert_extended_pk(session_maker) -> None:
    """Fail fast if the table still has the pre-T2.3 (language, word) PK.

    Without the extended PK, ``ON CONFLICT (language, word, embedder,
    embedder_revision)`` would silently do nothing on existing
    (language, word) hits and the ingest would *partially* succeed —
    new rows go in, conflicting ones get clobbered through a fallback.
    Surface the missing migration loudly instead.
    """
    check = text(
        "SELECT array_length(conkey, 1) "
        "FROM pg_constraint "
        "WHERE conrelid = 'language_word_embeddings'::regclass "
        "  AND contype = 'p'"
    )
    async with session_maker() as session:
        n_pk_cols = (await session.execute(check)).scalar()
    if n_pk_cols != 4:
        raise RuntimeError(
            "PRIMARY KEY does not yet include (embedder, embedder_revision); "
            f"current PK has {n_pk_cols} column(s). Run alembic upgrade head "
            "(migration b7e6f7a8b9c1) before invoking this ingest."
        )


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
        ON CONFLICT (language, word, embedder, embedder_revision) DO UPDATE SET
            vector = EXCLUDED.vector,
            source = EXCLUDED.source
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
        "--embedder", default=None,
        help="Stored as `embedder` for ett rows. T2.3+ canonical flag. "
             "Set to e.g. 'xlmr-lora' for the v4 ingest. If unset, falls "
             "back to --etr-embedder-tag.",
    )
    parser.add_argument(
        "--etr-embedder-tag", default="xlm-roberta-base+etr-lora-v3",
        help="DEPRECATED: pre-T2.3 alias for --embedder. Kept for "
             "backward compat with the v3 ingest invocation. Prefer "
             "--embedder for new work.",
    )
    parser.add_argument("--revision", default="v3")
    parser.add_argument("--chunk-size", type=int, default=500)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # Resolve the ett-side embedder label: --embedder wins, falling back to
    # --etr-embedder-tag for compat. Surface the resolution so audit logs
    # are unambiguous about what label went into the DB.
    etr_embedder_resolved = args.embedder or args.etr_embedder_tag
    logger.info(
        "ett-embedder=%r  base-embedder=%r  revision=%r",
        etr_embedder_resolved, args.base_embedder, args.revision,
    )

    _, session_maker = get_engine()

    # Fail fast if the alembic migration b7e6f7a8b9c1 hasn't run.
    await _assert_extended_pk(session_maker)

    grand_total: dict[str, int] = {}
    for uri in args.gcs_uri:
        logger.info("Streaming %s", uri)
        per_file = await _ingest_one_file(
            session_maker, uri,
            args.base_embedder, etr_embedder_resolved,
            args.revision, args.chunk_size,
        )
        for k, v in per_file.items():
            grand_total[k] = grand_total.get(k, 0) + v

    logger.info("GRAND TOTAL by_lang=%s", grand_total)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
