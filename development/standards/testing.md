# Testing

Test taxonomy + conventions. The plan of an issue names the spec file of each slice. The *how*
lives here.

## Test layers

### 1. Unit - pure, fast, no I/O
The default. Anything that's a pure function of its inputs:
- OpenSearch **query/aggregation builders** (assert the emitted DSL body, not a live cluster).
- **Severity normalizer** (each scanner's vocab → `crit/high/med/low`, verbatim word preserved).
- **Projection logic** (decision precedence, `apply_both`, expiry).
- FE **option-builders** + emitted query params (Vitest).

No network, no containers. Milliseconds.

### 2. Integration - against a real OpenSearch container
For anything that depends on OpenSearch behavior (merge semantics, `update_by_query`, aggregations, CAS):
- Spin a **real containerized OpenSearch** (testcontainers / docker-compose); never mock the client.
- `pytest-asyncio` + `httpx.AsyncClient` against the actual FastAPI app + ingest path.
- Each test isolates by a unique `cluster_id` (and cleans up its indices).
- Covers: ingest round-trips, partial-doc merge, reconcile-on-commit, watermark guard, PIT two-step queries.
- **The cross-stack round trip** (issue 631) runs in `scanner-images.yml`'s compat job, per supported scanner
  version: the real binary scans the compat fixture, `scanner.compat --push` sends it through the real cycle
  to a real backend, and `development/scripts/check-ingest-roundtrip.sh` checks the run's stored
  per-severity counts, scan-event version and committed inventory against what was sent.

### 3. Golden fixtures - checked-in real data + expected output
The anti-regression backbone for the data model. A real scanner envelope (or sequence of scans) in, the
expected resulting docs out. **Mandatory golden coverage for:**
- Severity canonicalization (M0)
- Golden-envelope ingest round-trip (M1 gate)
- Partial-doc merge - scanner fields update, human fields untouched (M3)
- Out-of-order scan: older run never flips **or re-creates** a finding (M3/D40 keystone)
- Clean rescan: resolved CVE drops from "now" immediately; reads as clean at T, not as prior snapshot (M3/M8b)
- Reconcile-on-commit `present=false` (M3)

Fixtures live next to the code they test (`tests/fixtures/`), are real scanner output where possible, and are
regenerated only with an explicit, reviewed reason.

### 4. E2E smoke - Playwright, real browser against the running app
For the **frontend** only: a thin set of **smoke** flows (not exhaustive UI coverage) proving the app boots
and the core loop round-trips. Keep it to a handful of fast, deterministic specs in the `Frontend` CI gate:
- App shell loads, routes render, login works, and the **degraded banner** shows when `/readyz` is down (M9a).
- **Core triage loop:** findings grid lists from a seeded backend → open a finding → a triage action persists
  and the row re-renders (M9b - the core-loop gate).
- **Server-side-everything holds:** the grid pages/filters via backend queries (assert the network calls; no
  client-side counting).
Run Playwright against a **built frontend + a seeded backend** (real OpenSearch container). Playwright **MCP**
drives the same browser interactively during dev (authoring/debugging these specs) - see
[`TOOLING-AND-MCP.md`](../../docs/research/TOOLING-AND-MCP.md); the committed specs are what gate CI.

**As built — the spec suite (M9f slice 5, same CI job):** `frontend/playwright.config.ts` +
`frontend/tests/e2e/*.spec.ts` (`npm run test:e2e`), run right after the route walk against the
same built FE + seeded backend. Fifteen spec files, one worker, zero retries; among them: login
round-trip incl. the bad-password path (`app.spec.ts`) · the core triage persist-and-revert loop
(`triage-loop.spec.ts`) · the degraded banner via a `/readyz` route intercept — the mount-time
health check makes it deterministic, no 30s poll wait (`degraded-banner.spec.ts`) · grid
paging/filtering asserted on the NETWORK — cursor + filter params must ride backend requests
(`paging.spec.ts`) · the `/inspect` console loops and its capability gate (`inspect.spec.ts`) ·
the grid value actions' layout rules, which jsdom cannot judge (`value-actions.spec.ts`) · the
client-events beacon end to end: a real `logger.warn` in the built app, flushed by `pagehide`,
must appear as a `client.<name>` line in the backend's log (`beacon.spec.ts`; the job writes
backend stdout to `development/e2e/logs/backend.log` for it) · a slow cluster list, where the
Findings loading row must not pass for a data row, and a click whose page is still loading when
the list lands must still open it (`slow-cluster-list.spec.ts`, issues 786 and 669). Selectors and
login come from `scripts/walk.mjs` (still the one owner).

