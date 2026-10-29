# Screens — javv (v5, refreshed against the shipped backend)

> **Living UI contract** (formerly `SCREENS-v5.md` in the old `v5/docs/` folder — suffixes dropped 2026-07-16, #410).
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

**Time range, an absolute range (issue 984):** the two date fields take no date after today.
Apply stays disabled for an end date after today, as it does for a start after the end. A time
later today reads as now. A later day put dates on the button and the captions that the charts
did not show.

**Data**
- `GET /auth/me` — `username`, `role`, `capabilities`, `must_change`. All gating flows from
  `capabilities` (A-4). Nav items whose screen is capability-gated (Approvals, admin Settings
  sections) are **hidden** without the capability.
- `GET /readyz` (polled) — drives the global **degraded banner**; any API `503` envelope raises it
  too, as does a proxy's `502` or `504`; auto-clears on `200`. The banner and the sidebar footer
  say what is down (issue 675): a `503` is the backend reporting its store ("Search backend
  unavailable. Check OpenSearch health.", footer "Store degraded"); no answer or a proxy error is
  the backend itself ("The backend is not answering. Screens cannot load until it is back.",
  footer "Backend not answering"). A store that answers but cannot serve everything gets the
  **amber** line (`tone-degraded`, `role="status"`) instead of the red one (issue 832; tone and
  read-only copy ruled on the A/B deck 2026-10-12, red copy ruled on the plan 2026-10-13):
  read-only, from `/readyz`'s `checks.store: "read-only"` or a `503` with the problem type
  `store-read-only`, says "The store is read-only: its disk is full. Reads work; changes are not
  saved."; red, from `checks.store: "red"`, says "Part of the store is not available. Some screens
  and changes can fail until it recovers." The footer keeps "Store degraded" for both (ruling:
  no change).
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

**Loading bar (issue 902, operator decision D1 B, 2026-10-17).** A 2px coral bar on the bottom
edge of the topbar shows when a page change or an API request is open for more than 250 ms. It
grows more slowly near the end, then fills and fades when the work ends. The notification poll
does not count. The main area has `aria-busy` while the work is open. The code of the other pages
loads while the browser is idle, so most clicks show the new page at once.

**Window head (issue 1049, operator ruling 2026-10-29).** Every window (`ModalShell`) has a dark
blue head: the band of the table heads and of the side panel head (`--table-head-bg`,
`--table-head-fg`). The title is light, and the line under it has 75% of that color. The close
button has a light fill on the band, a stronger fill and a lighter edge on hover, a pressed fill
and the focus ring. These are the colors of the sidebar collapse button. No window changes the
head, so all 20 windows look the same.

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
`JAVV_LOGIN_MAX_ATTEMPTS`, all cases of a name counted together; the username can be typed in any
case: the backend looks for the name as typed, then in lower case, issue 965),
`POST /auth/password` (the only mutating route a `must_change` session may call),
`POST /auth/logout`, `GET /auth/me`.
**States:** bad-credentials (generic copy), locked-out (429 — "try again later", no countdown
oracle), forced password change (SEC-6: bootstrap admin / temp password), **server not answering**
(issue 675: no answer or a `5xx` from the session check, the sign-in or the password change shows
"The server is not answering. This page checks again on its own." in place of any credential
error; the page asks `/readyz` every 30 seconds, and when the server returns it re-checks the
session, so a visitor whose session is still good goes straight to Overview. A failed session
check is not remembered as signed out: the next navigation asks again), **store read-only**
(issue 832: a sign-in or a forced password change the full disk refuses, a `503` with the
problem type `store-read-only`, shows "The store is read-only: its disk is full." and starts no
re-check, since the server answers; the password change by operator ruling on PR 843), **session
not kept** (issue 869: a sign-in that answers `200` and a session check that finds no session.
The browser did not keep the cookie. On a page that is not a secure context, plain `http` and
not `localhost`, the form says "This browser refused the session cookie, because the page uses
http. Use https, or ask the admin to set JAVV_SESSION_COOKIE_SECURE=false." Else it says "Signed
in, but this browser did not keep the session. Allow cookies for this site, then sign in again."
The form stays on sign-in. A server failure on that check stays "not answering". Copy B of two,
ruled by the operator on built specimens, 2026-10-15).
**Rulings (operator, on built specimens, 2026-10-02):** the server-down message on the login page
is the form's plain red line (A of two; B was a tinted box). The banner for a backend that is gone
reads "The backend is not answering. Screens cannot load until it is back." (A of two; B ended
"Check that the JAVV backend is running.").
**The password rule** (issue 726): the forced change states it under the fields, as the
prototype does ("At least 12 characters. Your current password stops working once you set the new
one."), refuses a shorter password before sending it, and shows the server's own reason for a `422`.
**An ended session on the forced change** (issue 833): a wrong current password and an ended session
are the same `401`, so the page asks `GET /auth/me`. With the session ended, the form turns into
sign-in, emptied, with "Your session ended. Sign in again."; with it live, the message stays "Password
change failed. Check the current password." A change that landed but got no new session (a `200`
with no cookie) also turns the form into sign-in, with "Password changed. Sign in again." Copy ruled
by the operator on the issue, 2026-10-12.
**A forgotten password** (issue 761): the sign-in screen carries a note under **Sign in**, in the
prototype's `login-note` place (small, muted, centered): "Forgot your password? Ask an admin to
reset it. If no admin can sign in, see *A forgotten password* in the Deploying guide." The page is
named in words, the title in italics: no URL and no repository path (operator ruling, issue 833).
It is the same for every visitor (no user-existence hint) and is not on the forced change. Ruling
(operator, on built specimens, 2026-10-06): A, the note always shown, of two; B hid it behind a
"Forgot your password?" button. No self-service reset: users have no email and JAVV no mail server,
and OIDC (#131) moves those passwords to the identity provider.
**Changed:** copy states capability-based access; SSO/OIDC removed (post-MVP, per V4-DELTA).

---

## 1. All clusters (bolt: **M9c**)

Fleet landing page; layout preserved (KPI strip → cluster table with MixBar).

**Header card (issue 902).** While the fleet loads, the note says only "Fleet current state".
When the counts arrive, it adds "· 34 clusters · 33 need attention" (or "all healthy"), and the
card stretches to the right. Before, it showed "0 clusters" while it loaded. Overview's card
stretches the same way when "last sweep" arrives. The scanner switch in the head is a screen head
control: 30px high, with the 1px edge under it (issue 1039, DESIGN.md §5).

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
  only cluster listed. It moves on the banner's 10-minute tick, from the list the banner re-reads,
  so a cluster that scans again loses its chip without a reload.

**States:** loading (skeleton rows); empty (no clusters registered — cold-start copy); degraded;
**T<now → `LimitedHistoricalNotice`**: "Historical all-clusters view is limited until the v1.1
metrics rollup" (C-5/D39) — the current-state table is replaced by the notice, never a wrong or
expensive query.
The cold-start state ("No clusters registered yet") is the whole page on the nine data routes,
so its title is the page's one h1 in the page-title style (issue 829; operator ruling
2026-10-12).

