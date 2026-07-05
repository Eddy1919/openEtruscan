# Community curation pivot — design (WBS P4 Option C)

**Status:** design + minimal API scaffold landed; full implementation gated on the WBS P4 decision-tree outcome (option A: publish negative result; option B: hard-negative-mining experiment; **option C: this**).

**Author:** coding agent + Edoardo, 2026-05-11.

## Why this exists

The WBS P4 Option C narrative is:

> Document the 17 anchors as the seed for a community-curated
> extension and pivot the system to support **review-and-extend**
> workflows rather than translation. This aligns with the M2
> qualitative-review track flagged in the WBS "out of scope"
> footnote.

The 17 attested anchors from T4.2 are below the contrastive-fine-tune
gate (≥30) by a factor of two. They are **not** below the threshold for
"useful seed for community-curated extension" — quite the opposite.
The literature on Etruscan attests several hundred candidate
equivalences scattered across editions, commentaries, and dictionaries
that the LLM-extraction pipeline of T4.1 cannot find because they
aren't framed in strict naming-verb prose. A philologist scanning the
same sources finds them in seconds.

The shift in the system's stance is from **\"translate this Etruscan
word\"** to **\"surface candidate equivalents and let a domain expert
keep or reject each\"**. Mechanically the existing
`/neural/rosetta` endpoint already does the surfacing; the missing
piece is a *write* path back into the corpus.

## What changes vs. status quo

| Layer | Before (today) | After (Option C) |
|---|---|---|
| Retrieval | `/neural/rosetta?word=X&from=ett&to=lat` returns top-k LaBSE neighbours, read-only. | Same surface; the response gains a per-row `propose_url` that opens a frontend modal pre-filled with the (etr, candidate) pair. |
| Submission | _none_ | New `POST /anchors/propose` accepts a candidate anchor (etr_word, equivalent, equivalent_language, evidence_quote, source, submitter_email). Lands in a moderation queue, doesn't enter the corpus. |
| Review | _none_ | New `GET /anchors/queue` lists pending submissions for an admin reviewer; the existing admin token (`oe-admin-token` secret) gates writes. |
| Promotion | _none_ | New `POST /anchors/{id}/promote` moves a queued submission into `research/anchors/attested.jsonl` (i.e. the canonical training-eligible list). |
| Display | Inscription page surfaces only the prod inscription text. | Inscription page surfaces the corpus token *and* "Proposed equivalences" pulled from `attested.jsonl` for that word. |

## Schema additions

New table `proposed_anchors`:

```sql
CREATE TABLE proposed_anchors (
  id                  bigserial PRIMARY KEY,
  etruscan_word       text NOT NULL,
  equivalent          text NOT NULL,
  equivalent_language text NOT NULL CHECK (equivalent_language IN ('lat', 'grc')),
  evidence_quote      text NOT NULL,                    -- verbatim substring of `source`
  source              text NOT NULL,                    -- "Bonfante 2002 §3.4" / "Suetonius Aug. 97" / etc
  submitter_email     text NOT NULL,
  submitter_orcid     text,                             -- optional, raises trust priority
  status              text NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'approved', 'rejected', 'duplicate')),
  reviewer            text,                             -- email of the admin who acted
  review_note         text,
  reviewed_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_proposed_anchors_status_created
  ON proposed_anchors (status, created_at DESC);
CREATE INDEX ix_proposed_anchors_etr_word
  ON proposed_anchors (etruscan_word);
```

Alembic migration: `<new>_proposed_anchors_table.py`. No data migration
needed; new table populates only via submissions.

## API endpoints

### `POST /anchors/propose`

Public-write, no auth (rate-limited via the existing nginx/Cloud
Armor surface — same rule as `/feedback` if/when that exists). Body:

```json
{
  "etruscan_word": "tular",
  "equivalent": "limes",
  "equivalent_language": "lat",
  "evidence_quote": "tular as boundary-stone term in Bonfante 2002 §3.4",
  "source": "Bonfante 2002 §3.4",
  "submitter_email": "philologist@example.edu",
  "submitter_orcid": "0000-0000-0000-0000"
}
```

Validates:

- `equivalent_language ∈ {lat, grc}`
- `evidence_quote` ≥ 10 chars
- `source` ≥ 3 chars
- Dedup against `proposed_anchors` (same `(etruscan_word, equivalent, equivalent_language)` triple → return existing id with `status: "duplicate"`).
- Dedup against `attested.jsonl` (same triple → return `status: "already_attested"` with the existing source).

Returns:

```json
{ "id": 42, "status": "pending", "queue_position": 3 }
```

Rate limit: 10 submissions per hour per IP, 100 per day per email.

### `GET /anchors/queue` (admin)

