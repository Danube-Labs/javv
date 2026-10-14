# Definition of Done

The uniform bar **every** bolt clears before it merges. A bolt README adds only its *own* extra gates on top
of this - it does not repeat this list.

## 1. Static floor (must be clean)
- **Backend:** `uv run ruff check .`, `uv run ruff format --check .` and `uv run pyright` clean (from
  `backend/`, tree-wide, no path arguments: the commands that CI runs).
- **Frontend:** `npm run lint` (ESLint + eslint-plugin-vue + Volar) clean.
- No new warnings introduced in touched files.

## 2. Tests (see [testing.md](testing.md))
- New/changed logic has tests **first** (TDD - `test-driven-development` skill).
- The commands that CI runs are green. Backend, from `backend/`, against a store of its own:
  `uv run pytest -n 2 -m "not serial" --cov=src/backend --cov-fail-under=90`, then
  `uv run pytest -m serial`. Frontend, when the change touches it: `npm run test:ci` (the type check,
  Vitest and the coverage minimum).
- The bolt's specific **golden fixtures** (if any) are checked in and asserted.
- Meaningful coverage on the modules the bolt creates - not a number game, but no untested logic branches.

## 3. The bolt's PLAN gate passes
Each bolt maps to a milestone in [`PLAN.md` §8](../../docs/engineering/PLAN.md) that ends on a
**verifiable check** (e.g. M1's golden-envelope round-trip, M3's out-of-order-scan guard). That check is
demonstrated - by an automated test wherever possible.

## 4. Hard constraints honored (non-negotiable - see [CLAUDE.md](../../CLAUDE.md))
- **Per-scanner never merged** - disagreement flags only, never summed/averaged across Trivy+Grype.
- **Every read/export query carries an explicit `cluster_id` filter** (query layer, not UI).
- **Server-side everything** - no raw findings shipped to the client to compute counts.
- **No external broker** - coordination via OpenSearch; background jobs run inside the backend on
  `JAVV_JOB_<KIND>_CRON` schedules (D47); the k8s CronJobs are the scanners and the vuln-DB refresh.
- Indices touched? **Read [INDEX-MAP.md](../../docs/engineering/INDEX-MAP.md) first**; `dynamic:false`
  + explicit mappings; never aggregate on `text`.
- **Logging goes through the shared library only** (`libs/javv-common` structlog pipeline,
  [observability.md §1](observability.md)) - never `print()`, never `logging.getLogger()` in app code,
  never a private setup. Operator rigs under `development/e2e/` are the one exception.

## 5. Security
- Request models use `extra="forbid"`; `cluster_id` shape validated at the edge.
- Scanner/ingest input is **untrusted** (size + decompression caps, structured queries, no injection).
- No secrets committed (`.env*` git-ignored); tokens hashed (peppered SHA-256), passwords argon2id.
- `security-and-hardening` skill consulted for ingest (M1) and auth (M5a).

## 6. Design integrity (anti-drift)
- The bolt implemented what the canonical docs say. **A new decision is not invented in code** - if reality
  forces a change, update `PLAN`/`SPEC`/`INDEX-MAP` (with a decision id) *first*, then build.
- The bolt README's **Deliverables** all exist; **Out of scope** items were genuinely deferred, not silently built.
- **New config keys are tracked.** If the bolt introduces any configuration setting — a `JAVV_*` or
  OpenSearch env var, a `system-config` key, or a scanner scan flag — add it to
  [`docs/CONFIGURATION.md`](../../docs/CONFIGURATION.md) in the **same PR**: its default, how it's set,
  and whether it's UI-controllable. That file is the single tracker for every setting; leaving a new key
  out is config drift.
- **Routes are tracked.** A route added, changed (method/params/auth/capability), or removed →
  [`docs/API.md`](../../docs/API.md) updated in the **same PR** (same rule as config keys; the major
  audit found API.md at 6 of 34 routes because this line didn't exist). The capability column's source
  of truth is `tests/security/test_rbac_idor_contract.py` — the doc says what the registry says.

- **UI surfaces follow the binding UI standards.** Any bolt touching `frontend/` satisfies
  [`frontend/DESIGN.md`](../../frontend/DESIGN.md) and
  [`ui-foundations.md`](ui-foundations.md) — including the **Audit rules** (issue 343: accurate
  errors, contract guards, feedback within 200ms, restorable state, the D28 semantics surface,
  silence-is-a-bug, the Playwright zero-console-error + measured-parity gates) and the shared
  patterns they produced (`IngestLens`, provenance stamps on now-claims, `failureCopy`,
  `foreignQuery`/`ownQuery` URL sync in `src/system/globalUrl.ts`). Re-solving one of these ad hoc
  is drift.

## 7. Review & CI
- `code-review-and-quality` skill pass on the diff.
- One bolt (or thin slice) → one PR; CI green; reviewed before merge to `main`.
