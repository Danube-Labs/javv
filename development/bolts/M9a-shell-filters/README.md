# M9a - Shell + tokens + filter module + typed API client

**Status:** tracked in [#35](https://github.com/Danube-Labs/javv/issues/35) — live status on the GitHub issue/board

## Goal
The frontend foundation: app shell (router, layout, global time-travel picker host), design tokens,
and the **reusable `fields`-config filter module** — a single config that drives both the FacetRail
(faceted aggregations) and the FilterBar (active-filter chips + query params). Also the **owner of the
generated, typed TS API client** (`@hey-api/openapi-ts` off FastAPI's OpenAPI) so the FE↔BE contract
cannot drift silently.

**Canonical refs:** [`PLAN §8 M9a`](../../../docs/engineering/PLAN.md) (line 675) ·
`SPEC` FR-12 (faceted-by-scanner filters), FR-23 (global time picker / whole-app rewind), FR-18
(RBAC-gated client) · [`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (read-only; no index
owned) · decisions D27 (DataTable lazy default), D28 (global rewind picker), D33 (capability-based RBAC).
AUDIT items folded in: **I4** (owns `@hey-api/openapi-ts` client generation), **I7** (CI contract gate).

## Depends on
- **M6** — read/reporting API (faceted-by-scanner search + composite aggregations + `T=now` reads).
  M9a generates its typed client from M6's OpenAPI and the FacetRail consumes M6's aggregation shapes.

## Deliverables
Files this bolt creates — **in the layered tree, not here** (paths proposed):
- `frontend/src/main.ts`, `frontend/src/App.vue` — bootstrap (Vue 3 `<script setup lang="ts">`, PrimeVue,
  Pinia, Vue Router).
- `frontend/src/router/index.ts` — route table with lazy-loaded route components; placeholder routes for
  Findings (M9b), Overview/Images (M9c), Audit (M9d), Settings (M9e).
- `frontend/src/layouts/AppShell.vue` — top bar + nav rail + content slot; hosts the global time picker.
- `frontend/src/components/system/BackendHealthBanner.vue` — **global degraded banner**: polls `/readyz`,
  and on `503 degraded` (or any API 503-envelope) shows a persistent, dismissible-but-recurring
  *"Search backend unavailable — check OpenSearch health"* bar across every screen; auto-clears when
  `/readyz` returns `200`. The app stays usable (chrome up), data areas show the degraded state rather than
  blank/cryptic errors. Reads the M1 error envelope (`status`/`title`/`request_id`); see
  [`standards/observability.md`](../../standards/observability.md).
- `frontend/src/components/system/ScannerFreshnessBanner.vue` — **the "data as of T; scanner silent since
  T′" banner (SPEC FR-6 / D20; audit m-7).** Shown on inventory views when a `(cluster, scanner)` is silent
  (read-time, computed from `system-tokens.last_ingest_at` — **not** written by the M3 staleness sweep).
  Reads **`GET /api/v1/scanners/freshness`** (per-cluster/scanner `last_ingest_at` + derived silent-since
  — built as its own small backend PR *before* this bolt, **issue #218**; the earlier wording implied an
  existing "M6 freshness read" that never existed — major-audit finding 04 §4); this bolt
  owns the shared banner component (sibling to `BackendHealthBanner`), M9b/M9c mount it. *(Ownership was
  unassigned — the staleness sweep correctly leaves the banner as a read-time view; landed here because
  M9a owns the app-shell global banners.)*
- `frontend/src/components/time-travel/GlobalTimePicker.vue` — days/hours/minutes-ago picker, default `now`
  (D28/FR-23). Emits a normalized `T` (`null` = now).
- `frontend/src/stores/timeTravel.ts` — Pinia store holding global `T`; every data-fetching store/composable
  reads it so one picker rewinds the whole app (D28).
- `frontend/src/styles/tokens.css` (+ `tokens.ts`) — **the binding design-token source of truth** per
  [`standards/ui-foundations.md`](../../standards/ui-foundations.md) (promote the DESIGN_SYSTEM values once;
  components use tokens only). Also wire **stylelint** into the `Frontend` CI gate to fail on raw
  hex / non-token fonts. design tokens (color/space/type/severity palette),
  PrimeVue theme bridge. Single source for severity colors used by M9b/M9c.
- `frontend/DESIGN.md` — the **agent-facing design contract**, written once the tokens are promoted:
  token tables (light + dark values side by side), do's/don'ts naming the exact anti-patterns
  (raw hex → token; hand-rolled severity color string → the badge/token helpers; `dark:`-style
  overrides where a token already handles theming), an **agent quick reference** of the ~15
  most-used tokens, and copy-pasteable component patterns. The substance already lives in
  `ui-foundations.md` + `DESIGN_SYSTEM.md` + `SCREENS.md` — this is the operational condensation
  a cold session reads before touching any screen, kept in lockstep with `tokens.css`.
- `frontend/tests/style-ratchet.test.ts` — the **style ratchet** (sibling to the stylelint gate):
  fails CI when a component **adds** a hand-rolled severity/status color that bypasses the token
  map / badge helpers; the recorded baseline may only shrink, never grow. stylelint catches raw
  hex/fonts — the ratchet catches *semantic* bypasses (a literal red where the severity token belongs).
- **Filter module (the reusable core):**
  - `frontend/src/filters/fields.config.ts` — the `fields` config: per-filter `{ key, label, type
    (terms|range|date|bool), facetable, scanner_faceted }` for namespace / image / tag / severity /
    timestamp / **scanner** / state / assignee / KEV / fix-available / **disagree** (FR-12).
  - `frontend/src/filters/buildFilterQuery.ts` — **pure option-builder**: `fields`-config + active
    selections → the emitted query-param object sent to M6 (`cluster_id` always present; severity
    case-insensitive per D16). This is the primary unit-tested surface.
  - `frontend/src/components/filters/FacetRail.vue` — renders facet buckets from M6 aggregations
    (faceted-by-scanner; per-scanner buckets **never summed**).
  - `frontend/src/components/filters/FilterBar.vue` — active-filter chips, add/remove, clear-all.
  - `frontend/src/stores/filters.ts` — Pinia store: active selections, serialized to/from the URL query.
- **Typed API client (I4):**
  - `frontend/openapi-ts.config.ts` — `@hey-api/openapi-ts` config pointed at M6's OpenAPI.
  - `frontend/src/api/generated/**` — **generated + committed** typed client (checked in).
  - `frontend/package.json` script `gen:api` (regenerate) wired so CI can diff it.
- `frontend/src/composables/useApi.ts` — thin wrapper injecting `cluster_id` + global `T` into every call;
  RBAC-capability guards (D33) for gating UI.

## Definition of Done
Everything in [`definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each a gate, not a promise):
- **Contract gate (I4+I7):** `npm run gen:api` regenerates the client and **CI fails if `git diff` is
  non-empty** — a backend Pydantic change without a client regen breaks the build, not runtime.
- **PLAN gate:** one `fields` config drives **both** FacetRail and FilterBar — adding a filter to the config
  surfaces it in both with no component edits (proven by a test that adds a field and asserts both render it).
- `buildFilterQuery` emits `cluster_id` on **every** query and never sums per-scanner buckets (FR-12, per-scanner sacred).
- Global time picker sets `T` in the Pinia store; changing it re-triggers dependent fetches (`T=now` vs `T<now`
  branch is observable in the emitted params).
- App shell renders, routes lazy-load, ruff-equivalent FE gates pass (ESLint + Volar + Vitest green).
- `frontend/DESIGN.md` exists and matches `tokens.css` (spot-check: every token family in the CSS has
  a table row); the **style ratchet** test is wired into the `Frontend` CI gate with an empty baseline.

## Tests to write
See [`testing.md`](../../standards/testing.md). FE rule: **unit-test the option-builders + emitted query params
as pure units** (Vitest).
- **Unit (pure, primary):**
  - `buildFilterQuery` — config + selections → exact emitted query-param object (incl. `cluster_id` always,
    `T` passthrough, case-insensitive severity, per-scanner facets kept separate). This is the contract.
  - `fields.config` round-trip: config → FilterBar chips → URL serialize/deserialize → identical selections.
  - time-travel store: setting `T` produces `T=now` (omit param) vs `T<now` (explicit `T`) in emitted params.
- **Component (vue-test-utils):** FacetRail renders per-scanner buckets without merging; FilterBar add/remove
  updates the store; one-config-drives-both assertion.
- **Contract:** a committed snapshot/CI step proving the generated client matches current OpenAPI (the I7 gate).
- **Playwright (E2E):** the shell-loads/login + degraded-banner smoke lives in **M9f's E2E suite** ([`testing.md §4`](../../standards/testing.md)) — note only here.

## Out of scope (defer)
- Findings grid + triage → M9b. Overview/images/dashboards → M9c. Audit/approvals → M9d. Settings panels → M9e.
- Global search, bell notifications, saved views, empty/cold-start states → M9f.
- OpenAPI **breaking-change** classifier (`oasdiff`, AUDIT I8) → CI/process work, not this bolt.

## Updates
- **2026-07-10 — post-M9b foundation extensions (#319, PRs #320/#323):** the shell sidebar is
  now **collapsible to a 64px icon rail** (Nuxt UI sidebar grammar on our tokens, state
  persisted in localStorage, `aria-expanded` toggle; the width transition is the ONE ruled
  layout animation — DESIGN.md §9). And the foundation gained a **motion layer**: motion tokens
  (`--ease-out`, `--dur-quick`, `--dur-panel`) in `tokens.css` + shared `t-pop`/`t-fade`/
  `t-modal` Transition classes in `base.css`, baked into UiDropdown (menus animate both ways,
  `closed` fires post-leave) and ModalShell (entrance only — unmount resets consumer state);
  banners crossfade. Feedback text (errors/success notes) stays deliberately instant. Contract:
  DESIGN.md §5 "Motion"; ruled exceptions §9.
- **2026-07-07 — backend↔UI drift rulings (major audit #224, 05 §C-1/§A-4):** the global time
  picker ships here but **`T<now` works only after M8b** — if M9 starts before M8b lands, the
  picker needs a "history available after M8b" state (the `as_of` seam 501s cleanly today; check
  the milestone order at kickoff, currently M8→M9 makes this moot). And the shell's RBAC gating
  reads **capabilities from `/auth/me`** (`viewer/triager/security_lead/admin` bundles, D33) —
  never role names.
- **2026-07-07** — **freshness endpoint dependency made concrete (major audit, 04 §4 / 05 §D-1):**
  the `ScannerFreshnessBanner` deliverable referenced a "small M6 freshness read" that was never
  built. The real dependency is **`GET /api/v1/scanners/freshness`**, tracked as **#218** and
  scheduled *before* this bolt (audit execution order, PR 3). Deliverable text amended above.
  Further M9-wide backend↔UI drift rulings land right before kickoff via #224
  (`.deprecated/docs/audits/major_audit/05-backend-ui-drift-m9.md` §E).

- **2026-07-07 — v5 design rulings (#237) + handoff/docs landed (#235):** the design contract for
  this bolt is now `handoff/docs/SCREENS.md` (Global chrome, Login) — v4 stays the visual
  base (DESIGN_SYSTEM/BRAND/ui-foundations unchanged). Rulings touching M9a: **A-1** severity
  vocabulary in the reusable filter module is lowercase + a **`negligible`** bucket (muted, never
  red); **A-4** all gating from `/auth/me` capabilities (settled). The topbar cluster switcher
  reads the **M8c cluster registry** (`GET /api/v1/clusters`, D-5 ruling) for display names.

- **2026-07-08 — dev-workflow deliverables added (#284):** two new deliverables —
  **`frontend/DESIGN.md`** (the agent-facing design contract condensed from the tokens) and the
  **style-ratchet test** (CI fails on *added* hand-rolled severity/status colors; baseline only
  shrinks) — plus a DoD line for each. Repo-level **`/visual-test`** (authoring-time Playwright-MCP
  screenshot loop against the live dev stack) and **`/qa`** (delta-scoped verification) commands
  landed with #284 and apply to every M9 bolt from this one on.

- **2026-07-09 — filter-module contract rulings (slice 4):** the `fields` config mirrors the
  **shipped M6 contract**, not the prototype's local filtering — only `severity`/`state` are
  multi-value params; `scanner`/`ptype`/`namespace`/`image_repo`/`assignee` are **single-valued**
  (multi-select in the prototype → single-select here; a second selection *replaces*, and
  `buildFilterQuery` throws rather than silently joining). KEV / fix-available / disagree are
  three boolean params grouped as the prototype's one "Attribute" facet. Facet counts render the
  **server's numbers verbatim** (per-scanner split as tooltip, never combined client-side, FR-12).
  Fields without a backend aggregation (namespace/image/assignee) are FilterBar-only free-text —
  no invented client-side buckets.

- **2026-10-20 — several values for namespace, package type and assignee (issue 949):** the
  backend now takes lists for `namespace`, `ptype`, `assignee`, `image_repo`, `cve_id` and
  `package_name` (PR 953). The Findings config gives `multi: true` to `namespace`, `ptype` and
  `assignee`, so a second pick adds the value. Their facets count without their own field's
  filter, so the other values stay in the list. Image, CVE and Package follow in issue 949 PR C,
  with the control ruled on 2026-10-21 (a list of values under the edit box). `scanner` stays one
  value.

- **2026-10-21 — several typed values for image, CVE and package (issue 949 PR C):** the three
  text fields get `multi: true`. The operator ruled the control on a built specimen: Enter in the
  edit box adds the value to a list under the input (`FilterValueRows`, shared with the facet
  values), and a click removes it. A table cell pick adds the value. The URL, the saved views and
  the query keep every value. On Findings a filter stops at 32 values (the API cap) and says so
  in the edit box, and in the rail for a facet field; a pasted comma list adds each value. A
  refused cell pick at the cap shows nothing yet (known gap on the PR).

### 2026-10-26 — Frozen as history

The bolts M0 to M10 ended on 2026-10-09. This file is history now, not the spec of record. New work
follows one GitHub issue for each feature, with the plan and a spec file for each slice on the
issue. The timeline, the rulings that still apply and the open work are in the
[memory bank](../../memory-bank/README.md) (issue 1012).

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
> **Frontend analog (M9a+):** `logger` from `frontend/src/lib/logger.ts` — structured, leveled,
> backend-shaped lines; raw `console.*` in app code is ESLint-banned. Threshold: `VITE_LOG_LEVEL`
> ([CONFIGURATION.md §2b](../../../docs/CONFIGURATION.md)); never log tokens/cookies/bodies (NFR-5).

- **2026-07-09 — global time control re-ruled (operator, PR #300): ONE Kibana-style RANGE.**
  The two-concept design (time-travel T + trend window, audit C-1 "visibly distinct controls")
  confused in practice — two lookalike time menus, one driving nothing until M9c. Re-ruled as a
  single range: the range END is the whole-app `as_of` (minute-precise; amber control + banner
  when in the past), the SPAN is the trends `days` param (whole days 1–365 — sub-day quick-selects
  round the chart span up to 1 day; the label keeps the exact choice). C-1's intent (don't
  conflate state-at-T with the window) is carried by the control's own copy: "tables show state
  at the end of the range; charts aggregate the span." All time display is 24-hour.

- **2026-07-10 — VISUAL FEEDBACK IS A MUST (operator ruling, applies retroactively to every M9a
  surface):** every interactive element ships visible hover (wash + border, never border-only),
  pressed and focus states — global rule in `frontend/src/styles/base.css`, binding text in
  `frontend/DESIGN.md` §2. Feedback-less controls fail review.
