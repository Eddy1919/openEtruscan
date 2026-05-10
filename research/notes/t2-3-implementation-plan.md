# T2.3 implementation plan — drafted, ready to execute

Drafted by the Plan subagent during the CI-migration session, 2026-05-10.
Save here so the next session that implements T2.3 doesn't have to
re-derive the design.

> ⚠️ **Critical correction before implementing.** The plan below
> suggests `j5e6f7a8b9c0` as the new alembic revision id. **Do NOT
> use that id** — it is the exact phantom revision we just stamped
> over while unblocking the prod deploy (`alembic_version
> j5e6f7a8b9c0 → a6d56926ff21`, see PR #21 commit body). Reusing it
> would create a real-vs-phantom-with-the-same-name collision that
> alembic can't recover from. Pick a fresh id (e.g.
> `k5e6f7a8b9c1`) and verify with `git log --pickaxe-regex -S "<id>"`
> that it has never appeared in the repo before committing.

---

## Schema decision (upfront, drives everything else)

**Recommended: Option (a)** — extend the PK to `(language, word, embedder, embedder_revision)`.

Reasoning:

1. `embedder` and `embedder_revision` **already exist** as non-PK columns (verified in `i4d5e6f7a8b9_resize_embeddings_to_768.py` lines 53–54). The migration is therefore an ALTER-PK + NOT-NULL backfill, not a column-add.
2. The WBS explicitly recommends this and the v4 ingest already wants both axes (`xlmr-lora` and `v4`) to live in the same column.
3. Option (b) loses the ability to differentiate between two distinct embedders sharing a revision tag (e.g. `LaBSE/v1` vs `xlmr-lora/v1`); narrower than the model deserves.
4. Option (c) (sibling table) duplicates the HNSW index and the WHERE-clause logic in `find_cross_language_neighbours`, and complicates `/neural/rosetta/vocab` (UNION-with-distinct).
5. With ~60k rows total (50k Latin + 8.9k Etruscan + small grc), an in-place PK swap is cheap (single-digit seconds).

Note on **labels**: the WBS calls the existing-vector embedder `LaBSE`, but the resize-migration (`i4d5e6f7a8b9`) hard-codes the DEFAULT as `xlm-roberta-base`. We need to inspect prod's actual values before the migration backfills.

---

## Phase 1 — Reconnaissance & schema state-pinning (read-only) [~20 min]

Run these read-only queries against the prod DB via the standard IAP path:

```sql
-- Are embedder / embedder_revision NULL anywhere?
SELECT embedder, embedder_revision, COUNT(*)
FROM language_word_embeddings GROUP BY 1, 2 ORDER BY 3 DESC;

-- Pre-existing duplicates that would block the PK extension (should be 0).
SELECT language, word, COUNT(*) c FROM language_word_embeddings
GROUP BY 1, 2 HAVING COUNT(*) > 1;

-- Total row count + per-language breakdown for time-budgeting.
SELECT language, COUNT(*) FROM language_word_embeddings GROUP BY 1;
```

Also: confirm the alembic head matches `a6d56926ff21` and there are no phantom revisions:

```bash
alembic heads          # expect exactly one head
alembic history --verbose | head -20
# Every .py in src/openetruscan/db/versions/ must be reachable from head.
```

---

## Phase 2 — Write the alembic migration [~45 min]

**File:** `src/openetruscan/db/versions/<FRESH_ID>_extend_embedding_pk.py`.
Pick the id fresh — see the warning above.

```python
revision: str = "<FRESH_ID>"
down_revision: str | Sequence[str] | None = "a6d56926ff21"
branch_labels = None
depends_on = None
```

### `upgrade()` — `op.*` call sequence (in this exact order)

1. `op.execute("ALTER TABLE language_word_embeddings ALTER COLUMN embedder SET DEFAULT 'LaBSE'")` — defensive.
2. `op.execute("UPDATE language_word_embeddings SET embedder = 'LaBSE' WHERE embedder IS NULL")` — backfill nulls. Use the label confirmed in Phase 1.
3. `op.execute("UPDATE language_word_embeddings SET embedder_revision = 'v1' WHERE embedder_revision IS NULL")` — backfill revision nulls.
4. `op.execute("ALTER TABLE language_word_embeddings ALTER COLUMN embedder SET NOT NULL")` (idempotent).
5. `op.execute("ALTER TABLE language_word_embeddings ALTER COLUMN embedder_revision SET NOT NULL")`.
6. `op.execute("ALTER TABLE language_word_embeddings DROP CONSTRAINT language_word_embeddings_pkey")`.
7. `op.execute("ALTER TABLE language_word_embeddings ADD PRIMARY KEY (language, word, embedder, embedder_revision)")`.
8. `op.execute("CREATE INDEX IF NOT EXISTS ix_lwe_lang_emb ON language_word_embeddings (language, embedder, embedder_revision)")`.

