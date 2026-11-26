---
paths:
  - "backend/src/**"
  - "scanner/src/**"
  - "libs/**"
  - "frontend/src/**/*.ts"
  - "frontend/src/**/*.vue"
  - "frontend/server/**"
---

# Logging (shared library on both stacks — never `console.*`, never `print`)

> **One carve-out, and it is structural, not a file list:** `print()` is allowed only inside
> `if __name__ == "__main__":` blocks — stdout-as-output for CLI entry points (the job CLIs,
> `core/tokens.py`, `core/bootstrap.py`, `auth/reset_password.py`, `tools/export_openapi.py`,
> scanner `compat.py`), enforced by `backend/tests/test_logging_discipline.py`. Everything inside a
> request path, job body, or library uses the logger. A CLI whose stdout is its answer (a token, a
> password) sends its log lines to stderr, as `auth/reset_password.py` does.

Loaded when you touch source on either stack.

One pipeline per stack, structured, event-first. Ad-hoc logging is lint-banned, not merely discouraged.

**Backend** — `structlog.get_logger()` only, configured once by
`javv_common.logging.configure_logging()` (`libs/javv-common/`). The scanner uses the *same* call, so
both emit identical JSON.
- **Event name first, context as kwargs** — never an f-string sentence:
  `log.info("scan done", image_ref=ref, findings=n, duration_s=1.2)`, not `log.info(f"scanned {ref}")`.
  Structured fields are queryable; prose is not.
- **Bind who/where once per unit of work** with `structlog.contextvars.bind_contextvars(...)`
  (`cluster_id`, `scanner`, `scan_run_id`) and every later line carries it automatically.
- **Secrets are redacted by a processor**, not by remembering: bearer tokens and sensitive-looking
  keys become `[REDACTED]` on the way out. Don't defeat it by pre-formatting a token into a string.
- Level via `JAVV_LOG_LEVEL`. INFO = progress a human wants; WARNING = degraded-but-continuing
  (skipped image, dead-letter, a cap hit); ERROR = the unit of work failed.

**Frontend** — `@/lib/logger` only (`logger.debug|info|warn|error(event, fields?)`). **`console.*` is
lint-banned** and CI fails on it. Same shape as the backend: an event name plus a fields object.

**Frontend server** (`frontend/server/`, the frontend container's Node process, issue 452) —
`server/log.mjs` only: JSON lines to stdout in the backend's shape (`timestamp`, `level`, `event`,
then fields), the backend's level names, `JAVV_LOG_LEVEL` with the same fail-fast on an unknown
name. `console.*` is lint-banned there too. It logs startup and failures only, since the backend
already writes one line per request. Redaction is by omission: no header, body or query string goes
in a line (`serve.spec.ts` greps the server for it). Its 502 falls under the exception below.

**Ops parity is not optional on bounded or streamed paths.** An endpoint that caps (413/429) logs a
`warning` *and* bumps its metric; a streaming export counts rows and bytes in the stream's `finally`,
so a client disconnect still records what left the building.

**A slow read logs the time of its steps (issue 1318).**

- A read or a job that can take more than about one second writes one line at `info` when it ends.
- The line gives the time of each step and the size of the work, for example the rows.
- The request line gives only the total time. Without the step times, the log of a deployment cannot show the slow step.
- The rule also covers the exports and the reads of a dashboard. Add the line when you add or change such a path.
- The past-time reads write `past-time read` (`query/as_of_t.py`).

**One exception: a rejection an unauthenticated sender can repeat with no budget is metric-only**,
because a line per request would let the sender choose our log volume. Today that is ingest's 401,
decided before any token is known. A rejection with a budget but an attacker-chosen key logs at most
once per key per window (ingest's 429); the frontend server's 502 while the backend is down logs
once per window with the count it held back. Everything past authentication logs a warning, since the
per-token rate limit already bounds it (issue 523).
