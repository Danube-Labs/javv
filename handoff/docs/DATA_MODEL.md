# Data Model — javv (v5, UI-facing shapes against the shipped backend)

> **Living UI contract** (formerly `DATA_MODEL-v5.md` in `handoff/v5/docs/` — suffixes dropped 2026-07-16, #410).
> Layered over the frozen `handoff/v4/` prototype (the DESIGN.md §8 fidelity source).

Replaces `handoff/v4/docs/DATA_MODEL.md`. Every shape below is an **API response the UI consumes**
(`docs/API.md` is the contract; the live OpenAPI at `/docs` is authoritative). Field names are the
**real** OpenSearch/Pydantic fields (drift table §B); the v4 prototype names they replace are noted.

> **Counts are server-computed — no exceptions.** Every number the UI shows (KPIs, facet counts,
> totals, "X of Y", badge counts, blast radius) is an OpenSearch aggregation returned by the
> backend. The client never counts, sums, or pages an array.
>
> **Per-scanner is sacred — on every count.** Each counted shape in this file carries its scanner
> scope explicitly. A Trivy number and a Grype number may sit side-by-side; they are **never**
> summed, averaged, or merged into one figure. This rule is restated per shape below because it is
> the product's core promise.

---

## Enums & vocabulary

```
severity   (filter/agg values, lowercase — A-1/D16, implemented by D46/#274):
           "critical" | "high" | "medium" | "low" | "negligible" | "unknown"
           — stored verbatim-from-scanner in _source (display/evidence); filters and
             facets are served by the server-derived `severity_canonical` keyword
             (D46 — the lowercase normalizer only folds case and could not map
             non-standard words like `Moderate`); display MAY uppercase. Sort by
             severity_rank (byte), never alphabetically. `negligible` is a real
             bucket (Grype emits it) — RULED (A-1, 2026-07-07): its own muted
             bucket, never folded.

state      (6, A-2): "open" | "acknowledged" | "not_affected" | "risk_accepted"
           | "resolved" | "stale"
           — `stale` is sweep-only (system-set, read-only in the UI).
           — `not_affected` REQUIRES a `vex_justification` (CISA five).
           — `present` is ORTHOGONAL to state (D39): every "now" list is implicitly
             present=true; a present=false row appears only in history/time-travel views.

vex_justification (CISA five, iff state=not_affected):
           "component_not_present" | "vulnerable_code_not_present"
           | "vulnerable_code_not_in_execute_path"
           | "vulnerable_code_cannot_be_controlled_by_adversary"
           | "inline_mitigations_already_exist"
           — the two *not-present* values render as "False positive"; verify exact
             wire strings against live OpenAPI at M9b kickoff.

scanner    "trivy" | "grype" (lowercase in filters; display capitalized). Read-only
           row provenance — never a merge key, never a version selector (D41/C-4).

role       (4, A-4): "viewer" | "triager" | "security_lead" | "admin"
           — the UI NEVER gates on these strings; gate on `capabilities` from
             /auth/me. RULED (A-4, 2026-07-07): keep 4; a 5th is a later data change.

ptype      (returns per B-1 ruling, after M8d): package type from the scanner
           ("os" | ecosystem strings, verbatim-from-scanner lowercase — exact
            vocabulary pinned in the M8d bolt). Pre-M8d findings carry no ptype
            and aggregate as "unknown" until re-observed by a scan.

capability "can_triage" | "can_accept_audit_final" | "can_export" | "can_edit_dashboards"
           | "can_manage_tokens"
           | "can_manage_users" | "can_manage_settings" | admin = "*"
           — M9e adds (planned, with its endpoints): "can_manage_retention",
             "can_restore_snapshot", "can_drop_index".

audit      structured D32 events (A-5) — entity_type ∈ finding | decision | token
           | user | settings | … with an `action` per type. The v4 8-string
           AuditAction enum is GONE.
```

**Removed v4 enums:** `IngestStatus` (A-7/D-4 — no dead-letter store), the 5-role `Role` +
9-row permission matrix (A-4), uppercase `Severity` (A-1), 4-state `State` (A-2). *(v4's
`PackageType` returns as `ptype` after M8d — see above.)*

SLA defaults (server-side policy doc, editable via `/api/v1/settings/sla`): critical 2d, high 7d,
medium 30d, low 90d, KEV override hours. Deadlines are **server-computed at read time** (B-5) —
the UI never does SLA math.

---

## Finding — the atomic row

One row per (CVE × image × **scanner**). Source: `GET /api/v1/findings` (PIT + `search_after`;
rows + opaque `cursor`). Real fields (drift §B, from `bootstrap.py`):

```ts
{
  finding_key: string,        // stable identity; the PATCH …/triage path param
  cluster_id: string,
  scanner: "trivy" | "grype", // THIS row's scanner — the row is per-scanner, sacred

  cve_id: string,             // v4 `cve`
  severity: string,           // verbatim scanner word; filter lowercase (A-1)
  severity_rank: number,      // sort key
  cvss: number | null,        // float only — no vector/CWE/description/refs (B-2)
  epss: number | null,        // raw 0..1, GRYPE-ONLY — em-dash on trivy rows (B-3: no percentile)
  kev: boolean,

  app: string,                // v4 `component`
  package_name: string,       // v4 `pkg`
  ptype: string | null,       // package type — lands with M8d (B-1 ruled: keep);
                              // null on pre-M8d rows until a rescan re-observes them
  installed_version: string,  // v4 `current`
  fixed_version: string | null, // v4 `fixed`; null = "no fix"
  fixable: boolean,

  image_digest: string,       // image identity (content digest)
  image_repo: string, tag: string, // NO combined image_ref — compose repo:tag (#156-3)
  namespaces: string[],       // v4 `ns` (singular) — now plural

  state: State,               // 6-state (A-2)
  vex_justification: string | null, // iff not_affected
  state_decision_id: string | null, // link to the governing decision
  present: boolean,           // orthogonal to state (A-2)
  pre_stale_status: string | null,  // state to revert to when the scanner returns
  assignee: string | null,    // username; avatar/initials derived client-side
  notes: string | null,       // escaped — never rendered as HTML

  disagree: boolean,          // A-3: a BOOL. The other scanner's severity is NOT a
                              // field — query the sibling row (same cve_id+image,
                              // other scanner). That sibling query also builds the
                              // per-scanner evidence table (B-2).

  first_seen_at: string, last_seen_at: string, resolved_at: string | null,
  last_scan_*: …,             // last-scan provenance stamps
  schema_version: number
}
```

**Server-computed read-time additions (B-5):** SLA deadline + overdue flag ride on the findings
read response (not in the index mapping by design) — **verify exact field names against live
OpenAPI at M9b kickoff**. Never client math.

**Gone from v4 (do not design against):** `cvssVector`/`cwe`/`description`/
`refs[]`/`published` (B-2), `epssPct` (B-3), `images: number` (B-4 — it's an aggregation, below),
`sla`/`slaDeadline`/`overdue` as stored fields (B-5 — server-computed), `disagree: Severity`
(A-3 — now bool). *(`ptype` was on this list; B-1 ruling brings it back via M8d.)*

**Cursor semantics (A-m1):** `cursor` is opaque. `410` = PIT expired → re-run the search;
`422` = tampered/invalid → reset; `503` = OpenSearch transport → degraded state. Exports + cursors
share the per-principal PIT cap → `429` + `Retry-After`.

---

## Facets — every KPI and rail count

`GET /api/v1/findings/facets?cluster_id=…&<filter family>` — scanner-faceted aggregations:
counts per severity / state / namespace / attribute, **bucketed per scanner**.

```ts
{
  scanners: {
    trivy: { severity: { critical: n, high: n, …, negligible: n, unknown: n },
             state: { open: n, …6 keys… }, namespace: {…}, kev: n, fixable: n, disagree: n },
    grype: { …same shape… }
  }
  // NO merged/total block. If the UI shows one number it shows one scanner's
  // number, or both side-by-side — never trivy+grype summed. (Per-scanner sacred.)
}
```
(Exact envelope from live OpenAPI; the invariant — per-scanner buckets, lowercase severity keys
incl. `negligible`, 6 state keys — is the contract.)

---

## Groups — "images affected" and per-image rollups

`GET /api/v1/findings/groups?cluster_id=…&group_by=…` — composite group paging.

- **By CVE** (B-4): per-CVE group with per-scanner occurrence/image counts → the grid's "Images"
  column. *Verify the exact agg shape at M9b kickoff; else extend `/findings/groups`.*
- **By image**: per-image group carrying the **count-disagreement pair** (D5b):
  `trivy_count`, `grype_count`, `count_delta` — displayed side-by-side (`T n / G n / Δ`),
  `count_delta` for display only, **never a summed total**. Per-image count disagreement is a
  different signal from per-finding `disagree` (V4-DELTA-7) — never conflated.
  A zero-vs-nonzero pair gets the same visual weight as a severity disagreement (#156-4).

---

## Trends

`GET /api/v1/trends/findings` · `GET /api/v1/trends/scans` — `cluster_id`, range, `as_of`.
Server-built time series from `javv-scan-events`, **per scanner** (series never merged).
Carries `resolved_semantics: "scan_resolved"` (A-m9): "resolved" here = **scan-observed**
resolution (stopped appearing in scans), not human `state=resolved` — label charts accordingly.
The v4 client-side `days[]/CRITICAL[]/…` arrays are replaced by whatever the endpoint returns;
the chart option-builders are pure functions of the response.

---

## Freshness

`GET /api/v1/scanners/freshness?cluster_id=…` (D-1, shipped):

```ts
{ cluster_id, scanner, last_ingest_at: string | null,
  silent_for_seconds: number | null }[]   // per (cluster, scanner)
```
Max across that pair's tokens; disabled tokens still count (data freshness ≠ token validity);
never-ingested → nulls → "no data yet", not an error. Drives the freshness banner, sidebar chip,
scanner-status cards, and cluster health chips. Health is **derived** from
`silent_for_seconds` vs the staleness timers — the v4 `Health` enum is a presentation mapping,
not a stored field.

---

## Decisions (replaces v4 Approvals shape)

`GET/POST /api/v1/decisions` · `PATCH /api/v1/decisions/{id}` (edit = revoke+new, one
`effective_at`/`operation_id`, D40) · `POST …/{id}/revoke` ·
`GET /api/v1/decisions/approvals` (queue, `can_accept_audit_final`).

```ts
{ decision_id, type,               // risk_accepted type requires can_accept_audit_final (SEC-2)
  cve_id, cluster_id,
  scope: { images: string[], namespaces: string[] },  // empty = cluster-wide;
                                   // namespace/cluster scope CASCADES to new findings,
                                   // image scope does NOT
  justification: string, approver: string,
  expires_at: string,              // expired decisions resurface
  status: "active" | "revoked" | "expired",
  effective_at, operation_id, revoked_* }
```
Immutable + lifecycle stamp — there is no in-place edit. The v4 `approvals[]`
justification/impact/action/task shape is gone (V4-DELTA-2).

---

## Audit events (structured, D32 — A-5)

Shape (read endpoint scheduled — **M8c** `GET /api/v1/audit`, plain session; see SCREENS §10):

```ts
{ event_id: string, "@timestamp": string,
  actor: string,
  entity_type: "finding" | "decision" | "token" | "user" | "settings" | …,
  action: string,                  // per entity_type
  target_ids: string[],            // FROZEN affected set — rendered verbatim,
                                   // never a re-evaluated selector
  revision: number,                // same-field edits order by revision (causal replay)
  detail: … }
```
Ordered by `(@timestamp, event_id)`. Click-through only where `entity_type=="finding"`.
The v4 `AuditAction` string enum + `sev`/`task` fields are gone.

---

## Contributors

`GET /api/v1/contributors?cluster_id=…&range=…` (FR-15, shipped). Leaderboard rows + team stats —
**all server-aggregated** from `system-audit-log` (no raw rows shipped to count): per-person
resolved / acknowledged counts, median TTR, SLA-hit %. Window = the global trend picker, clamped
to audit-log retention. Triage counts here are **human actions** (audit log); any chart mixing in
trend data must label the `scan_resolved` semantics separately (A-m9). Severity mixes in
leaderboard rows are per-scanner-safe server aggs; avatars/initials/tones derive from `username`
client-side (presentation only — not counting).

---

## Reports / exports

- `GET /api/v1/findings/export.csv?<lens>` — streaming; `413` past `JAVV_EXPORT_MAX_ROWS` (50k).
- `GET /api/v1/findings/export.vex?scanner=<one>&<lens>` — **`scanner` required**: one VEX file =
  one scanner (per-scanner sacred).
- `POST /api/v1/reports` (`kind:"export"`, session-only — A-6) → `{ report_id }`.
- `GET /api/v1/reports/{report_id}` → public status view (never leaks `params`/`attempt_id`/lease
  fields): `{ report_id, status: pending|running|done|failed, created_at, expires_at }`.
- Download: `GET /api/v1/reports/{id}/download` (M7 slice 3, planned) — **410 past `expires_at`**
  (`JAVV_EXPORT_TTL_HOURS`, default 24h). The UI derives "expires in Xh" from `expires_at` and
  renders the 410-expired state ("re-run the export"), never a dead link (C-2).

---

## Auth principal

`GET /auth/me` → `{ username, role, capabilities: string[], must_change: boolean }`.
**Gate every affordance on `capabilities`** — `role` is display-only (A-4). `must_change=true`
locks the session to `/auth/*`. Roles render as capability bundles from `system-roles` content;
there is no client-side permission matrix (the v4 `rbac.permissions` table is gone).

---

## Settings docs

- **SLA policy** (`GET/PUT /api/v1/settings/sla`, shipped): days per severity + KEV override —
  lowercase severity keys.
- **Scan scope** (session read = D-2 planned; `PUT /api/v1/scan-scope` = M9e): running-only,
  include/ignore namespaces, image globs, excluded kinds. Empty include = all; ignore wins;
  fail-closed.
- **Staleness timers** (M3 doc, `PUT /settings/staleness` = M9e): `freshness_days` (3),
  `scanner_down_days` (7).
- **Effective config + provenance** (read-only, C-4/D41/D44): from the latest committed
  scan-event's `effective_config` stamp — `{ tuning, scope }` + `scanner_version` /
  `scanner_db_version` / `scanner_db_built`. **Display only**; the v4 editable
  `config.trivy/grype/schedule/vulnDb` and **`config.versions` (version selector) are GONE** —
  versions change by swapping the published image tag; JAVV never writes to monitored clusters.
- **Retention / rollover / snapshots** (M9e planned endpoints): retention applies to
  time-partitioned append families only; never offered on findings/watermarks/scan-orders/
  system-*.
- **Tokens** (`/api/v1/admin/tokens`, shipped): `{ token_id, cluster_id, scanner, created_at,
  last_used_at, disabled }` — raw secret returned **once at mint**.
- **Users** (`/api/v1/admin/users`, shipped): `{ username, role, disabled, last_active }` —
  last-enabled-admin disable → 409; reserved names → 422.

---

## Cluster

`cluster_id` — immutable key, always-applied read filter (tenant read path). `cluster_name` —
relabelable display name, **RULED (D-5, 2026-07-07)**: lives in a `system-config` cluster-registry
doc, shipped with its session read (+ journaled rename write) in **M8c** — which also solves
cluster enumeration for the All-clusters screen. Display-only, never a query key.

---

## Saved views (C-6 RULED 2026-07-07: server-side — M8e)

`GET/POST /api/v1/views` · `PATCH/DELETE /api/v1/views/{view_id}` (M8e; session read, mutations
owner-or-admin), backed by the new `system-views` index:

```ts
{ view_id: string, name, description,
  preset: { filters, q },     // serializes LOWERCASE severities + 6-state values (A-1/A-2)
  owner: string,              // username; the v4 owner column returns
  created_at, updated_at }
```
Views are visible to all authenticated users; live card counts come from
`GET /api/v1/findings/facets` with the view's params (server agg — never a client count).

---

## Notifications (D-3, planned)

`GET /api/v1/notifications` + mark-read PATCH — `{ id, category: sla_overdue | assigned |
export_ready, target, created_at, read, expires_at? }`. Badge = **server-computed** unread count,
polled (NFR-9). `export_ready` items carry `expires_at` → "expires in Xh" + 410 handling (C-2).

---

## Error envelope (every non-2xx)

`{ status, title, request_id }` — one problem-details shape app-wide. The UI surfaces
`request_id` on error states ("include this id when reporting"). Status codes the UI must design
for: 401 (session expired → login), 403 (capability — hide/disable, D33), 404, 409 (CAS/conflict
— reload-and-retry, never silent overwrite), 410 (expired cursor/download), 413 (too large —
narrow or schedule), 422 (validation), 429 (+ `Retry-After`), 501 (`as_of` pre-M8b — C-1),
503 (degraded banner).