**Changed vs SCREENS.md**
- Fleet KPI strip severity buckets: lowercase + `negligible` (A-1); per-scanner, never summed.
- Historical all-clusters explicitly limited (C-5).
- Cluster name source ruled: `system-config` registry (D-5 → **M8c**).
- "Replicas" column: fed by the **M8c** inventory read (see Running images).

---

## 2. Overview — single cluster (bolt: **M9c**)

**Head (issue 1039):** the scanner switch and **Triage critical** are screen head controls, both
30px high with the 1px edge. Triage critical is the slate primary at the size of a control button.

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

**Dashboard panels (issue 440).** The stat bands, Package type, Per namespace, Top components and
Riskiest images cards are panels of the dashboard catalog (`src/dashboards/catalog.ts`, DESIGN.md
§10). Overview reads the findings facets once and passes them to the stat bands, Package type and
Per namespace, so their numbers agree, as before. Top components and Riskiest images get their own
data: each shows the loading shimmer until its answer comes, and its own error text if the read
fails ("Component ranking unavailable.", "Riskiest images unavailable."). Before, both showed their
"no data" text while the read was open, and Riskiest images also showed it when the read failed.
When the cluster has no committed inventory yet (`inventory: null`), Riskiest images says "No
inventory committed yet. Images show once a scanner cycle completes." (at a past time: "No
inventory committed at this point in time."), not "No image findings in the running inventory.":
JAVV does not know what runs there, which is not a clean cluster. Operator ruling 2026-10-25 on the
A/B picture `visual-assets/440/440-riskiest-unknown-ab.png`.

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

**Several values** (issue 949): Severity, State, Namespace, Package type and Assignee take more than
one value. A second pick adds the value, and the filter bar reads "is one of". In exclude mode, the
bar reads "is none of", and the grid leaves out the rows with any of the values. Scanner takes one
value.

**Typed values** (issue 949 PR C, ruled 2026-10-21 on a built specimen): Image, CVE and Package
also take more than one value. In the filter bar's edit box, Enter adds the typed value to a list
under the input, and the box stays open for the next value. A click on a value in the list removes
it. A pick from a table cell adds the value, and the same pick again removes it. A pasted list with
commas adds each value. A filter takes at most 32 values (the API limit), and the edit box says so
when the list is full.

**Assignee with Unassigned** (operator ruling 2026-10-23 on a built specimen, issue 975, option
B): Findings refuses the two filters together, so the last pick wins. A click on Unassigned clears
the Assignee values. A pick of an Assignee value, or a change of Assignee from "is not" to "is",
turns Unassigned off. A message tells the user what changed, for example "Assignee cleared.
Assignee and Unassigned can't be used together." Assignee "is not" with Unassigned stays, because
the API accepts it. A link that holds both filters keeps both, and the grid shows the 422 text
(see States). Only a pick of Unassigned or of an Assignee value then picks the winner. A click on
another filter, or the removal of an Assignee value, keeps both.

