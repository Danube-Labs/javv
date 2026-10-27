# M9c - Overview / all-clusters / images (+ point-in-time image view)

**Status:** tracked in [#37](https://github.com/Danube-Labs/javv/issues/37) — live status on the GitHub issue/board

## Goal
Dashboards and the image surface: the **Overview** (current-state severity/trend summaries), the
**all-clusters** view, and **per-image drill-down** with a Trivy/Grype scanner dropdown and per-scanner
finding table — fully **time-travelable** via the global picker (FR-14/FR-23), including the
**point-in-time image view** (per-digest sub-timelines: which CVEs on which digest at T). All numbers come
from server-side aggregations / M8b reconstruction; nothing is computed client-side.

**Canonical refs:** [`PLAN §8 M9c`](../../../docs/engineering/PLAN.md) (line 677) ·
`SPEC` FR-12 (dashboards), FR-14 (per-image report, time-travelable), FR-23 (whole-app rewind +
**all-clusters cost guardrail**) · [`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md)
(`javv-scan-events` trends; `javv-finding-occurrences` for as-of-T; **`javv-metrics-*` is v1.1/deferred,
no bolt**) · decisions D28 (rewind), D38/M16 + D39/M11-r2 (historical all-clusters limited in MVP).
AUDIT item folded in: **I3** (`javv-metrics` deferred to v1.1; all-clusters/historical degrades gracefully).

## Depends on
- **M9b** — shell, filter module, findings components (the image table reuses finding rows / disagreement
  views; per-scanner sacred).
- **M8b** — point-in-time query API: forward ("digest X at T") + the symmetric two-step catalog query;
  `runtime_inventory_at_T` vs `vulns_as_scanned_at_T` (kept distinct, FR-14).

## Deliverables
Files this bolt creates — **in the layered tree, not here** (paths proposed):
- `frontend/src/views/OverviewView.vue` — current-state KPIs + trend charts (single-cluster default).
- `frontend/src/views/AllClustersView.vue` — cross-cluster current-state roll-up; **degrades for `T<now`**
  (see DoD / Out-of-scope).
- `frontend/src/views/ImageDetailView.vue` — per-image (`image_digest`) drill-down; Trivy/Grype **scanner
  dropdown**; per-scanner verbatim-severity finding table (reuses M9b components); `repo:tag`→digest nav (F3).
- **Charts (ECharts, per FE rules):**
  - `frontend/src/components/charts/SeverityTrendChart.vue`, `OverviewSummaryChart.vue` — use
    `shallowRef` + `markRaw` for the ECharts option/instance; **manual ECharts module imports** (no full bundle).
  - `frontend/src/charts/buildSeverityTrendOption.ts`, `buildOverviewOption.ts` — **pure option-builders**
    (data → ECharts option). Primary unit-tested surface.
- **Query/param builders (pure):**
  - `frontend/src/charts/buildTrendQuery.ts` — trend params from `javv-scan-events` (`cluster_id`, range, `T`).
  - `frontend/src/images/buildImageAtTQuery.ts` — emits the M8b two-step params: `runtime_inventory_at_T`
    (latest `status=committed` inventory-run ≤ T by `inventory_order`) and `vulns_as_scanned_at_T`
    (max-`scan_order` committed run ≤ T, then occurrences via R-CATALOG). **Kept as two distinct results,
    never conflated** (D38/H6).
- `frontend/src/components/images/DigestSubTimeline.vue` — per-digest sub-timeline; marks "image build
  changed here" rather than a silent gap (F3); "not yet scanned then" when no committed snapshot ≤ T.
- `frontend/src/components/dashboards/LimitedHistoricalNotice.vue` — the **graceful-degradation banner** for
  all-clusters-historical (I3): "Historical all-clusters view is limited until the v1.1 metrics rollup."
- `frontend/src/stores/overview.ts`, `frontend/src/stores/images.ts` — Pinia state, both reading global `T`.

## Definition of Done
Everything in [`definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each a gate):
- **PLAN gate (point-in-time image):** moving the global picker to a past `T` reconstructs an image's exact
  CVE list + as-of-then severities (via M8b); a **clean rescan reads as clean at T, not the prior snapshot**;
  a digest that dropped CVE-Y by T does **not** appear (false-positive guard). Proven by tests against M8b.
- **`runtime_inventory_at_T` vs `vulns_as_scanned_at_T` never conflated** — the image view shows both as
  distinct facts; "not yet scanned then" state when no committed snapshot ≤ T (FR-14).
- **Server-side everything:** every dashboard number is a server aggregation / M8b result; charts only
  render what the server returns. No client-side summing across scanners (per-scanner sacred).
- **ECharts hygiene:** `shallowRef`+`markRaw` for options/instances; manual module imports (asserted by a
  bundle/import check or lint rule).
- **I3 graceful degradation (explicit):** single-cluster current-state + per-cluster rewind work fully;
  **all-clusters-historical (`T<now`) shows `LimitedHistoricalNotice`, not an error or a wrong/expensive
  query.** All-clusters **current-state** (`T=now`) works. No code path attempts a historical all-clusters
  raw-occurrences scan.

## Tests to write
See [`testing.md`](../../standards/testing.md). FE rule: **unit-test option-builders + emitted query params
as pure units** (Vitest).
- **Unit (pure, primary):**
  - `buildSeverityTrendOption` / `buildOverviewOption` — data → exact ECharts option (series, axes, severity
    colors from tokens). Deterministic; the contract.
  - `buildTrendQuery` — `cluster_id` + range + `T` → exact emitted params.
  - `buildImageAtTQuery` — emits the **two distinct** M8b queries (inventory-at-T, vulns-as-scanned-at-T);
    asserts they are never merged; `T=now` vs `T<now` branch.
  - **I3 guard (unit):** the all-clusters store, given `T<now`, returns the `limited` state and **emits no
    historical all-clusters query** (asserted on the emitted-params mock).
- **Component:** `DigestSubTimeline` marks build-change vs gap vs not-yet-scanned; `ImageDetailView` scanner
  dropdown swaps the per-scanner table without merging; `LimitedHistoricalNotice` renders for all-clusters `T<now`.
- **Integration (optional, against M8b):** as-of-T image reconstruction matches a known sequence.
- **Playwright:** time-travel E2E deferred to M9f — note only.

## Out of scope (defer)
- **`javv-metrics-*` rollup → v1.1 (locked; I3 + INDEX-MAP).** No bolt builds it in MVP. Therefore
  **historical all-clusters dashboards are limited/unavailable in MVP** (D38/M16, D39/M11-r2); this bolt
  ships the graceful-degraded state, not the rollup. Cheap multi-year all-clusters trends arrive with the
  v1.1 metrics rollup, read from the rollup (not raw occurrences).
- Audit/approvals/contributors/scanner-status → M9d. Settings (Data & OpenSearch, staleness) → M9e.
- Streaming/scheduled export from a lens → M6/M7 (export dialog wiring); cross-cutting empty states → M9f.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates
- **2026-07-11 — time-semantics round (operator debug session — PR #340; bolt #341 filed):**
  "Last 24 hours shows a full findings table" ruled **correct** (D28: tables show state at the
  range **END** — an empty state table would claim the cluster was clean), but the idle-scanner
  signal must be visible on the screen. Shipped: the **ingest lens** — a reusable strip in a
  two-track screen-head band (title card on the rail track in the kpi voice; lens spans exactly
  the table track), reading `/trends/scans` + `/scanners/freshness`; a quiet range names the
  moment the shown state was committed; **clicking a day bar rewinds the whole app** to that
  day's end (a still-running day = back to now); the lens sub states the D28 semantics
  permanently ("the table shows the state at the end of this range"). **"New in range"** ruled
  in as the event view of the state table: an Attribute flag → `new_within_days` on
  `GET /findings` + `/findings/facets` (range on `first_seen_at`, day-floored via the SAME
  `window_bounds` as the trend charts so lens bars and rows always agree; a quiet window
  honestly answers 0); mirrors pinned on `ExportParams`/`ViewPreset` (the 1:1 guards caught the
  gap in CI); past T = `_unrecorded` 422; hover hint on the rail row. Also: finding-detail
  **image fact links** to `/images/<digest>?repo&tag` (digest identity implies the navigation);
  image-detail table's nested card unwrapped (pager on page bg like every sibling screen);
  scanner lens selection tone → **accent** (neutral read white-on-white). Long-form home for
  this mental model = the **About/tutorial page bolt, issue #341**.
- **2026-07-11 — slice 3 rulings (operator review rounds — PR #339):** images screen rebuilt to
  **full findings parity** ("findings is the reference screen" — measured with Playwright, not
  eyeballed): M9a rail/FilterBar via `makeFiltersStore('imageFilters', IMAGES_FIELDS)` with URL
  sync, ColumnsMenu + density (images-scoped keys), client CSV export of the served run
  (`can_export`-gated), GridPager. Shared extractions: the data-screen scaffolding AND the whole
  table skin moved to `base.css` — the **`.tbl.tbl` doubled selector is load-bearing** against
  the PrimeVue theme cascade (single-class rules lose the padding war; scoped overrides must
  match the weight). Readability rulings: **CountDisagree chip** (T/G scanner-colored letter
  chips + amber Δ badge, sentence tooltip) replaced the cryptic T/G·Δ trio; **two per-scanner
  severity-mix columns** (bar + colored counts under it; zeros = a committed clean scan, dash =
  never scanned) fed by the server-side `severity_by_scanner` decoration from the scan-events
  catalog (R-CATALOG max `scan_order` — the image doc's own buckets are the committing
  scanner's alone); the Scanners column **dropped** (an inventory run is ONE scanner's cycle —
  the tag misled; the other scanner shows via the D5b pair); `as_of` lands on `GET /images` +
  new `GET /images/timeline` (digest eras / build-history sub-timeline); table headers ink/700;
  toolbar centered on the search-box midline.
- **2026-07-11 — slice 2 rulings (operator, live A/B — PR #338):** per-cluster **signal
  columns ruled as explicit columns** (variant A) over an exception-based signals cell:
  KEV (alarm-red when >0) · Fix % · Disagree · Triage (stacked state bar + % triaged) — all
  straight reads of the facets response each row already fetches, zero extra calls.
  **Anchoring ruling:** numeric table columns shrink-to-content + nowrap so numbers sit
  tight under their headers; layout slack goes to the cluster/mix cells, never into gaps
  between data columns. Cursor ruling **sharpened** (PR #337): no I-beam either —
  `* { cursor: default }` app-wide, ratchet-enforced.
- **2026-07-11 — polish round rulings (operator review, PR #335):** system-default **arrow
  cursor ruled app-wide** (DESIGN.md §5 — never `pointer`; ECharts series carry
  `cursor: 'default'`, pinned by a spec so it can't regress); **donut deep-links** — segment
  and legend rows navigate to `/findings?ptype=<key>`; donut ramp re-cut **hue-alternating**
  (the monochrome teal ramp read as one green mass); the findings "counts computed
  server-side" caption cut (dev assertion, not operator info); **findings column diet** —
  `epss/kev/current/fixed` hidden on first run (localStorage still rules), package/namespace
  cells truncate with title tooltips; 1920px shows no horizontal scroll; **1440px remainder
  ruled accepted** (operator, 2026-07-11) — the ~180px horizontal scroll below 1920 stands,
  no further column cuts.
- **2026-07-10 — slice 1 + 1b rulings (operator, live review):** slice-1 cuts beyond the
  audited ones — **KPI sparklines + "+new Nd" chips** (no per-severity-per-day agg pre-1b) and
  the **per-namespace severity MixBar** (no per-ns severity agg) — slots dropped, not kept.
  1b additions (operator-requested): **severity lens** on the trend chart via
  `GET /trends/findings?split=severity[&scanner=…]` (server sub-agg on `severity_canonical`;
  now-only — 422 at past T, the M8b reader stays per-scanner); **signal band** (KEV ·
  scanners-disagree · triage-progress stacked state bar — all straight facet reads);
  **at-rest clickability affordance** ruled app-wide (DESIGN.md §5: navigating cells carry a
  soft trailing chevron; identifier takes the link treatment on hover). KPI band + signal band
  render as the joined hairline-divided stat grammar (Nuxt reference), not floating cards.
- **2026-07-07 — backend↔UI drift rulings (major audit #224, 05 §B/§C):** **(B-1)** there is no
  `package_type` field — the packageTypes donut is **cut for MVP** (leave the layout slot; post-MVP
  enhancement issue if wanted); **(B-6)** `languageBinaries[]`/`topComponents[]` widgets have no
  backing aggregation — cut for MVP; **(C-5)** historical **all-clusters** dashboards are
  limited/unavailable until the v1.1 metrics rollup (D39 ruling) — the screen states this rather than
  showing wrong numbers; cluster list = distinct `cluster_id`s from data; **[DECIDE at kickoff]
  (D-5)** where the relabelable `cluster_name` lives (recommend: a small `system-config` doc — a tiny
  backend addition) or MVP shows raw ids.

- **2026-07-05 (pre-kickoff, from the first e2e smoke — #156 finding 3):** the `javv-images` docs
  have **no `image_ref` field** — the tag is stored split as `image_repo` + `tag` (e.g. `nginx` +
  `1.21.6`). Image views must read/compose from those two fields (or this bolt adds a derived
  `image_ref` at read time); anything expecting a combined `image_ref` gets null today.

- **2026-07-07 — v5 design rulings (#237):** contract = `SCREENS.md` §§1–2, 7–8. **B-1 ruled:
  the Overview package-type donut is KEPT** per the v4 design — backed by **M8d** (`ptype` facet);
  placeholder state until M8d + one sweep. The All-clusters list + `cluster_name` come from the
  **M8c cluster registry** (D-5 ruled: `system-config` doc). Running-images Replicas/first-last
  seen come from the **M8c inventory read** (`GET /api/v1/images`, latest complete run — clean
  zero-finding images must appear). Depends-on grows: M8c, M8d.

### 2026-10-26 — Frozen as history

The bolts M0 to M10 ended on 2026-10-09. This file is history now, not the spec of record. New work
follows one GitHub issue for each feature, with the plan and a spec file for each slice on the
issue. The timeline, the rulings that still apply and the open work are in the
[memory bank](../../memory-bank/README.md) (issue 1012).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
> **Frontend analog (M9a+):** `logger` from `frontend/src/lib/logger.ts` — structured, leveled,
> backend-shaped lines; raw `console.*` in app code is ESLint-banned. Threshold: `VITE_LOG_LEVEL`
> ([CONFIGURATION.md §2b](../../../docs/CONFIGURATION.md)); never log tokens/cookies/bodies (NFR-5).

## Design & fidelity (standing rule)
> Before touching any screen: read **`frontend/DESIGN.md`** — the binding agent contract
> (tokens-only styling, **Hanken Grotesk** UI face, the **AA contrast floor** (`--soft` minimum
> for text; `--muted` never colors words), route-`meta: {wide}` for grid screens, §9 ruled linter
> exceptions). Build **with the prototype open** per DESIGN.md §8: port the matching
> `handoff/v4/prototype/app/*.jsx` markup + CSS onto tokens — never restyle from memory — and
> name the ported component/classes in the PR. **Port structure, never palette: tokens.css
> supersedes the prototype's colors/fonts/text sizes** (the contrast gate
> `frontend/src/__tests__/contrast-gate.spec.ts` enforces the values; DESIGN.md §8 has the rule). Reuse the shared modules (M9a filter module,
> M9b chip set, the banners); never re-implement them. Verify UI deltas with **`/visual-test`**
> and run **`npx impeccable detect`** on rendered-HTML dumps of changed screens (fix real
> findings; §9 exceptions stand). The **`/impeccable`** skill (critique · typeset · layout ·
> harden) is available for design decisions — its product register applies.
> **VISUAL FEEDBACK IS A MUST** (operator 2026-07-10): every interactive element ships with
> visible hover (wash + border, never border-only), pressed and focus states — the global rule
> in  + DESIGN.md §2 are binding; feedback-less controls fail review.

- **2026-07-09 — trend window comes from the RANGE control (operator re-ruling, PR #300):** the
  dashboards consume `windowDays`/`windowLabel` from the timeTravel store — set by the single
  Kibana-style range picker (M9a-owned), not a separate window control. Charts aggregate the
  range's span; a past range end also sets `as_of`. Audit C-1 superseded (see M9a README).
- **2026-07-09 — sub-day ranges vs daily trend buckets (operator ruling):** the range picker
  allows sub-day quick-selects ("Last 90 minutes") but the trends API is day-grained: `days` is
  `int 1–365` with **day-floored UTC bounds** and a `calendar_interval: "day"` histogram
  (`backend/src/backend/query/trends.py` `_window()` / `_timeline()`). The picker rounds the
  chart span UP to 1 day while the header label keeps the exact choice — so a sub-day label
  sits over a 1-day chart. **MVP requirement:** when the label's span is sub-day
  (`windowLabel` from a minutes/hours quick-select), render a one-line caption on each trend
  chart, e.g. *"Trend at daily resolution — chart covers the last 1 day."* Detect it FE-side
  (the store's label/span pair); no backend change.
  **Optional upgrade, decide AT M9c once real scan cadence is visible:** the underlying data is
  full-precision (`ingested_at`/`first_seen_at`/`resolved_at` — D37), so true sub-day trends
  need only a contained trends-endpoint change: accept a sub-day span (e.g. `hours` param or
  minutes from the FE), skip the day-flooring in `_window()` (keep absolute ISO bounds — never
  `now`-date-math, see the DateRangeIncludingNowQuery note there), and switch `_timeline()` to
  `fixed_interval: "1h"` for sub-day spans (keep `extended_bounds` + `min_doc_count: 0`).
  No index/mapping changes. Worth it only if the scan CronJob cadence is sub-daily; in the
  smoke env (one-shot ingest) it plots a flat line.
