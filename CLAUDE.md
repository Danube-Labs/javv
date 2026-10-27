# JAVV - working instructions for Claude Code

> Project-scoped guidance for building JAVV (this folder). The repo of record is **`javv`**
> (`git@github.com:Danube-Labs/javv.git`; named `javv-poc` until 2026-10-27, the old name redirects);
> this folder is the working copy. Canonical design
> lives in **`docs/engineering/`** (PLAN · SPEC · ARCHITECTURE); V3 and earlier are frozen for the
> evolution trail. UI reference: `handoff/docs/` (current; `v4/` is the frozen trail - a *reference point, not a 1:1 contract*). Research
> backing the v4 revision: `docs/research/`. **Lost? Read `REPO-MAP.md` first** - it maps every folder.
> **Resuming a session?** Read the newest file in `.claude/sessions/` (the last handoff) before acting;
> save one with `/save-context` before ending or compacting.
> **New to the project, or need the history?** `development/memory-bank/` has the brief, the timeline,
> the rulings that still apply and the open work.

## Read this FIRST (per task area)
Not everything is in this file — these are the sources of truth per area. Read the matching file
before changing anything in that area; don't guess or work from memory.

**Some of it loads itself.** `.claude/rules/*.md` carry `paths:` frontmatter and enter context
automatically when you touch matching files, at the same authority as this file — they are not
optional reading you can skip, they are this file's other half:
`ui-design.md` (frontend source) · `logging.md` (source, either stack) ·
`data-model.md` + `backend-engineering.md` (backend/scanner source).

| When you are... | Read FIRST |
|---|---|
| Touching **any index / mapping / rollover / retention** | `docs/engineering/INDEX-MAP.md` |
| Adding/changing **HTTP endpoints** or their contracts | `docs/API.md` (+ the router in `backend/src/backend/routers/`) |
| Working an **issue** (any feature or fix) | the issue and its plan comment: a spec file for each slice. The bolts in `development/bolts/` are frozen history (issue 1012) |
| Writing/modifying **frontend UI / styling** | `.claude/rules/ui-design.md` (auto-loads on frontend source) → `frontend/DESIGN.md` (binding: tokens, Hanken Grotesk, AA floor, §8 fidelity protocol — **a screen's grammar is the prototype's; substituting it needs a live operator ruling on a built specimen, §8.5** — §9 ruled exceptions) → `development/standards/ui-foundations.md` · `handoff/docs/SCREENS.md` |
| Adding/changing **any config setting, env var, or threshold** | `docs/CONFIGURATION.md` — document the setting there the **same PR**; hardcoding a tunable is a review-fail. Constants only when they mirror an already-documented cap (say so in a comment). |
| **Committing / branching / PRs** | `development/standards/git-workflow.md` (issue tracking, housekeeping, the pre-commit trap) |
| **Starting/stopping/operating** the dev stack | § *Running the stack* below → `development/RUNNING-THE-STACK.md` (paths A/B/F) |
| Adding **any log line** (either stack) | `.claude/rules/logging.md` (auto-loads on source) — shared library only; `console.*`/`print` are banned |
| Running/extending the **e2e rigs** | `development/e2e/README.md` |
| Verifying a change | `/qa` (delta-scoped) · UI deltas: `/visual-test` |
| Lost in the tree | `REPO-MAP.md` |
| **Planning work, proposing scope, or new to the project** | `development/memory-bank/` — `rulings.md` (what is already ruled), `active-context.md` (open and held work), `timeline.md` (what shipped, by release) |

## Code comments
Default to none; add one only when the WHY is non-obvious (hidden constraint, subtle invariant,
workaround). Never explain WHAT well-named code already says, and **never narrate tickets, PRs, or
review history in comments** ("fixes #123", "audit caught this") — that context belongs in the PR/issue
and rots in code. Applies to every tool and human alike.

**A bare anchor is the exception, and it must ride along with the WHY.** A comment that already
explains the non-obvious thing may name where it was settled — `issue 540`, `D42`, `M9e slice 3`,
`FR-19` — because that record is permanent and points at reasoning too long to inline. Spell it
`issue NNN`, never `#NNN` (the style rules test reads that as a hex color). The banned form is the
comment whose *content is* the history; an anchor with no explanation next to it is that.

## Stack (fixed)
Backend: **Python 3.12 · FastAPI (async) · AsyncOpenSearch (opensearch-py) · Pydantic v2**. Frontend:
**Vue 3 (`<script setup lang="ts">`) · PrimeVue · vue-echarts · Pinia · Vue Router**. Store: **OpenSearch,
single store**. Deploy: **docker compose, or Helm → k3s**. Scanners: **Trivy + Grype** (per-scanner, **never merged**).

