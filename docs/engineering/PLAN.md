# JAVV - Just Another Vulnerability Viewer · MVP Plan (v4)

> **Living doc** (formerly `PLAN_v4.md` in the old `V4/` folder — suffixes dropped 2026-07-16, #410).
> The v1–v3 evolution trail is frozen in `.deprecated/`; version markers are reserved for frozen generations.

> **Status: revision 4 (2026-06-21).** Supersedes `.deprecated/docs/engineering/deprecated/V3/PLAN_v3.md` (kept frozen for the evolution
> trail). Folds in the post-v3 audit dialogue: index rename (`system-exceptions`→`system-decisions`),
> raw-fidelity via keyword normalizer (no duplicate fields), rebuildable triage state, idempotent appends,
> projection-on-new-only, two-timer staleness, vuln-age-at-read, pinned `apply_both` semantics, an explicit
> HA/multi-pod section, scheduled/throttled export, envelope-versioning policy, an Admin "Data & OpenSearch"
> panel, and a **re-sequenced, more granular milestone set**. Companions: `SPEC.md`, `ARCHITECTURE.md`.
> UI reference: `handoff/v4/`. Repo: `javv` (`javv-poc` until 2026-10-27)
> (`git@github.com:Danube-Labs/javv.git`). Vendor: **Danube Labs**. License: **BUSL 1.1** (→ Apache-2.0
> on 2030-06-10). Process: **specs.md FIRE flow, autonomy level 1 (Confirm)**. *Milestone = bolt.*

---

## 0. How to read this set

- **`handoff/v4/`** - UI/product reference (12 screens, tokens, React prototype). v4 targets it as
  closely as backend constraints allow; **divergences are expected and noted, not silently taken** - see the
  "UI extends beyond handoff" list in §8 (M9).
- **`docs/engineering/` (this set)** - canonical engineering plan/spec/architecture.
- **`.deprecated/docs/engineering/deprecated/V3/`, `.deprecated/docs/engineering/deprecated/` (v2), `.deprecated/docs/deprecated/` (v1)** - superseded; kept for history + the audits.
- **`docs/research/`** - the audit + best-practices + tooling + k8s research backing this revision.

### What changed from v3 (orientation map)
| v3 | v4 | change |
|---|---|---|
| M1 | M1 | + golden-envelope round-trip gate; + `severity` normalizer |
| - | **M2** | **new** - snapshot/restore (durability pulled forward) |
| M2 | M3 | + inline-preserve-as-cache framing; + two-timer staleness; projection-on-new (rebuild-state job deferred: M5c creates the human/decision arm, M8a adds the scanner-presence arm) |
| M2.5 | M4 | + idempotent `_id`; rollover settings surface in settings |
| M3 (one bolt) | **M5a–M5d** | split: access · state machine · decisions/projection · SLA/bulk |
| M4 | M6 | read/reporting + VEX **export** (import → v1.1) |
| - | **M7** | **new** - scheduled/throttled export (`system-reports`) |
| **M2.6** (before triage) | **M8a–M8b** (after read) | **moved + simplified**: full per-scan snapshots · point-in-time API (close events removed); + rebuild-state **scanner-presence arm** (base job created in M5c; M8a extends it — replays occurrences) |
| M5 (one bolt) | **M9a–M9f** | split reusable-first; core-loop gate; + Data & OpenSearch panel |
| M6 | M10 | polish & deploy |
| `system-exceptions` | `system-decisions` | renamed (clearer) |

## 1. Identity / Brand
Unchanged from v3. Lens-over-Danube-dusk mark; teal/slate; **severity-color firewall** (coral/amber are
brand; the red→blue severity ramp is *data*). Full guide: `handoff/v4/brand/BRAND.md`.

## 2. Context & market fit
Unchanged. The seam JAVV fills: **audit/triage workflow + flexible reporting, k8s-runtime-native,
lightweight.** Pure "scanner → Kibana" stacks are view-only; triage requires a mutable per-finding entity,
which is why JAVV keeps a current-state findings store, not just an append-only log.

## 3. Locked decisions

Carried from v3 (unchanged): decoupled drop-in **scanner module** (Trivy AND Grype, **local digest-dedup,
scan-all** - D30); **FastAPI + AsyncOpenSearch** (PIT + `search_after`); **OpenSearch-only**; **per-scanner,
never merged** + scanner dropdown; **multi-cluster** via immutable `cluster_id` + relabelable `cluster_name`;
private registries via an operator-mounted registry login (issue 739); vuln-DB mirror/cache + PVC; EPSS/KEV captured (Grype); Vue 3 +
PrimeVue + vue-echarts, **all server-side**.

**v3 decisions retained (summarised):** D1 VEX two-field state model · D2 hybrid data model (current-state +
append logs) · D2b accurate point-in-time history (full per-scan snapshots, no close events) · D3 human decisions as their own
layer · D4 scoped risk-acceptance w/ precedence + expiry-refresh · D5 scanner disagreement (**D5a** per-finding severity + **D5b** per-image count)
· D6 SLA/overdue · D7 trends from logs · D8 per-cluster retention (drop-whole-index) · D9 observability from
M1 · D10 ingest hardening · D11 **no extra infrastructure** (no Redis/Kafka/broker) · D12 tokens per
`(cluster,scanner)` · D13 idempotent jobs (no durable engine) · D14 notifications + saved views per-user ·
D15 scanner casing lowercase *(now via normalizer - see D16)*.

**New / changed in v4 (additions in bold):**

- **D2c - `system-exceptions` renamed `system-decisions`.** The index holds the **human decisions about
  CVEs** (risk-accepts, ignore-rules, not-affected), each anchored on **CVE + scope + approver + expiry**.
  The name now says what it holds. The trio: `findings` (the vulns) · `system-decisions` (what humans
  decided) · `system-audit-log` (the immutable trail). (§5.6/§5.7.)
- **D16 - Raw fidelity via a keyword normalizer (no duplicate normalized fields).** We **never modify**
  scanner output. Scanner enum/casing fields (`severity`, fix-state, …) are stored as a single `keyword`
  with a **lowercase `normalizer`**: the *indexed* token is lowercased (so `"CRITICAL"`/`"Critical"` bucket
  together and filters are case-insensitive) while **`_source` keeps the verbatim value** for evidence/
  display. No `severity_raw` duplicate. Severity also gets a derived numeric **`severity_rank`**
  (`critical=5, high=4, medium=3, low=2, negligible=1, unknown=0`) - a *sort key* (not a duplicate string)
  so the grid can sort and range-filter severity correctly (a keyword sorts alphabetically - wrong order).
  Vocabulary buckets are **explicit** - `crit/high/med/low/negligible/unknown` (Grype `Negligible`/`Unknown`
  are kept, not folded into `low`), so counts never lie - mapped **once at the M0 scanner adapter**; the
  per-finding `severity` keeps the scanner's own word. Supersedes the v3 "lowercase the data" reading of
  D15. (§5.2; §5.4; §7.)
- **D17 - Triage state is a projected cache (partial-merge + rebuild safety-net).** Human-owned fields live
  on `findings` only as a **denormalized cache** for fast grid filter/sort; the **sources of truth** are
  `system-decisions` (rule-derived state) + `system-audit-log` (every direct action, structured - D32).
  Ingest writes scanner fields via a **partial-doc `_update` (merge semantics)** that simply doesn't name
  human fields - **no preserve script, nothing to overwrite** (D31; a script only if newer-scan-wins ordering
  is wanted). Projection writes `state`; triage writes human fields directly. An admin **rebuild-state** job
  (kept day-one - OE-2) re-projects all findings from the sources of truth (self-heal; recomputes `stale`
  from `last_seen_at` - SND-6/D36). **Requirement:** *every* triage action appends to `system-audit-log`, so
  nothing human-authored lives only on the finding. (§5.2; §6; `INDEX-MAP`.)
- **D18 - Idempotent appends (deterministic `_id`).** Append writes get deterministic ids so a retried push
  overwrites instead of duplicating: `javv-scan-events` `_id = hash(scan_run_id + image_digest + scanner)`;
  `javv-finding-occurrences` snapshot row `_id = hash(scan_run_id + finding_key)`. Pure append - a retry
  overwrites, never duplicates, and there is **no read-modify-write**. Mirrors the rollup's deterministic-`_id`
  idempotency. (§5.4/§5.5.)
- **D19 - Projection at ingest touches only newly-created findings.** Only **cascading** rules
  (namespace-/cluster-scoped) auto-apply to findings that appear later, and only the **new** findings in a
  push are evaluated against them. Existing findings are re-projected **only** on decision-apply (rule
  added/edited/removed) or the daily sweep (expiry) - **never re-walked on every rescan**. Explicit-image
  and per-finding decisions are never evaluated at ingest. (Prevents `update_by_query`-shaped hot-path
  churn.) (§5.7.)
- **D20 - Two-timer staleness.** Two independent, **UI-configurable** timers: (1) **per-finding freshness**
  - a finding not re-seen for **N days (default 3)** → `stale`; (2) **scanner-down escalation** - a scanner
  silent for **M days (default 7)** → mark *all* that cluster's findings `stale`. Between the two thresholds
  the per-finding timer is **held** (a brief outage doesn't mass-stale) but every inventory view shows a
  **banner** *"data as of T; scanner silent since T'."* Past M days the guard releases. Replaces the v3
  "guard suppresses forever" behaviour. (§5.3; §6.)
- **D21 - Vuln-age computed at read time.** `finding_key` keeps `installed_version` (a package bump is a
  genuinely different scanner observation → a new finding; the old `finding_key` simply stops appearing in
  later snapshots). But **audit anchors on
  CVE + scope** (D4), so a version bump auto-inherits the existing decision. "How long have we carried
  CVE-X" / SLA age is a **read-time** rollup (group by `cve_id + image_digest`, earliest `first_seen_at`), so a
  patch bump never resets the clock. (§5.2; §5.7.)
- **D22 - `apply_both_scanners` semantics (pinned, no longer "decided under test").** `apply_both=true`
  means the decision matches on **`(cluster, cve, scope)` ignoring the scanner dimension** and projects onto
  **each** scanner's matching finding independently; **each scanner's finding still closes on its own** when
  that scanner stops reporting it; a **scanner-specific** decision (`apply_both=false`) **takes precedence**
  over a both-scanners one for that scanner. The M5c test now *verifies* this rule rather than discovering
  it. (§5.7.)
- **D23 - HA & multi-pod is a documented tier, not an MVP concern.** The append-only snapshot model
  (D2b/§5.5) is pure-append with deterministic `_id`, so it has **no close-event race** at any replica count
  (the early close-diff hazard is designed out - there is no read-modify-write). The one remaining multi-pod
  caveat: the in-proc `slowapi` rate-limit is **per-pod**, so the global limit ≈ configured × replicas
  (exact at `replicas:1`); a hard global cap would need shared state (out of scope by D11). Neither blocks
  the MVP (single-pod). (§HA in `ARCHITECTURE`.)
- **D24 - Scheduled / throttled export.** Large CSV/report requests become rows in **`system-reports`**
  (`status, params, requested_by, run_mode ∈ {now, offpeak}, scheduled_for, result_location`); the existing
  background CronJob drains the queue, off-peak runs **throttled** (PIT+`search_after`, small pages, brief
  sleeps), result lands in object storage, user is pinged via the **bell**. Broker-free (D11). Doubles as the
  mitigation for read/write contention in the single store. **Job claim uses optimistic concurrency** so API
  replicas/retries never double-run a job (D38/M17): `pending→running` via `seq_no`/`primary_term` CAS +
  `heartbeat_at` + `lease_expires_at` + `retry_count`, plus a **fencing `attempt_id`** (D39/M7-r2) - heartbeat
  and the `done` transition CAS on the current `attempt_id` and the result object path includes it, so a slow
  worker whose lease expired and was reclaimed cannot double-publish. (§6; `SPEC` FR-13.)
- **D25 - Envelope versioning & schema-skew policy.** The ingest envelope is versioned; the backend
  **accepts the current envelope only** and **rejects older** with a clear 4xx telling the operator to upgrade
  the scanner (current-only per D35/D38 - the earlier "N, N-1 dual-parse" is dropped; the versioning *policy*
  stays). Document-shape/mapping changes are handled by a **`_reindex` runbook**
  (new index + transform script); `dynamic:false` means new fields must be added to the mapping first.
  Migration tooling itself is post-MVP; the **policy** is decided now. (`SPEC` FR-3, NFR-1.)
- **D26 - Admin "Data & OpenSearch" settings panel.** A first-class Admin surface to configure OpenSearch
  behaviour from JAVV: **rollover** thresholds (doc count / age / size), per-cluster **retention_days**,
  **snapshot** config (repository + schedule) + manual snapshot/restore, and the **staleness timers** (D20)
  (here or a sibling "Scanning" section). (`SPEC` FR-19; M9e.)
- **D27 - Dense-grid table engine.** PrimeVue `DataTable` in **lazy (server-side) mode** is the default for
  every grid - in-stack, themed, free; **escape-hatch to AG Grid Community** (also free/MIT) only if a
  specific screen needs spreadsheet-grade interactions it can't do. TanStack rejected (headless → rebuild all
  table chrome for no cost saving). (`SPEC` FR-12; M9b.)
- **D28 - Whole-app time-travel (global rewind).** The global time picker sets a time `T` (days/hours/minutes
  ago; default now); **every screen is a projection at T**. `T=now` reads the materialized current-state
  (`findings` cache) - fast. `T<now` **reconstructs from the timestamped append logs, catalog-first** (D39 -
  no "latest snapshot ≤ T" shorthand): scanner facts = latest **committed** run from `scan-events` ≤ T, then
  `occurrences` for that run's `commit_key`; inventory = images of the latest `status=committed`
  `javv-inventory-runs` entry ≤ T; trends from `scan-events`; **human state from `system-audit-log` (replay ≤
  T, ordered by `(@timestamp, event_id)`, latest-per-field) + `system-decisions` active at T**; `stale`
  recomputed at T. Same UI, source swapped by T. **Reach = per cluster, as far back as its retained data
  allows** (oldest `occurrences`/`images` window + long-kept audit-log). Cost: past-T reconstruction is heavier
  than the now-index read (bounded per cluster); **historical all-clusters dashboards are limited/unavailable
  until the `javv-metrics` rollup, v1.1** (D39/M11-r2). Replaces FR-14's image-only scope.
  (`SPEC` FR-23; M6/M8/M9; read path in `ARCHITECTURE`.)
- **D29 - `images` is a time-partitioned append** (`javv-images-<cluster_id>-*`), not a mutable upsert
  (§5.3). Each scan cycle writes a **complete inventory run** stamped `inventory_run_id`. **"Running images
  now / at T" = the latest complete inventory run for the cluster** (R-CATALOG, D37), *not*
  latest-doc-per-digest - so an undeployed image disappears at the **next run**, not at retention (no zombie
  sweep).
- **D30 - Scanner scans everything every cycle (no skip-unchanged).** Stateless script: list images (minus
  excluded namespaces/labels) → **local digest-dedup** (each unique digest scanned once) → scan → push all,
  timestamped. No "was-this-scanned-before" state, no backend query. (Drops the v2/v3 skip-unchanged
  decision; in-cluster scan CPU accepted.) (`SPEC` FR-2.)
- **D31 - Partial-doc merge replaces the preserve script.** Ingest updates `findings` with a **partial doc of
  scanner fields only**; OpenSearch merge leaves human fields untouched - no preserve script, nothing to
  overwrite. (D17; §5.1/§5.2.)
- **D32 - `system-audit-log` is structured + required (enriched per D38/D39).** One row per field change with
  the **full schema** (`event_id`, `actor`, `action`, `entity_type`, `entity_id`, `finding_key`, `field`,
  `field_type`, typed `old_value`/`new_value` (+ `*_json` for non-scalars), **frozen `target_ids`** for bulk
  actions, **`revision`** (the finding's resulting version from the CAS write - D40/H-r3), `@timestamp`),
  **not** the old `(field, old, new)` shape and **no `seq` counter** - replay orders same-`(entity, field)`
  events by **`revision`**, then `(@timestamp, event_id)` for unrelated events (D39/H6-r2, D40/H-r3). It **is** the human-state timeline for time-travel (D28) and rebuild
  (D17). Append-only via a create-only role (D34). Canonical mapping: `INDEX-MAP`.
- **D33 - Capability-based RBAC.** Roles are bundles of **capabilities**; endpoints check capabilities, not
  role strings. Risk-accept is gated by **`can_accept_audit_final`** (Admin always holds it) - single-step
  role-gate, **no two-person maker/checker** for MVP (the accepting user is `created_by`). Resolves the
  4-vs-5 role mismatch (SEC-9). Destructive caps (restore/drop-index/rebuild/retention) Admin-only +
  journaled. (`SPEC` FR-18; M5a.)
- **D34 - Security hardening bundle.** Create-only OpenSearch role for `system-audit-log` + the append
  indices + WORM snapshot (SEC-1; "append-only by role," not "immutable"). **`system-decisions` is *not*
  create-only** - it is immutable **except `revoked_at`** (D39/H5-r2); a scope **or `expiry`** edit is
  **revoke + create-new**, so the role allows only the `revoked_at` stamp while every change still emits an
  audit-log event. **Ingest tokens:** 256-bit random, **peppered SHA-256** at rest (M14/D38); **token↔payload
  binding** = authorization matching - reject payload `cluster_id`/`scanner` ≠ token scope → 403 (SEC-3); not
  cryptographic body signing (body-HMAC + replay nonce → post-MVP). **tenant read path** (one `tenant_search`
  helper + negative test - SEC-4); **bootstrap admin** mounted-secret/seed-once/server-`must_change` (SEC-6);
  **replay protection** (reject envelope older than the latest committed run for `(cluster,scanner,digest)` -
  SEC-7); **TLS** on all hops + OpenSearch security plugin on in prod (SEC-8); snapshot/export creds in OS
  keystore; export results stored in OpenSearch (chunked) + a tenant-read-path-gated backend download
  endpoint with a short-lived signed token + `expires_at` + download entitlement (SEC-10, revised by M7/#32);
  **decompression-ratio kill-switch** (~100:1 abort + per-token abort rate-limit - SEC-11). (`SPEC` NFR-7;
  M1/M5a/M10.)
- **D35 - MVP simplifications.** `severity_rank` on `findings` only, not occurrences (OE-5); ingest accepts
  the **current envelope only**, rejects older with a clear 4xx (drop N/N-1 dual-parsing; keep the versioning
  policy - OE-6); drop the SQLite/Postgres-swap justification for the `system-*` access module (OpenSearch-
  only is locked - OE-7).
- **D36 - Verification pins.** rebuild recomputes `stale` from `last_seen_at` (SND-6); ingest scripted-update
  `retry_on_conflict≥3` + triage 409-retry + concurrent ingest+triage golden test (SND-8); `apply_both` +
  expiry-refresh fallback test in M5c (SND-9); ingest `total = Σ severity buckets` invariant check; CSV
  sanitize rule pinned (prefix `= + - @ \t \r` with `'`, incl. notes/justification); no `v-html` for user
  text; bulk-action audit records the target set, not a count; DR snapshots small audit/decision indices more
  often than bulky append (RPO).
- **D37 - Read through the commit catalog; reconcile the cache on commit (external-audit C1/C2/H3/H5/M12/
  M13).** Folds in the ChatGPT audit (`AUDIT-RESPONSE.md`). The point-in-time model was correct; the read
  path had a lazy "latest doc per key" shortcut that breaks on a *clean rescan* (which writes no occurrence
  rows). Fix is read-discipline + one `update_by_query` - **no new infra, no close-events in history.**
  - **R-CATALOG (C1/H5).** "Latest state" is resolved through the **commit catalog**, never "latest doc per
    key." *Vulns:* read the latest committed `scan_run_id` for a digest from `javv-scan-events ≤ T` (the
    catalog), **then** read `occurrences` for that exact run - **zero rows = clean image** (a clean rescan
    leaves no occurrence rows, so latest-doc-per-digest would resurrect fixed CVEs). *Inventory:* "running
    now / at T" = the **latest complete inventory run** for the cluster (`inventory_run_id`), not
    union-of-latest-doc-per-digest (an undeployed image disappears at the next run, not at retention).
  - **`commit_key` (H3).** Commit/snapshot identity is the 4-tuple
    `commit_key = (cluster_id, scanner, image_digest, scan_run_id)`; every catalog query matches **all four**.
    Bans the loose "scan_run_id has a doc" phrasing (a reused run id can't commit another image's snapshot).
  - **Reconcile-on-commit (C2).** On a committed scan for `(digest, scanner)`, an `update_by_query` sets
    `present=false` + `resolved_at` on `findings` for that pair whose `last_scan_run_id` ≠ the new run, so the
    "now" grid is correct **immediately**, not after N days. This repairs the disposable **cache** only -
    `occurrences` stays tombstone-free and absence in history is still *inferred* via the catalog (this is
    **not** a close-event reintroduced into the log).
  - **Stale ≠ delete (M12).** `stale`/`present` are flags; `findings` docs are deleted only after a separate
    **long** window (or once gone from inventory that long) - never on the freshness timer.
  - **Full timestamps (M13).** `findings.first_seen_at` / `last_seen_at` are full `date` (not day-grain) so
    minute-level as-of-T is exact; `occurrences.@timestamp` already is. (`INDEX-MAP`; §5.2; §5.5; §6.)
- **D38 - External-audit consistency + hardening fixes (M10/H7/H8/H9/M14/M17/M11/M15/M16/L18).**
  - **Envelope current-only (M10).** Reconciles D25↔D35: ingest accepts the **current envelope only**, rejects
    older with a 4xx (drop N/N-1 dual-parse; versioning *policy* retained). Supersedes the N/N-1 reading of D25.
  - **Decisions immutable + lifecycle stamp (H7; tightened by D39/H5-r2).** `system-decisions` docs are
    **immutable except `revoked_at`**; editing scope **or `expiry`** = **revoke + create-new** (mutating
    `expiry` in place would rewrite past-T reconstruction). `revoked_at` is the only post-hoc stamp and is
    forward-correct (`revoked_at > T` leaves the past intact). Resolves the "create-only role can't revoke"
    paradox in D34 and keeps "active at T" time-travelable.
  - **Audit-log faithful replay (H8).** `system-audit-log` carries `event_id`, `entity_type`, `entity_id`,
    `field`, typed value fields, deterministic ordering; **bulk actions store frozen `target_ids`** (or
    query + result-hash + count), never just a selector - otherwise replay drifts. Strengthens D32/D36.
  - **Tenant scope = all-clusters-visible for MVP (H9).** Any authenticated user sees all clusters;
    `cluster_id` is a **data filter applied on every read/agg/export** (defense against accidental
    cross-cluster bleed), **not** a per-user auth boundary. Per-user/role cluster grants are **post-MVP**.
  - **Token hardening (M14).** 256-bit random ingest tokens, **peppered SHA-256** at rest; "token↔payload
    binding" (D34/SEC-3) = **authorization matching** (token scope must equal payload `cluster_id`/`scanner`),
    not cryptographic body signing (body-HMAC + replay nonce → post-MVP).
  - **Report job lease (M17).** `system-reports` job claim uses **optimistic concurrency**
    (`seq_no`/`primary_term` CAS `pending→running`) + `heartbeat_at` + `lease_expires_at` + `retry_count` so
    API replicas / retries can't double-run an export. Broker-free (D11) - OpenSearch *is* the coordinator.
  - **`severity_rank` stays off occurrences (M11).** Honors OE-5; as-of-T severity sort uses a **fixed order
    map** (`crit > high > med > low > negligible > unknown`). SPEC/FLOW corrected to match (was inconsistent).
  - **scanner = field, not index name (M15).** `javv-scan-events` partitions by **`cluster_id` only** (scanner
    stays a field) to halve index/shard count; supersedes the `javv-scan-events-<scanner>-<cluster_id>` name.
  - **Historical-dashboard guardrail (M16).** Multi-cluster *historical* dashboards read the `javv-metrics`
    rollup (v1.1), not raw occurrences; PIT/search contexts are **explicitly closed** (not left to expiry).
  - **Index naming (L18).** Hyphens everywhere (`system-decisions`, `system-audit-log`, …); `INDEX-MAP.md`
    is canonical.
- **D39 - Round-2 audit fixes: ordering, completeness, immutability (`AUDIT-RESPONSE.md` round-2).** The
  round-1 fixes were directionally right but left correctness gaps in *write/read ordering and completeness
  contracts* - out-of-order scans and uncommitted cache writes could make the "now" grid lie. D39 closes them.
  - **Symmetric query via the catalog + `commit_key` on occurrences (C1-r2).** "Which images had CVE-Y at T"
    Step 1 pages `javv-scan-events` by `(cluster_id, scanner, image_digest, @timestamp ≤ T)` → latest
    committed `scan_run_id` per digest; Step 2 is `commit_key IN {…} AND vuln_id=Y`. **`commit_key` is now also
    stored on each occurrence row** so Step 2 is an exact 4-tuple membership test - never "latest snapshot per
    digest" over occurrences.
  - **Newer-scan-wins (C2-r2; ⚠ guard key superseded by D40).** `findings` carries a per-doc guard so the
    partial-merge and reconcile no-op for an out-of-order *older* run. **D40 supersedes the key:** guard on the
    backend-allocated (D45) **`scan_order`** (not `@timestamp`/`last_scan_at`) **and the per-digest
    `javv-scan-watermarks` watermark** - the watermark is what guards a *create* (a finding the newer scan
    omits that has no doc yet), which per-doc `last_scan_at` could not. See D40.
  - **Cache-after-commit ordering (H3-r2).** Ingest order is: **append occurrences + images → write the
    scan-events commit doc only after per-item `_bulk` success → then partial-merge `findings` + reconcile
    last.** The "now" cache is derived only from committed state; a crash before the merge self-heals on the
    next scan / rebuild-state. (No `pending_scan_run_id` needed.)
  - **Inventory commit manifest (H4-r2).** New index **`javv-inventory-runs-<cluster_id>-*`**: one manifest per
    `inventory_run_id` (`started_at`, `completed_at`, `expected_count`, `written_count`, `status`), written
    **last**. **"Running images now / at T" reads only `status=committed` runs** - a partial or zero-image run
    is never read as the inventory (the inventory analog of scan-events-as-catalog).
  - **Immutable expiry (H5-r2).** `system-decisions.expiry` is **immutable after creation**; changing it =
    **revoke + create-new**. `revoked_at` stays the only post-hoc stamp (forward-correct: `revoked_at > T`
    leaves the past intact). Mutating `expiry` in place would rewrite past-T reconstruction. Supersedes the
    D38/H7 "lifecycle stamp includes expiry" wording.
  - **Deterministic audit order, no phantom counter (H6-r2).** Drop the monotonic `seq`; replay orders by
    **`(@timestamp, event_id)`** (same-instant independent actions unordered - acceptable). A `system-counters`
    CAS doc / `if_seq_no` is the post-MVP path if strict total ordering is ever required.
  - **Report fencing token (M7-r2).** `system-reports` jobs carry an **`attempt_id`**; heartbeat and the
    `done` transition **CAS on the current `attempt_id`**; the result object path includes `attempt_id` (orphan
    cleanup) so a slow worker whose lease expired and was reclaimed cannot double-publish.
  - **Presence ⟂ state (M10-r2).** `present`/`resolved_at` (scan-presence) is **orthogonal** to `state` (human
    lifecycle + system `stale`). Combos: `present=true` = on the latest committed scan; `present=false` +
    healthy scanner = **resolved-by-scan** (fixed/withdrawn); `state=stale` = **scanner silent** (presence
    unknown). Every "now" grid/report **must filter on both** (`present=true` + the screen's `state` filter)
    and carry `cluster_id`+`scanner`.
  - **All-clusters MVP (M11-r2).** Historical **all-clusters** dashboards are **limited/unavailable until the
    `javv-metrics` rollup (v1.1)**; per-cluster rewind is fully supported in MVP.
  - **Sweeps.** Read-path prose rewritten **catalog-first** (no "latest occurrences/images snapshot ≤ T"
    shorthand); **D32 updated to the enriched audit schema**; "now" query examples carry
    `cluster_id`/`scanner`/`present=true`; residual `first_seen`/`last_seen` → `*_at`.
- **D40 - Round-3 audit fixes: a committed-scan watermark + trustworthy ordering (`AUDIT-RESPONSE.md`
  round-3).** D39's newer-scan-wins guarded *per-doc* state, which **can't guard a create** - an out-of-order
  older run could re-create a finding a newer *clean* scan already retired. D40 adds the missing serialization
  primitive and trustworthy ordering; **still broker-free** (one tiny new mutable index).
  - **Trustworthy `scan_order` (C-r3).** The scanner stamps each run with a monotonic **`scan_order`** (its
    scan-start), monotonic per `(cluster, scanner)` because the CronJob `Forbid` policy serializes runs - run
    spacing (minutes) dwarfs clock skew. **All correctness ordering uses `scan_order`, never `@timestamp`**
    (display still uses `@timestamp`). Carried on the envelope, stamped onto `scan-events` and every
    `occurrences` row. (Keeps D30 - no scanner→backend query.)
  - **Per-digest committed-scan watermark (keystone, A/B-r3).** New single mutable index
    **`javv-scan-watermarks`** (`_id = hash(cluster+scanner+digest)`, `cluster_id` field for tenant filter;
    holds `max_committed_scan_order` + `max_committed_scan_at`). At commit the backend **CAS-bumps the watermark to
    `max(current, my_scan_order)`**; if `my_scan_order < watermark` the run is **stale → skip all cache writes**
    (history is immutable/idempotent and the catalog orders by `scan_order`, so stale history is harmless).
    **Both create and update paths** (partial-merge *and* reconcile) guard against the watermark - fixing the
    "finding only in an older out-of-order scan" resurrection that per-doc `last_scan_at` could not. `findings`
    gains **`last_scan_order`** as the per-doc guard key.
  - **Scanner-cache rebuild (D-r3).** `rebuild-state` is extended to **rebuild the scanner-presence cache**
    (`present`, `last_scan_order`, `last_scan_at`, `last_scan_run_id`, `resolved_at`) from `scan-events` +
    `occurrences`, so a crash between commit and the findings merge self-heals (on demand + after a detected
    crash). (Previously rebuild-state was human-state only.) **The job is built in M8a, not M3** (it replays
    `occurrences`, which land in M8a — 2026-07-03); in M3 the same crash self-heals via the stateless
    full re-scan every cycle (D30).
  - **Reconcile retries to zero conflicts (E-r3).** The reconcile `update_by_query` **inspects the conflict
    count and re-runs scoped until zero** (not `conflicts=proceed`-and-forget), so a doc racing a human triage
    write is never wrongly left `present=true`. The script patches **scanner-owned fields only**.
  - **Decision edit atomicity (G-r3).** A scope/`expiry` edit (= revoke + create-new) assigns **one
    `effective_at`** to both docs (`revoked_at(old) = created_at(new) = effective_at`) under one
    **`operation_id`**; projection runs **only after both writes land**, so active-at-T never sees a
    neither/both gap.
  - **Audit causal ordering (H-r3).** Each triage write is CAS'd on the finding and the audit event records the
    resulting **`revision`** (the finding's new version); replay orders same-`(entity, field)` events by
    `revision`, not `event_id` (which is only a tiebreak for unrelated events). Fixes the same-millisecond
    same-field race.
  - **Inventory ordering (F-r3).** The `javv-inventory-runs` manifest gains **`inventory_order`**
    (backend-allocated - D45, same basis as `scan_order`; minted when M8a builds the manifest); "running at T" sorts by `inventory_order`, not `@timestamp`.
    A partial run writes no `committed` manifest → reads fall back to the prior committed run + the staleness
    banner.
  - **PIT catalog ordering (C-r3).** The catalog's "latest commit per digest ≤ T" sorts by
    **`(scan_order, commit_key)`**, not `@timestamp desc`.
  - **Report orphan cleanup (I-r3).** Publication was already safe (bell reads the `done` doc's
    `result_location`); add **orphan-object cleanup** - `attempt_id` in object metadata + a TTL sweep of
    failed/stale attempts.
  - **Regression corrections.** D23/NFR-9: *history* has **no close-event race**, but the *current cache* uses
    **guarded read-modify-write** (watermark + newer-scan-wins + retry-on-conflict) - claim reworded. Residual
    "one pass" → "one ingest request, **ordered phases**." **Reconcile cost bound:** route by `cluster_id`,
    query exact `cluster_id`+`scanner`+`image_digest`, throttle, observe conflict/retry counts, document
    expected max findings/digest.
- **D41 - Scanner version is build-time; no live in-app version switch.** The scanner binary version is
  **pinned in the Dockerfile `ARG`** (`TRIVY_VERSION`/`GRYPE_VERSION`), and JAVV **publishes** the self-built,
  pinned images (public once the repo is; Dockerfiles stay public for supply-chain transparency). A cluster
  operator changes the version by **swapping the published image tag in their own deploy** (Helm value →
  GitOps reconcile); JAVV **never writes to monitored clusters** (a backend that PATCHes CronJobs / writes
  other clusters' GitOps repos is a cross-cluster privilege-escalation surface and often network-impossible
  when JAVV is separate/SaaS). So the reference UI's "version **select**" (`SCREENS.md` §12) becomes
  **read-only version *display*** (running `scanner_version` + DB freshness, Harbor-style), **not** a control.
  - **"Multiple versions" lives in CI, not at runtime:** a **compatibility gate** runs candidate
    Trivy/Grype versions through the JAVV adapters/golden contracts; green → the image is published as compatible
    (new bolt, between M0 and M1). Keep the published set **small** (current + 1-2 prior) - each pinned tag is
    supply-chain surface (re-base/re-scan) and risks an **EOL vuln-DB** (Grype <0.88 scans a frozen DB;
    v5↔v6 schemas are incompatible - the PVC DB cache in M10 must be **per-schema**, not per-binary).
  - **Scanner image release ≠ JAVV release.** Image publishing is its own track (`scanner-v*` tag /
    `workflow_dispatch`), independent of release-please's `v*` app version - a new compatible scanner
    version or a base-layer rebuild ships **without bumping JAVV**. Each build pushes a **moving `:<ver>`**
    tag + an **immutable `:<ver>-<git-sha>`** tag with OCI labels (`…image.version/revision/source`,
    `javv.scanner`); the `-<git-sha>` ties the image to the JAVV commit that built its entrypoint (entrypoint
    *logic* changes are JAVV code and still version with JAVV, but can be published any time via dispatch).
  - **Provenance (M0):** the envelope stamps **`scanner_version` + `scanner_db_version` + `scanner_db_built`**,
    self-reported by the binary (Trivy `Trivy.Version`; Grype `descriptor.version` + `descriptor.db.status`;
    Trivy's standalone JSON has no DB info → DB fields null). Stored on `scan-events` for the read-only version
    view + audit version matrix (`AUDIT-RESPONSE.md` "scanner/backend version matrix"). A deliberate
    *downgrade* must still mint a **greater `scan_order`** (D40) so newer-wins reconcile doesn't mis-rank it.
- **D42 - Single source of truth for externally-owned versions (`versions.yaml`).** The versions of tools/
  services JAVV doesn't own (scanners, OpenSearch; toolchain in a phase 2) are pinned in one root file
  **`versions.yaml`**, the human-/app-readable "what JAVV supports" registry (surfaced in the README's
  *Supported versions*). **Renovate** watches it via a `customManager` (bumps only the annotated `current`
  pins; `also_supported` priors are manual), and a Renovate bump's PR is auto-validated by the **D41
  compatibility gate**. Consumers keep a literal pin so they work standalone (`docker build`,
  `docker compose up`); a CI **drift check** (`development/scripts/check-versions.sh`, `--fix` to propagate)
  fails if a consumer diverges from `versions.yaml`. Code *libraries* (pyproject), GitHub Actions, and
  pre-commit hooks stay in their native files where Renovate manages them directly - **not** centralized
  (centralizing them would fight Renovate, not help).
- **D43 - Scan scope is UI-configurable via `system-config`; the scanner fetches it from the backend.**
  *Which* namespaces/images/kinds the scanner scans is **operational policy** an operator changes often, so
  it is **runtime data** (tier ③) - a `scan_scope:<cluster_id>` doc in `system-config`, editable from the
  Settings→Scan scope UI (M9e). This is distinct from scanner *tuning* flags (severities/ignore-unfixed -
  env/GitOps, read-only in the UI, #91) and scanner *version* (build-time, D41). The **scanner fetches scope
  from the backend** (`GET /api/v1/scan-scope`) at cycle start and filters discovery **before** pull/scan; it
  **never reads OpenSearch directly** (the backend owns the client + always-applied `cluster_id` filter,
  SEC-4). A deliberate, bounded departure from "purely env-configured scanner": a **read-only config fetch**,
  still stateless, and it does **not** change D30 (still scans *everything in scope* every cycle, no
  skip-unchanged). **Fail-closed fetch:** backend unreachable → **no-op cycle** (nothing to push to anyway);
  a *successfully-fetched empty* scope → **scan all** (the default) - `fetch failed` and `fetched empty` are
  distinct paths. **Token (MVP):** any valid, non-disabled token may read **its own cluster's** scope - no
  scope-broadening; scope is non-secret data the scanner already effectively sees (it lists all namespaces),
  and real capability-based auth is M5a (D33). Write path = the M9e UI + an interim admin CLI; the
  effective-scope envelope stamp is a later **joint schema-v3** with the scanner effective-flags stamp (#91).
  (**FR-24**.)
- **D44 - Effective config is stamped on the envelope (schema v3) - read-only display, never a control.**
  Every envelope carries an `effective_config` block: the scanner's effective **tuning** flags (the
  per-scanner `JAVV_TRIVY_*`/`JAVV_GRYPE_*` values actually used, a per-scanner-discriminated shape) and
  the **scope** actually applied that cycle (the fetched D43 `ScanScope`). Purpose: the M9e per-scanner
  cards + audit answer "what did this scan run with" from data, not inference. **Display/audit only** -
  there is no write-back path; tuning stays env/GitOps (D41 + the #91 read-only ruling), scope's write
  path stays D43's. The stamp is persisted on the **scan-events** docs only (the run-level record) - not
  findings, not images. The envelope stays **current-only** (D37/D38 ruling): the v2→v3 bump is a
  **flag-day** - scanner images and backend upgrade in lockstep (a deploy constraint, noted in M10); the
  backend 422s non-current envelopes by design. Supersedes the old "phase-2 `scanner_config` doc in
  `system-config`" idea. (Closes the #91 arc; joint with #94's effective scope.)
- **D46 - full-word canonical severity vocabulary (#274, ruled 2026-07-08).** The canonical severity
  vocabulary is the six FULL words - `critical, high, medium, low, negligible, unknown` - everywhere a
  severity **value** appears (API filters, facet bucket keys, saved-view presets, SLA settings
  `critical_days`/`medium_days`, the stored canonical field). The historical `crit`/`med` shorthand
  survives only as count **column names** on the envelope/scan-events/images (documented physical names -
  they live in the immutable append history; renaming them buys nothing a human ever types). Findings +
  occurrences carry a server-derived **`severity_canonical`** keyword: the QUERY key filters/facets
  target; the verbatim scanner word (D16) stays display/evidence-only. `SlaPolicy.days_for` canonicalizes
  its input (before this, a real ingested `CRITICAL` matched nothing and no real finding ever went
  overdue). For every standard scanner word canonical == verbatim-lc, so the two vocabularies coincide on
  the normal path; the stored field is the correctness net for non-standard words. Dev-store ruling: past
  data disposable - hard renames, no aliases/backfills.
- **D47 - the backend runs its own background jobs (issue 691, ruled 2026-10-02).** Staleness, lifecycle,
  findings cleanup, session sweep, report drain and report sweep are started by a scheduler inside the
  backend process, each on a cron expression from an env var read on the local wall clock. One job runs at
  a time and the export drain goes first. This **supersedes "CronJob" for a backend job wherever this plan
  says it**: there is no CronJob per job and no second backend for jobs, so a docker compose deployment
  runs the same as a Kubernetes one. Why: nothing started the jobs outside Kubernetes, and the app could
  not know a schedule that lived in a manifest. Accepted costs: a heavy job shares the process that serves
  the UI and ingest, and a backend restart cuts a running job (every job is safe to run again). Scanners
  are unaffected: they stay CronJobs (`Forbid`) in the monitored clusters, which is what keeps `scan_order`
  monotonic.
- **D45 - `scan_order` is backend-allocated (amends D40's *source*; the intent - never a clock - stands).**
  The M0 scanner minted `scan_order` from wall-clock `time.time_ns()`; monotonic on one host, but CronJob
  pods reschedule across nodes, and a skewed/stepped node clock could make a **newer** run's order regress -
  M3's watermark CAS would then (correctly) reject it and **silently drop its findings**. So the ordering
  key is minted by the **backend**: at cycle start the scanner `POST`s `/api/v1/scan-runs` (token-scoped,
  **fail-closed** like the D43 scope fetch - backend down → skip the cycle); the backend CAS-increments a
  per-`(cluster_id, scanner)` counter doc in **`javv-scan-orders`** - a dedicated, tiny mutable index
  (`#clusters × #scanners` docs, `_seq_no`/`_primary_term`-guarded, no rollover/ISM/retention ever,
  save deleting a whole cluster, issue 765) -
  and returns the new order. **Separate from `javv-scan-watermarks` on purpose:** watermarks are
  *derived* state (rebuild-state may wipe + recompute them from the catalog); the counter is
  *authoritative* (allocated-but-uncommitted orders are invisible to the catalog, so a naive rebuild
  could re-issue one) - the index boundary makes "rebuild never touches the counter" structural. The
  counter self-heals only **forward** (if `max(committed) > counter`, bump up; never down). Pure logical
  (Lamport-style) sequence: 1, 2, 3, … - **can never regress**, independent of any node clock; gaps
  (allocated-but-crashed cycles) are harmless (monotonicity, not density, is the contract).
  `@timestamp` stays display-only (D40).
  Envelope schema unchanged - same `scan_order` field, different mint. Built as M3's first slice (#25);
  contract page: `development/bolts/M3-dedup-identity-projection/CORRECTNESS-CONTRACT.md`.
- **Promoted/retained MVP:** per-finding occurrences + point-in-time (now M8); VEX **export** (M6).
- **Moved to v1.1:** **VEX import** (consuming external VEX into `system-decisions`) - MVP ingests **only
  the scanner JSON envelope**; Jira ticket push; dashboard **builder** (saved views stay the default);
  `javv-metrics-*` downsample tier; CEL/expression policies; LDAP/OIDC.
- **Contributors:** **kept and expanded** (MVP) - richer leaderboard/TTR/SLA metrics; rides
  `system-audit-log`, which therefore gets **long/independent retention** (D8/§5.5b).
- **Explicit non-goals:** supply-chain hash-integrity checking; **cross-scanner merge** (disagreement flags
  only).

## 4. Architecture
See `ARCHITECTURE.md`. Summary unchanged in shape from v3 (scanner → hardened ingest → OpenSearch single
store with current-state + append-logs + system layer → Vue frontend); v4 adds the `system-decisions`
rename, `system-reports`, the rebuild-state + scheduled-export jobs, and an HA/multi-pod section.

## 5. Core data model

### 5.1 Two layers, strict field ownership
- **Scanner-owned** (severity, cvss, fixed_version, package, purl, fix_state, first_seen_at/last_seen_at, scan_run_id):
  written **only by ingest**, overwritten each scan. Enum/casing fields use a **lowercase normalizer**
  (D16) - verbatim value preserved in `_source`.
- **Human-owned** (state, vex_justification, assignee, notes, decision linkage): a **rebuildable cache** on
  `findings` (D17). Source of truth = `system-decisions` + `system-audit-log`. Written by triage/projection
  only; **never** touched by ingest - which writes scanner fields via a **partial-doc merge** that leaves
  human fields intact (no preserve script - D17/D31).

Append-logs layer: `javv-scan-events-*` (severity *summaries* → trends, §5.4) and
`javv-finding-occurrences-*` (full *per-scan snapshots* → *point-in-time*, §5.5). Both use `@timestamp`; current-state
carries `first_seen_at`/`last_seen_at` as fields.

**Relationships are shared-key joins** (no foreign keys, no embedded sub-tables): finding↔image via
`cluster_id`+`image_digest`; finding↔history via `finding_key`→occurrences; finding↔decision via `cve_id`+
scope→`system-decisions`. The `images` doc holds **rollup counts, not the vuln list** - the CVE list comes
from querying `findings` by `image_digest` (findings **denormalize** image/namespace/tag so you filter/agg by
image without touching `images`). A CVE on N images = **N findings rows** (`finding_key` includes
`image_digest`, per-scanner, never merged); a single **CVE-anchored** `system-decisions` record with a
**scope** projects `state` onto the in-scope rows (D4/§5.7). Worked example: `FLOW-EXAMPLE.md` §7–§8.

### 5.2 `findings` - mutable current-state (UPSERT) · the triage entity
`_id = finding_key = hash(cluster_id + image_digest + scanner + cve_id + package_name + installed_version)`
→ per-scanner rows (never merged).

Holds: scanner-owned fields (above) + EPSS/KEV (Grype) + denormalized image/namespace/tag fields +
**full-precision `first_seen_at`/`last_seen_at`** (`date`, not day-grain - D37/M13) + `last_scan_run_id` +
**`last_scan_order`** (the newer-scan-wins guard key - integer, D40/C-r3) + `last_scan_at` (committed run
`@timestamp`, display) + **`present`/`resolved_at`** (reconcile-on-commit - D37/C2) + the human-owned **cache**
fields + precomputed `disagree` flag (D5a) + `schema_version`. **Both create and update guard against the
per-digest watermark** (`javv-scan-watermarks`, D40) - a stale out-of-order run never writes the cache.

**Presence ⟂ state (D39/M10-r2).** `present`/`resolved_at` (scan-presence) is **orthogonal** to `state` (human
lifecycle + system `stale`): `present=true` = on the latest committed scan; `present=false` + healthy scanner =
**resolved-by-scan** (fixed/withdrawn); `state=stale` = **scanner silent** (presence unknown). Every "now"
grid/report **must filter on both** (`present=true` + the screen's `state` filter) and always carry
`cluster_id`+`scanner`.
`severity` is a `keyword` with a **lowercase normalizer**, plus a derived `severity_rank` (`byte`) for
correct severity sort/range (D16). Human-owned fields are a **projection** -
recoverable via the rebuild-state job from `system-decisions` + `system-audit-log` (D17). **Vuln-age/SLA is
computed at read time** (D21), not stored, so a package-version bump never resets `first_seen_at`.

**State machine (D1):** `state ∈ {open, acknowledged, not_affected, risk_accepted, resolved, stale}` +
`vex_justification` (CISA five; required iff `not_affected`). "False positive" = `not_affected` +
component/code-not-present justification (UI chip). `risk_accepted` is set by **decision projection** (an
approved `system-decisions` record); `stale` by the sweep; `resolved` manual-only. Every user transition
**appends to `system-audit-log`** (D17). Transitions per v3 §5.2.

### 5.3 `images` - time-partitioned inventory snapshots (APPEND · D29)
k8s-runtime inventory, **one immutable snapshot per (image, scan)** appended to `javv-images-<cluster_id>-*`
(no longer a mutable upsert), each cycle stamped a shared **`inventory_run_id`**. A run's completeness is
certified by an **inventory commit manifest** in `javv-inventory-runs-<cluster_id>-*` (`status=committed`,
written last - D39/H4-r2; `inventory_run_id` alone can't tell a partial/zero-image run from a complete one).
**"Running images now / at T" = the images of the latest `status=committed` `inventory_run_id` ≤ T** - *not*
latest-doc-per-digest, and never an uncommitted/partial run; an undeployed image is absent from the next
committed run and disappears **at that run**, not at retention - **no zombie sweep**. Per-severity counts (incl.
`negligible`/`unknown`); `replicas` observed at scan time; `scanners[]`; **count-disagreement pair**
`{trivy_count, grype_count, count_delta}` (D5b); `fixable`. Rolls over (size/age/docs) + per-cluster
drop-whole-index retention. A scanner outage shows the **staleness banner** (latest snapshot is old). Full
mapping: `INDEX-MAP.md`.

### 5.4 `javv-scan-events-*` - append-only severity summaries (trends) · PINNED
One **immutable** doc per **(image, scanner, scan)**. Logs/events, not metrics.

| field | type | notes |
|---|---|---|
| `@timestamp` | `date` | scan time; rollover/retention axis (**display only**, not ordering - D40) |
| `scan_run_id` | `keyword` | the run this summary belongs to |
| `scan_order` | `long` | backend-allocated (D45) monotonic per (cluster,scanner); **the catalog ordering key** (D40/C-r3) |
| `cluster_id` | `keyword` | immutable; tenant filter + index routing |
| `scanner` | `keyword` | `trivy`/`grype` |
| `namespace` | `keyword` | |
| `image_repo` | `keyword` | |
| `image_digest` | `keyword` | dedup identity |
| `tag` | `keyword` | display only |
| `app` | `keyword` | workload/app label |
| `crit`,`high`,`med`,`low`,`negligible`,`unknown`,`total`,`fixable` | `integer` | severity buckets; `total = crit+high+med+low+negligible+unknown` (Grype `Negligible`/`Unknown` kept, not folded; vocabulary mapped at adapter, D16) |
| `schema_version` | `short` | forward-compat (D25) |

- **`_id = hash(scan_run_id + image_digest + scanner)`** → idempotent append (D18). Carries the
  **`commit_key = hash(cluster_id + scanner + image_digest + scan_run_id)`** (D37/H3).
- **Commit catalog + marker (F1/R-CATALOG, D37):** this doc is the **authoritative snapshot catalog** - an
  occurrences snapshot (§5.5) is eligible "latest" only if a matching scan-events doc exists for its full
  `commit_key` 4-tuple. The point-in-time read path resolves the latest committed `scan_run_id` **here first**,
  then reads occurrences for that run (so a clean rescan that wrote zero occurrence rows is read as *clean*,
  not as the stale previous snapshot). A clean scan still writes this doc (`total:0`).
- `dynamic:false`, 1 primary shard, **monthly rollover**, partition `javv-scan-events-<cluster_id>-NNNNNN`
  (**`scanner` is a field, not in the index name** - D38/M15; write to a rollover alias; rollover makes
  backing indices).
- **Lifecycle (D8):** rollover (doc count / age / size, configurable via D26) → delete by **dropping
  whole indices** at per-cluster `retention_days`. Never delete-by-query. Executed by the M4 **lifecycle
  CronJob** (`_rollover`+`conditions`, evaluated server-side; the Curator model), NOT the ISM plugin —
  ISM's per-index `rollover_alias` setting can't be templated per cluster, its policy edits don't
  live-apply, and per-cluster `retention_days` doesn't fit one static policy (settled at M4 kickoff, #26).

### 5.5 `javv-finding-occurrences-*` - append-only per-scan snapshots (point-in-time) · PINNED
**Full snapshot per successful scan:** every scan of a digest appends one **immutable** row for **every**
finding currently on that digest (not just changes), `@timestamp`-axed. A fixed/absent vuln is simply not
present in later snapshots - **no close events** (validated: this is Elastic CSPM's raw+latest pattern; see
`docs/research/SNAPSHOT-MODEL-VALIDATION.md`).

| field | type | notes |
|---|---|---|
| `@timestamp` | `date` | scan time; point-in-time axis (one value per `scan_run_id`) |
| `scan_run_id` | `keyword` | the snapshot's scan run |
| `scan_order` | `long` | backend-allocated (D45) monotonic per (cluster,scanner); ordering key (D40/C-r3) |
| `commit_key` | `keyword` | = scan-events `commit_key` (cluster+scanner+digest+run); exact membership for the symmetric query (D39) |
| `cluster_id` | `keyword` | tenant + routing |
| `scanner` | `keyword` | |
| `image_digest` | `keyword` | the reconstruction identity (immutable, content-addressed) |
| `namespace` | `keyword` | |
| `vuln_id` | `keyword` | CVE pivot (= `cve_id` in other indices) |
| `package_name`, `package_version` | `keyword` | `package_version` = findings' `installed_version` |
| `finding_key` | `keyword` | per-row identity |
| `severity` | `keyword` (lowercase normalizer) | **as-of-then**; verbatim in `_source` (D16; no `severity_rank` here - OE-5/D38) |
| `cvss` | `float` | as-of-then |
| `fixable` | `boolean` | |
| `fixed_version` | `keyword` | |
| `schema_version` | `short` | (D25) |

- **`_id = hash(scan_run_id + finding_key)`** → idempotent append (D18): a retried push overwrites, never
  duplicates. Pure append - **no read-modify-write, no multi-pod race at any replica count.**
- **Atomic-complete-snapshot guard (commit record, F1).** One push = one `scan_run_id` + one `@timestamp`;
  append **only for a fully successful scan** - the scan-events commit doc is written **last, after the
  occurrences `_bulk` returns zero item-level errors** (inspect per-item status, not just the top-level flag -
  H4). The `javv-scan-events` doc (§5.4) is the **commit catalog/marker** - point-in-time resolves "latest
  snapshot ≤ T" **only among `scan_run_id`s that have a matching scan-events doc**, so a half-written `_bulk`
  is never read as "latest." Broker-free; reuses an index we already write.
- **Forward query - "digest X at T" (R-CATALOG two-step, D37):** **(1)** from `javv-scan-events ≤ T` get the
  **max-`scan_order`** committed `scan_run_id` for X (+`scanner`) (D40 - order by `scan_order`, not
  `@timestamp`); **(2)** read occurrences for *that exact run*. Its
  rows = the state then; **zero rows = clean image** (a clean rescan wrote no occurrence rows - reading
  "latest occurrence doc per digest" instead would resurrect the previous scan's fixed CVEs, C1). "Not yet
  scanned then" when no committed run ≤ T. **Never** sort occurrences by `@timestamp desc` and take the top
  doc.
- **Symmetric query - "which images had CVE-Y at T" (two-step via the catalog, F2/D39 - NOT a swapped
  collapse, NOT a composite over occurrences).** **(1)** page the **`javv-scan-events` catalog** by
  `(cluster_id, scanner, @timestamp ≤ T)`, composite-agg on `image_digest` + `top_hits` size 1 sort
  **`scan_order desc`** (not `@timestamp` - D40/C-r3) → the latest committed `commit_key` per digest, paginate
  with `after_key`; **(2)**
  `commit_key IN {…} AND vuln_id=Y` against occurrences → which digests had Y in their latest **committed**
  snapshot. Step 1 over the catalog (not occurrences) is what keeps a clean run from resurfacing a digest;
  matching on `commit_key` (not bare `scan_run_id`) keeps the two scanners' runs independent. Per-scanner (run
  twice, side-by-side, never union).
- **"Image X" = digest (F3).** Reconstruction is per `image_digest`; the UI selects by `repo:tag`/workload
  and maps to the digest(s) running at T (with a "build changed here" marker, not a silent gap). Results are
  **as-scanned, not as-running** (F4) - historical deployment/presence is a named non-goal (current-state
  `images` covers "now").
- **Naming/lifecycle:** `javv-finding-occurrences-<cluster_id>-NNNNNN`, partition per `cluster_id`, monthly
  rollover, per-cluster `retention_days` (drop-whole-index). **NON-downsampled** - accurate detail horizon =
  raw retention.

### 5.5b Retention horizons (one setting per purpose)
| Index | Type | Retention = how far back you can see… | Size | Default |
|---|---|---|---|---|
| `findings` / `images` | current-state (mutable) | "now" | bounded | no time-retention |
| `javv-finding-occurrences-*` | append (per-finding) | **exact CVE-level point-in-time** | **big - cost lever** | per-cluster `retention_days` |
| `javv-scan-events-*` | append (summaries) | trend charts (counts) | medium | per-cluster `retention_days` |
| `system-audit-log` | append (immutable) | **audit + Contributors** (who did what) - **bounds the leaderboard window** | small | **keep long**, compliance-aware |
| `system-reports` | small mutable | export job records | tiny | short |
| `javv-metrics-*` (v1.1) | downsample rollup | cheap multi-year trends (lossy counts) | tiny | keep long |

### 5.6 `system-*` - system + human-decision indexes
`system-users` (username, `password_hash` argon2id, role, created_at, disabled), `system-roles`,
`system-tokens` (per `(cluster,scanner)`, hashed, scope `push:findings`, `last_ingest_at`), `system-sessions`
(server-side sessions - SEC-5), `system-config`, **`system-decisions`** (scoped decisions - see 5.7; *was
`system-exceptions`*), **`system-audit-log`** (immutable, every action - D17), **`system-views`** (saved filter
views, visible to every signed-in user - M8e/C-6), **`system-notifications`** (per-user SLA breaches +
assignments), **`system-reports`** (export jobs - D24) + `system-report-chunks` (their stored output),
`system-jobs` (the repair-actions lease + status). `system-tags` is planned, not created yet (tagging, FR-9, is
post-MVP). All behind a **repository interface** (later SQLite/Postgres swap stays localized).

### 5.7 `system-decisions` - scoped decisions + projection (D3/D4)
```
{ type: "risk_accepted" | "ignore_rule" | "not_affected",
  cve_id, scope: { namespaces?: [...], images?: [...] },   // image and/or namespace; empty = cluster-wide
  apply_both_scanners: bool,                                 // semantics pinned in D22
  vex_justification?, justification, approver, expiry, created_by, created_at,
  revoked_at?, effective_at, operation_id }                  // edit = revoke+create-new sharing one effective_at/operation_id (D40/G-r3)
```
**Projection.** A finding's `state` is derived by selecting matching decisions + **precedence**
(explicit-finding > image > namespace > cluster; direct human action > auto-rule; conflict-only). **Scope**
picks the image/namespace dimension; **`apply_both_scanners`** the scanner dimension (D22). Re-projection
runs at **(1) ingest - newly-created findings only, vs cascading namespace/cluster rules (D19)**,
**(2) decision-apply**, **(3) daily sweep** (expiry → next applicable rule, not `open`). Explicit-image
scopes do **not** auto-apply to new images; namespace/cluster scopes do (the cascade). The result is a
**cache** on `findings`, rebuildable from this index + `system-audit-log` (D17). While a finding is
`stale`, projection leaves `state` alone and updates the state saved under the flag (`pre_stale_status`),
so the sweep's revert lands on the current projection (issue 705).

## 6. Background jobs - idempotent, resumable, no engine (D13)
- **Reconcile-on-commit** (at ingest, not a cron - D37/C2; **after** the commit doc lands - D39/H3-r2; **only
  if this run won the watermark CAS** - D40): when a scan commits for `(digest, scanner)`, an `update_by_query`
  flips `present=false` + `resolved_at` on `findings` for that pair whose `last_scan_order` < this run's
  `scan_order`, so the "now" grid drops resolved CVEs immediately. **Newer-scan-wins (D39/C2-r2, D40):** both
  this and the partial-merge guard on `scan_order` vs the per-digest watermark **and** `doc.last_scan_order`, so
  an out-of-order *older* run can never flip or re-create a finding (a stale run skips the cache entirely). The
  `update_by_query` **retries scoped until zero version-conflicts** (E-r3 - never `conflicts=proceed`-and-drop),
  and is **bounded** (routed/filtered to exact `cluster_id`+`scanner`+`image_digest`, throttled, conflict/retry
  counts observed). Cache-only, scanner-owned fields only - `occurrences` is never touched (no close-events).
- **Staleness sweep** (daily CronJob, `Forbid`): **two-timer** (D20) - per-finding `last_seen_at < now−N →
  stale` (save `pre_stale_status`); **scanner-down guard** holds the per-finding timer between N and M days
  (banner shown); past **M days** silent → mark all that cluster's findings `stale`. A `stale` row a
  later scan confirmed gone (`present=false`) reverts to `pre_stale_status` on every sweep (issue 576:
  `stale` means presence unknown, and gone is known). Also runs
  **decision-expiry re-projection** (5.7). **`stale` is a flag, not a delete** (D37/M12): `findings` docs are
  removed only after a separate **long** window (or once gone from inventory that long), never on the
  freshness timer. Re-running is a no-op; `conflicts=proceed`.
- **(No close-event job.)** Occurrences are full per-scan snapshots (§5.5); absence in a later snapshot =
  resolved, so there is no close-event computation, no per-image diff, and no associated CronJob (designed
  out - `docs/research/SNAPSHOT-MODEL-VALIDATION.md`).
- **Rebuild-state** (admin-triggered + optional periodic): re-project all (or scoped) findings' **human cache**
  from `system-decisions` + `system-audit-log` (D17 safety net; replay ordered by `revision` then
  `(@timestamp, event_id)` - D40/H-r3) **and rebuild the scanner-presence cache** (`present`,
  `last_scan_order`, `last_scan_at`, `last_scan_run_id`, `resolved_at`) from `scan-events` + `occurrences` via
  R-CATALOG (D40/D-r3 - so a crash between commit and the findings merge self-heals). Idempotent.
- **Export drain** (rides the background CronJob, D24): process `system-reports` queue; **claim each job by
  optimistic concurrency** (`pending→running` via `seq_no`/`primary_term` CAS + `heartbeat_at` +
  `lease_expires_at` + `retry_count` - D38/M17) so replicas/retries never double-run; off-peak runs throttled;
  write result to object storage; notify via bell.
- **Rollup** (v1.1): deterministic `_id` downsample of old scan-events into `javv-metrics-*`.

Crash-safety = immutable sources + deterministic ids + condition-based writes. No Temporal/durable engine.

## 7. Research baked in
Carried from v3 §7 (VEX two-field model; ELK hybrid append+materialized-current-state; point-in-time via
collapse-latest verified against `elastic/kibana`; downsampling is lossy → accurate history bounded by raw
retention; DT 5.0 lessons; ingest hardening; Apache-2.0 deps; mapping-explosion guards; `_bulk` 5–15 MiB;
PIT+`search_after`). **v4 additions:**
- **Keyword normalizer (D16):** OpenSearch `keyword` fields support a `normalizer` (lowercase filter) - the
  indexed/aggregated token is normalized while `_source` keeps the original. Gives case-insensitive
  aggs/filters with **zero duplicate fields** and **no mutation** of scanner data. Lowercasing cost is
  negligible vs index I/O. Vocabulary (not casing) differences are mapped once at the adapter.
- **Rebuildable state (D17/D31):** with `system-decisions` + a structured append-only `system-audit-log` as
  sources of truth, the human fields on `findings` are a cache kept correct by a **partial-doc merge**
  (ingest writes scanner fields only - human fields untouched, no preserve script), backed by a recompute
  job - not a single point of irreversible loss.
- **OpenSearch snapshot/restore (NFR-6):** native Snapshot API to a repository (shared FS or S3/MinIO via
  `repository-s3`); ISM can automate scheduled snapshots; restore drill = fresh node + `_restore`.
- **HA concurrency (D23):** the point-in-time model is pure-append (full snapshots, deterministic `_id`), so
  it has no close-event race at any replica count - the only multi-pod caveat left is the per-pod rate-limit.
- **Snapshot point-in-time (validated):** full snapshot per scan + **resolve the latest committed run via the
  catalog, then read its occurrences** (R-CATALOG, D37/D39 - not a bare "latest snapshot ≤ T") is Elastic
  CSPM's raw+latest pattern; absence in a later committed snapshot = resolved (no tombstones). The
  `javv-scan-events` doc is the broker-free commit catalog/marker (F1). See
  `docs/research/SNAPSHOT-MODEL-VALIDATION.md`.

## 8. Milestones (FIRE bolts) - v4
Order: **scanners → backend core → durability → identity/triage → read → history → frontend → deploy.**
Each ends on a verifiable check + Confirm gate.

1. **M0 - Scanner modules** (Trivy+Grype, shared pipeline). v3 gates + EPSS/KEV, `scan_run_id`,
   **local digest-dedup, scan-all** (no skip-unchanged - D30), **full-precision `last_seen_at`** (D37/M13),
   backoff/jitter/dead-letter. **+ severity vocabulary
   canonicalization** (map each scanner's ramp → the canonical words, full since D46; verbatim word preserved) (D16).
2. **M1 - Backend skeleton + indexes + ingest + observability.** Explicit `dynamic:false` mappings
   (keyword ids, **severity normalizer** D16, reshaped CVSS, EPSS/KEV) for current-state + `system-*`;
   versioned bootstrap; **hardened** `POST /ingest/scan` (rate-limit, size+decompression caps, **256-bit
   random `(cluster,scanner)` tokens, peppered SHA-256** D38, structured queries, **current-envelope-only
   acceptance** D25/D35); `AsyncOpenSearch` +
   `_bulk`; **structlog + `/metrics` + `/healthz`/`/readyz`** (D9). **Gate: golden-envelope round-trip** -
   a checked-in real scanner envelope POSTed through the actual ingest path asserts resulting
   `findings`/`images`/`scan-events` docs (raw preserved in `_source`, normalized severity bucketed).
3. **M2 - Snapshot/restore (durability early).** Register a snapshot repository (FS/MinIO); automated ISM
   snapshot of `findings`/`images`/`system-*`. **Gate: tested restore drill** (fresh node → `_restore` →
   triage state + users return). (NFR-6.)
4. **M3 - Dedup/identity + staleness + projection (highest risk).** **Partial-doc merge** (scanner fields
   only - human fields untouched, no preserve script; D31) with golden-fixture tests incl. **concurrent
   ingest+triage** (`retry_on_conflict≥3` / 409-retry - SND-8); `detect_noop` (free upsert default);
   **commit-then-cache ordering** (append occurrences+images → scan-events commit after per-item `_bulk`
   success → findings merge+reconcile **last** - D39/H3-r2); **backend-allocated `scan_order`** (D45) + **per-digest
   committed-scan watermark** (`javv-scan-watermarks`, CAS at commit; stale run skips cache - D40) as the
   newer-scan-wins guard on **both create and update**; **reconcile-on-commit** `update_by_query` (mark
   `present=false`/`resolved_at` on findings the committed run omitted, **retry scoped until zero conflicts** -
   D37/C2, E-r3; **gates:** a clean rescan drops the resolved CVE from the "now" grid immediately, **an
   out-of-order older run never flips OR re-creates a finding** (D40 keystone), and **a crash between commit
   and merge self-heals via scanner-cache rebuild**); **rebuild-state job** day-one (D17 human cache + D40
   scanner cache; recomputes `stale` from `last_seen_at` - SND-6); **two-timer
   staleness** + scanner-down guard + banner (D20); **projection-on-new-only** at ingest (D19); optimistic
   concurrency.
5. **M4 - Logs layer (scan-events) + retention.** `javv-scan-events-*` append on ingest with **idempotent
   `_id`** (D18); per-`cluster_id` partition + write aliases + the lifecycle CronJob (rollover on
   doc/age/size, configurable D26; per-cluster `retention_days` drop-whole-index); scanner-disagreement
   flags (D5a/b).
6. **M5 - Triage (split):**
   - **M5a - Auth & Session (own bolt - SEC-5).** `system-users` (argon2id) + **server-side sessions**
     (`system-sessions`, httpOnly+Secure+SameSite cookie, TTL, revoke-on-role-change); **password policy +
     login lockout/throttle**; **capability-based RBAC** (`system-roles` bundles; `can_accept_audit_final`
     gates risk-accept - D33); **bootstrap admin** (mounted secret, seed-once, server-enforced `must_change`
     - SEC-6); `get_current_principal()`; **tenant `cluster_id` read path** (one `tenant_search` helper +
     negative test - SEC-4); IDOR; **auth-event auditing**. *Prerequisite for all mutations.* (Ingest-token
     auth stays separate, with **token↔payload binding** - SEC-3.)
   - **M5b - VEX two-field state machine.** `state` + `vex_justification`; transitions; **every action →
     `system-audit-log`** (D17). `refresh=wait_for` on triage writes.
   - **M5c - Decisions & projection (own gate).** `system-decisions` scoped risk-accept/ignore/not-affected
     with **precedence + expiry-refresh + `apply_both` per D22**; projection cache + rebuild. *Gate verifies
     the pinned `apply_both` rule.*
   - **M5d - SLA/overdue + bulk.** SLA policy + KEV override (FR-10); overdue; bulk via `_bulk` (bounded-synchronous:
     up to `JAVV_BULK_INLINE_LIMIT` applies now, larger is a 413 - A-Mc; one audit entry per bulk action); approval list.
7. **M6 - Read/reporting + VEX export.** PIT+`search_after` search (faceted by scanner, composite aggs);
   trend endpoints over scan-events; **Contributors (expanded)** over `system-audit-log`; streaming
   sanitized CSV; **VEX export** (state/justification → OpenVEX/CycloneDX). *(VEX import → v1.1.)* **As-of-T
   projection read path (D28):** every read endpoint accepts a time `T` - `T=now` reads materialized
   current-state; `T<now` reconstructs from the append logs (occurrences ≤ T ⋈ decisions-active-at-T +
   `system-audit-log` replay ≤ T; `javv-images` snapshot ≤ T; `stale` recomputed). Short-circuits to
   current-state when `T=now`. Bounded by per-cluster retention.
8. **M7 - Scheduled / throttled export (D24).** `system-reports` queue; "run now" vs "off-peak (throttled)";
   CronJob drain; result to object storage; bell notification. Gate: a large export runs off-peak without
   starving ingest.
9. **M8 - Per-scan snapshots + point-in-time (after read; split):**
   - **M8a - Snapshot append.** `javv-finding-occurrences-*` full snapshot per **successful** scan, each row
     stamped **`commit_key` + `scan_order`** (D39/D40); idempotent `_id` (D18); atomic/complete (one
     `scan_run_id` + one `@timestamp`); **scan-events as the commit catalog** (F1, written after per-item
     `_bulk` success) + **per-digest watermark CAS** (`javv-scan-watermarks`, D40); + **`javv-inventory-runs`
     commit manifest** with `inventory_order` (D39/H4-r2, D40/F-r3); failed/stale-run guard. *(No close events
     - validated, `docs/research/SNAPSHOT-MODEL-VALIDATION.md`.)*
   - **M8b - Point-in-time query API.** Forward ("digest X at T" = R-CATALOG two-step: latest **committed**
     `scan_run_id` from scan-events ≤ T, then occurrences for that run - D37) + the **two-step symmetric** query
     (Step 1 pages the `scan-events` catalog → `commit_key` per digest; Step 2 = `commit_key IN {…} AND
     vuln_id=Y` over occurrences - F2/D39). Gates: reconstruct exact CVE-list-at-T for a digest; **a clean
     rescan reads as clean, not as the prior snapshot** (C1 zero-finding guard); the symmetric
     image-set-for-CVE-at-T resolved via the catalog (**not** "latest snapshot per digest"); **a digest that
     dropped CVE-Y by T does NOT appear** (false-positive guard); a failed scan never makes a vuln look fixed;
     results labelled **as-scanned** with `repo:tag`→digest navigation (F3/F4).
   - **M8c - M9-prep session reads** *(v5 design rulings 2026-07-07, #237)*: `GET /api/v1/audit`
     (plain session, D32 shape) · latest-committed scan-event provenance/`effective_config` read
     (catalog-first, D41/D44) · latest-complete-inventory read (`GET /api/v1/images`; the `T=now`
     case of M8b - spec the overlap) · `system-config` **cluster registry** (D-5 ruling:
     `cluster_id`+`cluster_name` doc, read + journaled rename; display-only, never a query key).
   - **M8d - Envelope `ptype`** *(B-1 ruling: keep the v4 package-type donut)*: both adapters emit
     package type, `schema_version` bump (backward-compat window), findings/occurrences mappings +
     facets/groups support; pre-M8d rows heal on the next sweep (D30).
   - **M8e - Server-side saved views** *(C-6 ruling: selling point, durable + shareable)*: new
     `system-views` index (INDEX-MAP first) + `/api/v1/views` CRUD, owner-or-admin mutations,
     journaled (D17); view **counts** stay server aggregations via `/findings/facets`.
10. **M9 - Frontend (reusable-first; per `handoff/docs` current / `handoff/v4` visual base, reference not 1:1):**
    - **M9a - Shell + tokens + reusable filter module** (the `fields`-config driving FacetRail + FilterBar).
    - **M9b - Findings grid + detail/triage (core loop). Gate** before the long tail.
    - **M9c - Overview / all-clusters / images** (incl. **point-in-time image view** via the time picker).
    - **M9d - Audit / approvals / contributors / scanner-status.**
    - **M9e - Settings: Data & OpenSearch panel** (rollover/retention/snapshot - D26, FR-19) + Scanning
      (staleness timers D20).
    - **M9f - Cross-cutting:** global search, **bell notifications** (SLA + assignments), saved views, RBAC
      gating, **empty states / cold-start**. All grids server-side lazy.
    - **UI extends beyond handoff** (expected divergences to build): `not_affected` + `vex_justification`
      pickers ("False positive"/"Not exploitable" chips); the scoped risk-accept dialog (pick images/
      namespaces + approver + expiry); the inventory staleness banner; the export run-now/off-peak dialog.
11. **M10 - Polish & deploy.** Helm (PVC cache, CronJob hygiene, scanner RBAC, snapshots); docs (OpenSearch
    sizing, the `_reindex` migration runbook D25, the HA/multi-pod notes D23); finalize VEX export; attribution.

## 9. Verification (v4 deltas)
As v3 §9 plus: **golden-envelope round-trip** (M1); **snapshot/restore drill** (M2); **idempotent appends**
(a retried push = no double-counted trend / no phantom occurrence - D18); **rebuild-state** reproduces
correct human cache from sources of truth (D17); **projection-on-new** (steady-state rescan with no new
findings ≈ 0 projection writes - D19); **two-timer staleness** + banner (D20); **`apply_both` per the pinned
rule** (D22); **severity normalizer** (verbatim in `_source`, aggs case-insensitive - D16); **scheduled
export** runs off-peak without starving ingest (D24); point-in-time reconstruction both directions + the
**dropped-CVE false-positive guard** and **no-false-fix on a failed scan** (M8b); snapshots are eligible as
"latest" only via the scan-events commit marker (F1).

## 10. Open items
- **Project-specific Claude Code skills** (scan-fixture ingest helper, "run the JAVV stack") + the GitHub/CI
  workflow on the Ubuntu VM (`javv-poc` already remote).
- *(Resolved: close-event model - removed via full-snapshot occurrences (D2b/§5.5). Severity vocabulary +
  `severity_rank` - D16, pinned at M0. Table engine - D27: PrimeVue DataTable lazy + AG-Grid-Community
  escape-hatch.)*