**Counts after a pick** (issue 949, ruling 2): the Namespace, Package type and Assignee lists count
without the filter of their own field. After you pick a namespace, the other namespaces stay in
the list with their counts. An excluded value also stays in the list, with a line through it and
its count. The Unassigned count leaves out the Assignee "is" values (issue 979), because a click
on Unassigned clears them. Thus the count is the number of rows that the click shows. Assignee
"is not" stays in that count, because the click keeps it. All other groups count with all
filters. Thus Severity shows only the counts of the rows that the grid shows. A list shows at
most 32 values. A picked value that is not in them stays at the end of the list, with no count, on
every screen that uses the rail.

**A count of 0** (operator ruling 2026-10-23, issue 980, on each screen that uses the rail): a
value of a fixed list with no rows shows 0, as the prototype does. The fixed lists are Severity,
Scanner, State, Entity, Action and the Attribute flags. A value shows no count when its count is
not known: the server did not count the field (New in range), the server stopped at the cap of
the field before the value, or the scan history does not record the flag (KEV and Scanners
disagree at a past time). The cap is 32 buckets. The Audit log Entity and Action lists have a cap
of 64 (issue 983).

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

**The open search** (operator rulings on the issue 832 plan, 2026-10-13): each walk holds one of
the user's open searches until the grid closes it.
- Prev from the last page works: the grid reads with `keep_open`, so the last page keeps the search.
- Opening a finding keeps the walk, so Back lands on the same page.
- Leaving for any other screen closes it: the grid comes back on page 1, with its filters and sort.
- A change of filter, sort, page size, cluster or T, and Prev back to page 1, close it too: each
  starts a new walk.
- A reload or a closed tab closes it as the page goes.

**States**
- loading — skeleton rows; empty/first-run — "no sweep yet" friendly state; filtered-empty —
  "no findings match" + clear-filters.
- **A refused later page stays where it is** (operator ruling 2026-10-12, issue 833 G1): the
  alert, the grid's "could not be loaded" row, and the pager still on that page's range with Prev
  usable. The head count keeps the total, which page 1 of the same query gave (operator ruling
  2026-10-13). A **410** (the page's search expired after the keep-alive) says "These results expired.
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
- **A refused filter, 422** (operator rulings 2026-10-23, issue 975): the alert says "These
  filters can't be used together, or a value isn't valid. Check the filters." A 1-character search
  never gets to the server, so no 422 is about a short search. At a past time, a 422 for Assignee
  with Unassigned gets the same text. Any other 422 at a past time keeps the past-time text.
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
  **Who sees which button (operator ruling 2026-10-17, issue 892 option 1):** "New decision" opens
  the risk-accept dialog, so only `can_accept_audit_final` sees it, as in the prototype. Revoke shows
  on every active decision for `can_accept_audit_final`, and on an active `not_affected` decision for
  `can_triage`. A `risk_accepted` or `ignore_rule` decision is made, changed and revoked by
  `can_accept_audit_final` only (the server answers 403). An `ignore_rule` decision wears the
  "Risk accepted" tag, the state it gives the finding.
  **Expiry (operator ruling 2026-10-23, issue 984):** the first date in the risk-accept dialog
  is tomorrow in UTC. A date stops at 00:00 UTC on that day. The date field
  has that `min`. For an earlier date, "Create decision" stays disabled, and the hint says *Pick
  an expiry date after today.* The server refuses the same dates with the `expiry-passed`
  problem type, and the dialog then shows that text.
  **Expired (issue 984):** a decision with an expiry in the past has no effect. The card shows it
  as the prototype does. The status reads "expired", and the row has a line through it and no
  Revoke button. It goes after the active rows, with the revoked rows.

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

**Activity card:** the audit rows of this finding (`GET /api/v1/audit?finding_key=…`), which
include each bulk change that included it (issue 912). A row is: time, actor, then the action as
the Audit log's action pill (`ActionTag`, the same pill the Contributors feed uses). A single state
change adds nothing after the pill, because the pill names the state it set. A bulk row adds the
state tag, the assignee and the note that it set. An assignee or note row adds the new value, with
its label and value kept together. Operator decision 2026-10-18 (issue 918, option B), made on
built pictures of options A, B and C. A change to Not affected, a new reason and a bulk change
to Not affected add "Reason:" and the plain label of the triage panel, for example "Reason:
Component not present" (issues 924 and 931). The assignee and note rows say "Assigned to:" and
"Note:", the names of the triage panel.

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
- Schedule: `POST /api/v1/reports` (`kind: export`, needs `can_export`, issue 243). Status:
  `GET /api/v1/reports/{report_id}`. Download: `GET /api/v1/reports/{id}/download`. The
  schedule carries every filter on the screen; `EXPORT_PARAM_KEYS` must equal `ExportParams` in
  openapi.json (`export-params.spec.ts`, issue 962).

**States (C-2 — all drawn):** run-now streaming progress · **413 over
`JAVV_EXPORT_MAX_ROWS` (50k)** → "narrow the lens or **schedule off-peak**" (switch tab) ·
scheduled-pending → bell on done · **"expires in Xh"** on the bell item and the download row
(`JAVV_EXPORT_TTL_HOURS`, default 24 h) · **410 expired** → "download expired — re-run the
export" · 429 PIT cap with `Retry-After` · **export blocked** (issue 962; `exportBlockMessage`
in `findings/exportParams.ts`). The button of the open tab (Download or Schedule) stays off and
the dialog says why:
  - Schedule, a filter the schedule cannot carry → "A schedule cannot use these filters: <filter
    names>. Clear them, or use Run now." (at a past time: "… Clear them.", as Run now is hidden).
  - Schedule at a past time, a filter the scan history does not record (Search, KEV, Scanners
    disagree, Image, New in range) → "At a past time, a schedule cannot use these filters:
    <filter names>. Clear them."
  - Both tabs, Assignee with Unassigned → "An export cannot use Assignee and Unassigned
    together. Clear one of them."
  - Both tabs, VEX with Scanner is not → "A VEX file covers one scanner. Clear the Scanner filter
    first."
  - Both tabs, VEX with a scanner other than the screen's Scanner → "This screen shows trivy
    findings only. Pick trivy for the VEX file." The VEX scanner starts on the screen's Scanner
    when the screen has one.