## Running the stack (dev)
Full walkthrough incl. ingest, triage and the two-cluster loop: **`development/RUNNING-THE-STACK.md`**
(paths A / B / F, teardown §T, troubleshooting). The operating essentials:

```bash
# 1. store — wait for green OR yellow, don't race it (single-node dev settles at yellow, never green)
docker compose -f development/setup/opensearch-dev.yml up -d
until curl -s localhost:9200/_cluster/health | jq -e '.status=="green" or .status=="yellow"' >/dev/null; do sleep 3; done

# 2. backend (foreground; re-runs bootstrap, seeds admin + default roles, then serves)
cd backend
export JAVV_OPENSEARCH_URL=http://localhost:9200
export JAVV_SECRET_KEY='local-dev-pepper-change-me'            # hashes ingest tokens + session ids
export JAVV_BOOTSTRAP_ADMIN_USERNAME='admin'
export JAVV_BOOTSTRAP_ADMIN_PASSWORD='dev-admin-passphrase-12+'  # used once; new one needs 12+
export JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL=50   # default 10 starves UI navigation/rigs with 429s
export JAVV_SCHEDULER_ENABLED=false                # dev: no automatic sweeps on a store you want to keep
uv run python -m backend.core.bootstrap            # idempotent, versioned (MAPPING_VERSION)
uv run uvicorn backend.main:app --port 8000        # /docs = live API reference

# 3. frontend, second terminal
cd frontend && npm run dev                          # :5173, proxies /api + /auth to :8000

# health
curl -s localhost:8000/healthz            # liveness, no OpenSearch needed
curl -s localhost:8000/readyz | jq        # 200 = OpenSearch reachable
```

**Log in** (the bootstrap admin is born `must_change=true`; the session can do nothing else until
rotated): `POST /auth/login` -> `POST /auth/password` -> `GET /auth/me` shows `must_change:false`.
Same dance in the UI. Cookies land in `backend/cookies.txt` for curl work.

**Background jobs** are started by the backend itself, on the schedules in `JAVV_JOB_<KIND>_CRON`
(`docs/CONFIGURATION.md`, "Background jobs"; `JAVV_SCHEDULER_ENABLED=false` stops that, which is what you want on a dev
store whose data you care about: the lifecycle sweep drops history past retention and the staleness
sweep marks old findings stale). They can also be run by hand from `backend/`:
`staleness` · `lifecycle` · `findings_cleanup` · `cluster_retirement` · `report_drain` · `report_sweep` ·
`session_sweep` · `rebuild_state` (`uv run python -m backend.jobs.<name>`). Every one of them takes the
`system-jobs` lease for its kind (`jobs/registry.py` lists the eight), which also records the run;
`staleness`, `lifecycle` and `rebuild_state` share that lease with their Data inspector buttons,
and `report_drain` additionally claims each report under the reports lease.

