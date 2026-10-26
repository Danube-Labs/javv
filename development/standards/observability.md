# Observability & error handling

How JAVV logs, surfaces health, and reports errors. Each backend change follows it (FR-20, NFR-5/8).
The bar is **near-perfect error visibility**: every failure is structured, correlatable, and never silent -
and the app **degrades loudly, not blindly** when its datastore is unavailable.

> Implemented first in **M1** (the skeleton owns `/healthz`, `/readyz`, `/metrics`, structlog, and the error
> envelope). The frontend degraded banner is **M9a**. Later work reuses this contract and never reinvents it.

## 1. Structured logging (structlog via `libs/javv-common`)
- **The shared library is the ONLY pipeline** (#156/#159): `structlog.get_logger()` + key-value
  fields, configured ONCE at process start by `javv_common.logging.configure_logging` (backend:
  `create_app`; scanner: its entrypoint). Redaction, JSON rendering, `timestamp→level→event`
  ordering, `JAVV_LOG_LEVEL`, and the stdlib bridge (uvicorn/opensearch-py/kubernetes) all come
  free — **never `print()`, never `logging.getLogger()` in app code, never a private logging
  setup**. **Two exceptions, both operator interfaces, not app code:** (1) operator rigs under
  `development/e2e/` — stdout is their interface; (2) job CLI entrypoints — the `__main__` blocks of
  `python -m backend.jobs.*` (`rebuild_state`, `lifecycle`, `staleness`) may `print()` progress/results
  to stdout, exactly like the e2e rig (audit A-n). The jobs' *library* code still uses the shared
  logger; only the operator-facing `__main__` invocation path prints. One event per line.
- **Bound context on every request:** `request_id` (generate if absent), `cluster_id` (when known), `path`,
  `method`, `status`, `duration_ms`. A single request's lines are greppable by `request_id`.
- **Levels:** `debug` (dev detail) · `info` (lifecycle + each request) · `warning` (handled-but-notable:
  429/503 backpressure, `_bulk` partial failures, retries) · `error` (unhandled / dropped work — always with
  `request_id` + stack). Reserve `error` for things a human should see; don't cry-wolf.
  The OpenSearch client logs every failed request at `warning`; the shared library drops its 404
  and 409 lines, which the callers expect and handle (a first watermark read, the roles seeded with
  `op_type=create` at each start), so a client warning still means degraded service (issue 831).
- **Never log** (NFR-5): passwords, ingest tokens, session cookies, raw `Authorization` headers, full scanner
  payloads. Log *shapes/sizes/ids*, not secrets. A redaction processor enforces this — tested.

- **Frontend (M9a+):** same discipline, browser-side — `logger` from `frontend/src/lib/logger.ts`
  is the ONLY pipeline (leveled, structured, `timestamp→level→event` lines shaped like backend.log);
  raw `console.*` in app code is **ESLint-banned** (the FE "never `print()`"), with the logger module
  as the single sanctioned touchpoint. Threshold via `VITE_LOG_LEVEL` (build-time; `debug` dev /
  `warn` prod — see `docs/CONFIGURATION.md`, "Frontend build settings"). The never-log list applies unchanged: no tokens,
  no cookie values, no raw response bodies — shapes/sizes/ids.
- **Frontend server (issue 452):** the frontend container's Node process (`frontend/server/`) logs
  through `server/log.mjs` only: JSON lines to stdout in the backend's shape and level names,
  threshold from `JAVV_LOG_LEVEL`. Startup and failures only (the backend already logs every
  request); no header, body or query string in a line; its 502 logs once per window with a count.

## 2. Health endpoints — `/healthz` vs `/readyz`
| Endpoint | Means | Depends on OpenSearch? | Used by |
|---|---|---|---|
| `/healthz` | **Liveness** — the process is up and the event loop responds | **No** | k8s liveness probe (restart if failing) |
| `/readyz` | **Readiness** — can actually serve: OpenSearch answers | **Yes** (a ping, then the cluster health and the blocks of JAVV's indices) | k8s readiness probe + the **FE degraded banner** |

`/readyz` returns one of three answers (issue 832, operator ruling 2026-10-12):
- `200 {status:"ready"}`: OpenSearch answers and is neither red nor read-only.
- `200 {status:"ready", checks:{store:"read-only"|"red"}}`: OpenSearch answers, but a JAVV index
  carries the flood-stage block (its disk is full, so writes are refused) or the cluster is red
  (part of the data is not available). Red wins when both hold. Reads still work, so the pod stays
  in service: a 503 here would take the only backend pod out of its Service. The banner says so.
- `503 {status:"degraded", opensearch:"unreachable"}`: OpenSearch does not answer.

A check that fails (a timeout, a refusal) leaves the answer at `ready`; it counts in
`javv_opensearch_request_errors_total{kind="other"}` and logs `store check failed` at most once per
10 s. Nothing is cached: each call pings and makes the two cluster reads.

## 3. Boot vs runtime — fail-fast, then degrade
Two distinct failure modes, deliberately handled differently:
- **At startup** (lifespan): if OpenSearch is unreachable, **fail fast** — log a clear `error` and exit
  non-zero. Don't boot blind into a broken state (a misconfig should be obvious immediately).
- **At runtime** (was healthy, store drops): **do NOT crash.** The API stays up, `/readyz` flips to `503`,
  data endpoints return the **503 error envelope** (below), and the **frontend shows a global banner**
  ("Search backend unavailable — check OpenSearch health") instead of blank screens or cryptic errors.
  Recovers automatically when `/readyz` returns `200` again. The envelope comes from one handler
  (`core/errors.py`, issue 832): a connection error, a timeout, or a 502/503/504 from OpenSearch
  answers 503 "Search backend unavailable", counted in `javv_store_unavailable_total`, with one
  `store unavailable` warning per 10 s at most (a sender can repeat requests while the store is
  away) and no traceback. Ingest keeps its own `storage_error` record. Two more answers come from
  the same handler, by the same window rule: a write the store's full disk refuses answers 503
  "The store is read-only: its disk is full" (problem type `store-read-only`, counted in
  `javv_store_read_only_total`), and OpenSearch's own 429 (a full queue, a circuit breaker)
  answers 429 "The search backend is busy" with `Retry-After: 5`, counted in
  `javv_opensearch_request_errors_total{kind="429"}`.
- **The backend itself gone** (the process is down, or the proxy in front of it answers `502`/`504`):
  the frontend cannot get a `503` from a backend that is not there, so it reads the failure's shape
  (`downReason` in `frontend/src/stores/health.ts`). A `503` means the store; no answer or any other
  failure means the backend. The banner then says "The backend is not answering" rather than
  pointing at OpenSearch, and the login page says the server is not answering rather than rejecting
  the password (issue 675).

## 4. Error envelope (one shape, everywhere)
Every non-2xx JSON response uses **one** problem-details-style body — routers never hand-roll error shapes:
```json
{ "type": "about:blank|<slug>", "title": "Search backend unavailable",
  "status": 503, "detail": "The search backend is not reachable.", "request_id": "<uuid>" }
```
`request_id` matches the logged line, so a user-reported error maps to exact logs. Taxonomy (stable `status`):
`400` validation (`extra="forbid"` / bad `cluster_id`) · `401/403` auth/capability · `404` not found ·
`413` payload too large · `429` rate-limited (`slowapi`) · `503` backpressure (`Semaphore`) **or** OpenSearch
degraded. 4xx are `warning` at most; unexpected `5xx` are `error` with a stack. Never leak internals/stack to
the client body — only the envelope; the stack goes to the log under the same `request_id`.

## 5. Metrics (`/metrics`, Prometheus) — FR-20
Ingestion rate, **4xx/413/429/503 counters**, payload sizes, **decompression ratio**, in-flight/queue depth
(the `Semaphore`), request latency, memory. The same events that log `warning`/`error` increment a counter —
logs explain *one* failure, metrics show the *trend*. The reverse holds too, with one exception: a
rejection an unauthenticated sender can repeat with no budget is counted but not logged, and a
rate-limit rejection keyed on unverified input logs once per key per window (`.claude/rules/logging.md`).

**Background jobs (issue 691).** The scheduler runs inside the backend, so its failures follow the same
rule: `job failed` and `scheduler tick failed` log at `error` and count in `javv_job_runs_total{outcome="failed"}`
and `javv_scheduler_tick_errors_total`. A job that fails never stops the loop, and a store that is away never
takes the backend down: the loop logs, counts and tries again on its next tick.

## 6. Tested, not assumed
- **Redaction:** a log line built from a request carrying a token/password contains neither.
- **`/readyz`:** returns `503 degraded` when the OpenSearch ping fails (mock the client), `200` when it passes.
- **Error envelope:** every error path returns the envelope shape with a `request_id`; 413/429/503 map correctly.
- **Boot fail-fast:** lifespan raises/exits non-zero when OpenSearch is unreachable at startup.