All eight steps in one alembic transaction.

### `downgrade()` — destructive; document loudly

1. `DROP INDEX IF EXISTS ix_lwe_lang_emb`
2. `DROP CONSTRAINT language_word_embeddings_pkey`
3. `DELETE FROM language_word_embeddings WHERE NOT (embedder = 'LaBSE' AND embedder_revision = 'v1')`
4. `ADD PRIMARY KEY (language, word)`
5. `ALTER COLUMN embedder_revision DROP NOT NULL`

### Lock-window risk

DROP CONSTRAINT briefly holds `ACCESS EXCLUSIVE`. With ~60k rows the migration finishes in seconds, but any in-flight `/neural/rosetta` request blocks until commit. Set a short `statement_timeout` (e.g. 30 s) on the migration session.

### Phantom-revision landmine

Re-read the warning at the top of this file. Verify the chosen revision id is fresh in `git log --pickaxe-regex` AND that `alembic heads` returns exactly one head before merging.

---

## Phase 3 — Update the ingest script [~30 min]

**File:** `scripts/training/vertex/ingest_embeddings.py`.

1. New args:

   ```python
   parser.add_argument("--embedder", default=None,
                       help="The `embedder` column value for non-base rows "
                            "(typically 'xlmr-lora' for v4 ingest)")
   parser.add_argument("--revision", default="v4")
   ```

   Keep `--etr-embedder-tag` as a deprecated alias.

2. **Critical**: change `ON CONFLICT (language, word) DO UPDATE` to `ON CONFLICT (language, word, embedder, embedder_revision) DO UPDATE`. If this is forgotten, v4 ingest silently overwrites LaBSE rows.

3. Add a startup probe that fails fast if the PK doesn't yet have 4 columns:

   ```sql
   SELECT array_length(conkey, 1) FROM pg_constraint
   WHERE conrelid = 'language_word_embeddings'::regclass AND contype = 'p'
   ```

   Expect `4`; refuse to run if less.

---

## Phase 4 — Plumb `embedder` through `find_cross_language_neighbours` [~30 min]

**File:** `src/openetruscan/ml/multilingual.py`.

New signature:

```python
async def find_cross_language_neighbours(
    *,
    word: str,
    source_lang: str,
    target_lang: str,
    session: AsyncSession,
    k: int = 10,
    embedder: str | None = None,
    embedder_revision: str | None = None,
) -> list[CrossLanguageHit]:
```

Defaults (top of function, after the LANGUAGE_TIERS validation):

```python
embedder = embedder or "LaBSE"
embedder_revision = embedder_revision or "v1"
```

Both internal queries gain `AND embedder = :embedder AND embedder_revision = :embedder_revision`. The new `ix_lwe_lang_emb` covers the WHERE; HNSW handles the ORDER BY.

---

## Phase 5 — `/neural/rosetta` + `/neural/rosetta/vocab` route changes [~30 min]

**File:** `src/openetruscan/api/server.py`.

Add a translation table near `LANGUAGE_TIERS`:

```python
_EMBEDDER_ALIASES = {
    None:           ("LaBSE",     "v1"),
    "LaBSE":        ("LaBSE",     "v1"),
    "xlmr-lora-v4": ("xlmr-lora", "v4"),
}
def resolve_embedder(alias: str | None) -> tuple[str, str]:
    if alias not in _EMBEDDER_ALIASES:
        raise ValueError(f"Unknown embedder {alias!r}; "
                         f"valid: {sorted(k for k in _EMBEDDER_ALIASES if k)}")
    return _EMBEDDER_ALIASES[alias]
```

`/neural/rosetta`: add `embedder: str | None = None` query param; map via `resolve_embedder`; 400 on unknown; pass through to `find_cross_language_neighbours`; include `"embedder": embedder or "LaBSE"` in the response.

`/neural/rosetta/vocab`: same query param; **cache key change** from `lang` to `f"{lang}:{embedder or 'LaBSE'}"` to fix the existing TODO at line 1137; SQL gains the same filter.

---

## Phase 6 — Operational sequencing (rollout order)

Strict order; each step reversible without affecting the next:

