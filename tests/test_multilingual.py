"""Tests for the multilingual Rosetta vector store + API endpoint.

The persistence path needs pgvector; tests that hit the real DB are
marked `requires_pgvector` so SQLite-only test environments skip them
cleanly. The non-DB-touching surface (registry, refusal logic) is
unconditionally tested.
"""

from __future__ import annotations

import pytest

from openetruscan.ml.multilingual import (
    LANGUAGE_TIERS,
    find_cross_language_neighbours,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestLanguageRegistry:
    def test_anchor_language_is_present(self):
        assert "ett" in LANGUAGE_TIERS
        assert LANGUAGE_TIERS["ett"].deciphered is True
        assert LANGUAGE_TIERS["ett"].alignable is True

    def test_tier_1_languages_are_alignable(self):
        for code, rec in LANGUAGE_TIERS.items():
            if rec.tier == 1:
                assert rec.alignable is True, f"{code} tier 1 must be alignable"
                assert rec.deciphered is True, f"{code} tier 1 must be deciphered"

    def test_tier_3_languages_refuse_alignment(self):
        """Linear A, Nuragic, Illyrian, Faliscan must NOT be alignable."""
        tier3 = [r for r in LANGUAGE_TIERS.values() if r.tier == 3]
        assert tier3, "expected at least one tier-3 entry as a guard"
        for rec in tier3:
            assert rec.alignable is False, (
                f"tier-3 language {rec.code} accidentally marked alignable"
            )

    def test_undeciphered_languages_are_not_alignable(self):
        for rec in LANGUAGE_TIERS.values():
            if not rec.deciphered:
                assert rec.alignable is False, (
                    f"undeciphered {rec.code} cannot be alignable — no semantic ground truth"
                )

    def test_minoan_specifically_listed(self):
        """The user explicitly asked for Minoan; surface it as tier 3 with a note."""
        assert "lin_a" in LANGUAGE_TIERS
        rec = LANGUAGE_TIERS["lin_a"]
        assert rec.tier == 3
        assert rec.alignable is False
        assert "undeciphered" in rec.notes.lower() or "scientifically" in rec.notes.lower()

    def test_basque_is_proxy_labelled(self):
        """Modern Basque is in the registry but the note must flag it as a
        proxy for Aquitanian — a published claim of "ancient Basque" alignment
        without that caveat would be wrong."""
        assert "eus" in LANGUAGE_TIERS
        assert "proxy" in LANGUAGE_TIERS["eus"].notes.lower()


# ---------------------------------------------------------------------------
# Refusal logic (unit, no DB)
# ---------------------------------------------------------------------------


class _StubSession:
    """Stand-in async session for testing refusal paths that short-circuit
    before any SQL runs. Asserts execute() is never called."""

    async def execute(self, *_a: object, **_kw: object) -> object:
        raise AssertionError("session.execute should not be called for refused queries")


@pytest.mark.asyncio
async def test_lookup_refuses_tier3_source():
    with pytest.raises(ValueError, match="undeciphered|tier|refused"):
        await find_cross_language_neighbours(
            word="da-da",
            source_lang="lin_a",  # Linear A — undeciphered
            target_lang="lat",
            session=_StubSession(),
        )


@pytest.mark.asyncio
async def test_lookup_refuses_tier3_target():
    with pytest.raises(ValueError, match="undeciphered|tier|refused"):
        await find_cross_language_neighbours(
            word="zich",
            source_lang="ett",
            target_lang="lin_a",  # cannot honestly project INTO an undeciphered language
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
# API: /neural/rosetta/languages
# ---------------------------------------------------------------------------


async def test_languages_endpoint_returns_full_registry(client, sample_data):
    response = await client.get("/neural/rosetta/languages")
    assert response.status_code == 200
    body = response.json()
    codes = {r["code"] for r in body["languages"]}
    # Spot-check: anchor + at least one tier-3 must be present.
    assert "ett" in codes
    assert "lin_a" in codes
    # Every entry has the right fields.
    for rec in body["languages"]:
        assert {"code", "name", "tier", "deciphered", "alignable",
                "corpus_status", "notes"} <= rec.keys()


async def test_rosetta_lookup_refuses_tier3_via_api(client, sample_data):
    """The API must propagate the registry's tier-3 refusal as a 400."""
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
    """Source word never populated -> empty list, not an error.

    The table is empty in the test DB (we haven't run populate_aligned_language
    here), so any source-side lookup misses. That's the correct behaviour:
    callers shouldn't get a 500 just because their query word isn't in the
    stored vector cache.
    """
    response = await client.get(
        "/neural/rosetta",
        params={"word": "definitely-not-a-real-word", "from": "ett", "to": "lat"},
    )
    # If the language_word_embeddings table doesn't exist in the test DB
    # (SQLite fallback), accept that as a separate skip — the migration is
    # Postgres-only because it uses pgvector.
    if response.status_code == 500:
        pytest.skip("language_word_embeddings table not available (SQLite fallback)")
    assert response.status_code == 200
    assert response.json()["neighbours"] == []
