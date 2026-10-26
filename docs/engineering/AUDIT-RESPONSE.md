# JAVV v4 - Response to external (ChatGPT) design audit

> **Living doc** (formerly `AUDIT-RESPONSE_v4.md` in the old `V4/` folder — suffixes dropped 2026-07-16, #410).
> The v1–v3 evolution trail is frozen in `.deprecated/`; version markers are reserved for frozen generations.

> **Status:** settled. Every round's rulings are applied: they live in `PLAN.md` as D37-D40 and in
> `INDEX-MAP.md` / `SPEC.md` / `ARCHITECTURE.md` / `FLOW-EXAMPLE.md`. This file keeps the reasoning:
> each external finding, its verdict, the concrete fix, and the doc(s) it changed.
>
> **Decisions already locked for this round:**
> - **H9 tenant scope →** *all clusters visible to any authenticated user* for MVP. `cluster_id` is a
>   **data filter that is ALWAYS applied**, not a per-user auth boundary. Per-user/role cluster grants
>   are post-MVP.
> - **M11 severity_rank →** *keep removed from occurrences* (honor OE-5). As-of-T severity sort uses a
>   **fixed order map** (`crit > high > med > low > negligible > unknown`). Fix SPEC/FLOW to match.
>
> **Overall:** sound-with-fixes. The auditor's "I'd refuse to build as-is" is overstated - the real
> bug (below) is query-path discipline + one cheap `update_by_query`, **not** an architecture change.
> No new infrastructure, no broker, no close-events reintroduced into history.

---

## 0. The headline: one root cause behind C1 + C2 + H5

All three "critical/high" data-model findings are the same missing rule:

> **R-CATALOG - "Latest state" is resolved through the commit catalog, never as "latest doc per key."**
>
> - For vulns: latest committed `scan_run_id` for a digest comes from **`scan-events ≤ T`**, *then*
>   occurrences are read for that exact run. Zero occurrences for the latest run = **clean image**.
> - For inventory: "running now / at T" = the **latest complete inventory run** for the cluster, not
>   union-of-latest-doc-per-digest.
>
> This closes the "resurrected fixed CVE" hole without tombstones in history. Absence is still
> computed (snapshot model intact); we just compute it against the *catalog*, not against the raw row
> stream.

---

## 1. Findings → verdict → fix → target

### Critical

**C1 - zero-finding snapshot resurrects fixed CVEs.**
*Auditor loc: PLAN §5.5, FLOW §4.*
**Verdict: REAL - adopt.** A clean rescan writes no occurrence rows, so a naive "latest occurrence
per digest" returns the previous dirty scan.
**Fix:** apply **R-CATALOG**. `scan-events` is already the per-`(cluster_id, scanner, image_digest,
scan_run_id)` receipt - promote it explicitly to *snapshot catalog*. Read path: resolve latest
committed run from `scan-events ≤ T`, then read occurrences for that `scan_run_id`. Empty = clean.
**Target:** `PLAN.md` (read-path / §5.5), `SPEC.md` (FR-5b), `FLOW-EXAMPLE.md` (§4 + §9),
`INDEX-MAP.md` (scan-events = catalog note).

**C2 - `findings` "current-state" isn't actually current.**
*Auditor loc: PLAN §5.2, INDEX-MAP findings.*
**Verdict: REAL - adopt.** Absence in a later scan only ages out after N days, so resolved CVEs show
as open for up to N days in the "now" grid.
**Fix:** **reconcile-on-commit.** When a scan commits for `(digest, scanner)`, run one
`update_by_query` setting `present=false` / `resolved_at` on `findings` for that pair whose
`scan_run_id` ≠ the new run. **This is a cache-projection update, NOT a history close-event** -
`occurrences` stays tombstone-free; this only repairs the disposable `findings` cache. (Consistent
with your rejection of close-events in history.)
**Target:** `PLAN.md` (D17 / M3 ingest), `ARCHITECTURE.md` (§3 step 4), `INDEX-MAP.md`
(findings: add `present`, `resolved_at`, `last_scan_run_id`), `FLOW-EXAMPLE.md` (§6).

### High

**H3 - commit marker under-specified; `scan_run_id` reuse risk.**
*Auditor loc: PLAN §5.4-5.5, INDEX-MAP scan-events.*
**Verdict: REAL - adopt.** Pin commit identity as the 4-tuple `commit_key =
(cluster_id, scanner, image_digest, scan_run_id)` everywhere; queries must match all four. Bans the
loose "scan_run_id has a doc" phrasing. Directly enables C1/R-CATALOG.
**Target:** `INDEX-MAP.md` (scan-events), `PLAN.md` (F1/D-commit), `SPEC.md` (FR-5b),
`FLOW-EXAMPLE.md`.

**H4 - bulk partial success treated too confidently.**
*Auditor loc: ARCHITECTURE §3, SPEC NFR-7.*
**Verdict: MOSTLY COVERED (F1) - tighten wording.** F1 already says commit doc is written last only
after the occurrences `_bulk` succeeds. Add explicit "inspect the bulk `errors` flag / per-item
statuses; write snapshot first, commit marker last, only on all-item success."
**Target:** `ARCHITECTURE.md` (§3), `SPEC.md` (NFR-7).

**H5 - image inventory has the same absence problem.**
*Auditor loc: PLAN §5.3, INDEX-MAP javv-images.*
**Verdict: REAL - adopt (R-CATALOG for inventory).** "Running now / at T" = latest **complete
inventory run** for the cluster (each cycle writes a full inventory snapshot), not latest-doc-per-
digest. Undeployed images correctly disappear at the next run, not at retention.
**Target:** `PLAN.md` (§5.3), `SPEC.md` (FR-14), `INDEX-MAP.md` (javv-images: add
`inventory_run_id`), `FLOW-EXAMPLE.md` (images section).

**H6 - FR-14 conflates "running at T" with "as-scanned, not as-running."**
*Auditor loc: SPEC FR-14, FLOW §5.*
**Verdict: REAL - adopt.** Split the guarantees: `runtime_inventory_at_T` (from image manifests) vs
`vulns_as_scanned_at_T` (from committed scan snapshots). Two terms, two read paths.
**Target:** `SPEC.md` (FR-14), `FLOW-EXAMPLE.md` (§5), `DESIGN-BRIEF.md` (§2.3 wording).

**H7 - `system-decisions`: "mutable" vs "create-only role" contradiction.**
*Auditor loc: INDEX-MAP system-decisions, PLAN D34.*
**Verdict: REAL - adopt.** Resolution: decision docs are **immutable except the lifecycle stamp**
(`revoked_at`, `expiry`). Editing scope = **revoke + create-new** (preserves time-travel:
active-at-T = `created_at ≤ T < revoked_at` and not expired). Every change also emits an audit-log
event. Drop the "create-only" wording - it's "append + lifecycle stamp."
**Target:** `INDEX-MAP.md` (system-decisions), `PLAN.md` (D33/D34), `SPEC.md` (FR-18).

**H8 - audit replay under-modeled (matters: time-travel replays this log).**
*Auditor loc: INDEX-MAP system-audit-log, SPEC FR-7.*
**Verdict: REAL - adopt.** Enrich the schema: `event_id`, `entity_type`, `entity_id`, `field`, typed
value fields (`old_value`/`new_value` kept as keyword for scalars; add structured fields for
non-scalars), deterministic ordering (`@timestamp` + monotonic seq). **Bulk actions store frozen
target IDs** (or query + result-hash + count), never just the selector - otherwise replay drifts.
**Target:** `INDEX-MAP.md` (system-audit-log), `SPEC.md` (FR-7), `PLAN.md` (D32).

**H9 - tenant isolation: no allowed-cluster list on users/roles.**
*Auditor loc: SPEC FR-18, INDEX-MAP system-users.*
**Verdict: REAL gap, but DECISION = defer (locked).** For MVP, **all clusters are visible to any
authenticated user**; `cluster_id` is a **data filter applied on every read** (incl. the 2-step PIT
query and exports), not a per-user auth boundary. Add per-user/role cluster grants post-MVP.
**Fix to land now:** add an explicit invariant "every read/aggregate/export carries a `cluster_id`
filter" (defense against accidental cross-cluster bleed), and a post-MVP note for grants.
**Target:** `SPEC.md` (FR-18 + NFR security), `PLAN.md` (note in RBAC section / backlog).

### Medium

**M10 - envelope version policy contradiction (N/N-1 vs current-only).**
*Auditor loc: PLAN D25/D35, SPEC FR-3, ARCHITECTURE §3.*
**Verdict: REAL - adopt current-only.** Matches D35. Fix SPEC FR-3 + PLAN M1 to current-only;
document a scanner/backend version matrix.
**Target:** `SPEC.md` (FR-3), `PLAN.md` (M1, reconcile D25↔D35).

**M11 - occurrences `severity_rank` inconsistent.**
*Auditor loc: SPEC FR-5b, PLAN §5.5, INDEX-MAP occurrences, FLOW samples.*
**Verdict: REAL inconsistency - DECISION = keep removed (locked).** Honor OE-5: no `severity_rank`
on occurrences. As-of-T severity sort uses a **fixed order map** (`crit > high > med > low >
negligible > unknown`) at query/render time. Remove the stray `severity_rank` from SPEC FR-5b and
FLOW sample docs.
**Target:** `SPEC.md` (FR-5b), `FLOW-EXAMPLE.md` (sample docs), note in `INDEX-MAP.md`.

**M12 - `findings` stale-cleanup deletes useful cache.**
*Auditor loc: INDEX-MAP findings, PLAN §5.5b.*
**Verdict: REAL - adopt.** Separate **"stale" (a flag)** from **"delete" (long retention)**. Don't
`delete_by_query` on the freshness timer. The C2 reconcile sets `present=false`; deletion only after
a separate long window (or once the image is gone from inventory for that window).
**Target:** `INDEX-MAP.md` (findings retention), `PLAN.md` (§5.5b).

**M13 - minute/hour time picker vs day-granularity `last_seen`.**
*Auditor loc: PLAN D21/D28, SPEC FR-23.*
**Verdict: REAL - adopt.** Store full `first_seen_at` / `last_seen_at` timestamps; derive day buckets
for UI. `occurrences.@timestamp` is already full precision, so minute-level as-of-T works off the
catalog + occurrences.
**Target:** `INDEX-MAP.md` (findings), `PLAN.md` (D21).

**M14 - token hashing underspecified.**
*Auditor loc: PLAN D34, INDEX-MAP system-tokens.*
**Verdict: REAL - adopt (MVP scope).** Generate **256-bit random** tokens; store **peppered
SHA-256** (entropy makes Argon2id unnecessary for random secrets). Clarify "token↔payload binding" =
**authorization matching** (token's allowed scope must match payload's cluster_id/scanner), not
cryptographic body signing. Body-HMAC + bounded replay nonce = **post-MVP** unless you want replay
resistance now.
**Target:** `INDEX-MAP.md` (system-tokens), `PLAN.md` (D34), `SPEC.md` (FR-18/NFR).

**M15 - per-cluster × per-scanner × rollover shard explosion.**
*Auditor loc: SPEC NFR-2, INDEX-MAP summary.*
**Verdict: ALREADY CAVEATED - one improvement.** Root note already says monthly rollover, 1 primary
shard, "hundreds → revisit." **Improvement: keep `scanner` as a FIELD, not in the index name**
(drop the `trivy_..._CLUSTER` idea) - halves index count for free while keeping per-cluster
partitioning. Restate the scale threshold honestly in NFR-2.
**Target:** `INDEX-MAP.md` (partition/naming), `SPEC.md` (NFR-2).

**M16 - all-cluster rewind + aggs + replay is expensive; PIT contexts leak.**
*Auditor loc: PLAN D28, SPEC FR-23.*
**Verdict: REAL guardrail - adopt.** Historical *dashboards* read the pre-aggregated `javv-metrics`
rollup (v1.1), not raw occurrences; per-cluster rewind is the fast path; **close PIT/search contexts**
(don't rely on expiry); paginate aggs via composite `after_key`. Full history stays available
(non-negotiable) - these are cost guardrails, not scope cuts.
**Target:** `ARCHITECTURE.md` (§3/§6), `PLAN.md` (D28), `SPEC.md` (FR-23/NFR-2).

**M17 - `system-reports` job queue needs lease/claim semantics.**
*Auditor loc: PLAN D24, ARCHITECTURE §6.*
**Verdict: REAL no-broker gap - adopt.** CronJob `Forbid` guards one CronJob, not API replicas /
retries. Add **optimistic-concurrency claim**: `pending → running` via `seq_no` / `primary_term` CAS,
plus `heartbeat_at`, `lease_expires_at`, `retry_count`. This is the correct "OpenSearch as the
coordinator" pattern - no broker introduced.
**Target:** `INDEX-MAP.md` (system-reports), `PLAN.md` (D24), `ARCHITECTURE.md` (§6).

### Low

**L18 - index names alternate hyphen vs underscore.**
*Auditor loc: all docs.*
**Verdict: REAL trivial - adopt.** `INDEX-MAP.md` is canonical; **hyphens everywhere**
(`system-decisions`, `system-audit-log`, …). Sweep all docs.
**Target:** all V4 docs.

---

## 2. Summary table

| # | Sev | Verdict | One-line fix |
|---|-----|---------|--------------|
| C1 | Crit | Adopt | scan-events = snapshot catalog; resolve latest run before reading occurrences (R-CATALOG) |
| C2 | Crit | Adopt | reconcile-on-commit `update_by_query` on `findings` cache (not history) |
| H3 | High | Adopt | `commit_key` = 4-tuple, matched on all queries |
| H4 | High | Covered+tighten | inspect bulk item statuses; snapshot first, commit last |
| H5 | High | Adopt | "running now/at T" = latest complete inventory run |
| H6 | High | Adopt | split `runtime_inventory_at_T` vs `vulns_as_scanned_at_T` |
| H7 | High | Adopt | decisions immutable + lifecycle stamp; edit = revoke+new |
| H8 | High | Adopt | richer audit schema; bulk = frozen target IDs |
| H9 | High | Defer (locked) | all clusters visible; cluster_id always-applied filter; grants post-MVP |
| M10 | Med | Adopt | envelope current-only (D35) |
| M11 | Med | Keep-removed (locked) | no severity_rank on occurrences; fixed order map; fix SPEC/FLOW |
| M12 | Med | Adopt | stale = flag; delete only on long retention |
| M13 | Med | Adopt | full first/last_seen timestamps |
| M14 | Med | Adopt | 256-bit random tokens, peppered SHA-256; clarify binding |
| M15 | Med | Caveated + tweak | scanner = field not index name |
| M16 | Med | Adopt | historical dashboards use javv-metrics; close PIT contexts |
| M17 | Med | Adopt | OCC claim/lease on system-reports |
| L18 | Low | Adopt | hyphens everywhere; INDEX-MAP canonical |

**Net new schema fields introduced by these fixes:**
`findings`: `present` (bool), `resolved_at` (date), `last_scan_run_id` (keyword), full
`first_seen_at`/`last_seen_at` (date). · `scan-events`: `commit_key` (keyword). · `javv-images-*`:
`inventory_run_id` (keyword). · `system-audit-log-*`: `event_id`, `entity_type`, `entity_id`,
`field`, structured value fields, frozen `target_ids`. · `system-reports`: `heartbeat_at`,
`lease_expires_at`, `retry_count`, claim state. · `system-decisions`: `revoked_at`, `expiry` (if not
already present).

**Nothing here adds infrastructure.** No broker, no Redis/Kafka, no close-events in history. The
snapshot point-in-time model and whole-app time-travel survive intact - they just read through the
commit catalog instead of raw latest-per-key.

---

## 3. Round 2 - verification of the round-1 fixes (→ D39)

The round-1 fixes were re-audited. Verdict: directionally right, but the *write/read ordering and
completeness contracts* were underspecified - out-of-order scans and uncommitted cache writes could make
the "now" grid lie. All round-2 findings adopted; folded into **D39** (`PLAN`). Two locked design
choices: **inventory completeness → a dedicated `javv-inventory-runs-*` index**; **presence model →
`present`(bool)+`resolved_at`, orthogonal to `state`, reuse `state=stale` for scanner-down**.

| # | Sev | Verdict | Fix (→ D39) |
|---|-----|---------|-------------|
| C1-r2 | Crit | Adopt | Symmetric query goes through the **scan-events catalog** (Step 1) + **`commit_key` added to occurrence rows** for exact Step-2 membership - no "latest snapshot per digest" over occurrences |
| C2-r2 | Crit | Adopt | **Newer-scan-wins**: `findings.last_scan_at`; partial-merge + reconcile **no-op when `committed_run_ts ≤ last_scan_at`** (out-of-order older run can't corrupt the cache) |
| H3-r2 | High | Adopt | **Commit-then-cache ordering**: append occurrences+images → commit (after per-item `_bulk` success) → merge findings + reconcile **last**; crash before merge self-heals |
| H4-r2 | High | Adopt | **`javv-inventory-runs-*` commit manifest** (`status=committed`); "running at T" reads only committed runs |
| H5-r2 | High | Adopt | **`expiry` immutable** after creation; expiry change = revoke+create-new (`revoked_at` is the only post-hoc stamp) |
| H6-r2 | High | Adopt | Drop the monotonic `seq` (no broker to back it); replay orders by **`(@timestamp, event_id)`**; CAS counter is post-MVP |
| M7-r2 | Med | Adopt | **Fencing `attempt_id`** on `system-reports`: heartbeat + `done` CAS on it, result path includes it - expired-then-reclaimed worker can't double-publish |
| M8-r2 | Med | Adopt | Sweep residual "latest occurrences/images snapshot ≤ T" → **catalog-first** (D28/FR-23/FLOW §9/ARCH §3) |
| M9-r2 | Med | Adopt | "now" query examples carry `cluster_id`+`scanner`+`present=true` (FLOW §8) |
| M10-r2 | Med | Adopt (locked) | **Presence ⟂ state** documented; grids filter on both; `present=false`+healthy=resolved-by-scan vs `state=stale`=scanner-silent |
| M11-r2 | Med | Adopt | **Historical all-clusters dashboards limited/unavailable in MVP** (per-cluster rewind fully supported); DESIGN-BRIEF + SPEC FR-23 |
| L12-r2 | Low | Adopt | D32 rewritten to the enriched audit schema (drops old `field/old/new` shape, no `seq`) |
| L13-r2 | Low | Adopt | Residual `first_seen`/`last_seen` → `*_at` swept (PLAN §5.1/§5.2/D21/D36, SPEC FR-10/FR-12) |

**Round-2 net new schema fields:** `findings.last_scan_at`; `javv-finding-occurrences.commit_key`; the new
**`javv-inventory-runs-<cluster_id>-*`** index (`inventory_run_id`, `started_at`, `completed_at`,
`expected_count`, `written_count`, `status`); `system-reports.attempt_id`; `system-audit-log` loses `seq`
(ordering by `(@timestamp, event_id)`).

**Still no new infrastructure.** One new (tiny) index for inventory manifests; everything else is ordering
discipline, scripted newer-scan-wins guards, and a fencing token - all on OpenSearch.

---

## 4. Round 3 - concurrency proof of the round-2 fixes (→ D40)

A mechanism-level concurrency review found that D39's newer-scan-wins guarded **per-doc** state, which
**cannot guard a create** - an out-of-order older run could re-create a finding a newer *clean* scan had
retired. Real bug. Fixed in **D40**, plus the supporting ordering/atomicity gaps. Locked choices:
**scanner-assigned `scan_order`** (monotonic via CronJob `Forbid`; *source since amended to backend-allocated - D45*) as the trusted ordering key (not
`@timestamp`); **extend `rebuild-state`** to also rebuild the scanner-presence cache.

| # | Sev | Verdict | Fix (→ D40) |
|---|-----|---------|-------------|
| Keystone (A/B-r3) | Crit | Adopt | New **`javv-scan-watermarks`** index (`max_committed_scan_order`, CAS at commit); **create AND update** guard against it - a stale out-of-order run skips the cache (history harmless) |
| C-r3 (ordering) | Crit | Adopt | Correctness ordering uses **`scan_order`** (then scanner-assigned; backend-allocated since D45), never `@timestamp`; on `scan-events` + `occurrences` rows; catalog sorts by `scan_order` |
| D-r3 (crash) | High | Adopt | `rebuild-state` extended to rebuild the **scanner-presence cache** (`present`/`last_scan_order`/`last_scan_at`/`last_scan_run_id`/`resolved_at`) from the catalog |
| E-r3 (reconcile vs triage) | High | Adopt | Reconcile `update_by_query` **retries scoped until zero conflicts** (not `conflicts=proceed`); scanner-owned fields only |
| G-r3 (decision edit) | High | Adopt | Revoke+create share **one `effective_at` + `operation_id`**; projection deferred until both land - no neither/both gap |
| H-r3 (audit causal order) | High | Adopt | Audit event records the finding's resulting **`revision`** (CAS); replay orders same-`(entity,field)` by `revision`, not `event_id` |
| F-r3 (inventory order) | Med | Adopt | Manifest gains **`inventory_order`**; "running at T" sorts by it; partial run → no committed manifest → fall back + banner |
| I-r3 (report orphans) | Med | Adopt | `attempt_id` in object path + metadata; bell reads only the `done` doc; **orphan-object TTL sweep** |
| Regr. (RMW claim) | Med | Adopt | D23/NFR-9 reworded: *history* has no race; *cache* is **guarded RMW** (watermark + scan_order + retry) |
| Regr. (wording/cost) | Low | Adopt | "one pass" → "ordered phases"; reconcile **cost bound** documented (routed/filtered/throttled, conflict counts observed) |

**Round-3 net new schema:** new **`javv-scan-watermarks`** index (`max_committed_scan_order`,
`max_committed_scan_at`); `scan_order` on `scan-events` + `occurrences`; `findings.last_scan_order`;
`javv-inventory-runs.inventory_order`; `system-decisions.effective_at` + `operation_id`;
`system-audit-log.revision`.

**Still broker-free.** One more tiny mutable index (the per-digest watermark); the rest is a trusted
monotonic `scan_order`, CAS guards, retry-to-zero-conflicts, and an extended rebuild job - all on OpenSearch.