**Changed vs SCREENS.md:** C-2 (TTL/expiry affordances + 410 state — new). A-6 (2026-07-07,
export stays session-only) is **replaced by issue 243 (2026-10-24)**: every export file needs
`can_export`, which `triager`, `security_lead` and `admin` hold and `viewer` does not. Ruled on
built A/B pictures (option A): a role without it still sees each export control (Findings, Audit
log, Contributors, Approval list, Running images), disabled, with `UiRoleNote` next to it: a key
and "Your role does not allow export." The control points at the note (`aria-describedby`).
`export-capability.spec.ts` pins the five screens.

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
must reproduce identical query params). The whole card is the link (issue 1004): its address is
the /findings address of the filters, so a ctrl click opens a new tab. A plain click applies the
whole view first (columns, density, sort, time window). The footer ends in a quiet
"Open in Findings ›", not a button.

**States:** empty ("save a filter set from Findings"); count-loading per card; degraded (counts
show em-dash); 403 on mutating someone else's view (edit/delete affordances hidden unless owner
or admin). The head count shows "-" until the list read answers, and after a refused one, never
"0 views" (issue 833 F5); the alert follows the G2 rule (§3).

**Changed vs SCREENS.md:** C-6 ruled server-side (M8e); owner column kept per the v4 design.
The card and the grid are `components/saved/SavedCard.vue` and `SavedGrid.vue`, shared with
Dashboards (§20, issue 440). **The card (issue 1004, operator rulings 2026-10-29 on A/B pictures
of the real app):** the title is a link whose layer covers the card, so a click anywhere on the
card opens the item. The badge, × and the buttons sit above that layer and keep their own clicks.
On hover and on keyboard focus the card stays white, its border turns coral and it rises 1px (the
prototype card, DESIGN.md §5). A line separates the footer, and the buttons in the card have the
darker border (`UiButton` `bordered`). The page color stays the warm paper (DESIGN.md §9). The
footer shows the owner as "Owner <name>" at the size of the other card text, and the name is
dark (operator, 2026-10-29). The badge that says who can see the item takes a color (operator,
2026-10-29, `--share-*` tokens). Only the owner is a quiet gray fill, everyone is teal, and a
role list is blue. Role ids show as words: security_lead reads "security lead".

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

**Filters:** the rail and the filter bar filter the served inventory in the browser. Severity,
Namespace, Image and Tag take several values: OR within a field, AND across fields. A second pick
adds the value (issue 950). Scanner takes one value. Findings keeps the one-value limit of its
backend (issue 949).

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

The "Showing results from" switch in the head is a screen head control: 30px high, with the 1px
edge (issue 1039).

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

**States:** loading; empty ("no pending decisions"); 403 (nav hidden); degraded. A refused read
keeps the rail's values with "-" for each count, since the counts come with the rows (operator
ruling 2026-10-13, issue 833).

**Filters (issue 952):** Status and Approver take several values. A second pick adds the value,
and the pill reads "is one of" (or "is none of" in exclude mode). Scanner and the CVE search take
one value, as on Findings. The Approver counts leave out the Approver filter, so a picked approver
does not hide the others. The Status counts follow the pick, as Severity does on Findings. A
filter stops at 32 values, the API cap, and the rail and the edit box show "A filter takes at most
32 values." The queue table is `components/approvals/ApprovalsTable.vue`.

**Edit dialog and the expiry (issue 984):** an edit keeps the current expiry unless it sets a
new one. The date field takes tomorrow in UTC or later. A decision whose expiry is in the past
needs a new date. Until the user sets one, "Revoke + re-issue" stays disabled, and the hint says
*Pick an expiry date after today.* That text also shows when the server refuses the date.

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
(Spec drawn against the D32 doc shape.) **Account events (operator rulings 2026-10-16 and
2026-10-17, issue 892):** the rows with `entity_type` `user` or `token` reach only
`can_manage_users`, in the list, the facets and the CSV. For the other users the rail does not offer
the `user` and `token` values nor their actions (sign-in, password, user, role and token actions),
which could only count 0 there (`auditFields()` in `audit/fields.config.ts`). In the same way, the
rows with `entity_type` `dashboard` reach only `can_manage_settings` (issue 440, ruling of
2026-10-25), and for the other users the rail does not offer `dashboard` nor the three dashboard
actions.
The Action list has 45 values. The server counts Entity and Action with 64 buckets, so each
action has a count. An action with no events shows 0 (issues 980 and 983). The User list keeps
the top 32.

