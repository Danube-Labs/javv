# M1 - Backend skeleton + indexes + ingest + observability

**Status:** tracked in [#23](https://github.com/Danube-Labs/javv-poc/issues/23) — live status on the GitHub issue/board

## Goal
Stand up the FastAPI backend, bootstrap the current-state + `system-*` indices with explicit mappings, and
accept the M0 envelope through a **hardened** ingest endpoint - proving the end-to-end path with a
golden-envelope round-trip. This is the foundation every later backend bolt builds on.

**Canonical refs:** [`PLAN §8 M1`](../../../docs/engineering/PLAN.md) · `SPEC` FR-3, NFR-2/5/7 ·
[`INDEX-MAP.md`](../../../docs/engineering/INDEX-MAP.md) (**read before writing any mapping**) ·
decisions **D9** (observability), **D16** (normalizer), **D25/D35** (current-envelope-only), **D38** (peppered tokens).

## Depends on
- **M0** - produces the envelope this bolt ingests.
- **Local environment:** run [`development/setup/preflight.sh`](../../setup/preflight.sh) first - it verifies the Docker
  daemon, the k3d cluster, OpenSearch reachability, and required tool versions before this bolt can run.

## Deliverables
The layered backend (`backend/`, per [STACK-BEST-PRACTICES §1](../../../docs/research/STACK-BEST-PRACTICES.md)):
- `backend/core/` - settings, structlog config, **lifespan** holding the single `AsyncOpenSearch` client
  (injected via `Depends`, `await`-closed on shutdown). **Boot vs runtime** (per
  [`standards/observability.md`](../../standards/observability.md)): **fail-fast at startup** (clear error,
  non-zero exit) if OpenSearch is unreachable; but at **runtime** the app **stays up and degrades** - data
  endpoints return the 503 envelope and `/readyz` flips to `503`, never crash. **Startup also runs
  `core/bootstrap.py`** (ping → bootstrap → serve, the Kibana pattern): idempotent/version-gated so every
  boot is a no-op when current, and the concurrent-create race is already handled — wire this in the
  observability slice, don't leave bootstrap manual-only.
- `backend/core/errors.py` - the **single error envelope** (problem-details: `type/title/status/detail/request_id`)
  + exception handlers; **every** non-2xx response uses it (routers never hand-roll error bodies). `request_id`
  is bound into structlog so a client error maps to exact logs.
- `backend/core/bootstrap.py` - **versioned index bootstrap**: `dynamic:false` mappings for current-state
  (`findings`, `images`) + `system-*`, with keyword ids, the **severity normalizer**, reshaped CVSS, EPSS/KEV,
  and the **schema-v2 observed topology** — `namespaces` as **`keyword[]`** (never singular; array-contains
  filter, per-ns counts overlap), `replicas` `integer`, `image_ref` `keyword`. Read `INDEX-MAP.md` (now
  reconciled, audit finding #1) before writing any mapping — never aggregate on `text`.
- `backend/models/` - Pydantic v2 schemas; **request models `extra="forbid"`**; `cluster_id` shape validated.
  **Coupling (D41):** because the ingest envelope model is `extra="forbid"`, it **must** include M0's provenance
  fields — `scanner_version`, `scanner_db_version`, `scanner_db_built` — or it will reject the M0 envelope.
  **Observed topology (resolved — envelope schema v2):** the scanner envelope now carries `image_ref`,
  `namespaces[]` (a digest can span namespaces), and `replicas` (running pod count) — the scanner-only
  observations the indexes reserve. So the ingest model **must** accept them (`extra="forbid"`), and
  `findings`/`occurrences`/`scan-events`/`images` all use `namespaces` **`keyword[]`** (+ `images.replicas`
  `integer`) — INDEX-MAP reconciled (audit finding #1). A namespace filter is array-contains, so the same
  finding surfaces under each namespace it runs in; per-namespace counts overlap (only the all-ns total is deduped).
- `backend/repositories/`, `backend/services/`, `backend/routers/ingest.py` - the ingest path: validate →
  normalize → `_bulk` write (inspect `response["errors"]` + per-item status; backoff on 429/503).
- `POST /api/v1/ingest/scan` - **hardened:** rate-limit, size + decompression caps, **256-bit random
  `(cluster,scanner)` tokens stored as peppered SHA-256**, structured queries, **current-envelope-only**
  acceptance. Sets the house conventions in [`standards/api-design.md`](../../standards/api-design.md)
  (`/api/v1` prefix, snake_case, `extra="forbid"`, error envelope).
- `/healthz` (liveness, **no** OpenSearch dependency) + `/readyz` (readiness, reflects OpenSearch reachability)
  + `/metrics` + structlog with bound `request_id`/`cluster_id`. See [`standards/observability.md`](../../standards/observability.md).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** the M1 PLAN gate:
- **Golden-envelope round-trip:** a checked-in real scanner envelope POSTed through the *actual* ingest path
  results in the expected `findings` / `images` / `scan-events` docs - **raw preserved in `_source`,
  normalized severity bucketed**. Automated.
- Ingest rejects: oversized/over-compressed bodies, an envelope with extra fields (`extra="forbid"`), a bad/missing
  token, and a non-current envelope.
- `/healthz` stays `200` without OpenSearch; `/readyz` returns `503 degraded` when OpenSearch is unreachable
  and `200 ready` when it recovers; the app **fails fast** (non-zero exit) only at **startup**, and at
  **runtime** stays up returning the **503 error envelope** (with `request_id`) instead of crashing;
  `/metrics` emits ingest counters. Redaction test: a token/password never appears in a log line.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md). This bolt needs:
- **Integration (real OpenSearch):** the golden-envelope round-trip; bootstrap is idempotent + versioned.
- **Unit:** token hashing (peppered SHA-256, constant-time compare); the `_bulk` error/backoff helper (shared,
  well-tested - the only flow control without a broker); request-model validation (`extra="forbid"`, `cluster_id`).
- **Security:** rate-limit + size/decompression caps; rejection of malformed/oversized/forbidden payloads
  (`security-and-hardening` skill).

## Out of scope (defer)
- Dedup/identity, partial-merge, watermark, reconcile, projection → **M3** (don't pre-build merge logic here).
- scan-events append + retention → **M4**. Occurrences/PIT → **M8**.
- Auth/RBAC for *human* endpoints → **M5a** (ingest-token auth is separate and lives here).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**

## Updates

### 2026-10-26 — Frozen as history

The bolts M0 to M10 ended on 2026-10-09. This file is history now, not the spec of record. New work
follows one GitHub issue for each feature, with the plan and a spec file for each slice on the
issue. The timeline, the rulings that still apply and the open work are in the
[memory bank](../../memory-bank/README.md) (issue 1012).