1. **Migration first** (DB-only). Old API code still works because new PK is a superset.
2. **Code deploy second**. Default routes to `LaBSE/v1` — unchanged client behaviour.
3. **Ingest third** from the openetruscan-eu VM via IAP:

   ```bash
   python scripts/training/vertex/ingest_embeddings.py \
     --gcs-uri gs://openetruscan-rosetta/embeddings/etr-xlmr-lora-v4.jsonl \
     --embedder xlmr-lora --revision v4
   ```

4. **Smoke test fourth** (Phase 8 commands).

Swapping 1↔2 → `/neural/rosetta` returns empty for minutes. Swapping 3↔1 → v4 ingest clobbers LaBSE rows.

---

## Phase 7 — Tests [~1 h]

`tests/test_multilingual.py`:

- `test_find_cross_language_neighbours_defaults_to_labse`
- `test_find_cross_language_neighbours_empty_partition`
- `test_pk_allows_dual_embedders`

`tests/test_server.py`:

- `test_rosetta_default_returns_labse`
- `test_rosetta_xlmr_lora_v4_param`
- `test_rosetta_unknown_embedder_400`
- `test_rosetta_vocab_partitioned_cache`

`tests/conftest.py`: update the inline `CREATE TABLE` to match the new 4-column PK; add `embedder_revision TEXT NOT NULL DEFAULT 'test'` so existing tests pass without per-test edits.

`tests/test_migrations.py` (new): alembic up/down round-trip; skip in fast CI runs.

---

## Phase 8 — Pre-curl smoke + acceptance verification

Pre-curl probes:

```bash
psql -c "SELECT embedder, embedder_revision, COUNT(*) FROM language_word_embeddings GROUP BY 1, 2 ORDER BY 1, 2"
# Expect ≥ 2 partitions: ('LaBSE', 'v1', ~60k) and ('xlmr-lora', 'v4', ~8.9k)

psql -c "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
         WHERE conrelid = 'language_word_embeddings'::regclass AND contype = 'p'"
# Expect: PRIMARY KEY (language, word, embedder, embedder_revision)

psql -c "SELECT embedder, embedder_revision FROM language_word_embeddings
         WHERE language='ett' AND word='fanu'"
# Expect 2 rows
```

WBS acceptance:

```bash
curl -sf 'https://api.openetruscan.com/neural/rosetta?word=fanu&from=ett&to=lat&k=5' \
  | jq '.neighbours[0].word'   # expect "fanum"

curl -sf 'https://api.openetruscan.com/neural/rosetta?word=fanu&from=ett&to=lat&k=5&embedder=xlmr-lora-v4' \
  | jq '{first: .neighbours[0].word, n: (.neighbours | length)}'
# expect n >= 1

curl -s -o /dev/null -w "%{http_code}\n" \
  'https://api.openetruscan.com/neural/rosetta?word=fanu&from=ett&to=lat&embedder=banana'
# expect 400
```

---

## Risk register

| Risk | Likelihood | Detection | Rollback |
|---|---|---|---|
| `ON CONFLICT (language, word)` left in ingest silently overwrites LaBSE | High if unreviewed | Phase 7 test + post-ingest row counts | Re-ingest LaBSE from its source JSONL |
| Migration before code deploy queries with v1 filter and matches nothing | Low | Phase 8 smoke (a) returns empty | Code defaults to LaBSE → no impact |
| Phantom alembic revision (T1.5 incident repeat) | Medium | `alembic heads` > 1 OR `alembic check` errors | Pick a fresh id; never SQL-stamp |
| Live `/neural/rosetta` blocked on PK-rebuild lock | Low (60k rows is small) | `pg_stat_activity` | 30 s `statement_timeout` aborts |
| HNSW index rebuild | None — index is on `(vector)` only | n/a | n/a |
| Backfill label mismatch (`LaBSE` vs `xlm-roberta-base`) | Medium | Phase 8 smoke (a) | Single `UPDATE` to normalise |
| Vocab cache returns wrong partition | Low if Phase 5 cache-key fix lands | Phase 7 test | Bounce API |

---

## Critical files

- `src/openetruscan/db/versions/i4d5e6f7a8b9_resize_embeddings_to_768.py` — current schema reference
- `scripts/training/vertex/ingest_embeddings.py` — ON CONFLICT clause + new CLI flags
- `src/openetruscan/ml/multilingual.py` — `find_cross_language_neighbours` signature + queries
- `src/openetruscan/api/server.py` — `/neural/rosetta` + `/neural/rosetta/vocab` query param, response field, alias resolution, cache-key fix at line 1137
- `tests/conftest.py` — fixture DDL at ~lines 173–183 must match the new PK shape
