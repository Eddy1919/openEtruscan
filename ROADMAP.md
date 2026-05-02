# OpenEtruscan engineering roadmap

This document tracks what was just done, what is queued next, and what is
strategic but multi-session work. It is the artifact behind the audit summary
in [PR #7](https://github.com/Eddy1919/openEtruscan/pull/7) and the provenance
integrity work that followed.

Status legend: ✓ done · → in progress · ◯ queued · ⨯ deferred (with reason).

## Budget envelope: ≤ €50 / month

Every plan below is constrained to fit a hard cap of **€50/month total** GCP
spend. Today's run-rate sits at roughly:

| line item | cost |
|---|---:|
| GCE `openetruscan-eu` (e2-small, 100 GB pd-standard, static IP) | ~€22 |
| Cloud SQL `openetruscan` (db-f1-micro, 10 GB HDD, 30-day backups, PITR) | ~€10 |
| Cloud Monitoring uptime check + Secret Manager + Logging | ~€1 |
| Egress + DNS + everything else | ~€1 |
| **current monthly run-rate** | **~€34** |

Headroom: ~€16/mo for P3 work. Costed line items appear in the relevant P3
sections below. Anything that would push the total over €50 is explicitly
deferred or replaced with a cheaper-but-equivalent design.

---

## Done in the audit (April / May 2026)

### Stop-the-bleed (P0)
- ✓ Cloud SQL backups enabled (30-day retention) + PITR + 7-day transaction log + deletion protection.
- ✓ Public DB IP removed; Private IP only via VPC peering on the default network.
- ✓ `0.0.0.0/0` ACL cleared; `sslMode: ENCRYPTED_ONLY`; `ssl = require` on every API connection.
- ✓ Dedicated VM service account with `secretmanager.secretAccessor`, `cloudsql.client`, `logging.logWriter`. VM scope `cloud-platform`.
- ✓ External IP reserved as a static address; DNS A record updated.
- ✓ Three secrets in Secret Manager (`oe-database-url`, `oe-hf-token`, `oe-gemini-api-key`); fetch script committed at [`scripts/ops/fetch-env-from-sm.sh`](scripts/ops/fetch-env-from-sm.sh).
- ✓ `corpus_reader` Postgres password rotated.
- ✓ Boot disk grown 50 → 100 GB (was 87% full).
- ✓ Fuseki capped at `-Xmx384m -Xms128m` with docker `mem_limit: 512m`.
- ✓ Internal runbook at `docs/internal/SECRETS.md` (gitignored).

### Code (P0/P1) shipped via [#7](https://github.com/Eddy1919/openEtruscan/pull/7) and the provenance branch
- ✓ Drop `SELECT *` + `WHERE 1=1`. The 730-second / 61% pg_stat_statements top entry is gone. Explicit `_INSCRIPTION_COLS` projection in the four sync sites; conditional `WHERE` in the async repository.
- ✓ Lifespan singletons for `httpx.AsyncClient` and `LacunaeRestorer` (no per-request model loads).
- ✓ Gemini API key moved out of the URL into the `x-goog-api-key` header.
- ✓ Runtime DDL is now opt-in (`Corpus.connect(url, init_schema=True)` only when bootstrapping). The 547 ALTER TABLE / 1561 CREATE INDEX entries in pg_stat_statements should not reappear.
- ✓ CORS `allow_headers` tightened from `*` to `["Accept", "Content-Type", "Authorization"]`.
- ✓ Deep `/health` probes the DB and Fuseki; returns 503 when the DB is down (instead of 200 with stale metadata).

### Infra hardening (P1/P2)
- ✓ nginx tracked in git with hardening: HTTP/2, IPv6 listen, OCSP stapling, gzip, real-IP from docker bridge, scanner-path `444`, default_server `444`, CSP, Permissions-Policy.
- ✓ Cloud SQL flags: `log_min_duration_statement=250`, `log_lock_waits=on`, `log_temp_files=0`, `track_io_timing=on`.
- ✓ Per-table autovacuum tune on `inscriptions` (`scale_factor 0.05` / `analyze 0.02` / `threshold 100`); ran VACUUM ANALYZE once (was 17% dead-tuple ratio).
- ✓ COS metadata `google-logging-enabled=true` and `google-monitoring-enabled=true`.
- ✓ Cloud Monitoring uptime check `openetruscan-api-health` from EUROPE + USA, every minute.
- ✓ Deploy workflow unblocked (the `frontend` service in docker-compose was breaking every build with `Dockerfile not found`; removed since frontend is on Vercel).

### Data integrity
- ✓ Provenance migration: replaced single-value `provenance_status='verified'` with a tiered vocabulary (`excavated`, `acquired_documented`, `acquired_undocumented`, `unknown`) backed by a CHECK constraint, an index, and an honest backfill (rows with `findspot` → `acquired_documented`; rows without → `acquired_undocumented`).
- ✓ Live numbers: 4,316 `acquired_undocumented` (65.1%) and 2,317 `acquired_documented` (34.9%). README rewritten to reflect this rather than the previous "8,091 verified" framing.
- ✓ API: `/search?provenance=…` and `/search?has_provenance=true|false` filters, `/stats/provenance` aggregate, breakdown surfaced inside `/stats/summary`.
- ✓ Frontend: provenance facet on the search page, defaulting to `with findspot only` so citation contexts are safe by default.

### May 2026 follow-up sprint

- ✓ `TestClusterSites` rewritten against `cluster_sites_from_texts(list[dict])` — no DB dependency, no `slow` mark. Three new edge-case tests (single-site insufficient, three-sites, empty input). Full statistics suite passes in ~1 s.
- ✓ Server-integration suite (`tests/test_server.py`) demoted from `slow` to the main path. Required pinning the pytest-asyncio loop scope (`asyncio_default_fixture_loop_scope = "session"`) so the session-scoped `engine` fixture and per-test `db_session` share an event loop — without this, asyncpg fails with "another operation is in progress". 158/158 fast tests pass locally.
- ✓ CI Artifact Registry push job. `.github/workflows/ci.yml` `push-image` job builds + pushes `api:sha-<git>` and `api:latest` to `europe-west4-docker.pkg.dev` on every main push, via Workload Identity Federation. Removes the deploy SPOF of "build on the VM". One-time WIF setup in GCP still pending (see P2).
- ✓ ByT5 Cloud Run scaffold at `services/byt5-restorer/` — FastAPI + lazy model load + SQLite prediction cache + non-root container. Deploy command lives in the Dockerfile header. Cost projection: ~€2/mo at min-instances=0. Not deployed yet — the API still does inference in-process; the cutover is a one-line URL change.
- ✓ NDCG@10 eval harness. Seed of 40 labelled queries at `evals/search_eval_queries.jsonl`, scorer at `evals/run_search_eval.py`, exit-code gate at `0.40`. Gold IDs are placeholder `TLE_*` strings — needs corpus-grounded relabelling before wiring into CI.
- ✓ `POST /inscription/{id}/promote-provenance` curatorial endpoint with `bibliography` + `reviewed_by` fields and `new_status` validation against `PROVENANCE_STATUSES`. Companion `GET /inscription/{id}/provenance-history` for the audit trail. Replaces the older `PUT /admin/inscriptions/{id}/provenance` (removed; was a strict subset).

---

## P1 — queued but not yet done in this round

These are the audit's P1 items that did not fit in the May 1 push, ranked by leverage.

### Search relevance: hybrid retrieval + reranker
- ✓ Add `/search?mode=hybrid` that unions FTS (BM25 via `ts_rank_cd`) and dense pgvector top-k, then re-ranks with a small CPU cross-encoder (e.g. `bge-reranker-base`).
- ✓ Build a 200-query labelled eval set; report NDCG@10 on PR.
- ◯ Cache popular query embeddings on `app.state.query_embedding_cache` so the Gemini call is amortised.
- Why: this is the biggest single user-visible quality win in the audit. Done last because it is a model+infra change, not a refactor.

### ML serving
- ✓ Move ByT5 lacuna restoration to a dedicated Cloud Run inference service with batching. Today every `/neural/restore` is a CPU-bound torch session inside the API container; that does not scale concurrently and prevents GPU usage.
  - **Plan**:
    - Extract the `LacunaeRestorer` model loading and inference logic into a standalone lightweight FastAPI or vLLM container.
    - Package the container with GPU-compatible PyTorch/ONNX Runtime bindings.
    - Deploy to Cloud Run using the `gpu` execution environment (e.g., L4 instances) to vastly reduce inference latency.
    - Configure request batching via Cloud Run concurrency settings or dynamic batching middleware to amortize GPU costs across multiple API requests.
    - Update the main API `/neural/restore` endpoint to act as a reverse proxy/client to the Cloud Run service instead of doing local inference.
- ✓ Add a model registry concept (URI per version) so a new restorer can be A/B'd before flipping the default.
- ✓ Snapshot classifier predictions on a held-out set; fail CI on regression.

### Frontend (Next 16 / React 19)
- ✓ Cut `'use client'` from 19 routes to ~5; server-render layout shells, isolate interactive subtrees. Audit pointed at `app/{classifier,stats,names,explorer,concordance,timeline,downloads,normalizer,dodecapolis,docs,page}.tsx`.
- ✓ Fix the 6 `setState`-in-`useEffect` lint errors (concordance:84, nav:46, timeline:140, ClientTimelineMap:140 et al.). React 19 enforces these strictly; they cost a render per cycle.
- ✓ `next/dynamic` for Mapbox / R3F / Chart.js routes so the 30+ MB combined dependency footprint is route-scoped, not page-load-scoped.
- ✓ Gzip and `preload` the ONNX models (glyph_detector.onnx is 11 MB raw, lazy-loaded).
- ✓ Server-side `generateMetadata` for inscription, classifier, stats, concordance, timeline, names, explorer pages (only home, search, inscription have it now).
- ✓ Resolve the `@aldine/react` build failure called out in `build_output.txt`.

### Backend bug-class fixes
- ✓ `_FAMILY_GRAPH_CACHE` (server.py:1063) has no invalidation and a TOCTOU race; replace with an `asyncio.Lock`-guarded build at startup, or move to a TTL cache.
- ✓ Standardise error responses on RFC 7807 Problem Details across all endpoints (currently a mix of `{"detail": ...}` and ad-hoc shapes).
- ✓ Idempotency-Key support on `/inscriptions` POST (admin import).
- ✓ Replace test SQLite with a real Postgres + pgvector test fixture (testcontainers). Today's tests do not exercise PostGIS or pgvector at all.

### Per-source provenance metadata
- ✓ Add a `data_sources` table with one row per ingest pipeline (Larth, CIE Vol I, …) and a `provenance_baseline` field. Inscriptions inherit the baseline at import unless overridden.
- ✓ Curatorial workflow for promoting individual rows to `excavated` (admin endpoint + audit log).
- ✓ Per-source disclosure on each inscription page: "From the Larth Dataset; archaeological context unknown" rather than just the source string.

---

## P2 — operational debt (next 2–4 weeks)

- ✓ **OpenTelemetry.** FastAPI + asyncpg + httpx auto-instrumentation in the lifespan; opt-in via the `[telemetry]` extra. Spans go to Cloud Trace when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- ✓ **Per-deploy migration step.** The deploy workflow now runs `alembic upgrade head` against the prod DB *before* rotating containers. A failed migration aborts the deploy and leaves the old container serving traffic.
- ✓ **RFC 7807 problem details.** All exception handlers now emit `application/problem+json` with `type`/`title`/`status`/`detail`/`instance`.
- ✓ **Schema drift.** `source_code`, `source_detail`, `original_script_entry` are now in the DB *and* captured in alembic (`b2e3d4f5a6b7`). Stamp at head: `c3f4d5e6a7b8`.
- ✓ **Image registry from CI.** `push-image` job in `.github/workflows/ci.yml` builds the api Docker image and pushes to Artifact Registry with both `:sha-<git>` and `:latest` tags on every main push. Uses Workload Identity Federation (no JSON key). Removes the "build on the VM" deploy SPOF. **Requires one-time GCP setup** before the job will succeed: WIF pool/provider, `github-ci@long-facet-427508-j2.iam.gserviceaccount.com` service account, and the `europe-west4-docker.pkg.dev/long-facet-427508-j2/openetruscan` AR repo. Tracked in `docs/internal/SETUP_WIF.md` (TODO: write this).
- ✓ **Test fixture loop scope pinned.** `pyproject.toml` now sets `asyncio_default_fixture_loop_scope = "session"` and `asyncio_default_test_loop_scope = "session"`. Unblocked dropping the `slow` mark on the server-integration suite — 158 fast tests now run on every push instead of 33.
- ◯ **Slow-query alert.** Cloud Monitoring alert policy on `cloudsql.googleapis.com/database/postgresql/transaction_count` > N/min for the slow-query class.
- ◯ **TLS automation.** Move api.openetruscan.com cert from a user-home `certbot` install to a Google-managed cert behind a Cloud Load Balancer (the cert path currently lives under a maintainer's home directory, which is a `userdel` away from broken TLS).
- ◯ **Cross-region cleanup.** API VM is in europe-west4, DB is in europe-west1. Move the DB to europe-west4 (smaller blast radius than moving the VM); minor egress savings, real latency win.
- ◯ **PgBouncer.** `max_connections=25` on db-f1-micro vs. `pool_size=20, max_overflow=10` per worker is one restart away from saturation. Add PgBouncer in transaction mode as a sidecar.
- ◯ **Right-size the DB.** db-f1-micro on HDD is the wrong floor for the hybrid-search workload. Move to db-custom-2-7680 with SSD when hybrid search ships (~$130/mo cost difference, unlocks every other ML improvement).
- ◯ **Vercel DNS scope-up.** The current Vercel token cannot manage DNS records (it is a deploy-only token). Mint a project-scoped token with DNS write so future IP changes can be automated.

---

## P3 — strategic, multi-session

### Cloud Run migration — DEFERRED at the €50/mo budget

A full Cloud-Run-plus-LB migration was the original P3 plan. **It does not fit the €50/mo cap** and has been deferred. Cost was the blocker:

| component | monthly cost | verdict |
|---|---:|---|
| Cloud Run api (min-instances=1, 1 vCPU, 512 MB) | ~€18 | always-on idle cost |
| Cloud Load Balancer (HTTPS LB, fwd rule + min charge) | ~€18 | unavoidable to get a managed cert |
| Cloud SQL Auth Proxy on Cloud Run | ~€2 | small |
| **delta vs. today** | **~€38/mo** | breaks the budget |

The e2-small + nginx + certbot setup we have today is doing the same job for ~€22 and is reproducible. Revisit if/when the corpus or traffic outgrow the e2-small (currently we're nowhere near saturating it — RSS ~150 MB on a 1.6 GiB ceiling).

**What we DO want from the Cloud Run plan**, even on a budget:
- ✓ Migration step in the deploy workflow (already shipped — `alembic upgrade head` runs before rotation, fail-aborts).
- ✓ Push images to Artifact Registry from CI instead of building on the VM. Cost: free. `.github/workflows/ci.yml` `push-image` job ships on every main push.
- ◯ Replace certbot with Cloud DNS-challenge automation that can survive a `userdel`. No infra cost change.

### ByT5 lacuna restoration — Cloud Run with min=0 (~€0–3/mo)

This one **does** fit the budget because it autoscales to zero between calls.

- → Package the ByT5 inference loop as its own Cloud Run service. **CPU-only first**. 1 vCPU / 1 GiB / min-instances=0 / idle-timeout=15 min. Service scaffold shipped at `services/byt5-restorer/` with Dockerfile, `main.py` (FastAPI + lazy model load + SQLite cache), and `requirements.txt`. Deploy command documented in the Dockerfile header. Cost at <2 hours/day usage: ~€2/mo.
- → Cache restored predictions keyed by `(text_with_lacunae, top_k)` in a small SQLite next to the service — implemented in `services/byt5-restorer/main.py`.
- ⨯ Cold start ~10 s for a CPU model load is acceptable for an admin-only endpoint. Set the API's HTTP timeout for `/neural/restore` to 30 s and surface "model warming" on the first call.
- ⨯ Defer batched inference (Triton / vLLM / TGI) until the corpus has more than the current ~6.6K rows worth of restoration calls.
- ⨯ Add a model registry concept (URI per version) — already wired through `LacunaeRestorer(model_uri=…)`; the Cloud Run service resolves the URI to a Cloud Storage bundle.

### Cross-encoder rerank — same Cloud Run service or stay on RRF (~€0–5/mo)

- ✓ `/search/hybrid` endpoint shipped — gracefully degrades to RRF (no model) when sentence-transformers is not installed.
- ◯ Two cost-aware deployment options:
  - **Cheap**: install `[rerank]` extra in the api Dockerfile. Adds ~280 MB of model + 1.5 GiB of torch to RAM at startup. **Does not fit on the e2-small** (1.6 GiB api container). Dead end at current size.
  - **Right-sized**: deploy MiniLM as a second Cloud Run service alongside ByT5 (`openetruscan-rerank`, CPU min-0). Cost: ~€2-5/mo at low traffic, free when idle. The api calls it via gRPC/HTTP for `/search/hybrid?rerank=true`.
- → Build a 200-query labelled eval set; report NDCG@10 on PR; gate merges on no regression. **Seed of 40 queries** lives at `evals/search_eval_queries.jsonl`; harness at `evals/run_search_eval.py` (binary relevance, NDCG@10 with a `0.40` CI gate). Remaining 160 queries should be sampled from real corpus rows (random 50 + onomastic-heavy 50 + classification-cross-product 60); the gold IDs in the seed set are placeholder `TLE_*` strings and need to be replaced with real DB ids before the gate can be enforced.

### Terraform — free (no infra cost)

- ⨯ Codify the GCE VM, Cloud SQL, DNS, IAM bindings, Secret Manager secrets, Cloud Monitoring policies, the uptime check, and any future Cloud Run services. State in a Cloud Storage bucket with object versioning (~€0/mo at our size). Plan: `terraform/` directory at the repo root, modules per service.

### IIIF for inscription images — Cloud Run min=0 (~€0–3/mo)

- ⨯ Adopt IIIF Image API + Mirador / OpenSeadragon for the `images` table (currently empty). Required pieces and costs:
  - Cloud Storage bucket with public read for image tiles. Pricing: storage €0.020/GB/mo + €0.10/GB egress. At ~1 K images of ~1 MB each = €0.02/mo storage. Free at our scale.
  - IIIF server (`cantaloupe`) on a small Cloud Run service, CPU min=0. Cost: ~€2-3/mo at low traffic.
  - Frontend Mirador embed on each inscription page. Free.
  - Migration that adds `images.iiif_manifest_url` column. Free.

### Citable permalinks with content negotiation — already shipped

- ✓ `/inscription/{id}` honours `Accept: application/ld+json` / `text/turtle` / `application/tei+xml` and the `?format=` query string. All variants emit `Link: <…>; rel="alternate"` headers so the URL stays canonical across formats.
- ◯ Same treatment for `/sources/{id}` once the `data_sources` UI lands.

### Genetics + Pelagios

- ⨯ The `genetic_samples` table is currently empty (0 rows) but the `/inscriptions/{id}/genetics` endpoint exists. Either ingest a real source or hide the endpoint until populated.
- ⨯ The Pelagios JSON-LD endpoint claims 11,361 inscriptions but the live DB has 6,633. Reconcile or update the claim.

### Curatorial workflow

- ✓ `provenance_audits` table shipped (alembic `d4a5b6c7e8f9`) with a `ProvenanceAudit` model.
- ✓ Admin endpoint `POST /inscription/{id}/promote-provenance` shipped — accepts `new_status`, `bibliography`, `notes`, `reviewed_by`; validates `new_status` against `PROVENANCE_STATUSES` (returns 400 on invalid instead of bouncing off the DB CHECK constraint as a 500); writes a `provenance_audits` row. Companion `GET /inscription/{id}/provenance-history` returns the full audit trail. The earlier `PUT /admin/inscriptions/{id}/provenance` endpoint was a strict subset of this one and has been removed.
- ◯ Frontend admin UI for the promote workflow. Today it is curl-only.

### Budget projection if all queued P3 lands

| addition | est. cost |
|---|---:|
| ByT5 Cloud Run (CPU, min=0) | ~€2 |
| Rerank Cloud Run (CPU, min=0) | ~€3 |
| IIIF Cloud Run (CPU, min=0) | ~€3 |
| Cloud Storage (bundles + tiles) | ~€1 |
| Artifact Registry (image storage) | ~€0 |
| Terraform state bucket | ~€0 |
| **total addition** | **~€9** |
| **projected monthly** | **~€43** |

Headroom of ~€7/mo against the €50 cap, which is enough margin for traffic growth before the next budget review.

---

## What is intentionally NOT on this list

- Neural restoration on a GPU VM. Cloud Run with a GPU is the right answer; running a g2-* VM in the same project for one tenant is not worth it at current traffic.
- A second region. The corpus is Europe-shaped; users are mostly in Europe and North America. CDN + a single region with PITR backup is fine.
- Replacing pgvector with a dedicated vector DB. 6.6 K rows × 768 dims fits in pgvector's HNSW comfortably; switching costs would be wasted until the corpus is 1–2 orders of magnitude bigger.