**Stopping:** Ctrl-C the backend and vite, or kill by PID (`ss -ltnp`), **never `pkill -f`** (blocked
by the hook — it matches the tool's own wrapper). `docker compose … down` keeps data, `down -v` wipes it.
`k3d cluster delete alpha beta` for Path B. After a backend pytest run against this store, sweep the
residue: `development/scripts/clean-dev-store.sh` (keeps `{admin, rig}`).

**The two that always bite:** the dev backend has **no `--reload`** (restart it after backend edits or
new routes 404), and after any contract change regenerate the client *and* restart vite
(`export_openapi` -> `npm run gen:api`; a stale module graph 500s with "does not provide an export").

**A merge is a code change too.** Restart both after merging or switching branches, not just after
editing — the running processes keep whatever code they started with. This is worse than a 404: a
param the running backend doesn't know is **silently dropped** by FastAPI, so a negation filter comes
back unfiltered and reads as a product bug in a feature that is actually fine. Ask the age of the
process before debugging behaviour (`ps -o lstart -p <pid>`), and confirm what it actually serves:
`curl -s localhost:8000/openapi.json | jq '.paths["<route>"].get.parameters[].name'`.

## Hard constraints (do not violate)
- **No Redis/Kafka/RabbitMQ/external broker.** Coordination via OpenSearch. The backend runs its own
  background jobs on cron schedules from env vars (`jobs/scheduler.py`, issue 691): a deployment is one
  backend container and one frontend container, with no CronJob and no second backend for jobs.
  Scanners are the exception: they stay CronJobs in the monitored clusters.
- **Server-side everything** - never ship raw findings to the client to compute counts; every number/page
  comes from an OpenSearch aggregation/query.
- **Multi-tenant by immutable `cluster_id`** - every read/export query carries an explicit `cluster_id`
  filter (enforced in the query layer, never UI-only). Route indices on `cluster_id`, never the
  relabelable `cluster_name`.
- **Per-scanner is sacred** - never dedupe/merge a CVE across scanners; disagreement flags only.
- **Scanners are self-built images** - one JAVV-built Dockerfile per scanner (`Dockerfile.trivy`,
  `Dockerfile.grype`, pinned scanner version + our entrypoint), run as CronJobs. **Never the Trivy
  Operator / Starboard or any third-party scanner operator** - own the images for version/supply-chain control.
- **Scanner version = build-time, operator-swapped (D41).** Version is pinned in the Dockerfile `ARG`; JAVV
  **publishes** the pinned images and the operator changes versions by **swapping the published image tag**
  (GitOps). **No live in-app "version select"** and JAVV **never writes to monitored clusters**. "Multiple
  versions" = a **CI compatibility gate**, not a runtime switch; the envelope stamps `scanner_version`
  (+ vuln-DB version) for read-only display + audit.
- **Externally-owned versions live in `versions.yaml` (D42).** Scanners + OpenSearch (toolchain later) are
  pinned in one root file (Renovate-watched; drift-checked into the Dockerfiles/compose by
  `development/scripts/check-versions.sh`); README *Supported versions* renders it. Edit there, not in the
  consumers. Code libs (pyproject), GH Actions, pre-commit hooks stay native — don't centralize those.
- **Diagrams are Mermaid** (working-agreement). `.deprecated/docs/deprecated/original_notes_for_app.md` is read-only.

## Hard-won reflexes (each line has bitten ≥ 2 sessions — check them, don't rediscover them)

> Two of these are now **mechanical**, not advisory: `.claude/hooks/guard_bash.py` (a PreToolUse hook,
> set up in `.claude/settings.json`) refuses `git add -A|.` and `pkill|pgrep -f` before they run. It
> tokenizes properly, so those strings are still fine inside a commit message or a heredoc. Cases:
> `python3 .claude/hooks/test_guard_bash.py`.

**Verify, don't trust the happy path**
- A commit isn't committed until `git log --oneline -1` shows it — pre-commit hooks reformat-and-abort
  silently ("Everything up-to-date" on push = it never landed). A merge isn't merged until
  `gh pr view N --json mergedAt` is non-null — `gh pr merge` on a behind branch no-ops with a clean exit.
- Exit codes are the gate, never printed output: vitest reports "N passed" and still fails CI on
  unhandled rejections; run the EXACT CI commands (`npm run lint` / `npm run test:ci` from `frontend/`,
  tree-wide `pyright` from `backend/` with no path args, full pytest).
- Status-code checks lie — the SPA answers 200 HTML for ANY GET; verify proxied responses by body.
- The Bash cwd drifts after `cd`-compounds — re-anchor to the repo root before git/npm; stage explicit
  paths, never `git add -A` (it has swept gitignored files into commits).
- No stacked PRs, ever: every slice bases on `main`; hold finished work rather than stacking
  (merging a stacked base closed its child once, and one PR merged INTO a feature branch).

**Reuse before writing — code and design (grep first, build second)**
- Before any new control/panel/helper: the kit probably has it — `components/ui/`, `components/chips/`,
  the M9a filter module, the shared table skin + GridPager, the stat-band skin, `query/paging.py`, the bulk
  helpers. A raw parallel implementation of a solved surface fails review.
- UI grammar comes from the prototype and research, never memory — see § *UI work* below.
- **VISUAL FEEDBACK IS A MUST**: every interactive element ships hover (wash + border, never
  border-only), pressed and focus states; rows get the hover wash too.
- After ANY design pass on a view, `wc -l` it — passes accrete markup; crossing ~500 lines means
  extracting self-contained panels in the same PR (issue 384's F-15 pattern: DataOpenSearchView
  quietly hit 721 before anyone re-measured).

**Contract changes carry their artifacts in the same PR**
- New mutating route → the RBAC/IDOR registry (`tests/security/test_rbac_idor_contract.py`).
  Any route/param change → `docs/API.md` + regenerated `frontend/openapi.json` + `npm run gen:api`
  client (the contract gate diffs the snapshot). Mapping change → `MAPPING_VERSION` bump + INDEX-MAP.
  New setting → CONFIGURATION.md (§ "Read this FIRST" table).
- New field on a shared shape (SearchFilters and friends) → sweep every consumer and the parity
  guards; targeted test runs have missed these.
- Scanner vocabulary is canonicalized at every boundary (`canonical_severity()`); seed tests with the
  raw verbatim casing, never pre-canonicalized — self-consistent tests hide the bug (bit twice).

**Environment quirks (they will not fix themselves)**
- Kill dev processes by PID/port (`ss -ltnp`), NEVER `pkill -f` (it matches its own wrapper). The dev
  backend has no reload — restart it after backend edits **or a merge/branch switch**, or new routes
  404 and unknown params are silently dropped (see § *Running the stack*); restart vite after
  `gen:api` (stale module graph "does not provide an export").
- Backend pytest against the shared dev store leaves residue (`nu-*`/`ext-*`/`0-list-*` users,
  `t-*` indices) — sweep AFTER the last run, keep `{admin, rig}`.
- Commit subjects: lowercase first word even for identifiers (`m5c`, `opensearch`), header **and every
  body line** ≤ 100 chars, types `feat|fix|chore|docs|test|refactor` only. The local commit-msg hook
  mirrors CI commitlint, so a rejection locally is the same one CI would give.
- `#NNN` in a code comment reads as a hex color to the style rules test — write "issue NNN".

## UI work
The settled UI rulings (grammar sources incl. ui.nuxt.com + framework7.io, the color buckets,
the two type families, the kit inventory, the lens contract) live in
**`.claude/rules/ui-design.md`**, which loads automatically when you touch frontend source.
Contract of record: **`frontend/DESIGN.md`** (§8 fidelity · §8.5 built-specimen rulings ·
§9 ruled exceptions · **§10 new panels are self-contained lenses**).

## Use these skills (when the work matches)
Invoke the matching skill before starting that kind of work:
- **incremental-implementation** - default for any multi-file feature. Build in thin vertical slices.
- **test-driven-development** - any logic/bugfix. Backend query-builders + aggregation correctness +
  the projection engine especially (golden fixtures).
- **api-and-interface-design** - designing FastAPI endpoints / Pydantic schemas / the backend↔Vue contract.
- **frontend-ui-engineering** - any Vue/PrimeVue screen or the new panels (Data Retention, CVE audit).
- **impeccable** (`.claude/skills/impeccable`) - design critique/typography/hardening/layout for any
  UI surface; run its **vendored** scanner (`node .claude/skills/impeccable/scripts/detect.mjs
  <paths>`) over changed frontend files as part of the authoring loop — **never `npx impeccable`**,
  which is unpinned and has already served a stale version whose retired rule invented a finding
  (DESIGN.md §9; ruled exceptions live there — don't relitigate).
- **security-and-hardening** - the ingest surface (untrusted scanner input), RBAC/authz, OpenSearch DSL
  construction. Mandatory for M1 ingest and M3 auth.
- **performance-optimization** - OpenSearch query/agg/shard tuning, large-table FE render. Measure first.
- **code-review-and-quality** - before merging any change.
- **git-workflow-and-versioning** - commits/branches throughout. **Track each feature on its GitHub
  issue**: the plan with a spec file per slice first, then comments at kickoff / blocker / scope-change /
  done, and `Closes #<n>` in the PR that finishes it. A ruling that stays in force also goes in
  `development/memory-bank/rulings.md`. Full convention: `development/standards/git-workflow.md`
  § "Tracking work".
- **ci-cd-and-automation** - the Helm→k3s pipeline + ruff/pyright/pytest CI gates.

## Tooling to lean on (see `docs/research/TOOLING-AND-MCP.md` for install)
- **Serena MCP** - symbol-level nav/edit across Python+TS. Use instead of grep-and-replace for refactors.
- **OpenSearch MCP** - introspect real mappings + run query-DSL to verify aggregations *before* adding
  them into FastAPI. The agent should read the schema, not guess it.
- **Context7 MCP** - pull version-current docs for Pydantic v2 / PrimeVue / vue-echarts / AsyncOpenSearch
  before generating API code.
- **Static floor:** ruff + pyright (Python); vue-tsc (Volar) + ESLint/oxlint + stylelint + the style rules test (Vue — all via `npm run lint` / `npm run test`). Run them; fix what they flag.
- **@hey-api/openapi-ts** - regenerate the Vue TS client from FastAPI's OpenAPI so types can't drift.
- **Kubernetes MCP / Playwright MCP** - once there's a deploy loop / UI to drive.
