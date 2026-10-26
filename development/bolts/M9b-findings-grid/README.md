# M9b - Findings grid + detail/triage (core-loop gate)

**Status:** tracked in [#36](https://github.com/Danube-Labs/javv-poc/issues/36) — live status on the GitHub issue/board

## Goal
The core triage loop: a **server-side lazy** findings DataTable (every count/page from an OpenSearch
aggregation via M6, never client-computed) plus the detail/triage panel implementing the **6-state VEX
model** (`open · acknowledged · not_affected · risk_accepted · resolved · stale`) with the
`not_affected` → `vex_justification` picker (CISA five) and the scoped risk-accept dialog. **Gate before
the long tail.**

**Canonical refs:** [`PLAN §8 M9b`](../../../docs/engineering/PLAN.md) (line 676) ·
`SPEC` FR-7 (triage / two-field VEX), FR-11 (scanner disagreement), FR-12 (lazy server-side grid +
faceted-by-scanner), FR-18 (RBAC-gated actions) · [`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md)
(`findings` read shape; `disagree`/`trivy_count`/`grype_count`/`count_delta` fields — read-only) ·
decisions D27 (PrimeVue DataTable lazy), D33 (capability gating). AUDIT item folded in: **N10**
(scanner-disagreement flags surfaced here; per-scanner columns never merged).

## Depends on
- **M9a** — shell, tokens, the reusable filter module (FacetRail + FilterBar), typed API client, global `T`.
- **M5b** — triage write endpoints + `system-audit-log` (every triage action journaled; D33 capabilities).

## Deliverables
Files this bolt creates — **in the layered tree, not here** (paths proposed):
- `frontend/src/views/FindingsView.vue` — page: FacetRail + FilterBar (from M9a) + grid + detail panel.
- `frontend/src/components/findings/FindingsTable.vue` — **PrimeVue `DataTable` in lazy server-side mode**
  (D27): emits `{ page, rows, sortField, sortOrder, filters }`; renders only the page the server returns.
  **Per-scanner columns are distinct and never summed** (per-scanner sacred).
- `frontend/src/components/findings/buildFindingsQuery.ts` — **pure option-builder**: lazy-load event +
  active filters + global `T` → the M6 query-param object (`cluster_id` always; `present=true` + scanner
  filter on every "now" query per INDEX-MAP; severity case-insensitive D16). Primary unit-tested surface.
- `frontend/src/stores/findings.ts` — Pinia: page state, total count (from server agg), selection.
- `frontend/src/components/findings/DisagreementBadge.vue` — renders the **`disagree`** boolean (D5a,
  per-finding severity disagreement) as a flag in a grid column; in the detail panel shows the
  per-scanner verbatim severities **side-by-side** (never reconciled). (N10)
- `frontend/src/components/findings/CountDisagreement.vue` — per-image count disagreement
  (`trivy_count` vs `grype_count` + `count_delta`, FR-11b) shown side-by-side, never summed.
- `frontend/src/components/findings/FindingDetailPanel.vue` — finding metadata, per-scanner severities,
  KEV/EPSS/fix-available, occurrences link (M9c), triage controls.
- `frontend/src/components/triage/TriageStateControl.vue` — the **6-state** picker (FR-7).
- `frontend/src/components/triage/VexJustificationPicker.vue` — shown **iff** `not_affected`; CISA five
  justifications; "False positive" = `not_affected` + component/code-not-present chip (FR-7).
- `frontend/src/components/triage/RiskAcceptDialog.vue` — scoped accept (images/namespaces + approver +
  **expiry**); gated by `can_accept_audit_final` (D33).
- `frontend/src/components/triage/BulkTriageBar.vue` — bulk triage with optimistic concurrency surfaced
  (conflict → reload-and-retry messaging, FR-7).
- `frontend/src/api/triage.ts` — typed calls to M5b write endpoints (notes; optimistic concurrency token).

## Definition of Done
Everything in [`definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each a gate):
- **PLAN core-loop gate:** ingest → filter → open a finding → set `not_affected` + justification → it
  persists and the grid reflects the new `state` (round-trip through M5b), proven E2E-style in a component/
  integration test against a stubbed-or-real M6/M5b.
- **Server-side everything:** the grid never computes a total or page client-side — total comes from the
  server agg; `buildFindingsQuery` always carries `cluster_id` + `present=true` + scanner filter.
- **VEX coupling:** `vex_justification` is **required iff** `state=not_affected`, blocked otherwise (FR-7).
- **Per-scanner sacred (N10):** `disagree` flag renders per finding; per-scanner severities + the
  `trivy_count`/`grype_count`/`count_delta` pair render **side-by-side, never summed/merged**.
- **RBAC:** triage controls and risk-accept are hidden/disabled without the capability (D33); server is the
  real gate but the client must not offer ungated actions.
- Optimistic-concurrency conflict on bulk triage is surfaced (no silent overwrite).

## Tests to write
See [`testing.md`](../../standards/testing.md). FE rule: **unit-test option-builders + emitted query params
as pure units** (Vitest).
- **Unit (pure, primary):**
  - `buildFindingsQuery` — lazy event + filters + `T` → exact emitted params (`cluster_id` always,
    `present=true`, scanner filter, sort/page, case-insensitive severity). The contract.
  - VEX rule unit: `not_affected` ⇒ justification required; other states ⇒ justification cleared/blocked.
  - disagreement view-model: builds the side-by-side per-scanner severity rows from `disagree`/per-scanner
    fields **without** merging; count pair derives `count_delta` for display only (never a summed total).
- **Component:** lazy DataTable emits correct load events; `VexJustificationPicker` appears only on
  `not_affected`; RBAC hides gated controls; `RiskAcceptDialog` requires approver+expiry; bulk conflict path.
- **Integration (optional, against M6/M5b):** triage write round-trip reflects in the grid.
- **Playwright (E2E):** the core-loop smoke (grid → finding → triage round-trip) lives in **M9f's E2E suite** ([`testing.md §4`](../../standards/testing.md)) — note only here.

## Out of scope (defer)
- Per-image occurrences / point-in-time image view → M9c. Overview & dashboards → M9c.
- Audit log / approvals queue / contributors → M9d. Saved views, bell, global search → M9f.
- VEX **import** (statement → decision) → v1.1 (FR-22); MVP triage writes scanner-JSON-backed findings only.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates
- **2026-07-10 — post-bolt detail-screen rework (operator session, PR #316):** the flat header
  meta ribbon is replaced by the **risk band** — CVSS/EPSS/SLA as one hairline-divided stat band
  (operator A/B ruling, presentation per the Nuxt UI stat-card reference on our tokens); urgency
  lives in the numerals (CVSS colored by severity, SLA countdown by tier); context facts are
  label-over-value stacks. The B-4 "images affected" per-scanner **counts card is superseded** by
  the prototype's **Affected components** table (one row per image+package with namespace,
  current/fixed, scanner tags) fed by the server-filtered occurrence search — no counts computed
  client-side; a version disagreement splits rows (per-scanner sacred; view-model unit-tested).
  **Namespace is a per-row dimension of that table, never a CVE-level header field** (operator
  ruling — an unqualified header list reads CVE-wide and can't scale). Workload names wait for
  the envelope (v1.1, #308). Also: the UI kit (`components/ui/`) landed — controls are imported,
  never re-rolled (DESIGN.md §5); the style ratchet now fails same-hue fg/bg pairs.

- **2026-07-07 — backend↔UI drift rulings (major audit #224, `.deprecated/docs/audits/major_audit/05-backend-ui-drift-m9.md`):**
  the grid + detail + triage flow follow the SHIPPED backend, not the v4 prototype where they differ:
  **(A-1)** filters/aggs send lowercase severities and the `negligible` bucket exists (display may
  uppercase; [DECIDE at kickoff]: show `negligible` — recommended — or fold into `unknown`);
  **(A-2)** all **6 states** (`open/acknowledged/not_affected/risk_accepted/resolved/stale`) with the
  CISA-five justification chip required iff `not_affected`; `present` is orthogonal — every "now" view
  is implicitly `present=true`; **(A-3)** `disagree` is a **bool** + images carry `count_delta` — the
  other scanner's severity comes from querying the sibling row (which also builds the per-scanner
  evidence table, B-2); **(B-2/B-3)** no `cvssVector`/`cwe`/`description`/`refs`/`epssPct` fields exist
  — detail renders what the doc has (`cvss` float, raw `epss`, `kev`); **(B-4)** per-finding "images
  affected" is an aggregation (verify the `groups` shape covers it at kickoff, else extend it);
  **(B-5)** SLA deadline/overdue are server-computed on the findings read — never client math;
  **(C-2)** the export dialog gains the M7 states: run-now 413 past `JAVV_EXPORT_MAX_ROWS` → offer
  "schedule"; scheduled results expire (`JAVV_EXPORT_TTL_HOURS`, default 24 h) → "expires in Xh"
  affordance + a 410-expired state.

- **2026-07-05 (pre-kickoff, from the first e2e smoke — #156 finding 4):** real-scanner divergence
  can be total: trivy reported **0** findings on alpine:3.14 where grype found **73** (EOL secdb —
  both scans committed, the trivy one with `total=0`). UI rule: never render one scanner's zero as
  a green "clean" check when the other scanner disagrees — show the pair side-by-side (the D5b
  `count_delta` / D5a `disagree` flags carry this), and a zero-vs-nonzero pair deserves the same
  visual weight as a severity disagreement.

- **2026-07-07 — v5 design rulings (#237):** contract = `SCREENS.md` §§3–5. **B-1 ruled: the
  package-type facet + column RETURN** (v4 design kept) — fed by the **M8d** envelope `ptype`;
  hide the facet until M8d lands + a sweep repopulates (`ptype: null` → "unknown" meanwhile).
  **A-1**: `negligible` is its own muted rail bucket. **C-6 ruled server-side**: the toolbar
  "Save view" button POSTs to **M8e** `/api/v1/views` (not localStorage). **A-6 ruled**: export
  stays session-only — no capability gate on the Export dialog.

- **2026-07-09 — grid contract rulings (slice 1):** the shipped M6 search pages by **cursor**
  (PIT + `search_after`, `next_cursor`) — there is no offset param, so the deliverable's assumed
  `{page, rows}` lazy event becomes **prev/next over a cursor stack** (no numbered page jumps;
  a stale/expired PIT cursor resets to page 0). And **sortable columns = the server's sort
  whitelist only** (`severity_rank`, `first_seen_at`, `last_scan_at`, `cvss`, `epss`) — the
  prototype's client-side sorts on cve/state/assignee have no server field and are dropped.
  EPSS is null on trivy rows (grype-only enrichment) → muted dash with the "via Grype" note.

- **2026-07-09 — detail contract rulings (slice 2):** the detail route is
  **`/findings/:cveId?digest=…&scanner=…&pkg=…&ver=…`** — a `(cve_id, image_digest)` search
  returns one row per PACKAGE per scanner (finding identity includes the package), so the
  per-scanner evidence table **scopes to the clicked package** (deep links without `pkg` scope
  to the first row) and lists the other affected packages as a pointer back to the grid. A
  scanner with no row in scope renders an explicit "no current finding from this scanner" row —
  never an implied clean bill. Images-affected = `groups?by=image_repo&cve_id` with the
  buckets' `by_scanner` counts side-by-side (zero-vs-nonzero flagged at disagreement grade).
  **Solid sev chips are critical-only** (white fails AA on every other solid — DESIGN.md §2);
  the header uses the tinted chip, and the prototype's 4px severity side-stripe is dropped
  (banned pattern). SLA box shows a countdown derived from the server's `due_at` — the
  deadline itself is never client math (B-5).

- **2026-07-09 — triage contract rulings (slice 3):** the panel follows the shipped M5b, not
  the prototype: **state targets are the 4 human ones** (open/acknowledged/not_affected/
  resolved) — risk_accepted is decision-driven (read-only block + the scoped dialog) and stale
  is system-only (read-only block; a human change overrides). The FE mirrors the server state
  machine in `frontend/src/findings/triageRules.ts` (justification iff not_affected, never sent
  alongside any other state) so Save disables with the reason before the server would 422 — the
  server stays the authority. `GET /api/v1/decisions` answers `{decisions: […]}` (not `data`).
  Prototype's Impact/Action/Approver/Task fields stay removed (V4-DELTA-1); assignee is a
  plain username + "Assign to me" (no avatar roster — no user-list read exists for non-admins).
  **T<now = panel read-only** ("viewing history"). Rig captures triage DRAFTS only — automated
  runs never save (mutations stay confirmation-gated). **Core-loop gate proven live (supervised,
  2026-07-09):** not_affected + justification round-tripped through M5b, survived reload, grid +
  facets reflected it, reverted clean — the run itself caught two latent bugs (StateTag label
  frozen at setup; state filter vocabulary listed only 4 of the 6 states).

- **2026-07-10 — metadata-gap rulings (operator review, pre-slice-4):** **Pods are NOT
  renderable — by design (D30):** the scanner dedups by image digest (N pods = one scan); a vuln
  is a property of the image, not the pod, and no pod/workload field exists in any index. Don't
  hunt for it; workload-level mapping is a **v1.1 scanner-envelope candidate ([#308])**. What DOES
  exist is `namespaces[]` — slice 4 folds in the delivered-vs-spec gaps: **Namespace + Assignee
  facet-rail sections** (SCREENS §3 — the Add-filter text path already worked, but hidden ≠
  delivered), the three missing specced **grid columns** (Component `app` · Images group-agg
  count B-4 · Assignee), and a **Namespaces line in the detail header** (from the sibling rows).
  Topbar search stays inert until **M9f** (global grouped search, per spec).

- **2026-07-10 — slice-4 contract rulings:** **bulk = the CURRENT LENS, not checkboxes.** The
  shipped M5d selector is predicate-based (cve/digest/severity/state/assignee → frozen id-set);
  arbitrary checked-row sets are not expressible, so the specced checkbox column is superseded:
  the Bulk dialog derives its selector from the active filters and **BLOCKS (never widens)**
  when the lens uses anything the selector can't express (scanner/flags/namespace/image/ptype,
  or multi-value severity/state) — a selector that ignored an active filter would triage more
  rows than the operator sees. Empty lens = refused (whole-cluster guard). If per-row selection
  is ever wanted, the selector needs a `finding_keys` list — a deliberate backend decision, not
  a UI patch. **Exports:** run-now streams the FULL lens; scheduled `ExportParams` carries no
  namespace/ptype → those lenses block scheduling with the reason. M7 shipped whole → the
  schedule path is LIVE (enqueue → poll → signed download + expiry), not drawn-disabled.
  **Facet rail:** namespaces/assignee = top-N-by-count rail dims (server caps at 32; complete
  enumeration stays groups territory); an "Unassigned" bucket needs a missing-agg — deferred,
  noted. Assignee rail lists only assignees that exist.

- **2026-07-10 — operator findings-review corrections (slice 4, same PR):** the rail gets the
  prototype's **`.facet-search` box** (missed in slice 1) — **exact CVE-id lookup** (the backend
  `cve_id` term filter; package/component search has NO backend param — the M9f-verify item
  stands). **Namespace column** added (first + "+n"); the images count column renamed
  **"Affected"** (menu: "Affected images") — "Image" = this row's image, "Affected" = CVE-wide
  distinct-image count. **Component column REMOVED until the envelope emits `app`** (0% populated
  — the ptype/B-1 precedent: never ship a dash-only column). **Decisions ≠ triage actions**: the
  decisions card lists scoped RULES; plain state changes are audit-journaled actions — the detail
  page now has an **"Activity on this finding"** card (audit route gained a `finding_key` filter,
  tested) so a triage action is visible where the operator expects it.

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
> in base.css + DESIGN.md §2 are binding; feedback-less controls fail review.
