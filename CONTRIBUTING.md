# Contributing to JAVV

Thanks for your interest. JAVV is source-available under
[BSL 1.1](LICENSE) and developed by a small team, so this file covers what you need to land a change
without guessing at house conventions.

**Reporting a security vulnerability? Do not open an issue.** Follow [SECURITY.md](SECURITY.md).

## Before you start

- **Open an issue first** for anything beyond a small fix. JAVV follows a milestone plan with
  settled architectural decisions, and a change that cuts against one is painful to unwind after
  it is written. A quick issue saves you that.
- **Lost in the tree?** [REPO-MAP.md](REPO-MAP.md) maps every folder and suggests a reading order.
- Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Bug reports and feature
  requests use the issue forms; security reports go through [SECURITY.md](SECURITY.md) instead.
- The canonical design lives in [`docs/engineering/`](docs/engineering/):
  [PLAN.md](docs/engineering/PLAN.md) holds the decisions and milestones,
  [SPEC.md](docs/engineering/SPEC.md) the requirements.

## Getting set up

On a fresh Ubuntu host, install first, then verify:

```bash
bash development/setup/setup-dev.sh    # installs the pinned toolchain (idempotent)
bash development/setup/preflight.sh    # checks the tools are present and the runtime is up
```

`setup-dev.sh` reads every pinned version from [`versions.yaml`](versions.yaml), so it installs
exactly what CI uses. `preflight.sh` hard-fails on a missing tool and warns (without failing) when
Docker, a k3d cluster, or OpenSearch is not running yet, which is expected before you start them.

Then bring the stack up by following
[`development/RUNNING-THE-STACK.md`](development/RUNNING-THE-STACK.md), which covers the
backend-only path, the full end-to-end path with real scanners against k3d, and the frontend.

## Read this first, per area

Do not work from memory on these. Each area has a source of truth, and reviews check against it:

| Touching | Read first |
|---|---|
| Any index, mapping, rollover, or retention | [`docs/engineering/INDEX-MAP.md`](docs/engineering/INDEX-MAP.md) |
| HTTP endpoints or their contracts | [`docs/API.md`](docs/API.md) |
| Frontend UI or styling | [`frontend/DESIGN.md`](frontend/DESIGN.md) (binding); see *Building UI* below |
| Adding a log line, either stack | *Logging* below: shared library only, never `console.*` or `print` |
| Any config setting, env var, or threshold | [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) |
| Commits, branches, PRs | [`development/standards/git-workflow.md`](development/standards/git-workflow.md) |
| What "done" means | [`development/standards/definition-of-done.md`](development/standards/definition-of-done.md) |

## Hard constraints

These are settled and non-negotiable. A PR that violates one will be sent back regardless of how
good the code is:

- **No Redis, Kafka, RabbitMQ, or any external broker.** Coordination happens through OpenSearch;
  the backend runs its own background jobs on cron schedules, and only the scanners run as
  Kubernetes CronJobs (each cycle refreshes its vuln DB first).
- **Server-side everything.** Never ship raw findings to the client to compute counts. Every number
  and page comes from an OpenSearch aggregation or query.
- **Multi-tenant by immutable `cluster_id`.** Every read and export carries an explicit `cluster_id`
  filter, enforced in the query layer and never only in the UI.
- **Per-scanner is sacred.** Never dedupe or merge a CVE across scanners. Disagreement gets flagged,
  not resolved.
- **No hardcoded tunables.** A new setting is documented in
  [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) in the same PR. Hardcoding one fails review.
- **Use the shared loggers.** Backend uses `structlog.get_logger()`; frontend uses `@/lib/logger`
  (`console.*` is lint-banned). See *Logging* below for the shape.

## Building UI

[`frontend/DESIGN.md`](frontend/DESIGN.md) is the contract; this is the orientation.

**Reuse before you build.** Most surfaces are already solved: `frontend/src/components/ui/`
(UiButton, UiField, UiDropdown, UiSegControl, UiDateTime, ModalShell, SlideoverShell, ToastStack,
EmptyState, AppIcon), plus `components/chips/`, the filter module, the shared table skin with
GridPager, and the stat-band skin. **Grep first.** A parallel implementation of a solved control fails review
however well written.