**Layout:** facet rail (entity_type, action, actor) + filter bar + timeline table: When · Actor ·
entity_type+action tag pair · Target (frozen `target_ids`, rendered verbatim — never a
re-evaluated selector) · Detail. **Click-through only where `entity_type=="finding"`** (A-5).
Task column dropped (no field; Jira linkage is v1.1 — V4-DELTA-1).

**Detail (issue 931):** a field reads by its plain name, and a state or a reason by its label, for
example `State: Open → Not affected` and `Reason: Component not present → Vulnerable code not
present`. The names are in `audit/fieldLabels.ts`, taken from the screen that sets the value (the
triage panel, the settings pages). A test fails when the backend writes a field with no name. The
stored field and value do not change: the CSV export and the API keep them. Issue 933 adds:
- A change to Not affected shows its reason after the states:
  `State: Open → Not affected · Reason: Component not present`.
- A number setting shows as a whole number: `History retention: 90 → 105`, not `105.0`.
- A settings change kept as JSON shows only the values that changed, with the names and units of
  its settings page: `SLA policy: Critical 2 → 7 days`. A save with the same values shows
  `no change`. A job run shows its counts: `Counts: Sessions deleted 15096 · Grace period 24
  hours`. The names are in `audit/jsonChange.ts`, and a test fails when a backend setting or job
  count has no name.

**Action rail (issue 933):** the rail lists each action that the backend writes, by its plain name
(`audit/actionLabels.ts`). A settings change uses the name of its setting, for example `History
retention`. A test fails when the backend writes an action with no name or with no rail entry.