Auth: `Bearer ${OE_ADMIN_TOKEN}`. Returns pending submissions in
created-at order, oldest first:

```json
{
  "items": [{ "id": 1, "etruscan_word": "tular", ... }, ...],
  "total_pending": 7
}
```

### `POST /anchors/{id}/promote` (admin)

Auth: admin token. Body:

```json
{ "review_note": "verified against Bonfante 2002 §3.4 p. 47", "action": "approve" }
```

On approve: row moves to `status='approved'`, AND a new row is
appended to `research/anchors/attested.jsonl` with `submitter_email`
and `reviewer` recorded. The repo's CI doesn't auto-merge this — the
JSONL append happens on the API server's data volume, and the next
data-refresh PR picks it up via a CI workflow. (Avoids the API having
git-push permissions, which would be a security hole.)

On reject / duplicate / not-attested: `status` updates, JSONL is
not touched.

### `GET /anchors/attested?word=X`

Public-read. Returns currently-attested equivalences for a given
Etruscan word, joining `attested.jsonl` to the prod corpus. Used by
the frontend inscription page.

## Frontend changes

### New page: `/review`

Admin-only (existing admin-token gate; same UX as the curatorial
"promote provenance" modal). Lists `GET /anchors/queue` rows, with
keep / reject buttons.

### New page: `/propose/{etruscan_word}`

Public. Pre-filled form (etruscan_word from path); fields:

- `equivalent` (text)
- `equivalent_language` (radio: lat / grc)
- `evidence_quote` (textarea, 10+ chars)
- `source` (text)
- `submitter_email` (text)
- `submitter_orcid` (optional)

Submit calls `POST /anchors/propose`. On success: thank-you message,
queue position estimate.

### Modification to `/inscription/[id]`

When an inscription token matches an entry in `attested.jsonl`,
surface the equivalences under a new "Proposed equivalences" panel.
Each row links to the source citation.

### Modification to `/explorer`

Same data, displayed map-side: hovering on a findspot pin shows the
top 3 attested equivalences for any words in that inscription.

## Workflow

1. Visitor browses an inscription, sees a token they recognise (`tular`).
2. Visitor clicks "Propose equivalence" → fills the form → submission lands in the queue.
3. Admin reviews; for each entry, has the original-source attestation visible side-by-side with the rosetta-eval-v1 contextual cosine cluster (UX TBD).
4. Admin approves → row appended to `attested.jsonl` on the API server.
5. **Quarterly:** data-refresh PR (new task TBD: T6.x) pulls the API-server JSONL into the repo via a Cloud Build job + auto-PR. Once merged, the canonical `attested.jsonl` reflects the community's growth.

## What this DOESN'T solve

- It doesn't bypass the structural data-poverty diagnosis of P3/P5/P4. The community will not produce 10,000 new anchors in a year — but 50–100 would already push the contrastive fine-tune past its threshold and re-open T4.3.
- It doesn't automate quality control beyond the verbatim-quote validation already in the LLM-extract pipeline. A bad-faith submitter (or an enthusiastic amateur with low-quality citations) can flood the queue; the admin review is the safety net.
- It doesn't address the "review fatigue" failure mode common in community-curation projects. Mitigation: pre-fill the form from `/neural/rosetta` top-k results so the cognitive cost of submitting is "did the system already get this right?", not "look up the philological literature from scratch."

## Acceptance criteria for "Option C shipped"

1. `proposed_anchors` table exists on prod (via alembic).
2. The three `POST /anchors/...` endpoints respond with the documented contracts (tested in `tests/test_anchors_api.py`).
3. Frontend `/propose/{word}` page renders and submits.
4. Frontend `/review` page renders and promotes.
5. Documentation in `research/notes/community-curation-design.md` (this file) referenced from `research/FINDINGS.md > P4 results so far > Option C`.
6. **Soft gate:** within 30 days of launch, ≥ 5 community submissions land in the queue. Below that, the curation pipeline doesn't have audience-fit and we pivot back to Option A (publish negative result).

## Implementation order (~ 1 day full execution; this PR is the design doc)

1. Alembic migration for `proposed_anchors` (1 hour).
2. `POST /anchors/propose` + tests (2 hours).
3. `GET /anchors/queue` + `POST /anchors/{id}/promote` + tests (2 hours).
4. Frontend `/propose/{word}` page (2 hours).
5. Frontend `/review` page (2 hours).
6. End-to-end smoke test on staging.

## API scaffold landing alongside this doc

A minimal placeholder is added to [`src/openetruscan/api/server.py`](../../src/openetruscan/api/server.py) at the new `/anchors/*` routes — they return `501 Not Implemented` with the design-doc URL in the response body, so consumers writing against the surface get a stable contract early. The actual handlers are implemented in the follow-up PR.