**Where the visual grammar comes from**, in order: the prototype in `handoff/` (composition
reference for a screen, per DESIGN.md §8); then [ui.nuxt.com](https://ui.nuxt.com) and
[framework7.io](https://framework7.io): borrow *composition grammar* and *transition style*, then
re-express them in JAVV tokens, never the libraries themselves; then the vendored anti-pattern
detector on the changed files — `node .claude/skills/impeccable/scripts/detect.mjs <paths>`, never
`npx impeccable` (unpinned; a stale version has already invented a finding). DESIGN.md §9 lists the
ruled exceptions, which are settled.

**Tokens, not literals.** Colors come from the right bucket and the wrong bucket is a bug: brand
(`--coral`, `--amber`, `--teal`) is chrome and must never encode severity; `--sev-*` is data only;
`--state-*`/`--health-*`/`--kev-*` carry workflow and status. From script use `SEV_COLOR`/`CHART_SEV`
from `@/styles/tokens`. Two families only: Hanken Grotesk for UI, Spline Sans Mono for code-like data
(CVE ids, digests, timestamps, counts). No raw hex, no ad-hoc sizes, AA contrast is the floor.

**Every interactive element ships hover (wash *and* border, never border-only), pressed, and focus
states**, and rows get the hover wash too. Every screen needs its loading, empty and error states.
Counts and pages are server-side aggregations, never computed in the client.

## Logging

Structured and event-first on both stacks. The event name is a stable identifier; the variables are
fields, not prose baked into a sentence:

```python
log.info("scan done", image_ref=ref, findings=n, duration_s=1.2)  # queryable
log.info(f"scanned {ref} and found {n}")  # not
```

- **Backend:** `structlog.get_logger()`, configured once by `javv_common.logging.configure_logging()`.
  Bind who/where once per unit of work with `structlog.contextvars.bind_contextvars(...)` and every
  later line carries it. A processor redacts bearer tokens and sensitive keys on the way out, so do
  not pre-format a secret into a string and defeat it. Level via `JAVV_LOG_LEVEL`.
- **Frontend:** `@/lib/logger` (`logger.debug|info|warn|error(event, fields?)`). `no-console` is an
  ESLint **error**, so CI fails on a stray `console.log`.
- **Capped or streamed endpoints** log a warning and bump their metric when a cap trips (413/429),
  and count rows and bytes in the stream's `finally` so a client disconnect still records what left.

## Branches and commits

- Cut from `main`. Naming: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- **Conventional commits:** `type: subject`, where type is one of
  `feat`, `fix`, `chore`, `docs`, `test`, `refactor`. Imperative and present tense.
- **Subjects are lowercase even for identifiers** (`opensearch`, not `OpenSearch`). The header and
  every body line must be 100 characters or fewer. The local hook checks the same rules as CI.
- The body explains *why* when it is not obvious. Leave the *what* to the code.
- **Never use `--no-verify`.** If a hook fails, fix the cause.

> **Pre-commit trap:** when the `ruff format` hook reformats a staged file it exits non-zero and
> aborts the commit with HEAD unmoved. A commit is not committed until `git log --oneline -1` shows
> it. Running `uv run ruff format <file>` before staging avoids this entirely.

> **If you use Claude Code, two commands are blocked** by `.claude/hooks/guard_bash.py`, set up as a
> PreToolUse hook in the tracked `.claude/settings.json`. `git add -A|.` has swept gitignored files
> into commits here, and `pkill|pgrep -f` matches the agent's own wrapper process, killing its shell
> or hanging a wait loop. Stage explicit paths; find the PID with `ss -ltnp`. The guard tokenizes the
> command, so these strings stay fine inside a commit message or heredoc. Cases:
> `python3 .claude/hooks/test_guard_bash.py` (also run by pre-commit when the guard changes).

## Code comments

Default to none. Add one only when the *why* is non-obvious: a hidden constraint, a subtle
invariant, a workaround. Never explain what well-named code already says, and never reference
tickets, PRs, or review history in a comment. That context belongs in the PR and rots in the code.

## The gates

Run the exact commands CI runs, and treat the **exit code** as the gate rather than the printed
output. Tools can report passing tests and still fail the build.

```bash
# backend (from backend/)
uv run ruff check . && uv run ruff format --check .
uv run pyright                 # tree-wide, no path arguments
uv run pytest -n 2 -m "not serial" && uv run pytest -m serial   # what CI runs

# frontend (from frontend/)
npm run lint
npm run test:ci
```

The end-to-end suite is a separate job and is not part of `test:ci`. To run it locally you need the
browser, which `setup-dev.sh` does not install yet:

```bash
cd frontend && npx playwright install chromium --with-deps
npm run test:e2e
```

If you change a route or its parameters, regenerate the API contract in the same PR:

```bash
cd backend && uv run python -m backend.tools.export_openapi ../frontend/openapi.json
cd ../frontend && npm run gen:api
```

## Pull requests

- Target `main` and keep them reviewable. Small beats big.
- The description should say what changed and why, and tick off
  [the Definition of Done](development/standards/definition-of-done.md).
- Use `Closes #<issue>` so merging closes the tracking issue.
- CI must be green before merge.
- Changes carry their artifacts **in the same PR**: a new mutating route updates the RBAC/IDOR
  registry, a route change updates `docs/API.md` plus the regenerated client, a mapping change bumps
  `MAPPING_VERSION` and updates INDEX-MAP, and a new setting documents itself in CONFIGURATION.md.

## Licensing of contributions

JAVV is licensed under the [Business Source License 1.1](LICENSE), which converts to Apache 2.0 on
2030-06-10. By submitting a contribution you agree that it is licensed under those same terms.
