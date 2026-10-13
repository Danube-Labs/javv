# Screens — javv (v5, refreshed against the shipped backend)

> **Living UI contract** (formerly `SCREENS-v5.md` in `handoff/v5/docs/` — suffixes dropped 2026-07-16, #410).
> Layered over the frozen `handoff/v4/` prototype (the DESIGN.md §8 fidelity source).

Refresh of `handoff/v4/docs/SCREENS.md` against the **shipped** contract (`docs/API.md`, through
M7 slice 1) and the drift rulings (`05-backend-ui-drift-m9.md`). Information architecture, brand,
tokens, and layout are preserved from v4 (`DESIGN_SYSTEM.md` / `ui-foundations.md` bind all values);
only ruling-forced changes are made. Every screen names its **bolt** (M9a–M9f READMEs).

Conventions used below:
- **Data** = concrete calls (method + path + key params from API.md). `cluster_id` is **required on
  every read** (tenant read path, D38/H9). The global `as_of` (`T`) rides on every read; `T=now`
  omits it.
- **Every number on every screen is a server aggregation** — the client never counts, sums, or
  pages locally. Per-scanner counts are **sacred**: Trivy and Grype numbers are never summed,
  averaged, or merged, anywhere.
- Severity values in filters/aggs are **lowercase** and include a **`negligible`** bucket (A-1);
  display may uppercase. States are the **6-state** set (A-2); every "now" list is implicitly
  `present=true`.
- **Capability gating** reads `capabilities` from `GET /auth/me` — never role names (A-4). A
  `must_change` session is routed to the password screen; everything else 403s.
- **DECIDE flags: ALL RULED 2026-07-07** (operator, #237) — see the RESOLVED register at the
  bottom. Where a ruling flipped the drawn recommendation (B-1 donut kept, C-6 views server-side)
  the sections below are amended in place.
- **BLOCKED: needs backend** items are now **scheduled**: the pre-M9 backend bolts **M8c**
  (session reads: audit log · scanner provenance · inventory · cluster registry), **M8d**
  (envelope `ptype`), **M8e** (server-side saved views).

---

## Global chrome (bolt: **M9a**)

Layout unchanged from v4: sidebar (226px slate, lockup → All clusters, grouped nav, footer health
chip + version line) + topbar (cluster switcher · time picker · global search · bell · avatar).
Place the real brand SVGs (`brand/lockup.svg`, dark variants in dark chrome) — never approximated.

**Data**
- `GET /auth/me` — `username`, `role`, `capabilities`, `must_change`. All gating flows from
  `capabilities` (A-4). Nav items whose screen is capability-gated (Approvals, admin Settings
  sections) are **hidden** without the capability.
- `GET /readyz` (polled) — drives the global **degraded banner**; any API `503` envelope raises it
  too, as does a proxy's `502` or `504`; auto-clears on `200`. The banner and the sidebar footer
  say what is down (issue 675): a `503` is the backend reporting its store ("Search backend
  unavailable. Check OpenSearch health.", footer "Store degraded"); no answer or a proxy error is
  the backend itself ("The backend is not answering. Screens cannot load until it is back.",
  footer "Backend not answering").
- `GET /api/v1/scanners/freshness?cluster_id=…` — per-(cluster, scanner) `last_ingest_at` +
  `silent_for_seconds`; drives the **ScannerFreshnessBanner** ("data as of T; scanner silent
  since T′") and the sidebar sweep-health chip. Never-ingested → nulls → "no data yet" chip, not
  an error.
- The selected cluster's row of `GET /api/v1/clusters` (`last_scan_at`, `warns_at`, `retires_at`)
  drives the **retirement countdown** (issue 765), its own line under the freshness banner, shown
  only inside the cluster's last `warn_days` before automatic retirement: "**beta** has sent no
  scans for 40 days. It will be retired in 5 days unless a scan arrives." Amber (`role=status`)
  while there is time, red (`role=alert`) on the last day and once past its date, when it says
  the next retirement sweep retires it unless a scan arrives. "No scans for" reads `last_scan_at`.
  The only cluster listed gets no countdown (the sweep never retires it: nothing else shows that
  scans still reach JAVV); its line says so and points at retiring it by hand. The list is
  re-read on the banner's 10-minute tick and after every Settings write that moves a schedule,
  keeping the selected cluster while it is still listed.

**Time picker (C-1, D28/FR-23).** Two visibly distinct controls in one group (V4-DELTA conflict 4):
the **time-travel `T`** (Now / rewind / jump-to-date → amber "Viewing history: as scanned at T"
banner + Back to now) and the **trend window** (relative to `T`, scopes charts + Contributors).
- State: **picker-set-but-unsupported** — if M8b hasn't landed, `T<now` reads return `501`; show
  the banner "History available after M8b", keep `T=now` fully working. (Check milestone order at
  M9a kickoff; currently M8→M9 makes this moot.)

**States:** degraded (banner, chrome stays up, data areas show degraded placeholders — never
blank); scanner-silent (freshness banner); must_change (locked to password change).
The freshness check itself is never silent (issue 651):
- if the read fails before any good answer, an amber degraded line says freshness couldn't be
  checked;
- if a later read fails, the last good result stays and says when it was last checked, either
  inside the red banner or as the amber line when no scanner is silent;
- the next good read clears it.

The amber is the health ramp's step between fine and down (operator ruling on built specimens,
2026-10-01). A 503 is covered by the degraded banner instead.

**Changed vs SCREENS.md**
- Capability gating replaces the 5-role matrix everywhere (A-4).
- Freshness banner is now a concrete endpoint call (D-1, shipped).
- Time-travel unsupported state added (C-1).
- Bell behavior moved to M9f (see Notifications, below) and gains export-expiry affordances (C-2).

---

## 0. Login & password change (bolt: **M9a**)

**Data:** `POST /auth/login` (generic 401 — no user-existence hint; `429` lockout after
`JAVV_LOGIN_MAX_ATTEMPTS`), `POST /auth/password` (the only mutating route a `must_change` session
may call), `POST /auth/logout`, `GET /auth/me`.
**States:** bad-credentials (generic copy), locked-out (429 — "try again later", no countdown
oracle), forced password change (SEC-6: bootstrap admin / temp password), **server not answering**
(issue 675: no answer or a `5xx` from the session check, the sign-in or the password change shows
"The server is not answering. This page checks again on its own." in place of any credential
error; the page asks `/readyz` every 30 seconds, and when the server returns it re-checks the
session, so a visitor whose session is still good goes straight to Overview. A failed session
check is not remembered as signed out: the next navigation asks again).
**Rulings (operator, on built specimens, 2026-10-02):** the server-down message on the login page
is the form's plain red line (A of two; B was a tinted box). The banner for a backend that is gone
reads "The backend is not answering. Screens cannot load until it is back." (A of two; B ended
"Check that the JAVV backend is running.").
**The password rule** (issue 726): the forced change states it under the fields, as the
prototype does ("At least 12 characters. Your current password stops working once you set the new
one."), refuses a shorter password before sending it, and shows the server's own reason for a `422`.
**A forgotten password** (issue 761): the sign-in screen carries a note under **Sign in**, in the
prototype's `login-note` place (small, muted, centered): "Forgot your password? Ask an admin to
reset it. If no admin can sign in, the deploy guide (DEPLOYING.md) shows how to reset one." It is
the same for every visitor (no user-existence hint) and is not on the forced change. Ruling
(operator, on built specimens, 2026-10-06): A, the note always shown, of two; B hid it behind a
"Forgot your password?" button. No self-service reset: users have no email and JAVV no mail server,
and OIDC (#131) moves those passwords to the identity provider.
**Changed:** copy states capability-based access; SSO/OIDC removed (post-MVP, per V4-DELTA).

---

## 1. All clusters (bolt: **M9c**)

Fleet landing page; layout preserved (KPI strip → cluster table with MixBar).

**Data**
- Cluster list: **RULED (D-5/C-5, 2026-07-07)** — the `system-config` cluster-registry doc
  (`cluster_id` + relabelable `cluster_name`) ships in **M8c** with its session read; the UI
  renders display names from it. Until M8c lands this stays blocked.
- Per-cluster severity mix + KPI strip: `GET /api/v1/findings/facets?cluster_id=<id>` — one call
  per cluster row; buckets are **per-scanner** — the MixBar renders one bar per scanner (or a
  scanner toggle), never a merged bar.
- Health chip + Last sweep: `GET /api/v1/scanners/freshness?cluster_id=<id>`.
- Retirement countdown (issue 765): a status chip under the cluster's name, "retires in 5 days"
  (amber) or, on the last day and past its date, red ("retirement due" once past it), from the
  cluster list's `warns_at` / `retires_at`; nothing outside the warning window, and none for the
  only cluster listed.

**States:** loading (skeleton rows); empty (no clusters registered — cold-start copy); degraded;
**T<now → `LimitedHistoricalNotice`**: "Historical all-clusters view is limited until the v1.1
metrics rollup" (C-5/D39) — the current-state table is replaced by the notice, never a wrong or
expensive query.

**Changed vs SCREENS.md**
- Fleet KPI strip severity buckets: lowercase + `negligible` (A-1); per-scanner, never summed.
- Historical all-clusters explicitly limited (C-5).
- Cluster name source ruled: `system-config` registry (D-5 → **M8c**).
- "Replicas" column: fed by the **M8c** inventory read (see Running images).

---

## 2. Overview — single cluster (bolt: **M9c**)

**Data**
- KPI strip (severity cards + Fix-coverage): `GET /api/v1/findings/facets?cluster_id=…` —
  severity buckets (lowercase; `negligible` shown muted, see DECIDE below) + `fixable` bucket.
  Cards remain click-through → Findings pre-filtered (deep-link preset preserved).
- Vulnerabilities over time: `GET /api/v1/trends/findings?cluster_id=…&range=…` — faceted by
  scanner (two series sets, never merged). Note: `resolved_semantics: "scan_resolved"` — any
  "resolved" series is **scan-observed** resolution, labeled as such (A-m9).
- Scan activity: `GET /api/v1/trends/scans?cluster_id=…&range=…`.
- Per-namespace table: namespace buckets from `GET /api/v1/findings/facets` (rows → Findings
  filtered by ns; deep-link preserved).

**Cut / changed widgets**
- **Package-type donut — RULED (B-1, 2026-07-07): KEEP, per the v4 design.** Backed by the
  **M8d** envelope change (`ptype` field + facet bucket). Until M8d lands + a rescan cycle
  repopulates, the donut shows the "awaiting package-type data" placeholder; pre-M8d findings
  aggregate as `unknown` ptype until re-observed by a scan.
- **Top components** + **Language-specific binaries** tables — **cut** (B-6, no backing agg);
  layout slots left.
- **Newly published** bar chart — **cut** (B-2: no `published` field exists); slot reused by the
  scan-activity trend.

**States:** loading (skeletons per card); empty/first-run ("no sweep has landed yet"); degraded;
scanner-silent banner; `T<now` history banner (single-cluster rewind is fully supported once M8b
lands; 501-state before that, C-1).

**Changed vs SCREENS.md:** A-1 (lowercase + negligible), B-1 (donut kept, fed by M8d ptype),
B-2/B-6 (widget cuts), A-m9 (trend semantics label), C-1 (time-travel states). Scanner-type
filter stays (it maps to the `scanner` filter param).

---

## 3. Findings — the core grid (bolt: **M9b**)

Layout preserved: facet rail + toolbar (FilterBar + Save view + ColumnsMenu) + bulk bar + table.

**Data**
- Rows: `GET /api/v1/findings?cluster_id=…&severity=…&state=…&scanner=…&namespace=…&image=…&cve_id=…&kev=…&fixable=…&disagree=…&as_of=…` —
  PIT + `search_after` paged; response = rows + opaque `cursor`. Every "now" query implicitly
  `present=true` (A-2).
- Facet counts: `GET /api/v1/findings/facets` with the same filter family — **per-scanner
  buckets rendered per scanner, never summed** (FR-12).
- "Images affected" column: `GET /api/v1/findings/groups?cluster_id=…&group_by=cve` (B-4 — the
  count is a group aggregation, not a field; **verify the exact agg shape at M9b kickoff**, else
  extend `/findings/groups`).
- Triage writes: see Finding detail. Bulk: `POST /api/v1/findings/bulk-triage` (frozen selector;
  `413` past `JAVV_BULK_INLINE_LIMIT`/`JAVV_BULK_MAX_TARGETS` → "narrow the selection" copy;
  `422` empty selector).

**Facet rail** (top→bottom): Severity (critical/high/medium/low/**negligible**/unknown — muted
treatment for negligible+unknown, never red) · Scanner (trivy/grype) · Attributes (KEV /
Fix available / Scanners disagree) · State (**6**: open, acknowledged, not_affected,
risk_accepted, resolved, stale) · Assignee (incl. Unassigned) · Namespace · **Package type**
(returns per B-1 ruling — buckets from the M8d `ptype` facet; hidden until M8d lands).
> **RULED (A-1, 2026-07-07):** `negligible` IS its own muted bucket — Grype emits it; hiding it
> breaks "counts sum". Display muted grey, never red.

**Table columns:** checkbox · Vulnerability (`cve_id`, mono) · Severity (verbatim word, display
uppercase) · EPSS (raw `epss` 0–1 bar; **Grype rows only**, em-dash on Trivy — B-3: no
percentile) · KEV · Component (`app`) · Package (`package_name`) · Current (`installed_version`) ·
Fixed (`fixed_version`) · Scanner (+ `±` badge when `disagree=true`; tooltip severities come from
the sibling-scanner row, A-3) · Images (group agg, B-4) · SLA (server-computed deadline/overdue —
B-5, **never client math**; field names verified at M9b kickoff) · State (6-state pill) ·
Assignee.

**Paging:** cursor-based (PIT + `search_after`) — the pager is **next/prev over server cursors**
with rows-per-page (10/25/50); total from the server agg. Numbered random-access pages from v4 are
dropped (contract is cursor paging).

**States**
- loading — skeleton rows; empty/first-run — "no sweep yet" friendly state; filtered-empty —
  "no findings match" + clear-filters.
- **A refused later page stays where it is** (operator ruling 2026-10-12, issue 833 G1): the
  alert, the grid's "could not be loaded" row, and the pager still on that page's range with Prev
  usable. A **410** (the page's search expired after the keep-alive) says "These results expired.
  Reload the page to start again.", since its cursor cannot be asked for again. **503**: the same,
  plus the global banner.
- **429 PIT cap** (`JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`) — "too many open searches/exports,
  retry in Ns" honoring `Retry-After`.
- **Any refused read**: the alert names the reason; the head count shows "-" and the grid row
  reads "Findings could not be loaded.", never "0 findings" or "No findings yet" (issue 817). Audit
  log, Contributors and Approvals follow the same rule for their counts (Audit's row: "Events could
  not be loaded."). A refused read after a good one clears the rows: they answered another
  query (issue 833 F1). On all four screens an answer to an older request is dropped, so it never
  replaces a newer one (F3). The bulk dialog says "count unknown" and keeps Apply disabled until a read for the
  current filters answers.
- **Only the filter counts refused** (operator ruling 2026-10-12, issue 833 F9): the rows stay,
  the alert says "Filter counts could not be loaded." with the reason, and the rail and the
  add-filter menu keep their values with "-" for each count.
- **The reason in any read's alert** (issue 833 G2, every screen): a 429 is the per-user search
  budget and says "The search backend is busy. Try again in a few seconds."; any other failure
  keeps the screen's own copy (`readFailureCopy` in `src/findings/failureCopy.ts`).
- 403-capability-hidden — bulk-triage bar and row checkboxes absent without `can_triage`.
- Bulk 413 — inline error offering to narrow the selection.
- Zero-vs-nonzero scanner pair (M9b update, #156-4): one scanner's 0 is **never** a green "clean"
  check while the other reports findings — the pair renders side-by-side with disagreement
  weight.

**Changed vs SCREENS.md:** A-1 (lowercase + negligible), A-2 (6 states + implicit
`present=true`), A-3 (disagree is a bool; tooltip queries sibling row), B-1 (ptype column/facet
KEPT per ruling — after M8d), B-3 (raw EPSS only), B-4 (images count = agg), B-5 (SLA
server-computed), A-m1 (cursor error states), C-2 (export entry point → Export dialog, below).

---

## 4. Finding detail + triage (bolt: **M9b**)

Layout preserved: back-link → header → `grid-2-1` (evidence stack left, sticky triage panel
right).

**Data**
- The finding row (all real fields, see DATA_MODEL) from `GET /api/v1/findings?cluster_id=…&cve_id=…&image=…` —
  and the **sibling-scanner row** from the same call without the `scanner` filter: that pair IS
  the per-scanner evidence table (A-3/B-2 — "no black box, no merge").
- Triage: `PATCH /api/v1/findings/{finding_key}/triage` — body `{state, vex_justification?,
  assignee?, notes?}`; `vex_justification` (CISA five) **required iff** `state=not_affected`;
  CAS'd, journaled (D17).
- Decisions on this CVE: `GET /api/v1/decisions?cluster_id=…&cve_id=…` (active / revoked
  struck-through / expired). Risk-accept: `POST /api/v1/decisions` (type `risk_accepted`
  additionally requires `can_accept_audit_final` — SEC-2 → 403 without); edit =
  `PATCH /api/v1/decisions/{id}` (revoke+new, D40); revoke = `POST …/revoke`.

**Header/meta — renders what exists (B-2/B-3):** CVE mono h1, severity tag (verbatim word), KEV
tag, meta line = CVSS float · raw EPSS (Grype rows only) · first seen (`first_seen_at`) · last
seen. **Cut:** description prose, CVSS vector, CWE, reference links, published date, EPSS
percentile — none exist; deep CVE metadata is a post-MVP NVD enrichment. The left column leads
with the **per-scanner evidence table** instead.

**Triage panel (6-state VEX, A-2):** open · acknowledged · not_affected (reveals CISA-five
justification chips; component/code-not-present chips labeled "False positive") · risk_accepted
(**read-only here** — comes from the scoped risk-accept dialog, with a manage pointer) ·
resolved (manual) · stale (**system-set, read-only** + "re-scan to refresh"). Fixed-vs-stale
explainer kept. Assignee (`assignee`, Assign to me / Reassign) + Notes (escaped, never rendered
as HTML). **Removed:** Impact / Action / Approver / Task free-text fields (V4-DELTA conflict 1 —
the model is state + justification + notes + structured decisions).

**Undo (issue 681):** after a save that changed the state, the panel shows "Changed from X to Y
just now" with an Undo button. Undo sends the earlier state back through the same triage PATCH
(with the earlier justification for not_affected and a note "Undo: back to X"), so it is
journaled like any change. Not offered when the earlier state was risk_accepted or stale, or
when only a note or assignee was saved. It restores the state only, and goes away on undo, on
the next state change, or on leaving the finding.

**SLA box:** server-computed deadline + overdue flag from the findings read (B-5).

**States:** loading; 403-capability-hidden (triage controls disabled-with-tooltip without
`can_triage`; risk-accept without `can_accept_audit_final`); CAS conflict on save → "changed by
someone else — reload and retry" (no silent overwrite); `T<now` — panel read-only ("viewing
history"); `present=false` row visible **only** in history views (A-2). **A refused card read**
(operator ruling 2026-10-12, issue 833 F2): the Affected components, Activity and Decisions cards
each say "Could not be loaded.", never their empty-state copy; the Affected badge shows "-";
"New decision" is disabled while the decisions read is refused; a refused read never leaves the
previous CVE's rows, and a late answer for the previous CVE never lands on the next one. A
refused read of the finding itself follows the G2 rule (§3).

**Changed vs SCREENS.md:** A-2 (6 states + justification flow), A-3 (evidence = sibling query),
B-2/B-3 (metadata cuts), B-5 (server SLA), V4-DELTA-1 (old triage fields removed), D40
(decision edit = revoke+new).

---

## 5. Export dialog + scheduled reports (bolt: **M9b** integration; download/bell states **M9f**)

Reachable from Findings/Overview/Images "Export".

**Data**
- Run now: `GET /api/v1/findings/export.csv?<current lens params>` (streaming, CSV-injection
  sanitized). VEX: `GET /api/v1/findings/export.vex?scanner=<one>&…` — **`scanner` required**,
  one scanner per file (per-scanner sacred).
- Schedule: `POST /api/v1/reports` (`kind: export`, session-only by design — A-6). Status:
  `GET /api/v1/reports/{report_id}`. Download: `GET /api/v1/reports/{id}/download` — **M7
  slice 3, not shipped yet**; until it lands the "schedule" path is **BLOCKED: needs backend
  (planned, M7 slice 3)**.

**States (C-2 — all drawn):** run-now streaming progress · **413 over
`JAVV_EXPORT_MAX_ROWS` (50k)** → "narrow the lens or **schedule off-peak**" (switch tab) ·
scheduled-pending → bell on done · **"expires in Xh"** on the bell item and the download row
(`JAVV_EXPORT_TTL_HOURS`, default 24 h) · **410 expired** → "download expired — re-run the
export" · 429 PIT cap with `Retry-After`.

**Changed vs SCREENS.md:** C-2 (TTL/expiry affordances + 410 state — new), A-6 **RULED
(2026-07-07): export stays session-only** — available to every authenticated user; the v4
"Viewer cannot export" matrix row is dropped. A `can_export` capability is parked as a tracked
idea (issue), deliberately not scheduled.

---

## 6. Saved views (bolt: **M9f**; backend in **M8e**)

Card grid preserved.

> **RULED (C-6, 2026-07-07): server-side.** Saved views are a selling point — they must be
> durable and shareable. New `system-views` index + CRUD endpoints ship in **M8e**
> (INDEX-MAP + MAPPING_VERSION + bootstrap + RBAC rows + API.md). The **owner column returns**
> (v4 design); views are visible to all authenticated users, mutable by their owner (+admin).

**Data:** `GET/POST /api/v1/views` · `PATCH/DELETE /api/v1/views/{view_id}` (**M8e**, session;
mutations owner-or-admin). The per-card **live count** is
`GET /api/v1/findings/facets?<view's filter params>` (server agg — fetched lazily per visible
card; never counted client-side). Card → Findings with the filter preset (deep-link round-trip
must reproduce identical query params).

**States:** empty ("save a filter set from Findings"); count-loading per card; degraded (counts
show em-dash); 403 on mutating someone else's view (edit/delete affordances hidden unless owner
or admin). The head count shows "-" until the list read answers, and after a refused one, never
"0 views" (issue 833 F5); the alert follows the G2 rule (§3).

**Changed vs SCREENS.md:** C-6 ruled server-side (M8e); owner column kept per the v4 design.

---

## 7. Running images (bolt: **M9c**)

**Data**
- Per-image severity mix + finding counts: `GET /api/v1/findings/groups?cluster_id=…&group_by=image&…`
  — per-scanner counts side-by-side + the `trivy_count`/`grype_count`/`count_delta`
  count-disagreement pair (D5b; per-image, distinct from per-finding `disagree` — V4-DELTA
  conflict 7). Facets for the rail via `GET /api/v1/findings/facets`.
- Inventory metadata (replicas at last sweep, app, first/last seen): **scheduled — M8c**
  inventory read (latest complete `inventory_run_id`, `status=committed`, ordered by
  `inventory_order`). M8c must check overlap with M8b's point-in-time API first (this read is
  the `T=now` special case).
- Image naming: compose from `image_repo` + `tag` (no `image_ref` field exists — M9c update,
  #156-3).

**Columns:** Image (`image_repo` + registry mono) · Tag · Namespace · Replicas (M8c inventory
read) · per-scanner finding counts (`T n / G n / Δ` — never a merged total) · Severity mix
(labeled MixBar, per scanner) · Scanners · Last seen.
A digest-pinned image (`repo@sha256:…`) has no tag anywhere in Kubernetes: its Tag cell shows the
empty-value dash with the title "Pinned by digest: the pod names no tag." (operator ruling
2026-10-11, issue 817).

**States:** loading; empty/first-run; **scanner-silent** banner ("Inventory as of T; scanner
silent since…"); **last-run-incomplete** banner ("showing the last complete inventory"); `T<now`
history banner; degraded. Never shows partial/stale inventory as live (V4-DELTA).

**Changed vs SCREENS.md:** A-3/D5b (count-disagreement pair per image), B-1 (ptype facet after
M8d), #156-3 (repo+tag composition), inventory read scheduled (M8c).

---

## 8. Image detail — point-in-time (bolt: **M9c**)

Identity is the **content digest** (`image_digest`). Layout preserved: header → scanner dropdown
("Showing results from Trivy|Grype") → per-scanner severity cards → findings table.

**Data**
- Per-scanner findings: `GET /api/v1/findings?cluster_id=…&image=<digest>&scanner=<sel>&as_of=…`;
  severity cards from `GET /api/v1/findings/facets` with the same params (one scanner's buckets
  only — the dropdown swaps, never merges).
- "Two questions" cards + Build-history digest sub-timeline (`runtime_inventory_at_T` vs
  `vulns_as_scanned_at_T`, kept as two distinct facts): **M8b point-in-time API — not shipped**;
  until M8b these render the C-1 "history available after M8b" state. `T=now` per-scanner
  findings work today.

**States:** loading; **"Not yet scanned then"** (T before the first committed scan); build-changed
marker (never a silent gap); scanner-silent; degraded; C-1 pre-M8b state for any `T<now`. A
refused build-history read says so in the Build history card and is never read as "not yet
scanned": neither the stat nor the "Not yet scanned then" card shows (issue 833 F5).

**Changed vs SCREENS.md:** scanner dropdown is a **read** lens only (no version anything — D41);
EPSS/KEV null on Trivy rows enforced here too (V4-DELTA-5); M8b dependency made explicit (C-1).

---

## 9. Approvals → Decisions queue (bolt: **M9d**)

Re-pointed from the old justification/impact/action shape to **`system-decisions`** (V4-DELTA
conflict 2).

**Data:** `GET /api/v1/decisions/approvals?cluster_id=…` — **gated by
`can_accept_audit_final`; the nav item is hidden without it** (403-capability-hidden). Row detail
+ actions: `GET /api/v1/decisions`, `POST /api/v1/decisions/{id}/revoke`,
`PATCH /api/v1/decisions/{id}` (revoke+new, D40).

**Columns:** CVE (mono) · type · **scope** (images and/or namespaces; empty = cluster-wide) ·
justification · approver · **expiry** (expired decisions resurface) · status (active / revoked
struck-through / expired) · when. Row → finding detail's "Decisions on this CVE".

**States:** loading; empty ("no pending decisions"); 403 (nav hidden); degraded.

**Changed vs SCREENS.md:** decisions shape replaces approval fields (V4-DELTA-2); capability
gate + nav hiding (A-4); revoke+new editing (D40).

---

## 10. Audit log (bolt: **M9d**)

Renders the structured D32 stream (A-5): `event_id`, `entity_type`
(finding/decision/token/user/settings/…), `action`, frozen `target_ids`, `revision`, ordered by
`(@timestamp, event_id)`; same-field edits order by `revision` (causal replay, D38/H8).

**Data:** **scheduled — M8c**: `GET /api/v1/audit?cluster_id=…&entity_type=…&actor=…&cursor=…` —
**plain session** (ruled 2026-07-07: read-only history of actions every user can already see;
Contributors already exposes derived views of it), cursor-paged, ordered `(@timestamp, event_id)`.
(Spec drawn against the D32 doc shape.)

**Layout:** facet rail (entity_type, action, actor) + filter bar + timeline table: When · Actor ·
entity_type+action tag pair · Target (frozen `target_ids`, rendered verbatim — never a
re-evaluated selector) · Detail. **Click-through only where `entity_type=="finding"`** (A-5).
Task column dropped (no field; Jira linkage is v1.1 — V4-DELTA-1).

**States:** loading; empty; degraded; retention note ("audit window bounded by
`system-audit-log` retention"). The count shows "-" until the first read answers (issue 833 G3).
A refused read follows the Findings rules in §3 (issue 833): the rows clear, a refused later
page stays put with Prev, a 429 says busy and a 410 says the results expired, an older answer
never replaces a newer one, and refused filter counts alone leave the rows and show "-" in the
rail (operator ruling 2026-10-12: F9's rule applies here too).

**Default view (issue 681):** the sidebar and command palette open the log at
`/audit?action=!login`, so it starts with a removable "Action is not Login" pill and the first
page is not all sign-ins. The filter lives in the address, never as a hidden default: a bare
`/audit` lists every event, and links that carry their own filters are untouched.

**Changed vs SCREENS.md:** A-5 (structured entity_type+action replaces the 8-string enum;
click-through rule; Task column dropped); endpoint scheduled (M8c).

---

## 11. Contributors (bolt: **M9d**)

**Data:** `GET /api/v1/contributors?cluster_id=…&range=…` (FR-15, shipped) — leaderboard +
TTR/SLA-hit computed server-side from `system-audit-log`. Scoped by the global trend window; the
"last 30 days" label follows the picker; window clamps to audit-log retention.

**Semantics label (A-m9):** any resolved-count series driven by trends carries
`resolved_semantics: "scan_resolved"` — label "scan-observed resolutions", distinct from human
`state=resolved` triage counts from the audit log. Don't conflate the two on one chart.

**Layout preserved:** team KPI strip → podium → leaderboard → resolved-over-time
(`GET /api/v1/trends/findings`, labeled per A-m9) → activity feed (from the M8c audit read —
same dependency as screen 10, feed only).

**States:** loading; empty (no triage activity in window); degraded; `T<now` fine (audit-log ≤T
is supported, C-1).

**Changed vs SCREENS.md:** A-m9 (resolution semantics label); activity feed blocked on the audit
read; severity colors stay firewalled from brand coral (unchanged rule).

---

## 12. Scanner status (bolt: **M9d**) — redesigned (C-3)

The v4 per-file ingest feed is gone. New composition per C-3:

**Per-(cluster, scanner) cards** — Trivy / Grype:
- **Freshness:** `GET /api/v1/scanners/freshness?cluster_id=…` — `last_ingest_at`,
  `silent_for_seconds` → health chip (ok / silent-N / never-ingested nulls → "no data yet").
- **Provenance (read-only, D41):** `scanner_version` · `scanner_db_version` · `scanner_db_built`
  from the latest committed scan-event — displayed as mono provenance lines with an
  "operator-managed (GitOps): change by swapping the image tag" affordance. **Never a control.**
  **Scheduled — M8c** provenance read (latest *committed* scan-event via the commit catalog;
  M9e's ScanningView shares the same read).
- **Last-N scan runs** (counts, durations): same M8c read.

**Trend:** `GET /api/v1/trends/scans?cluster_id=…&range=…` — scans over time per scanner
(replaces "ingested vs failed": accepted/rejected are Prometheus counters, not a UI API).
**Failed ingests strip (issue 575):** directly under the Scan ingest strip, joined to it as one
band — a single frame split by a canvas-coloured gutter, so each strip reads as its own lens
(operator ruling 2026-09-27, on built specimens) — `GET /api/v1/trends/ingest-failures?cluster_id=…&days=…&interval=…`, the
pushes refused per bucket, one bar series per scanner, on Scan ingest's axis (same range, same
day/hour rule) so a day lines up across both. Its own scale: runs peak in the hundreds, refusals are
a handful. Click a day to rewind, like Scan ingest; a range with none reads "No refused pushes in
this range", never an empty chart.

**Failed ingests — reinstated by ruling (issue 357, option 2, 2026-07-30):** the pushes JAVV itself
refused after the token check are recorded (`javv-ingest-failures-*`) and read per scanner by
`GET /api/v1/scanners/ingest-failures?cluster_id=…&scanner=…&days=…` (When · Scanner · Image · Stage ·
Error). **Still cut (A-7/D-4):** retry status, the Retry button, the "in retry queue" count and any
dead-letter feed — retries and dead-lettering stay scanner-local; JAVV only sees its own refusals.
**Placement (agreed by the operator 2026-09-26; §8.5 check on the built specimen in the UI PR):** one **Failed ingests** panel per
scanner, between that scanner's card and its committed-runs table (what needs attention before the
history; operator, 2026-09-26) — the screen's per-scanner columns carry it, so
no count mixes scanners (the prototype's single full-width table with a Scanner column is replaced).
Columns: When · Image (`-` when the push carried no image JAVV could read) · Stage · Error (HTTP
status + the server's message). Server-paged with the shared pager; empty = "No failed ingests in
this range." A self-contained panel (DESIGN.md §10), so it can sit on a composed dashboard.

**Scanner lanes (operator ruling 2026-09-27, on built A/B/C specimens — B chosen, plus C on narrow):**
each scanner is a lane — a head in the scanner hue with a 3px rule, then card · Failed ingests ·
committed runs. The lane's table heads take the scanner hue instead of the slate band, so the two
columns can't be confused at a glance. Lanes share one row grid (CSS subgrid): each section starts
on the same line in every lane. Below 1100px the lanes stop sitting side by side and a segmented
Trivy | Grype picker shows one lane at a time. Rejected: tinted lane backgrounds (too faint on the
warm canvas) and one-at-a-time on wide screens (loses the side-by-side comparison).

**States:** loading; never-ingested; scanner-silent (chip + global banner agree); degraded;
`T<now` → "history for scanner status is limited until the v1.1 metrics rollup" (C-1/D39). The
head count shows "-" until both reads answer, and after a refused one, never "0 scanners" (issue
833 F5); the alert follows the G2 rule (§3). The ingest strip on this and the other data screens
shows "last ingest -" when its freshness read is refused, never the previous read's time
(operator ruling 2026-10-12).

**Changed vs SCREENS.md:** C-3 (whole-screen redesign), A-7/D-4 (retry/dead-letter feed cut), issue 357 (JAVV-side refusals reinstated), D41
(version/DB lines are provenance display only), C-1 (historical limitation).

---

## 13. Settings (bolt: **M9e**; users/tokens panels also M9e)

Left sub-nav + panel + sticky save bar preserved — but the save bar appears **only on editable
sections**. Editable in MVP (C-4): **SLA policy · Users/Roles · Tokens · Scan scope · Data &
OpenSearch (retention) · Staleness timers**. Everything else is read-only display with an
**"operator-managed (GitOps)"** affordance.

**Before any cluster is listed** (a fresh install): Scan scope, the Scanning page's staleness
timers and the settings of Data & OpenSearch read per cluster, so they have nothing to read. Each
shows an empty state instead of its loading placeholder: *Settings for a cluster appear once it has
a scanner token. Mint one under Access & tokens.* A failed cluster list is not this state; the
shell reports that failure (issue 817).

### 13.1 Scan scope — editable (D43/FR-24)
**Data:** session read of the scan-scope doc — **D-2, planned, BLOCKED until it lands** (the
bearer `GET /api/v1/scan-scope` stays scanner-only; never widened). Write:
`PUT /api/v1/scan-scope` (M9e deliverable; capability-gated + journaled). Semantics fixed by
FR-24: empty include = all; ignore wins; fail-closed scanner fetch.
**Layout unchanged:** running-only toggle, include/ignore namespace lists, image globs, skipped
kinds.

### 13.2 Scanning — **read-only** (C-4, replaces v4's editable Scanners+Schedule+Vuln-DB)
Per-scanner cards display, from the latest committed scan-event's `effective_config` stamp
(D44, landed) + provenance (D41): running `scanner_version`, DB version/built (Trivy OCI /
Grype listing.json sub-tabs kept as **display**), effective tuning flags, applied scope.
**No version picker anywhere. No editable schedule/tuning.** Same M8c provenance read as
screen 12. Banner kept: "results kept per-scanner, never merged".
**Staleness timers** are the one editable control here (M3 backend shipped;
`PUT /settings/staleness` is the M9e deliverable — planned): `freshness_days` /
`scanner_down_days` + a banner-behavior preview.

### 13.3 SLA policy — editable (shipped)
**Data:** `GET /api/v1/settings/sla` · `PUT /api/v1/settings/sla` (gated `can_manage_settings`).
Days per severity (lowercase keys, incl. how negligible/unknown map — display note) + KEV
override hours.

### 13.4 Ignore rules → **Decisions** (redirect)
The v4 allowlist table is superseded by decisions (V4-DELTA-2): this section becomes a pointer
to the Decisions queue (screen 9) — decisions carry scope/justification/expiry/revocation.

### 13.5 Access & tokens — editable (shipped)
**Data:** `GET/POST /api/v1/admin/tokens`, `POST …/{token_id}/revoke`, `POST …/{token_id}/rotate`
(gated `can_manage_tokens`). Raw token shown **once at mint** (modal with copy affordance +
"you won't see this again"). Table: scanner scope, created, last_used, status.
Retired clusters (issue 765, `GET /api/v1/clusters?include_retired=true`) are named in the table
and listed apart in the mint picker under **Retired**; picking one says its first scan on the new
token brings it back to the cluster list (operator ruling 2026-10-07).
The mint picker always ends with **New cluster…**, which opens a Cluster ID field (the UID of the
cluster's `kube-system` namespace, with the `kubectl` command that prints it) checked against the
backend's ID rule. On a fresh install it is the only choice. A cluster is listed once its first
token exists, so after that mint the cluster list is re-read and the new cluster shows in the
switcher at once (operator ruling 2026-10-11 on a built A/B, option A; issue 817).
If a mint or rotate succeeds but its reply arrives with a body that could not be read, the token
exists and its value is lost. An error toast then says: *The token was created, but its value did
not reach this page. Rotate it to get a value you can copy.* (operator ruling 2026-10-10, issue 749).

### 13.6 Users & roles — editable (shipped)
**Data:** `GET/POST /api/v1/admin/users`, `PATCH …/{username}/role` (revokes their sessions —
confirm dialog says so), `PATCH …/{username}/disabled` (**409** on the last enabled admin —
inline error), `POST …/{username}/password-reset` (temp password + must_change) — all gated
`can_manage_users`. Reserved usernames `system`/`fleet` → 422 inline.
**Roles panel (A-4):** renders the 4 roles as **capability bundles** (viewer — none · triager —
can_triage · security_lead — + can_accept_audit_final · admin — *), from `system-roles` content.
The v4 5-role permission matrix is gone.
> **RULED (A-4, 2026-07-07): keep 4 roles.** A 5th can be seeded later as a `system-roles` data
> change, no migration.

**Recent sign-ins (card-head action):** opens the Audit screen with the lens pre-applied
(`/audit?action=login`) — the journal already filters `action` server-side, so this is a URL, not
a second read. Fleet-scoped auth rows only became visible to the UI when `audit_tenant_query`
started admitting rows with no `cluster_id`.
> **RULED (2026-07-30): a canned lens link, not a sign-ins card.** A card would count sign-ins as
> if they were all of auth activity, but **failed logins are not journaled** — only a metric and a
> log line. Revisit as a new issue if/when failure journaling lands.

### 13.7 Data & OpenSearch — editable (Admin)
Per-cluster retention days, rollover settings, snapshot repo/schedule + manual snapshot/restore —
retention/rollover offered **only** for time-partitioned append families; the mutable family
(findings, watermarks, scan-orders, system-*) never gets a drop control.
**Data:** `PUT /settings/retention`, `PUT /settings/rollover`, `POST /snapshots`,
`POST /snapshots/{id}/restore` — **M9e deliverables, planned, BLOCKED until they land**; gated
`can_manage_retention` / `can_restore_snapshot` / `can_drop_index`, journaled.

### 13.8 Cluster
`cluster_id` immutable (mono). `cluster_name` **editable** — the D-5 registry doc was ruled in
(**M8c**); rename is a `system-config` write, journaled, display-only (never a query key).

**Retirement (issue 765)**, three parts on the same panel:
- **Retire row** (in the Cluster card, below `schema_version`): `Retire cluster…` opens a confirm
  dialog; `POST /api/v1/clusters/{cluster_id}/retire` (`can_manage_settings`, journaled). The
  cluster leaves the list, the switcher and All clusters, its push tokens are revoked, its data is
  kept; the first scan on a newly minted token brings it back. 409 = already retired.
- **Cluster retirement card**: retire after N days without an accepted scan, or Never (seg
  control), and Warn before N days; `GET/PUT /api/v1/settings/retirement`. Edits this cluster's
  override when one exists, else the fleet default (also with no cluster selected), and says
  which. Refuses a window not longer than the scanner-down timer of the doc it edits (the
  cluster's own for an override, the fleet's for the default; named in the hint) and a warning
  not shorter than the window, inline on that field and with the save bar disabled. The backend
  checks the same timer; its 422 reason is shown when the timer was not known yet.
- **Retired clusters card**: every retired cluster (`GET /api/v1/clusters?include_retired=true`),
  since a retired one can no longer be selected; per row the last scan, `Bring back`
  (`POST .../unretire`) and `Delete…` (`can_manage_retention` only). Delete opens a dialog listing
  what goes and what stays (audit history; earlier snapshots) and enables only once the cluster's
  name is typed, and cannot be closed while the delete runs; `DELETE /api/v1/clusters/{cluster_id}`,
  503 = finish it by deleting again, 409 = it was brought back meanwhile (the list reloads).
  A cluster whose delete did not finish (`delete_started`, issue 778) offers only `Delete…`, with
  "Its delete did not finish. Delete it again." under its name; un-retiring it is refused (409).
  Bringing back a cluster retired by hand (`retirement_mode: manual`) says its tokens were revoked
  and its scanners need a new one; an automatic retire left them working, so its toast does not.

**States (all sections):** loading; 403-capability-hidden (section hidden from sub-nav without
its capability); save-bar dirty/saved; degraded; 409/422 inline errors as noted.

**Changed vs SCREENS.md:** C-4 (Scanners/Schedule/Vuln-DB → read-only effective_config +
provenance; **`config.versions` selector removed — D41**), D-2 (scan-scope session read planned),
V4-DELTA-2 (ignore rules → decisions), A-4 (capability bundles replace the matrix), 13.7 new
(V4-DELTA Data & OpenSearch).

---

## 14. Notifications bell (bolt: **M9f**)

**Data:** `GET /api/v1/notifications` + mark-read PATCH — **D-3, planned (ships with M7
slice 3), BLOCKED until then**. Badge count is the server-computed unread count; polled (no
broker, NFR-9).
**Categories:** SLA-overdue-assigned-to-you · newly-assigned · **ready-export** — the export item
shows **"expires in Xh"** (C-2) and opens `GET /api/v1/reports/{id}/download`; on **410** the
item flips to "expired — re-run the export" (never a dead link). **Cluster retiring** (issue 765):
written once per silence to every settings admin; names the cluster and the date it is due to be
retired (`ref` = `retires_at`; the sweep retires on its first run from then), or that it was due
and is held while no cluster scans, or that it has been retired; withdrawn by the sweep when the cluster scans again; opens
Settings › Cluster for that cluster, or says it is no longer listed and opens the panel with
Retired clusters.
**States:** loading; empty; 410-expired per item; degraded (badge pauses, no stale count).
**Changed vs SCREENS.md:** ready-export category + expiry/410 affordances (C-2/C-7); endpoint
BLOCKED (D-3).

---

## 15. Global search (bolt: **M9f**)

**Data:** three scoped, server-paged queries against the shipped read — no search endpoint is
invented: CVE match `GET /api/v1/findings?cluster_id=…&cve_id=<q>` · image match
`…&image=<q>` · namespace match `…&namespace=<q>`. Grouped dropdown (CVEs → finding detail;
images → image detail; namespaces → filtered Findings). Package-name search: the filter family's
coverage of `package_name` must be **verified at M9f kickoff**; if absent, that result group is
dropped (not client-filtered).
**States:** typing (≥2 chars); no-results; degraded.
**Changed vs SCREENS.md:** search = composed findings queries (server-paged), not a bespoke
endpoint; package group conditional.

---

## 16. About (issue 341)

**No prototype screen.** Grammar sources (DESIGN.md §8 source 2):
- ui.nuxt.com `PageHeader`;
- Framework7 grouped list rows (a name, a right-aligned mono value, a footer hint).

**Width: wide**, ruled by the operator on the built specimen (2026-09-29, an A/B at 1920px: A wide vs B narrow; at 1366 and 1024 the two are identical).
**Nav:** the last group **Help**: *Guide* (§17), then *About* (`info` icon), both ungated. The
group's dot is `--sect-help`, an alias of `--side-label` (neutral by operator ruling,
2026-09-29). The sidebar footer's version lines link here too. Both routes are live before any
cluster enrolls (`isColdStart` exempts `help`). About and the guide were one page until the
operator split them on the built specimens (2026-10-01).
**Data:**
- `GET /api/v1/meta`: the release, store schema, report formats accepted, OpenSearch version
  (live) and Python version;
- the frontend's own version from `src/version.ts`;
- `GET /api/v1/scanners/provenance` for the selected cluster: Trivy/Grype version, vuln-DB version
  and build time.

**Actions:** *Copy diagnostics*, a plain-text block of every version plus the browser and the
time (the toast confirms). **Links:** `UPGRADING.md`, verifying the signed images, `docs/API.md`;
the docs site once #639 lands.
**States:** loading (skeleton); `/meta` failed (visible error); OpenSearch version `null` →
"unavailable"; no committed scanner run for the cluster (empty); no cluster selected.

## 17. Guide: How to read JAVV (issue 341)

**No prototype screen.** Grammar sources (DESIGN.md §8 source 2):
- ui.nuxt.com docs page: `ContentToc` ("On this page", the active row following the scroll);
- CloudNativePG "Before you start" for the glossary: a bold term, then one to four plain
  sentences.

**Layout (operator ruling on built specimens, 2026-10-01, A of four: A rail + cards, B one
reading card with the contents on the right, C an accordion, D overview tiles):** "On this page"
is the shared `SectionNav` (Settings' left menu, moved into the kit so both screens use one
component), sticky on the left; one card per section beside it. **Width: wide.** **Nav:**
*Help → Guide* (`book` icon, an open book drawn for JAVV by operator ruling 2026-10-01: no
licensed icon sets), before *About*.
**Content:** eight sections: the time range, now vs new, two scanners never merged, scans and
freshness, images are digests, triage, a state or a risk acceptance (issue 698: the two side by
side, what the Approval list shows, and two worked examples, written in Simplified Technical
English), and a glossary that carries the data dictionary (#351 §6). Written for the people using the app: plain words, no internal decision codes, no
diagrams, no em dashes (operator rulings, 2026-10-01). Filter labels, the states a person can
set and the VEX reasons are read from the app's own definitions, not retyped.
**Links in:** `/guide#<section>`. The shell's URL re-stamp keeps the hash, and the router
scrolls only on arriving at a section, so changing the range or cluster on the page doesn't jump.
Two screens point in through the shared `GuideLink` (operator rulings, 2026-10-01: words on the
banner, a popover on the strip, the filter-rail tooltips unchanged):
- the freshness banner ends with the link *What this means* → `#scans-and-freshness`;
- the ingest strip has an info icon beside its explanation (outside the truncating text, so it
  is never clipped) that opens the time range's title and summary, then *Read more in the
  guide* → `#time-range`.
**States:** static content, no reads, so no loading, empty or error state.

## 18. Page not found (issue 674)

**No prototype screen**, and the app had none: an address no route matched rendered an empty
body. Grammar source (DESIGN.md §8 source 2): ui.nuxt.com `Error`: the shell stays, and the
centre holds a status code, a title, a message and one primary way out. Framework7 documents no
error page.

**Layout (operator ruling on built specimens, 2026-10-02, A of two: A the status-code layout on
the page ground, B the kit's empty-state card with no code):** centred on the canvas, no card:
"404" in mono coral, the title *Page not found*, one plain sentence, the address that failed in a
mono chip, then *Back to Overview* (primary) and, only when the visitor came from inside the app,
*Go back*. **Width: wide.** **Nav:** none; it is the router's catch-all, the last child of the
shell, so the sidebar and the auth gate still apply (a signed-out visitor lands on login).
**States:** static, no reads.

The layout is one component, `components/system/ErrorPage.vue`, shared with the crash page below.

### A page that fails while it is drawn (issue 675)

**Ruling (operator, 2026-10-02): the whole page is replaced, not the panel that failed.** Same
layout as above, inside the shell: "Error" in mono coral, the title *This page could not be
shown*, one sentence, then *Try again* (primary) and *Back to Overview*. The sidebar and the top
bar keep working, and moving to another page clears it.
- **What replaces the page:** an error raised while the page is set up or drawn, and a page whose
  file fails to load. **What does not:** an error in a click handler or a watcher. The page on
  screen still works, so the error is logged and the page stays.
- **Where:** `components/system/CrashBoundary.vue` around the routed page in `AppShell`; the rule
  is `replacesPage` in `system/crash.ts`. Every caught error is logged (`page crashed`,
  `page error`, `page failed to load`, `app error`) and reaches the backend log through the
  client-events beacon. Each line carries up to five frames from the top of the error's stack (`stack`,
  without the page's origin), so it names the file that threw (issue 749). A promise rejection
  that nothing caught is logged too, as `app error` with `info: unhandled rejection`.

### A backend that cannot be reached (issue 675)

**Ruling (operator, 2026-10-02): no full-page replacement.** The health banner and each screen's
own failure state stay as they are.

### The maintenance page (issue 675)

`frontend/public/maintenance.html`, served by the proxy in front of the app, not by the app: one
static file with no script, no font and no request to the backend, so it shows with the backend
switched off. **Look (operator ruling on built specimens, 2026-10-02, B of two: A the not-found
layout, B a card):** a white card on the canvas with the brand mark, like the login page. It has
no shell (there is no session to draw one for), falls back to system fonts, and asks again every
minute. **No in-app switch** (operator ruling, 2026-10-02): how to switch it
on is `development/RUNNING-THE-STACK.md` § R1.

---

## 19. Data inspector: the job cards (issue 556)

Two cards under the console, both fed by `GET /api/v1/admin/jobs` (one fetch, one poll while
anything runs), both drawn as the same table (`components/system/JobsTable.vue`, on the shared
table skin). Ruled on built specimens, 2026-10-02: first a status chip on every row, then (after
the first build stacked unlabelled lines in one column) a table with column headers, the way job
lists are drawn elsewhere.

- **Columns:** Job (icon, name, what it does) · Schedule · Last run (the time, with the counts or
  the error under it) · Next run · Status, plus the buttons in Repair actions.
- **Repair actions**: the three jobs that have a Run button. Lifecycle also has Dry run.
- **Scheduled jobs**: the four jobs the backend only runs on its schedule (export queue, export
  cleanup, old findings cleanup, expired sessions). Read-only: no actions column. The intro names
  the timezone the schedules are read in, and says so when the scheduler is switched off.
- **Schedule cell:** the cron expression the operator set, not rewritten in words; `by hand only`
  for a runnable job with none (Rebuild state), `switched off` for a scheduled-only job with none.
  Not editable here: schedules belong to the deployment (`docs/CONFIGURATION.md`, "Background jobs").
- **Status chip** (the kit's dot-and-word chip, on every row): `on schedule` (ok), `late` (warn),
  `failed` (down), `not run yet`, `scheduler off` and `not scheduled` (muted). `late` means the job
  missed a whole scheduled run (docs/API.md, `health`).
- Below about 760 px of card width the table scrolls sideways inside its card.

## Cross-cutting (unchanged rules, restated)

- Deep-links pass presets into `useFilters` — presets now serialize **lowercase** severities and
  6-state values (A-1/A-2).
- RelTime everywhere; deadlines absolute. Esc/arrow keyboard patterns; coral focus rings.
- First-run/empty states on every data screen (M9f owns the shared components).
- Capability gating on every mutating affordance — from `/auth/me` capabilities (A-4); client
  gate is convenience, server is authority.
- All timestamps/IDs/versions in the mono face (`--font-mono`); severity colors from the token map only; coral/amber
  never encode severity (ui-foundations).

## RESOLVED register (all six DECIDEs ruled by the operator 2026-07-07, #237)

| Id | Where | Ruling |
|---|---|---|
| A-1 | Findings rail, Overview KPIs | **Show** `negligible` as its own muted bucket |
| A-4 | Settings → Users & roles | **Keep 4** seeded roles (5th = later data change) |
| A-6 | Export dialog | **Session-only stays**; `can_export` parked as a tracked idea (issue, unscheduled) |
| B-1 | Overview donut, Findings facet/column | **KEEP the donut** per v4 design — envelope `ptype` ships in **M8d** |
| C-6 | Saved views | **Server-side** — `system-views` index + CRUD in **M8e**; owner column returns |
| D-5/C-5 | All clusters, Settings → Cluster | **Build** the `system-config` cluster registry — **M8c** |

## BLOCKED register (all scheduled)

| Screen | Needs | Scheduled |
|---|---|---|
| Export schedule download, Bell | `GET /api/v1/reports/{id}/download` · `GET /api/v1/notifications` + mark-read | **M7 slice 3** (D-3) |
| Settings → Scan scope | Session read of the scan-scope doc | **M9e** (D-2) |
| All clusters, Settings → Cluster | Cluster registry read (+ rename write) | **M8c** |
| Audit log, Contributors activity feed | `GET /api/v1/audit` (plain session, cursor-paged) | **M8c** |
| Scanner status, Settings → Scanning provenance | Latest committed scan-event read (provenance + effective_config + last-N runs) | **M8c** |
| Running images inventory metadata | Latest-complete-inventory read (replicas, seen) | **M8c** (check M8b overlap first) |
| Overview donut, Findings ptype facet/column | `ptype` in envelope + mapping + facets | **M8d** |
| Saved views CRUD | `system-views` index + `/api/v1/views` endpoints | **M8e** |
| Image detail point-in-time | M8b point-in-time query API | **M8b** |

## SHIPPED-DELTAS register (ruled deviations — the contract vs what was built)

Added 2026-07-16 (#410) so this contract and the app stop diverging silently. Every deviation
below was an **operator ruling against a built specimen** (recorded in the owning bolt README's
`## Updates` + its issue); this register is the one-hop index. The rule stands: a screen's
grammar is the prototype's — substituting it needs a live ruling (DESIGN.md §8.5).

| § | Contract said | Shipped | Ruling / record |
|---|---|---|---|
| 13.4 | Ignore rules → Decisions redirect stub | **No nav entry at all** — decisions live on `/approvals` + finding detail | 2026-07-15, M9e README (supersedes the #237 row-20 stub ruling) |
| — | (v4 prototype) per-CVE audit panel | **Struck** — no screen; the content ships on finding detail + Approvals + Audit | 2026-07-15, M9e README row 24 |
| 13.2 | (v4 prototype) scanner version select, tuning writes, enable toggles, Schedule section | **Read-only** provenance + `effective_config` cards; version = image-tag swap (D41), tuning = env/GitOps (C-4), no enable concept (D30), schedule = manifest | 2026-07-07 + 2026-07-15, M9e README §C |
| 13.2 | — | Namespace scope lists are **exact matches**; globs only on `exclude_images` | 2026-07-15, M9e README (verified in `scanner/scope.py`) |
| 13.3 | "Security Lead can edit" SLA | Edit gate is **`can_manage_settings`** (admin bundle) | M9e README row 5 |
| 13.6 | 5-role matrix, user delete | **4 capability bundles** (A-4), **disable-never-delete**, invite = temp password + `must_change` | M9e README row 8 |
| 13.7 | (v4 prototype) 4 editable per-purpose retention windows | **One** editable window over the 4 append families; protected families render read-only with the why written in the panel | 2026-07-15 ruling, M9e README row 23 |
| 13.7 | — | Panel additions beyond the contract: report/export-TTL setting (row 11: now runtime-editable), findings-cleanup window (D37/M12), read-only **OpenSearch runtime** card (§D), snapshots restore into `restored-*` copies only | M9e README rows 10/11 + §D |
| 13.8 | `schema_version: 3` | **4** (M8d ptype bump) | M9e README row 9 |
| 13.8 | (not in the contract) | **Cluster retirement** (issue 765): retire row in the Cluster card, a Cluster retirement window card and a Retired clusters card on the same panel (not a new Settings section); delete confirm lists what goes and what stays and needs the name typed | 2026-10-07 §8.5 A/B rulings on built specimens: placement A (Cluster panel), window card moved to the Cluster panel, delete dialog B (list + typed name) |
| 13.8 | (not in the contract) | **Unfinished delete** (issue 778): a Retired clusters row whose delete did not finish offers only Delete, with a note under the name | 2026-10-08 §8.5 A/B ruling on built specimens: B (note) over A (Bring back hidden, no note) |
| global · 1 | (not in the contract) | **Retirement countdown** (issue 765): its own amber line under the freshness banner, red on the last day; on All clusters a chip under the cluster's name | 2026-10-07 §8.5 A/B rulings on built specimens: B (own line) over a sentence inside the freshness banner, B (chip) over a Retires in column, which pushed the full-width table past the screen at 1440 px |
| 14 | (not in the contract) | **Cluster retiring** bell row (issue 765): title names the event ("Cluster retiring"), the description names the cluster and its date; opens Settings › Cluster for it | 2026-10-07 §8.5 A/B ruling on built specimens: A (event title) over the cluster's name in the title |
| global | FE freshness banner on a build-time env var | Banner + fleet chips read the **live staleness timers** (selected cluster's effective window); `VITE_FRESHNESS_BANNER_HOURS` removed | M9e README row 14 |
| global | — | Severity everywhere is the **six-word canonical vocabulary** (D46); verbatim scanner casing is display-only | D46/#274 |
| 2 | (v4 prototype had no Scan-activity card; the built one duplicated IngestLens) | Scan-activity card **dropped**; slot carries **Top components** (restored prototype card, ≤100-package server board w/ per-scanner unique-CVE counts, now-only read) + **Riskiest images** (ranked running images off the images read, rewindable) — both on the shared table skin + GridPager; Overview goes `wide` | 2026-07-16 §8.5 ruling on built specimens: **keep both** |
| global | (prototype: `--panel` table heads, dashed ghost add-filter) | **Section identity accents** (`--sect-*` tokens: sidebar group dots + head-card top bar via route `meta.section`), **scanner identity dots** (seg-control options + mix-bar labels wear trivy-teal/grype-violet; coral selection language untouched), **table-head band = solid slate** (`--table-head-bg: var(--slate2)` + parchment text, one token app-wide; third ruling on this surface — panel invisible, bg merged, washes faint/busy), **add-filter on card bg + darkened dashes** | 2026-07-16 §8.5 rulings on built specimens: keep-all accents · band B2 of B1/C/B2 |
| 6 | (v4 prototype) narrow finding detail: 8-col per-scanner evidence table, stacked full-width cards, sticky triage rail | **Wide route**; evidence table **transposed** (scanners = columns, attributes = rows); grid rows share tracks — evidence \| docked triage (equal height), decisions \| activity side-by-side, affected components full-width; GridPager always visible on all three tables; slate band on triage + activity heads ONLY; sticky removed; "scanners disagree" written out; unassigned chip | 2026-07-17 §8.5 A/B rulings on built specimens (#434): transposed in · docked over slideover · tracks-or-full-width |
| 3 | (prototype pills: include-only, "is / is one of") | **NOT-pill** (issue 349): a negated filter renders the fill/outline duality — hollow body (transparent on the canvas, 1.5px border, no shadow) with ONLY the op words ("is not"/"is none of") in red (`--fpill-not-op`) + bold; the op word doubles as the include⇄exclude toggle; picker gets an is/is-not seg. Red-tint fill specimen (B) built and LOST | 2026-07-17 §8.5 A/B ruling on built specimens: outline wins, keep the red op words only |
| 3 · 5 · 7 | (the first shipped cut of the value bar: inset from the cell edge, flipped below on row 1, no motion) | **Grid bar reworked against the running Kibana Discover** (issue 349 §2 follow-up): flush on the cell's top-LEFT corner (`left: 0`, as Kibana measures), overhanging UPWARD on **every** row — the first-row flip was built on a false clipping premise and made row 1 unusable, because the seam then held two bars and reaching for either swapped which was lit. Row 1 inverts to a light fill (the slate bar computes 1.17:1 on the head band) and every bar gains a `--chip-hi` hairline. Square corners + a gap between the marks, because at DPR 1 the bar cannot land on the pixel grid (card at x.5, 37.5px rows, percentage columns) so radii stair-step and 1px rules fringe. Reveal now LIFTS (ruled `t-pop`, mirrored) instead of popping | 2026-07-28 §8.5 rulings on built specimens: left corner · invert+hairline · gap over divider · square over 6px/3px |
| 3 · 5 · 7 | (prototype: filtering is the rail checkbox only — cells and rail rows offer no exclude) | **Value actions** (issue 349 §2): a `+`/`−` pair beside a value in the rail and in the Findings/Images/Audit/Approvals grids, revealed by the row's own hover; `components/filters/ValueActions.vue`, the M9a filter module's third part. An excluded rail row stays LISTED, struck in `--fpill-not-op`, so it can be clicked off. At-rest specimen (B) built and LOST — at 198 glyphs on a 25-row page it wrapped the narrow namespace column and inflated row heights against the §4 density contract. A knowing exception to DESIGN.md §5 "hover-only is not discoverable" and to Nuxt UI's at-rest row actions, bounded: an ACTIVE action always shows, and keyboard focus reveals it. Cells earn the affordance only where the cell value IS the filter value — a multi-namespace row, the shortened image cell and the severity-mix columns get none. The Images rail additionally grows **Image + Tag** as data-driven dims (deliberate: the cell action needs the fields, and listing them keeps an exclusion legible in the rail), capped at 32 by count like the server facets — `q` contains-matches both, so the note's "search reaches the rest" holds | 2026-07-28 §8.5 A/B ruling on built specimens: hover-reveal wins |
| 6 | §6 card counts "from `/findings/facets`" | Held EXACTLY as written — a `/findings`-based count was built first and immediately leaked a PIT per card + 429'd the concurrency cap; count = severity-bucket sum from facets | 2026-07-17, M9f slice 4 (the spec was right) |
| 6 | — | Cards additionally show the schema-v2 **workbench capture** (columns/density/sort/relative window; cluster-agnostic by shape) and page through the kit GridPager (operator ask); apply = deep-link round-trip incl. `!`-negation grammar | 2026-07-17, M9f slice 4 |
| global | (prototype topbar: disabled search input, text sign-out, mixed control heights) | **Topbar register**: all three controls (cluster switcher · time picker · search) at **40px** with **2px `--line` borders**, keep-beige (white-chip and slate-tint A/Bs LOST); search sits on `--bg` with ink hint + real control wash; Sign out = kit UiButton `control`; FilterBar pills/add-filter at **38px** | 2026-07-17 §8.5 rulings on built specimens (M9f slice 2) |
| global | (prototype primary button: gloss — inset highlight + drop shadow) | **Flat solid coral** (solid-button grammar): hue kept, gloss removed; hover/active = `--coral-dd` (a full step — `--coral-d` was too small). Muted-terracotta and soft-wash variants built and LOST | 2026-07-17 §8.5 ruling (M9f slice 3) |
| global | (prototype drawer: flush right panel, opaque card) | **Glass floating drawer** (SlideoverShell): `--glass` 0.78 white + 14px backdrop blur, neutral `--glass-edge`, 12px backdrop detach + 4px backdrop blur, nested head radius (kills the corner seam). 0.65 opacity tried and reverted | 2026-07-17 §8.5 rulings (M9f slice 3) |
| global | (prototype: topbar search input) | **⌘K command palette** (issue-319 ruling): composed `/findings/groups` queries (CVE/image/namespace) + jump-to-screen off the ONE nav model; the topbar "input" is a button that opens it | 2026-07-17, M9f slice 2 |
| global | — | **Notification bell**: ringed count badge (server unread, pauses on failed poll), inbox rows with per-row ✕ + Mark-all-read/Clear-all (kit mini buttons), ready-export resolves the signed token on click (expired flips the row), toast ECHO for mid-session arrivals only | 2026-07-17 rulings (M9f slice 3) |