**A code error fails the test (issue 749).** Every spec takes `test` and `expect` from
`tests/e2e/helpers.ts`, whose `test` fails a test whose page logs `page error` or `app error`,
or throws an error it never catches. Those leave a working page on screen, so a spec's own
assertions pass over them. `page crashed` and `page failed to load` draw the error page and are
left to the specs. A test that causes a code error on purpose empties its `codeErrors` list.
`page-errors.spec.ts` proves the catching, and fails naming any spec that takes `test` or `expect`
from Playwright directly.

**As built (audit F-14/#383, CI job `frontend-smoke`):**
- **One walk, two consumers.** `frontend/scripts/walk.mjs` owns the route matrix (per-route
  *data-ready* selector, not the shell), the layout laws (no horizontal scroll · no off-viewport
  bleed outside a scroller · no sibling-card overlap) and the login flow. The CI gate
  (`scripts/ci-smoke.mjs`, run via `npm run smoke`) and the authoring visual rig
  (`scripts/visual-capture.mjs`, screenshots + HTML dumps + forced states, desktop **and** phone)
  both import it — a renamed selector breaks one file, loudly.
- **A grid row is a data row (issue 786).** The grids render their loading and empty messages as a
  table body row, and Findings shows "Loading findings…" until the cluster list arrives. A wait for
  `.tbl tbody tr` takes that message as a row, and a click on it goes nowhere. In the gate (the
  smoke and the e2e specs), a wait for or click on a grid row that could be such a message uses
  `DATA_ROW` from `walk.mjs`; `slow-cluster-list.spec.ts` delays the cluster list to hold that in
  place. The authoring rig (`visual-capture.mjs`) still has its own row waits.
- **The seed is the golden fixture.** `development/scripts/seed-smoke.sh` logs in as the bootstrap
  admin (rotating `must_change`), mints an ingest token and pushes
  `backend/tests/fixtures/envelope-trivy-golden.json` + the inventory-run commit. When the ingest
  contract changes, the fixture PR updates the smoke for free — never hand-edit a second envelope.
  It pushes that envelope to **two clusters** (issue 666): the fixture's own and a second id the
  script rewrites with `jq` at seed time (no second file), sorting after the first so a fresh
  browser still selects the golden cluster.
- **One click does what it says (issue 666).** After the walk, the smoke clicks every sidebar item,
  a fleet row of the cluster that is not selected, and (with `--core-loop`, since it writes) a
  saved view with a 7-day window, and requires each to land on its first click. A route walk by
  URL can't see a click whose state change cancels its own navigation; this phase can. It also
  opens an address no route matches and requires the not-found page inside the shell, with a
  working way back (issue 674: that address used to render an empty body).
- **Desktop-only gate** (ruling on #387): no phone layout exists yet; phone runs in the rig as
  warn-only screenshots and flips to gating when a responsive pass lands.
- **Determinism rules:** event-based waits only in the gate (no arbitrary sleeps beyond the
  route-settle pacing); deep interactions (dialogs, forced states, drafts) stay in the rig, out of
  the gate; the walk's PIT-budget env raise is documented in `docs/CONFIGURATION.md`, "CI gate values".

## Conventions
- **Deterministic:** freeze time; no calls to real registries/vuln-DBs; seed any randomness.
- **No fixed date where code compares it to the real clock (issue 533).** Such a test passes
  today and fails on a calendar day nobody chose. Two shapes: a *past* date read through a window
  measured from now (a `days` window, an SLA cutoff) ages out of it; a *future* date (an expiry,
  an `as_of`) stops being future. The clock may be read by the server, not the test (a route's
  default window, the SLA filter, the token mint's expiry check), so a test that never calls
  `datetime.now()` can still carry one. Fix, in this order: freeze a module-level `NOW` and inject
  it where the code takes a `now` / `t` / `anchor` (`test_query_approvals.py`); otherwise build
  the date from `datetime.now(UTC)` ± a delta. Never widen the window to buy time. Dates compared
  only with each other (ordering, equality, an explicit `t` into a pure function) are fine as
  literals.
  - **Frontend (issue 564):** the same rule, with the clock usually read inside the component or
    helper rather than the spec. Pass a frozen clock through the seam where one exists —
    `refNowMs(t, wallMs)`, `expiryStatus(…, nowMs)`, `bucketEndT(…, nowMs)`,
    `dbAgeSeconds(…, nowMs)`, `SlaCell`'s `nowMs` prop, `tokenStatus` / `mintExpiry(…, now)` —
    otherwise pin it with `vi.setSystemTime`, otherwise build the date from `Date.now()`. Note that
    `vi.useFakeTimers()` alone does **not** pin a day: its clock starts at the real now (it only
    controls how time advances).
  - **The net under the rule:** `.github/workflows/clock-drift.yml` runs weekly (and on any edit to
    itself) with the clock shifted forward — backend `+90d`, frontend `+365d` — so a date bomb
    inside that horizon fails there instead of on `main`. A red run is a finding, not a flake:
    fix the test per this rule. Reproduce locally with libfaketime:
    `faketime -f '+90d' uv run pytest …` (the `-f` is required). **Never against the shared dev
    store:** the admin-jobs tests run the real staleness sweep over it, and at a shifted clock
    every scanner looks silent, so every real finding goes `stale` (it happened 2026-09-26: 60,355
    findings). Point `JAVV_OPENSEARCH_URL` at a throwaway OpenSearch (tests and app both read it).
    If a shifted run did hit the dev store, run `uv run python -m backend.jobs.staleness` on the
    real clock — it reverts re-seen findings to their `pre_stale_status`.
- **Concurrency tests are required** where the design relies on it: concurrent ingest+triage (`retry_on_conflict`),
  out-of-order commits, reconcile-to-zero-conflicts.
- A bug fix starts with a **failing test that reproduces it**, then the fix (TDD).
- Tests assert **behavior/contract**, not internal call shapes, except for DSL-builder unit tests (whose
  contract *is* the emitted body).
- **Suite budget (#221, re-set from measurements in issue 550):** the backend Pytest step **< 5 min in
  CI** (162–257 s on `main`, 2026-09-27) and CI's own command locally (`pytest -n 2 -m "not serial"`,
  then `-m serial`) **< 7 min** (347 s on the dev store after the issue 550 fix). The old "< 90 s local"
  was never met. Bootstrap runs ONCE per session (`tests/conftest.py`); a new test file must not re-run
  `bootstrap()`/`seed_default_roles()` per test on the shared indices. If the suite drifts past the bar,
  that's a named regression — profile with `--durations=25` before adding capacity.
- **A prefixed bootstrap tears down with `drop_prefix` (`tests/os_env.py`, issue 550).** It removes
  the prefix's indices AND its index templates; templates outlive their indices. Teardowns that
  dropped only indices leaked ~1,236 templates per local run into the shared dev store, and 51k of
  them made every later test ~5× slower there while CI (always an empty store) never noticed.
  `real_os` already does this; a hand-rolled prefix fixture must call it too.
- **Store-exclusive tests get `@pytest.mark.serial`.** A test that mutates GLOBAL store state other
  tests depend on (disabling every enabled admin, wiping a shared index) poisons concurrent tests
  under `-n N` — this broke main's CI 2026-07-07 (an admin demote-race test 401'd a concurrent
  test's session). CI runs `-n 2 -m "not serial"` then `-m serial` alone; a plain local `pytest`
  is serial anyway. Prefer NOT needing the marker (unique users/cluster_ids, self-scoped sweeps) —
  it's for tests whose semantics genuinely require store-wide exclusivity.
