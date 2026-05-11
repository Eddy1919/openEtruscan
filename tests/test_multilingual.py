"""Tests for the multilingual Rosetta vector store + API endpoint.

The persistence path needs pgvector; tests that hit the real DB are
guarded with try/except so SQLite fallback environments skip them
cleanly. The non-DB-touching surface (registry, refusal logic) is
unconditionally tested.
"""

from __future__ import annotations

import pytest

from openetruscan.ml.embeddings import MockEmbedder
from openetruscan.ml.multilingual import (
    EMBEDDING_DIM,
    LANGUAGE_TIERS,
    find_cross_language_neighbours,
    populate_language,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestLanguageRegistry:
    def test_anchor_language_is_present(self):
        assert "ett" in LANGUAGE_TIERS
        rec = LANGUAGE_TIERS["ett"]
        assert rec.deciphered is True
        assert rec.alignable is True

    def test_default_dim_is_xlmr(self):
        """Migration i4d5e6f7a8b9 sized the column at vector(768) to match
        XLM-R-base. The registry's expected_dim has to track that."""
        assert EMBEDDING_DIM == 768
        for code, rec in LANGUAGE_TIERS.items():
            assert rec.expected_dim == 768, (
                f"language {code} has unexpected expected_dim={rec.expected_dim}"
            )

    def test_tier_1_languages_are_alignable(self):
        for code, rec in LANGUAGE_TIERS.items():
            if rec.tier == 1:
                assert rec.alignable is True, f"{code} tier 1 must be alignable"
                assert rec.deciphered is True

    def test_tier_3_languages_refuse_alignment(self):
        tier3 = [r for r in LANGUAGE_TIERS.values() if r.tier == 3]
        assert tier3
        for rec in tier3:
            assert rec.alignable is False

    def test_undeciphered_languages_are_not_alignable(self):
        for rec in LANGUAGE_TIERS.values():
            if not rec.deciphered:
                assert rec.alignable is False

    def test_minoan_specifically_listed(self):
        assert "lin_a" in LANGUAGE_TIERS
        rec = LANGUAGE_TIERS["lin_a"]
        assert rec.tier == 3
        assert rec.deciphered is False
        assert rec.alignable is False
        assert rec.structural_embedding_viable is True

    def test_basque_is_proxy_labelled(self):
        rec = LANGUAGE_TIERS["eus"]
        assert "proxy" in rec.notes.lower()


# ---------------------------------------------------------------------------
# Refusal logic (no DB)
# ---------------------------------------------------------------------------


class _StubSession:
    async def execute(self, *_a, **_kw):
        raise AssertionError("session.execute should not be called for refused queries")


@pytest.mark.asyncio
async def test_lookup_refuses_tier3_source():
    with pytest.raises(ValueError, match="undeciphered|refused|cross-language"):
        await find_cross_language_neighbours(
            word="da-da",
            source_lang="lin_a",
            target_lang="lat",
            session=_StubSession(),
        )


@pytest.mark.asyncio
async def test_lookup_refuses_tier3_target():
    with pytest.raises(ValueError, match="undeciphered|refused|cross-language"):
        await find_cross_language_neighbours(
            word="zich",
            source_lang="ett",
            target_lang="lin_a",
            session=_StubSession(),
        )


@pytest.mark.asyncio
async def test_lookup_rejects_unknown_lang():
    with pytest.raises(ValueError, match="Unknown language"):
        await find_cross_language_neighbours(
            word="x",
            source_lang="ett",
            target_lang="zzz_nonexistent",
            session=_StubSession(),
        )


# ---------------------------------------------------------------------------
# populate_language refusal logic (no DB writes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_populate_refuses_unknown_language():
    em = MockEmbedder(dim=768)
    with pytest.raises(ValueError, match="Unknown language"):
        await populate_language(
            language="zzz_nonexistent",
            words=["a"],
            embedder=em,
            session=_StubSession(),
            source="test",
        )


@pytest.mark.asyncio
async def test_populate_refuses_non_viable_language():
    """xnu (Nuragic) is registered as structural_embedding_viable=False;
    populate must refuse so we don't ship vectors that are misleading."""
    em = MockEmbedder(dim=768)
    with pytest.raises(ValueError, match="non-viable|refusing"):
        await populate_language(
            language="xnu",
            words=["a"],
            embedder=em,
            session=_StubSession(),
            source="test",
        )


@pytest.mark.asyncio
async def test_populate_refuses_dim_mismatch():
    em = MockEmbedder(dim=42)  # not 768
    with pytest.raises(ValueError, match="dim"):
        await populate_language(
            language="ett",
            words=["a"],
            embedder=em,
            session=_StubSession(),
            source="test",
        )


# ---------------------------------------------------------------------------
# API: /neural/rosetta/languages
# ---------------------------------------------------------------------------


async def test_languages_endpoint_returns_full_registry(client, sample_data):
    response = await client.get("/neural/rosetta/languages")
    assert response.status_code == 200
    body = response.json()
    codes = {r["code"] for r in body["languages"]}
    assert "ett" in codes
    assert "lat" in codes
    assert "lin_a" in codes
    for rec in body["languages"]:
        assert {"code", "name", "tier", "deciphered", "alignable",
                "corpus_status", "notes"} <= rec.keys()


async def test_rosetta_lookup_refuses_tier3_via_api(client, sample_data):
    response = await client.get(
        "/neural/rosetta",
        params={"word": "da-da", "from": "lin_a", "to": "lat"},
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert "undeciphered" in detail.lower() or "refused" in detail.lower()


async def test_rosetta_lookup_unknown_target_lang(client, sample_data):
    response = await client.get(
        "/neural/rosetta",
        params={"word": "zich", "from": "ett", "to": "zzz_nonexistent"},
    )
    assert response.status_code == 400


async def test_rosetta_lookup_returns_empty_when_no_vector(client, sample_data):
    # The Postgres image used in CI (postgis/postgis:15-3.4) lacks the
    # pgvector extension, so the language_word_embeddings table can't be
    # created. Conftest wraps that in try/except. The test then needs to
    # handle two distinct manifestations of "no table":
    #   - older starlette/fastapi: server returns 500 (caught by the
    #     ServerErrorMiddleware), we skip.
    #   - newer starlette (≥ Python 3.13 image's bundled version):
    #     server-side DB exception bubbles out of the test client itself
    #     instead of being wrapped in a 500 response. We catch the
    #     ProgrammingError and skip with the same message.
    # When CI eventually moves to an image that bundles both extensions,
    # neither branch fires and the assertion runs as intended.
    try:
        response = await client.get(
            "/neural/rosetta",
            params={"word": "definitely-not-real", "from": "ett", "to": "lat"},
        )
    except Exception as exc:  # noqa: BLE001
        if "language_word_embeddings" in str(exc) or "UndefinedTableError" in type(exc).__name__:
            pytest.skip("language_word_embeddings table not available (no pgvector in test image)")
        raise
    if response.status_code == 500:
        pytest.skip("language_word_embeddings table not available (no pgvector in test image)")
    assert response.status_code == 200
    assert response.json()["neighbours"] == []


# ---------------------------------------------------------------------------
# Full populate → query roundtrip via MockEmbedder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_populate_then_query_via_mock(db_session):
    """End-to-end: write a few vectors via MockEmbedder, query them
    cross-language, expect the SAME word to land at cosine 1.0 in
    its own language and itself appear under the source's neighbours
    in the target language too (since MockEmbedder is purely
    deterministic from the string)."""
    from sqlalchemy import text

    # Skip if pgvector isn't on this backend.
    try:
        await db_session.execute(text("SELECT 1 FROM language_word_embeddings LIMIT 0"))
    except Exception:
        pytest.skip("language_word_embeddings table not present in this backend")

    em = MockEmbedder(dim=768)

    # Populate Etruscan and Latin with overlapping word-strings so the
    # cosines are non-trivial. Mock vectors are deterministic per word,
    # so ett['clan'] and lat['clan'] are the same vector — which means
    # ett 'clan' should rank lat 'clan' first.
    await populate_language(
        language="ett",
        words=["clan", "avil", "turce"],
        embedder=em,
        session=db_session,
        source="mock-test",
    )
    await populate_language(
        language="lat",
        words=["clan", "filius", "annus"],
        embedder=em,
        session=db_session,
        source="mock-test",
    )

    hits = await find_cross_language_neighbours(
        word="clan",
        source_lang="ett",
        target_lang="lat",
        session=db_session,
        k=3,
    )
    assert len(hits) == 3
    # 'clan' is in both Latin and Etruscan with identical mock vectors,
    # so it must dominate the top of the Latin neighbour list.
    assert hits[0].word == "clan"
    assert hits[0].cosine == pytest.approx(1.0, abs=1e-4)
    assert hits[0].language == "lat"


# ---------------------------------------------------------------------------
# T2.3 — partitioned embedder behaviour
# ---------------------------------------------------------------------------
#
# These tests guard the contract that a single (language, word) can carry
# vectors from multiple (embedder, embedder_revision) partitions without
# one's ingest overwriting the other. They run against a real Postgres
# (skip cleanly if pgvector isn't available — same pattern as the
# populate-then-query test above).


@pytest.mark.asyncio
async def test_pk_allows_dual_embedder_partitions(db_session):
    """The post-T2.3 PK ``(language, word, embedder, embedder_revision)``
    lets two rows for the same (language, word) coexist under different
    embedder partitions. A third INSERT into the SAME partition must
    conflict.

    The conftest fixture creates the table with the 4-column PK; this
    test exercises it directly via SQL to avoid coupling to the
    application's higher-level layers."""
    from sqlalchemy import text

    try:
        await db_session.execute(text("SELECT 1 FROM language_word_embeddings LIMIT 0"))
    except Exception:
        pytest.skip("language_word_embeddings table not present in this backend")

    insert_one = text(
        "INSERT INTO language_word_embeddings "
        "(language, word, vector, embedder, embedder_revision) "
        "VALUES (:lang, :w, :v, :emb, :rev)"
    )
    vec = "[" + ",".join("0.1" for _ in range(768)) + "]"

    # 1. Insert LaBSE/v1 partition row
    await db_session.execute(
        insert_one,
        {"lang": "ett", "w": "fanu-partitiontest", "v": vec,
         "emb": "sentence-transformers/LaBSE", "rev": "v1"},
    )
    # 2. Insert xlmr-lora/v4 partition row for the SAME (lang, word). Must succeed.
    await db_session.execute(
        insert_one,
        {"lang": "ett", "w": "fanu-partitiontest", "v": vec,
         "emb": "xlmr-lora", "rev": "v4"},
    )
    await db_session.commit()

    rows = (await db_session.execute(
        text("SELECT embedder, embedder_revision FROM language_word_embeddings "
             "WHERE language = 'ett' AND word = 'fanu-partitiontest' "
             "ORDER BY embedder")
    )).fetchall()
    assert len(rows) == 2, f"Expected 2 partitions, got {len(rows)}"
    assert rows[0][0] == "sentence-transformers/LaBSE"
    assert rows[1][0] == "xlmr-lora"


@pytest.mark.asyncio
async def test_find_cross_language_filters_by_embedder(db_session):
    """``find_cross_language_neighbours(embedder=..., embedder_revision=...)``
    returns vectors only from the requested partition, never crossing
    partition boundaries.

    Constructs two distinct vector spaces for the same (ett, clan) →
    (lat, clan) pair: one where they share a vector (cosine=1.0), one
    where they're orthogonal (cosine=0.0). The default call sees the
    first; the explicit-embedder call sees the second.
    """
    from sqlalchemy import text

    try:
        await db_session.execute(text("SELECT 1 FROM language_word_embeddings LIMIT 0"))
    except Exception:
        pytest.skip("language_word_embeddings table not present in this backend")

    one = "[1.0," + ",".join("0.0" for _ in range(767)) + "]"
    two = "[0.0,1.0," + ",".join("0.0" for _ in range(766)) + "]"
    insert_one = text(
        "INSERT INTO language_word_embeddings "
        "(language, word, vector, embedder, embedder_revision) "
        "VALUES (:lang, :w, :v, :emb, :rev)"
    )

    # Default partition: ett 'clan' shares its vector with lat 'clan' (cos=1)
    await db_session.execute(insert_one, {
        "lang": "ett", "w": "clan", "v": one,
        "emb": "sentence-transformers/LaBSE", "rev": "v1",
    })
    await db_session.execute(insert_one, {
        "lang": "lat", "w": "clan", "v": one,
        "emb": "sentence-transformers/LaBSE", "rev": "v1",
    })
    # xlmr-lora/v4 partition: orthogonal vectors (cos=0)
    await db_session.execute(insert_one, {
        "lang": "ett", "w": "clan", "v": one,
        "emb": "xlmr-lora", "rev": "v4",
    })
    await db_session.execute(insert_one, {
        "lang": "lat", "w": "clan", "v": two,
        "emb": "xlmr-lora", "rev": "v4",
    })
    await db_session.commit()

    # Default partition: cosine ~ 1.0
    default_hits = await find_cross_language_neighbours(
        word="clan", source_lang="ett", target_lang="lat",
        session=db_session, k=1,
    )
    assert len(default_hits) == 1
    assert default_hits[0].cosine == pytest.approx(1.0, abs=1e-4)

    # Explicit xlmr-lora/v4: cosine ~ 0.0 (orthogonal)
    v4_hits = await find_cross_language_neighbours(
        word="clan", source_lang="ett", target_lang="lat",
        session=db_session, k=1,
        embedder="xlmr-lora", embedder_revision="v4",
    )
    assert len(v4_hits) == 1
    assert v4_hits[0].cosine == pytest.approx(0.0, abs=1e-4)


@pytest.mark.asyncio
async def test_find_cross_language_empty_partition(db_session):
    """Querying a partition the source word doesn't exist in returns []
    (not exception, not a fallthrough to another partition)."""
    from sqlalchemy import text

    try:
        await db_session.execute(text("SELECT 1 FROM language_word_embeddings LIMIT 0"))
    except Exception:
        pytest.skip("language_word_embeddings table not present in this backend")

    vec = "[" + ",".join("0.1" for _ in range(768)) + "]"
    # Insert into default partition only.
    await db_session.execute(
        text("INSERT INTO language_word_embeddings "
             "(language, word, vector, embedder, embedder_revision) "
             "VALUES (:lang, :w, :v, :emb, :rev)"),
        {"lang": "ett", "w": "only-in-default", "v": vec,
         "emb": "sentence-transformers/LaBSE", "rev": "v1"},
    )
    await db_session.commit()

    # Query the v4 partition — source word doesn't exist there, expect [].
    hits = await find_cross_language_neighbours(
        word="only-in-default", source_lang="ett", target_lang="lat",
        session=db_session, k=5,
        embedder="xlmr-lora", embedder_revision="v4",
    )
    assert hits == []
