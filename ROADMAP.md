# OpenEtruscan engineering roadmap

This document tracks what was just done, what is queued next, and what is
strategic but multi-session work. It is the artifact behind the audit summary
in [PR #7](https://github.com/Eddy1919/openEtruscan/pull/7) and the provenance
integrity work that followed.

Status legend: ✓ done · → in progress · ◯ queued · ⨯ deferred (with reason).

---

## Done in the audit (April / May 2026)

### Stop-the-bleed (P0)
- ✓ Cloud SQL backups enabled (30-day retention) + PITR + 7-day transaction log + deletion protection.
- ✓ Public DB IP removed; Private IP `10.50.0.3` only via VPC peering on the default network.
- ✓ `0.0.0.0/0` ACL cleared; `sslMode: ENCRYPTED_ONLY`; `ssl = require` on every API connection.
- ✓ Dedicated VM service account `openetruscan-vm@…` with `secretmanager.secretAccessor`, `cloudsql.client`, `logging.logWriter`. VM scope `cloud-platform`.
- ✓ External IP `34.90.171.125` reserved as a static address (`openetruscan-eu-static`); Vercel A record updated.
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

---

## P1 — queued but not yet done in this round

These are the audit's P1 items that did not fit in the May 1 push, ranked by leverage.

### Search relevance: hybrid retrieval + reranker
- ◯ Add `/search?mode=hybrid` that unions FTS (BM25 via `ts_rank_cd`) and dense pgvector top-k, then re-ranks with a small CPU cross-encoder (e.g. `bge-reranker-base`).
- ◯ Build a 200-query labelled eval set; report NDCG@10 on PR.
- ◯ Cache popular query embeddings on `app.state.query_embedding_cache` so the Gemini call is amortised.
- Why: this is the biggest single user-visible quality win in the audit. Done last because it is a model+infra change, not a refactor.

### ML serving
- ◯ Move ByT5 lacuna restoration to a dedicated Cloud Run inference service with batching. Today every `/neural/restore` is a CPU-bound torch session inside the API container; that does not scale concurrently and prevents GPU usage.
  - **Plan**:
    - Extract the `LacunaeRestorer` model loading and inference logic into a standalone lightweight FastAPI or vLLM container.
    - Package the container with GPU-compatible PyTorch/ONNX Runtime bindings.
    - Deploy to Cloud Run using the `gpu` execution environment (e.g., L4 instances) to vastly reduce inference latency.
    - Configure request batching via Cloud Run concurrency settings or dynamic batching middleware to amortize GPU costs across multiple API requests.
    - Update the main API `/neural/restore` endpoint to act as a reverse proxy/client to the Cloud Run service instead of doing local inference.
- ◯ Add a model registry concept (URI per version) so a new restorer can be A/B'd before flipping the default.
- ◯ Snapshot classifier predictions on a held-out set; fail CI on regression.

### Frontend (Next 16 / React 19)
- ◯ Cut `'use client'` from 19 routes to ~5; server-render layout shells, isolate interactive subtrees. Audit pointed at `app/{classifier,stats,names,explorer,concordance,timeline,downloads,normalizer,dodecapolis,docs,page}.tsx`.
- ◯ Fix the 6 `setState`-in-`useEffect` lint errors (concordance:84, nav:46, timeline:140, ClientTimelineMap:140 et al.). React 19 enforces these strictly; they cost a render per cycle.
- ◯ `next/dynamic` for Mapbox / R3F / Chart.js routes so the 30+ MB combined dependency footprint is route-scoped, not page-load-scoped.
- ◯ Gzip and `preload` the ONNX models (glyph_detector.onnx is 11 MB raw, lazy-loaded).
- ◯ Server-side `generateMetadata` for inscription, classifier, stats, concordance, timeline, names, explorer pages (only home, search, inscription have it now).
- ◯ Resolve the `@aldine/react` build failure called out in `build_output.txt`.

### Backend bug-class fixes
- ◯ `_FAMILY_GRAPH_CACHE` (server.py:1063) has no invalidation and a TOCTOU race; replace with an `asyncio.Lock`-guarded build at startup, or move to a TTL cache.
- ◯ Standardise error responses on RFC 7807 Problem Details across all endpoints (currently a mix of `{"detail": ...}` and ad-hoc shapes).
- ◯ Idempotency-Key support on `/inscriptions` POST (admin import).
- ◯ Replace test SQLite with a real Postgres + pgvector test fixture (testcontainers). Today's tests do not exercise PostGIS or pgvector at all.

### Per-source provenance metadata
- ◯ Add a `data_sources` table with one row per ingest pipeline (Larth, CIE Vol I, …) and a `provenance_baseline` field. Inscriptions inherit the baseline at import unless overridden.
- ◯ Curatorial workflow for promoting individual rows to `excavated` (admin endpoint + audit log).
- ◯ Per-source disclosure on each inscription page: "From the Larth Dataset; archaeological context unknown" rather than just the source string.

---

## P2 — operational debt (next 2–4 weeks)

- ◯ **Image registry + canary deploys.** Push the `api` image to Artifact Registry per-tag; replace the SSH-then-`docker compose --build` flow with `gcloud run deploy` or Cloud Deploy. Removes the "SSH to prod" step entirely.
- ◯ **OpenTelemetry.** Instrument FastAPI with `opentelemetry-instrumentation-fastapi` + `opentelemetry-instrumentation-asyncpg`; export to Cloud Trace via the ops agent.
- ◯ **Slow-query alert.** Cloud Monitoring alert policy on `cloudsql.googleapis.com/database/postgresql/transaction_count` > N/min for the slow-query class.
- ◯ **TLS automation.** Move api.openetruscan.com cert from the user-home `certbot` install to a Google-managed cert behind a Cloud Load Balancer (the cert path is currently `/home/edoardo.panichi/certs/...`, which is a `userdel` away from broken TLS).
- ◯ **Cross-region cleanup.** API VM is in europe-west4, DB is in europe-west1. Move the DB to europe-west4 (smaller blast radius than moving the VM); minor egress savings, real latency win.
- ◯ **PgBouncer.** `max_connections=25` on db-f1-micro vs. `pool_size=20, max_overflow=10` per worker is one restart away from saturation. Add PgBouncer in transaction mode as a sidecar.
- ◯ **Right-size the DB.** db-f1-micro on HDD is the wrong floor for the hybrid-search workload. Move to db-custom-2-7680 with SSD when hybrid search ships (~$130/mo cost difference, unlocks every other ML improvement).
- ◯ **Per-deploy migration step.** Wire `alembic upgrade head` into the deploy workflow before `docker compose up -d --build`. Without this, schema changes need manual application, which is what we just did for the provenance migration.
- ◯ **Vercel DNS scope-up.** The current Vercel token cannot manage DNS records (it is a deploy-only token). Mint a project-scoped token with DNS write so future IP changes can be automated.

---

## P3 — strategic, multi-session

### Cloud Run migration
- ⨯ (queued, not in this scope) Move the API from the e2-small + nginx + IAP+SSH model to Cloud Run + Cloud Load Balancer + Google-managed cert + Workload Identity. Eliminates the single-VM SPOF, removes the manual deploy, and gives autoscaling 0→N for free. Fuseki stays on a small Compute instance with a regional Persistent Disk because it is stateful (single-writer TDB1).

### Terraform
- ⨯ Codify the GCE VM, Cloud SQL, DNS, IAM bindings, Secret Manager secrets, Cloud Monitoring policies, and the future Cloud Run service. Today every infra change is a click in the console. Once the migration is done this becomes the natural "infra reviewable in PRs" surface.

### IIIF for inscription images
- ⨯ Adopt IIIF Image API + Mirador / OpenSeadragon for the `images` table (currently empty). Field-archaeologist and palaeographer use cases expect zoom/region annotation as table stakes.

### Citable permalinks with content negotiation
- ⨯ `Link: <…>; rel="alternate"; type="application/ld+json"` headers and matching variants for inscription URLs (HTML / JSON-LD / Turtle / EpiDoc TEI). Cheap, big credibility win for citation aggregators.

### Genetics + Pelagios
- ⨯ The `genetic_samples` table is currently empty (0 rows) but the `/inscriptions/{id}/genetics` endpoint exists. Either ingest a real source or hide the endpoint until populated.
- ⨯ The Pelagios JSON-LD endpoint claims 11,361 inscriptions but the live DB has 6,633. Reconcile or update the claim.

### Schema drift
- ⨯ The `Inscription` SQLAlchemy model defines `source_code`, `source_detail`, `original_script_entry` columns that do not exist in the prod DB. Either backfill via an alembic migration or delete the model fields. This drift is what makes the CI OpenAPI schema check fail.

---

## What is intentionally NOT on this list

- Neural restoration on a GPU VM. Cloud Run with a GPU is the right answer; running a g2-* VM in the same project for one tenant is not worth it at current traffic.
- A second region. The corpus is Europe-shaped; users are mostly in Europe and North America. CDN + a single region with PITR backup is fine.
- Replacing pgvector with a dedicated vector DB. 6.6 K rows × 768 dims fits in pgvector's HNSW comfortably; switching costs would be wasted until the corpus is 1–2 orders of magnitude bigger.