**States:** loading; empty; degraded; retention note ("audit window bounded by
`system-audit-log` retention"). The count shows "-" until the first read answers (issue 833 G3).
Paging and the open search follow the Findings rules in §3 (issue 832): Back from a finding
keeps the page, and leaving for another screen brings the log back on page 1.
A refused read follows the Findings rules in §3 (issue 833): the rows clear, a refused later
page stays put with Prev, a 429 says busy and a 410 says the results expired, an older answer
never replaces a newer one, and refused filter counts alone leave the rows and show "-" in the
rail (operator ruling 2026-10-12: F9's rule applies here too).

**Filters (issue 952):** Entity, Action and User take several values. A second pick adds the
value, and the pill reads "is one of" (or "is none of" in exclude mode). The User counts leave out
the User filter, so a picked user does not hide the others. The Entity and Action counts and the
activity chart follow every filter, as Severity does on Findings. A filter stops at 32 values, the
API cap, and the rail and the edit box show "A filter takes at most 32 values."

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
same dependency as screen 10, feed only). The detail line of a feed row uses the plain names of
the Audit log's Detail column, for example `State → Risk accepted` (issue 931). A settings change
or a job run shows the same line as in the Audit log, for example `SLA policy: Critical 2 → 7
days`, not `SLA policy → updated` (issue 933).

**States:** loading; empty (no triage activity in window); degraded; `T<now` fine (audit-log ≤T
is supported, C-1).

**Dashboard panels (issue 440).** The Handled findings strip and Triage progress are panels of the
dashboard catalog. Here the strip takes its series from the same `/contributors` response as the
board, so the two cannot disagree; on a dashboard, where there is no board, the strip reads that
route itself and its empty text does not mention a board.

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

**Skipped kinds (issue 891):** the scanner compares each listed kind with the kind of the direct owner of the pod. The comparison is exact and uses case. Thus the row has two parts:

- Four buttons (`UiToggleGroup`) show the workloads that Kubernetes makes. "Deployment pods" saves `ReplicaSet`, "DaemonSet pods" saves `DaemonSet` and "StatefulSet pods" saves `StatefulSet`. "Job and CronJob pods" saves `Job`.
- The "Other owner kinds" list holds all other owner kinds, for example `Cluster` of CloudNativePG.

The saved value stays one `ignore_kinds` list. A typed value can match no pod: `Deployment`, `CronJob`, or a known kind with a different case. For such a value, a note names the button to select.

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
Rotate shows on an active token only (issue 984). The new token takes the old expiry, so an
expired token needs a new token from Mint token. Revoke stays on an expired token. The server
answers 409 to a rotation of a revoked or an expired token.

### 13.6 Users & roles — editable (shipped)
**Data:** `GET/POST /api/v1/admin/users`, `PATCH …/{username}/role` (revokes their sessions —
confirm dialog says so), `PATCH …/{username}/disabled` (**409** on the last enabled admin —
inline error), `POST …/{username}/password-reset` (temp password + must_change) — all gated
`can_manage_users`. A new username has 3 to 64 lower-case letters, digits, dots, underscores or
hyphens, and is not `system` or `fleet` (issue 965); anything else is a 422. The invite form's
Username hint says "3 to 64 lower-case letters, digits, dots, underscores or hyphens". A field-check
422 shows the form's own text inline: "Rejected: a username has 3 to 64 lower-case letters, digits,
dots, underscores or hyphens. You cannot use system or fleet." Any other refusal, for example the
409 for a username that exists, shows the backend's message.
**Role names (issue 1039):** each role shows in words, as in the user menu: `security_lead` reads
"security lead". That is so in the Role list of each user, the Role list of the Invite window, the
"Change role?" window ("becomes security lead"), its message after the change, and the column heads
of the Roles table and their screen reader labels. The value that the form sends is the id.
**Roles panel (A-4):** renders the 4 roles as **capability bundles** (viewer — none · triager —
can_triage · security_lead — + can_accept_audit_final · admin — *), from `system-roles` content.
The v4 5-role permission matrix is gone.
**Roles table (issue 990, option A, ruled 2026-10-24):** one table on the shared table skin. A row
for each permission that `GET /api/v1/admin/roles` lists in `permissions`, with its name and what it
allows under it, and no id. A column for each role, fewest permissions first, so admin is last. A
cell has a check mark or a dash. Admin (`*`) has a mark in each row. A permission that a role holds
but the server does not list gets a row named by its id. The note under the table says that admin
also gets the permissions of later releases, and that a disabled user stays in the Audit log. The
Users table shows Source (`local`) in the UI font, because it is a word, not an id.
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
and is held while no cluster scans, or that it has been retired (by its name, which the feed
carries as `cluster_name` since a retired cluster is off the cluster list); withdrawn by the sweep
when the cluster scans again; opens
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

## 20. Dashboards (issue 440)

No prototype screen: the prototype put a dashboard builder out of scope. The grammar is the
proof of concept on the issue (comment 6385665039), built on the real kit. The operator accepted
the built pictures of pull request D1 on 2026-10-25 (DESIGN.md §8.5): the list and the read page.
D2 adds new dashboard and edit mode. Issue 1004 records the colors and the clicks of the cards for
a later pass.

**List (`/dashboards`, Monitor group under Saved views):** the Saved views card grid. The card
and the grid are one component pair, `components/saved/SavedCard.vue` and `SavedGrid.vue`, that
both screens use. A card shows the name, a badge with who can see it (`Everyone`, the role list,
or `Only the owner`), the description, the number of panels and when it changed, the owner and
**Export**. The whole card opens the dashboard (issue 1004, §6), with no "Open" text (operator,
2026-10-29). The badge colors by who can see the dashboard (§6). The three head buttons (New
dashboard, Export all, Import) are screen head controls: 30px high, the darker line and a 1px
edge with no blur (`head`, issue 1039, option D). The soft lift of issue 1004 is gone. A long role list ends in "…", and the title of the badge has the full list.
- **Data:** `GET /api/v1/dashboards`: only the dashboards that the user can see (D2, Q3).
- **Head:** the count, `-` until the list read answers and after a refused one (issue 833 F5).
  **New dashboard** opens the details window (below) in its create mode. **Create** makes the
  dashboard with no panels and opens it in edit mode. A refused create stays in the window with
  the reason. **Export all** downloads every dashboard that the user can see as one NDJSON file.
  It needs no `can_export` (D7). **New dashboard** and **Import** need `can_edit_dashboards`. For
  a user without it, both buttons stay, off, with one reason in `UiRoleNote` (issue 243).
- **States:** loading (`UiSkeleton`), refused (the G2 alert), empty (`EmptyState`, with New
  dashboard and Import for a user who can make dashboards).

**Import dialog (`ModalShell`):** a kit button picks the file. Then **Keep the IDs** or **Make
copies** (`UiSegControl`), and a note that the importer owns each new dashboard. The file goes to
the backend as it is: the browser does not read it as text. An empty file is not sent. The
result: the counts (made, ID exists, not correct) and a table with a row for each line, in a
viewport that scrolls (at most 1,000 lines). A line error names the place and the reason in plain
words, never a value of the file. Only the name of a field that a dashboard does not have is
shown. A refused import shows one alert and no table: too large (413), no permission (403), no
connection, another 4xx (nothing made), or a store failure. A store failure (429, or 5xx but 504) stops
the import after the lines before it made their dashboards. A gateway timeout (504) and an answer
that the page cannot read leave the import done or still at work. In these three cases the alert
says what a second import does in each mode. The list reads again after each answer.

**Read page (`/dashboards/:id`):** the head card with the name, the description, who can see it, the owner, when it changed and the selected cluster. On the right,
the scanner switch (`UiSegControl`, the Overview options) and **Export**. While the dashboard
loads, the head card shows `Dashboard` and no actions. It stretches when the name arrives (issue
902). The page ignores a late answer for a dashboard that the user left.
- **Panels:** in blocks (`pageBlocks` in `dashboards/layout.ts`,
  `components/dashboards/DashboardGrid.vue`, ruling B of issue 1045). A Full panel is a block by
  itself. The Half panels between two Full panels are a block of two columns, and each column
  goes from the top down. Each panel is as tall as its content, so no panel scrolls and each card
  draws its whole shadow. The gap is `--grid-gap` across and down. The stored `y` gives only the
  order. A panel with no card of its own goes in `PanelFrame`. The Findings summary sets its
  bands by the width of its panel: in a panel narrower than 700 px, each band has 3 columns.
  Below 1,100 px, the page has one column, block by block, and the left column first.
- **Scanner switch (Q7):** starts on the scanner the owner saved. The URL keeps the viewer's
  choice (`?scanner=`), and the dashboard does not change. A panel pinned to one scanner shows
  the scanner tag and `pinned` over its top right corner and does not follow the switch. A switch
  renders again only the panels that follow it, so the other panels do not read their data again.
- **Data:** each panel reads its own data at the selected cluster, T and window (D8,
  DESIGN.md §10).
- **States:** loading, refused (the G2 alert), no cluster selected, no panels. A dashboard that
  does not exist or that the user cannot see is the "not found" page (§18, decision Q3).

**Edit mode (`/dashboards/:id?edit=1`, D2):** for the owner, or a user with
`can_manage_settings`, and only with `can_edit_dashboards` (D3). For any other user **Edit
dashboard** stays, off, with the reason in `UiRoleNote`, and `?edit=1` in a link opens the read
page.
- **Head:** `Editing <name>`. The scanner switch stays, so the panels show what they will show.
  **Add panel**, **Name and sharing**, **Remove** and **Exit edit** replace Export and Edit
  dashboard. Every control of the head is a screen head control, 30px high with the 1px edge
  (issue 1039): before, Exit edit was 34px and the scanner switch 36px. Exit edit is off while the page has changes to save: the save bar under the head
  card, Discard or Save changes, is the way out. Next to a long name, the controls go to a second row, on the
  right.
- **Name and sharing (`ModalShell`, `components/dashboards/DashboardDetailsDialog.vue`):** the
  name and the description (`SettingsInput` in the UI face, at most 128 and 1,024 characters), who can see it
  (Only me, Everyone or Some roles, D2), and the scanner that the page opens on. With Some roles,
  `UiToggleGroup` shows each role that `GET /api/v1/dashboards/roles` gives, admin too (ruling of
  2026-10-26), and a role of the dashboard that the list does not have. Each role shows in words
  (`security lead`), and the saved value is the id (issue 1039). A note says that an admin
  can see each dashboard. **Apply** is off while the name is empty or Some roles has no role, and
  the reason shows under the fields. Apply changes the draft, as the panel settings do: the save
  bar saves the details with the panels. If the list of roles does not load, an alert says so,
  and the other fields still work.
- **Remove (`ModalShell`, `components/dashboards/RemoveDashboardDialog.vue`):** asks first. It
  says that the data of the panels stays and that the audit log keeps a copy. **Remove dashboard**
  sends the revision that the page read, then goes to the list with a toast. A dashboard that is
  gone already counts as removed. A refused remove stays in the window with the reason: no
  permission, somebody changed it (409), the store is busy or read-only, or no answer.
- **Panels:** gridstack (`components/dashboards/DashboardEditGrid.vue`, its own chunk that only
  edit mode loads) in `top` mode: two columns, rows of 40 px, a 15 px margin, no resize (R10).
  Each panel takes the whole rows that its content needs, so no panel scrolls (ruling E1 of issue
  1045). A short panel lets the panel under it move up. These new rows are not a change: the save
  bar compares the reading order, the columns, the widths, the heights and the scanners, and not
  `y`. Each panel shows, at rest, a **Move** tab over its top left
  corner and **Settings** and remove over its top right corner, with the scanner tag of a pinned
  panel. The Move tab is the one drag handle, with the `grab` cursor (§5). During a drag the drop
  place is a dashed coral box, and the panels under it move down while the user drags. They jump to
  their places: there is no layout animation (DESIGN.md §9). No key moves a panel (R11).
- **Add panel (`ModalShell`, `components/dashboards/AddPanelDialog.vue`, ruling Q1):** on the
  left, the catalog by group (Findings, Scanners, People), one row for each panel with its name
  and its line. The chosen row has the coral selection of an overlay. On the right, the name, the
  line and the settings of the chosen panel, then a preview with live data as the dashboard
  shows the panel: as tall as its content, and half of the column for a Half panel. Only the
  window scrolls (ruling of 2026-10-29, issue 1045). A new choice starts from the default width and the first height. **Add panel** puts the
  panel at the left edge, in the first free place from the top: `top` mode moves it up. At 24 panels (Q2) **Add panel** in the head is
  off, and the reason shows next to it in `UiRoleNote` with an info icon, because a limit is not
  a permission. A dashboard with no panels shows **Add panel** in its `EmptyState`.
- **Panel settings (`PopoverShell`, ruling of 2026-10-26, option B):** a popover with an arrow
  next to the panel, on its right, else on its left, else over its top edge under Settings, else
  above Settings. The page has no backdrop, and the panel keeps a coral outline while its
  settings are open. The head names the panel and has a ✕. The scanner (Follow the dashboard, trivy or grype) for a panel with
  scanner data, the width (Half or Full) and the height (Short or Tall) for a panel with two
  heights. Apply changes the draft. A Full panel goes to the left column.
- **Save:** the settings `SaveBar`. A save sends the revision that the page read, the details
  that changed, and the panels only when they changed. A change of the sharing sends the roles
  too, so a change to Everyone clears them. The places that `top` mode gives as the grid starts are not a change.
  A refused save keeps the changes and shows the reason under the save bar: no permission (403),
  the dashboard is gone (404), somebody changed it (409, reload the page), a value JAVV cannot use
  (422), the store is busy (429) or read-only, or no answer, which does not say that nothing was
  saved. A save that works shows a toast. **Discard** starts the grid again from the saved panels.
- **States:** the edit grid loads with a skeleton. If its chunk does not load, an alert says to
  reload the page. A dashboard with no panels shows `EmptyState`.

## Cross-cutting (unchanged rules, restated)

- Deep-links pass presets into `useFilters` — presets now serialize **lowercase** severities and
  6-state values (A-1/A-2).
- RelTime everywhere; deadlines absolute. Esc/arrow keyboard patterns; coral focus rings.
- First-run/empty states on every data screen (M9f owns the shared components).
- Page entry (issue 902): each new block of the routed page fades in, and the outer blocks rise
  6px, also when data replaces a placeholder. The app shell does it for every screen.
- Capability gating on every mutating affordance — from `/auth/me` capabilities (A-4); client
  gate is convenience, server is authority.
- All timestamps/IDs/versions in the mono face (`--font-mono`); severity colors from the token map only; coral/amber
  never encode severity (ui-foundations).

## RESOLVED register (all six DECIDEs ruled by the operator 2026-07-07, #237)

| Id | Where | Ruling |
|---|---|---|
| A-1 | Findings rail, Overview KPIs | **Show** `negligible` as its own muted bucket |
| A-4 | Settings → Users & roles | **Keep 4** seeded roles (5th = later data change) |
| A-6 | Export dialog | ~~Session-only stays~~ replaced by issue 243 (2026-10-24): `can_export`; without it the control is disabled with a key and the reason (option A on built pictures) |
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
| 20 | (proof of concept: the panel settings in the kit slide-over, with a backdrop that blurs the panel) | **A popover next to the panel** (`PopoverShell`): no backdrop, an arrow at Settings, a coral outline on the panel; Cancel and Apply stay | 2026-10-26 §8.5 ruling on pictures A/B/C, option B (issue 440) |
| 13.4 | Ignore rules → Decisions redirect stub | **No nav entry at all** — decisions live on `/approvals` + finding detail | 2026-07-15, M9e README (supersedes the #237 row-20 stub ruling) |
| — | (v4 prototype) per-CVE audit panel | **Struck** — no screen; the content ships on finding detail + Approvals + Audit | 2026-07-15, M9e README row 24 |
| 13.2 | (v4 prototype) scanner version select, tuning writes, enable toggles, Schedule section | **Read-only** provenance + `effective_config` cards; version = image-tag swap (D41), tuning = env/GitOps (C-4), no enable concept (D30), schedule = manifest | 2026-07-07 + 2026-07-15, M9e README §C |
| 13.2 | — | Namespace scope lists are **exact matches**; globs only on `exclude_images` | 2026-07-15, M9e README (verified in `scanner/src/scanner/scope.py`) |
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
| global | (issue 1004: a soft lift on the Dashboards head buttons. Other heads: a 34px primary or ghost, 30px buttons and a 36px switch.) | **One 30px height for every screen head control, with a 1px edge and no blur.** The token is `--control-edge`, set by `head` on UiButton and UiSegControl. The soft shadow (C) LOST: it is the generic look of shadcn/ui. No shadow (E) LOST. | 2026-10-29 §8.5 ruling on built specimens, option D (issue 1039) |
| global | (the flat coral primary above) | **Flat solid slate** (`--slate2`, hover and press `--slate`, press ring `--slate-drop`), on every primary button and the sign-in button. Coral sits in the red-orange of critical, KEV and "down". A deep teal specimen LOST, because teal means info and Trivy | 2026-10-29 §8.5 ruling on built specimens (issue 1004) |
| global | (prototype drawer: flush right panel, opaque card) | **Glass floating drawer** (SlideoverShell): `--glass` 0.78 white + 14px backdrop blur, neutral `--glass-edge`, 12px backdrop detach + 4px backdrop blur, nested head radius (kills the corner seam). 0.65 opacity tried and reverted | 2026-07-17 §8.5 rulings (M9f slice 3) |
| global | (prototype: topbar search input) | **⌘K command palette** (issue-319 ruling): composed `/findings/groups` queries (CVE/image/namespace) + jump-to-screen off the ONE nav model; the topbar "input" is a button that opens it | 2026-07-17, M9f slice 2 |
| global | — | **Notification bell**: ringed count badge (server unread, pauses on failed poll), inbox rows with per-row ✕ + Mark-all-read/Clear-all (kit mini buttons), ready-export resolves the signed token on click (expired flips the row), toast ECHO for mid-session arrivals only | 2026-07-17 rulings (M9f slice 3) |
