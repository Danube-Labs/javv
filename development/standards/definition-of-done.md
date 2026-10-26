# Definition of Done

The uniform bar that **every** PR clears before it merges. The plan of an issue adds only its *own* extra
gates on top of this - it does not repeat this list.

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
- The change checks in its **golden fixtures** (if any), and its tests assert them.
- Meaningful coverage on the modules the change creates - not a number game, but no untested logic branches.

## 3. The gate of each slice passes
The plan of an issue gives each slice a **verifiable check**: its spec file
([git-workflow.md](git-workflow.md), "Tracking work"). An automated test shows that check wherever
possible. The bolts M0 to M10 each ended on the gate of a milestone in
[`PLAN.md` §8](../../docs/engineering/PLAN.md), for example M3's out-of-order-scan guard.

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
- `security-and-hardening` skill consulted for each change to the ingest or to sign-in and access.

## 6. Design integrity (anti-drift)
- The change implements what the canonical docs say. **A new decision is not invented in code** - if reality
  forces a change, update `PLAN`/`SPEC`/`INDEX-MAP` (with a decision id) *first*, then build.
- The **slices** of the issue plan all exist. The issue defers its out-of-scope items, and the change does not build them.
- **Track each new config key.** If the change introduces any configuration setting — a `JAVV_*` or
  OpenSearch env var, a `system-config` key, or a scanner scan flag — add it to
  [`docs/CONFIGURATION.md`](../../docs/CONFIGURATION.md) in the **same PR**: its default, how it's set,
  and whether it's UI-controllable. That file is the single tracker for every setting; leaving a new key
  out is config drift.
- **Routes are tracked.** A route added, changed (method/params/auth/capability), or removed →
  [`docs/API.md`](../../docs/API.md) updated in the **same PR** (same rule as config keys; the major
  audit found API.md at 6 of 34 routes because this line didn't exist). The source
  of truth is `tests/security/test_rbac_idor_contract.py` — the doc says what the registry says.

- **UI surfaces follow the binding UI standards.** Any change touching `frontend/` satisfies
  [`frontend/DESIGN.md`](../../frontend/DESIGN.md) and
  [`ui-foundations.md`](ui-foundations.md) — including the **Audit rules** (issue 343: accurate
  errors, contract guards, feedback within 200ms, restorable state, the D28 semantics surface,
  silence-is-a-bug, the Playwright zero-console-error + measured-parity gates) and the shared
  patterns they produced (`IngestLens`, provenance stamps on now-claims, `failureCopy`,
  `foreignQuery`/`ownQuery` URL sync in `src/system/globalUrl.ts`). Re-solving one of these ad hoc
  is drift.

## 7. Review & CI
- `code-review-and-quality` skill pass on the diff.
- One issue → one or more PRs, each with one or more slices. CI is green. A reviewer reads the PR before it merges to `main`.
