# JAVV - Index map & mappings (v4)

> **Living doc** (formerly `INDEX-MAP_v4.md` in `docs/engineering/V4/` — suffixes dropped 2026-07-16, #410).
> The v1–v3 evolution trail is frozen in `.deprecated/`; version markers are reserved for frozen generations.

> **The single source of truth for every OpenSearch index**: name, partition key, rollover/retention, and
> pinned mapping. Supersedes the scattered field tables in `PLAN` §5.x. Captured 2026-06-21. All indexes:
> `dynamic: false`. Enum/casing fields use the shared `lc` lowercase normalizer (verbatim in `_source`,
> normalized for aggs/filters - D16). Companion: `FLOW-EXAMPLE.md` (worked example). Diagrams: Mermaid.

## Summary - rolls over or not?

| Index | Shelf | Partition | Rollover | Retention |
|---|---|---|---|---|
| `javv-finding-occurrences-<cluster_id>-*` | append (history) | cluster | **yes** (lifecycle job: size/age/docs) | per-cluster drop-whole-index; **bounds how far back time-travel goes**; a cluster delete drops the cluster's series (issue 765) |
| `javv-scan-events-<cluster_id>-*` | append (trends + **commit catalog**) | cluster (scanner = field, D38) | **yes** | per-cluster drop-whole-index; a cluster delete drops the cluster's series (issue 765) |
| `javv-images-<cluster_id>-*` | append (inventory snapshots, per `inventory_run_id`) | cluster | **yes** | per-cluster drop-whole-index; a cluster delete drops the cluster's series (issue 765) |
| `javv-inventory-runs-<cluster_id>-*` | append (**inventory commit manifest**, 1/run) | cluster | **yes** | per-cluster drop-whole-index; a cluster delete drops the cluster's series (issue 765) |
| `javv-ingest-failures-<cluster_id>-*` | append (pushes rejected past the token check, issue 357) | cluster (scanner = field) | **yes** | per-cluster drop-whole-index (the same `retention_days`); a cluster delete drops the cluster's series (issue 765) |
| `system-audit-log-*` | append (human-state timeline + trail) | time | **yes** (fleet settings; rollover-ONLY in the sweep - task F m-6, #143) | **keep long** - the sweep NEVER retention-drops it (no expiry in MVP) |
| `javv-metrics-*` *(v1.1)* | append (downsample rollup) | cluster | **yes** | keep long (tiny) |
| `findings` | mutable current-state ("now" cache) | none (field `cluster_id`) | **no** | `stale`/`present` are **flags**; `delete_by_query` only after a **long** window (D37/M12), or for a deleted cluster (issue 765) |
| `javv-scan-watermarks` | mutable (per-digest commit pointer) | none (field `cluster_id`) | **no** | bounded by live fleet; prune with `findings`, and with a deleted cluster (issue 765) |
| `javv-scan-orders` | mutable (**authoritative** `scan_order` counter, D45) | none (field `cluster_id`) | **no** | **none, ever** — `#clusters × #scanners` docs; rebuild-state never touches it. The one exception is deleting a whole cluster (issue 765), which removes that cluster's counters with the rest of it |
| `system-decisions` | mutable (source of truth) | none | **no** | none (lifecycle-stamped; kept for time-travel/audit), except a deleted cluster's (issue 765) |
| `system-users` | mutable | none | **no** | none |
| `system-roles` | mutable (capability bundles) | none | **no** | none |
| `system-tokens` | mutable | none | **no** | manual revoke; a deleted cluster's are deleted (issue 765) |
| `system-sessions` | mutable | none | **no** | refused on lookup once `expires_at` passes; deleted by the session sweep (`jobs/session_sweep.py`) after `JAVV_SESSION_SWEEP_GRACE_HOURS` more (default 24h), revoked rows included |
| `system-config` | mutable | none | **no** | none, except a deleted cluster's per-cluster docs (issue 765) |
| `system-tags` | mutable *(planned — not yet created by bootstrap; the tags feature is post-MVP)* | none | **no** | none |
| `system-views` | mutable | none | **no** | none |
| `system-notifications` | mutable | none | **no** | No job deletes them by age or by read state. The user deletes one (`DELETE /api/v1/notifications/{id}`). The retirement sweep deletes a `cluster_retiring` notice when the cluster scans again or returns. A cluster delete deletes the notices of that cluster (issue 765). |
| `system-reports` | mutable | none | **no** | TTL sweep (`JAVV_EXPORT_TTL_HOURS`, default 24h); a deleted cluster's go with it, chunks included (issue 765) |
| `system-report-chunks` | mutable | none | **no** | TTL sweep with its parent report |
| `system-jobs` | mutable (one lease/status doc per background job kind: the three repair actions, issue 406, and since issue 691 the scheduled-only jobs too: four, and `cluster_retirement` since issue 765) | none | **no** | none — bounded at one doc per job kind |
| `restored-*` | copies a restore writes (**Settings › Data & OpenSearch**, `restored-<index>`), never read by JAVV | none | **no** | none: promoting or deleting a copy is a manual step; a cluster delete leaves the copies of that cluster's data in place |

**OpenSearch's `javv` role (issue 729) is drawn from this table:** `findings`, `javv-*` and `system-*` for everything JAVV reads and writes, and `restored-*`, the one pattern outside them, which it may only create and write (a restore). A new index outside these patterns needs the role changed with it (`docs/DEPLOYING.md` § An OpenSearch of your own, the compose file's `configs`).

**Time-travel horizon = per-cluster, "as far back as the data in OpenSearch allows"** - i.e. the oldest
retained `javv-finding-occurrences-<cluster_id>-*` / `javv-images-<cluster_id>-*` window, paired with
`system-audit-log` (kept long) for the human-state dimension. Each cluster's reach is set by its own
retention.

---

## Append shelf (time-partitioned · roll over · drop-whole-index)

### `javv-finding-occurrences-<cluster_id>-*` - full per-scan snapshots (point-in-time scanner facts)
1 immutable row per finding per scan. `_id = hash(scan_run_id + finding_key)` (idempotent). Settings: 1
primary shard, monthly rollover.
```
@timestamp        date          scan time (one value per scan_run_id); display only - not the ordering key (D40)
ingested_at       date          SERVER-stamped append time - the retention age basis (task F m-4, same rule as scan-events/images)
scan_run_id       keyword       the snapshot's run (valid only if a scan-events commit doc exists)
scan_order        long          backend-allocated (D45) monotonic per (cluster,scanner); ordering key (D40/C-r3)
commit_key        keyword       = scan-events commit_key; exact-tuple membership for the symmetric query (D39)
cluster_id        keyword       tenant + routing
scanner           keyword
image_digest      keyword       reconstruction identity (content-addressed)
namespaces        keyword[]    distinct namespaces the digest runs in — a digest can span several (D30 dedup); ns filter = array-contains
vuln_id           keyword       CVE pivot (= cve_id elsewhere)
package_name      keyword
package_version   keyword       (= findings.installed_version)
finding_key       keyword       per-row identity
severity          keyword/lc    as-of-then (verbatim in _source) - display/evidence only
severity_canonical keyword      D46 (#274): the full-word canonical query key, as-of-then
cvss              float         as-of-then
fixable           boolean
fixed_version     keyword
ptype             keyword       package type (M8d/B-1): "os" | ecosystem string; null on v3-era rows
schema_version    short
```
*(No `severity_rank` here - OE-5/D38; as-of-T severity sort uses a fixed order map
`crit>high>med>low>negligible>unknown`. No `status` field - absence in a later snapshot = resolved.)*
**Read via the catalog (R-CATALOG, D37/D40):** never `sort @timestamp desc, size 1` on occurrences - resolve
the **max-`scan_order`** committed `scan_run_id` from `javv-scan-events` first (order by `scan_order`, not
`@timestamp` - D40/C-r3), then read occurrences for **that exact run** (zero rows = clean image; a clean
rescan writes no rows here). **Symmetric "which images had CVE-Y at T" (D39):** Step 1 pages the
`javv-scan-events` catalog for the **max-`scan_order`** committed `commit_key` per digest ≤ T; Step 2 =
`commit_key IN {…} AND vuln_id=Y` here - **not** a composite "latest snapshot per digest" over occurrences.

### `javv-scan-events-<cluster_id>-*` - receipts + severity-count trends + **commit catalog**
1 immutable doc per (image, scanner, scan). **`scanner` is a field, not in the index name** (D38/M15).
**Authoritative commit catalog** (F1/R-CATALOG, D37): an occurrences snapshot is "latest" only if a matching
doc exists for its full `commit_key` 4-tuple; the point-in-time read resolves the latest committed
`scan_run_id` **here first**, then reads occurrences for that run. A **clean scan still writes a doc**
(`total:0`). `_id = hash(scan_run_id + image_digest + scanner)`. 1 primary shard, monthly rollover.
```
@timestamp        date          display only - NOT the ordering key (D40)
ingested_at       date          SERVER-stamped append time - the retention age basis (task F m-4, #143)
scan_run_id       keyword
scan_order        long          backend-allocated (D45) monotonic per (cluster,scanner); the catalog ordering key (D40/C-r3)
commit_key        keyword       hash(cluster_id + scanner + image_digest + scan_run_id) - 4-tuple commit identity (D37/H3); READ RULE: a rollover-straddling retry duplicates docs across backing indices - count/trend reads dedup by commit_key (cardinality), never raw doc counts (task B, #139)
cluster_id        keyword
scanner           keyword
scanner_version   keyword       self-reported binary version (D41); Trivy Trivy.Version / Grype descriptor.version
scanner_db_version keyword      vuln-DB schema version (D41); Grype descriptor.db.status.schemaVersion / Trivy per-cycle `trivy version` call (#96)
scanner_db_built  date          vuln-DB build time (D41); Grype descriptor.db.status.built / Trivy VulnerabilityDB.UpdatedAt (#96)
effective_config  object (enabled:false)  what the cycle ran with (D44/FR-25): {tuning: per-scanner flags, scope: applied D43 ScanScope} - _source-only (not indexed/aggregatable, display+audit read it off the doc); scan-events ONLY, not findings/images
namespaces        keyword[]    distinct namespaces the digest runs in — a digest can span several (D30 dedup); ns filter = array-contains
image_repo        keyword
image_digest      keyword
tag               keyword
app               keyword
crit high med low negligible unknown total fixable   integer   (total = sum of buckets - invariant-checked; clean scan = all 0)
schema_version    short
```

### `javv-images-<cluster_id>-*` - inventory snapshots ("running images")
1 immutable doc per (image, scan); each cycle shares one **`inventory_run_id`**, certified complete by a
manifest in `javv-inventory-runs-*` (below). **"Running images now / at T" = the images of the latest
`status=committed` `inventory_run_id` ≤ T** (R-CATALOG, D37/D39) - *not* latest-doc-per-digest, and never an
uncommitted/partial run; an undeployed image is absent from the next committed run and disappears at that run
(no sweep). `_id = hash(scan_run_id + image_digest)`. 1 primary shard, monthly rollover.
```
@timestamp        date
ingested_at       date          SERVER-stamped append time - the retention age basis (task F m-4, #143)
scan_run_id       keyword
inventory_run_id  keyword       the complete inventory run; "running now" = images in the latest one (D37/H5)
cluster_id        keyword
image_digest      keyword
image_repo        keyword
tag               keyword
namespaces        keyword[]    distinct namespaces the digest runs in — a digest can span several (D30 dedup); ns filter = array-contains
app               keyword
scanners          keyword[]     scanners that reported this image this run
crit high med low negligible unknown total fixable   integer
trivy_count grype_count count_delta                  integer   count-disagreement pair (D5b)
replicas          integer       observed at scan time
schema_version    short
```

### `javv-inventory-runs-<cluster_id>-*` - inventory commit manifest (D39/H4-r2)
1 immutable doc per inventory run - the **catalog for inventory completeness** (the images analog of
scan-events). Written **last**, after the `javv-images` bulk for that run succeeds. "Running images now / at T"
reads only `status=committed` runs **ordered by `inventory_order`** (not `@timestamp` - D40/F-r3), so a partial
run is never mistaken for the live inventory (it falls back to the prior committed run + the staleness banner).
A committed run with zero images is read like any other: it means the cluster runs nothing in scope. A run is partial when an image that **was scanned** did not land (a dead-lettered
push). An image the scanner could not scan at all is not expected, so it does not make the run partial: it is
absent from that run's inventory. The exception is a cycle in which no image scanned: the scanner sends the
discovered count, the run is partial, and the last good inventory keeps answering. `_id = inventory_run_id`. 1 primary shard, monthly rollover.
```
@timestamp        date          run completion time (display)
inventory_run_id  keyword       = the run's id
inventory_order   long          backend-allocated (D45 basis) monotonic per cluster; the "running at T" ordering key (D40/F-r3)
cluster_id        keyword       tenant + routing
started_at        date
completed_at      date
expected_count    integer       images the scanner scanned this run (one it could not scan is left out; all discovered when none scanned, issue 633)
written_count     integer       image docs successfully appended (== expected_count when committed)
status            keyword        committed | partial | failed   (only committed is read)
schema_version    short
```

### `javv-ingest-failures-<cluster_id>-*` - failed-ingest records (issue 357)
1 immutable doc per push the ingest route **rejected after the token check** — the data behind
scanner status's failed-ingests table (When · Scanner · Image · Stage · Error). The 401 and the
pre-token 429 write **nothing**: a write per anonymous request would let a sender choose our write
volume; past the token, the per-token rate limit bounds it. **Routed on the token's
`cluster_id`/`scanner`, never the payload's** (a `scope_mismatch` envelope's self-declared cluster is
the untrusted value). Recording never changes the response: a failed write is logged, counted in
`javv_ingest_failures_unrecorded_total`, and swallowed (`services/ingest_failures.py`). JAVV sees only its own refusal, so there is **no status/retry
field** — retries and dead-lettering stay scanner-side (A-7/D-4). `_id = failure_id`. 1 primary
shard, monthly rollover, retention = the lifecycle's per-cluster `retention_days` (drop-whole-index).
```
@timestamp        date          server time of the rejection
ingested_at       date          same server stamp - the retention age basis (task F m-4)
failure_id        keyword       uuid4 hex; = _id; the unique tiebreak for the newest-first paged read;
                                also on the route's `ingest rejected` warning (row ↔ log-line join)
cluster_id        keyword       the TOKEN's cluster (tenant + routing)
scanner           keyword       the TOKEN's scanner - a field, never in the index name (D38)
stage             keyword       receive | decode | validate | authorize | store
reason            keyword       the javv_ingest_rejected_total label: too_large | bad_gzip | bad_json |
                                invalid_envelope | unallocated_order | clock_skew | scope_mismatch |
                                storage_error
status            short         the HTTP status the scanner was sent
error             keyword       index:false, doc_values:false - display only. Server-authored: the
                                response text, plus the first validation error's location + type
                                (never the rejected input); control chars stripped, ≤ 512 chars
image_ref         keyword       ignore_above 512; best-effort, null until the body parsed as an
                                object; sender-supplied, so capped + stripped like `error`
schema_version    short
```

### `system-audit-log-*` - structured human-state timeline + trail (SND-2; required for time-travel)
1 immutable, **structured** row per field change (not prose). Source for reconstructing human state at any T
(replay ≤ T in deterministic order, latest-entry-per-field wins) and for Contributors/compliance. Append-only
via a **create-only role** (SEC-1). Time-rollover, **kept long**. Schema enriched for faithful replay (D38/H8).
```
@timestamp        date
event_id          keyword       unique per event; tiebreak for UNRELATED events - same-(entity,field) order by `revision` (D40/H-r3); no monotonic counter (D39/H6-r2)
actor             keyword       user_id (or "system")
action            keyword       enum: assign|note|acknowledge|risk_accept|not_affected|resolve|reopen|
                                login|logout|pwd_change|role_change|token_mint|token_revoke|decision_revoke|...
entity_type       keyword       finding|decision|user|token|session|... (what kind of thing changed)
entity_id         keyword       the entity's id (finding_key for findings, decision_id for decisions, ...)
finding_key       keyword       convenience target for finding actions (= entity_id when entity_type=finding)
target_ids        keyword[]     bulk actions: the FROZEN set of affected ids (not a selector, not a count - H8)
target_selector   object        {cve_id, scope} kept for provenance; replay uses target_ids
result_hash       keyword       hash of the affected-set (audit integrity for very large bulk actions)
result_count      integer       size of the affected set
cluster_id        keyword
field             keyword       e.g. state|assignee|notes
field_type        keyword       scalar|text|json - how to interpret old/new value
revision          long          the finding's resulting version (CAS write); replay orders same-(entity,field) by this, not event_id (D40/H-r3)
old_value         keyword       scalar/text values
new_value         keyword
old_value_json    object        non-scalar before-image (when field_type=json)
new_value_json    object        non-scalar after-image
decision_id       keyword       links to system-decisions when relevant
schema_version    short
```

### `javv-metrics-*` *(v1.1, deferred)* - downsample rollup (cheap multi-year trends, lossy counts).

---

## Mutable shelf (single index · no rollover)

### `findings` - current-state "now" cache (the fast grid)
1 doc per `finding_key`. Scanner fields **partial-merged** each scan (a partial-doc `_update` of scanner
fields only - merge semantics leave human fields untouched; **no preserve script**). Human fields are a
**projected cache** of `system-decisions` + `system-audit-log`. **Reconcile-on-commit** (D37/C2): a committed
scan for `(digest, scanner)` runs `update_by_query` setting `present=false`/`resolved_at` on findings whose
`last_scan_order < the new run's scan_order` (D40 newer-scan-wins — not `last_scan_run_id` equality), so
resolved CVEs leave the "now" grid immediately. **`stale`/`present` are
flags, not deletes** (D37/M12): `delete_by_query` runs only after a **long** retention window (or once gone
from inventory that long), never on the freshness timer. Both create and update are **newer-scan-wins**: a run
skips the cache when its `scan_order ≤ doc.last_scan_order` **or `< the per-digest `javv-scan-watermarks`
watermark** (D40/C-r3 - the watermark also guards *creates*, which per-doc state can't), runs **after** the
commit doc lands (D39/H3-r2), and the reconcile `update_by_query` **retries scoped until zero conflicts**
(D40/E-r3). A crash before the merge self-heals via the scanner-cache rebuild (D40/D-r3).
**Presence ⟂ state (D39/M10-r2):** `present`/`resolved_at` (scan-presence) is orthogonal to `state` (human
lifecycle + system `stale`) - `present=true` = on the latest committed scan; `present=false` + healthy scanner
= resolved-by-scan (fixed); `state=stale` = scanner silent. Every "now" query **must** filter on both
(`present=true` + the screen's `state`) and carry `cluster_id`+`scanner`. Settings: `lc` normalizer; start at 1
primary shard (route/shard by `cluster_id` only if it ever grows large - it scales with live fleet, not time).
**Namespace is multi-valued (D30):** digest-dedup collapses N pods of one image into one scan, but those pods
can live in different namespaces - so `namespaces` is a `keyword[]` (matching the schema-v2 scanner envelope),
not a scalar. `finding_key` excludes it (a vuln is a property of the image, not the namespace). A namespace
filter is an array-contains `terms` match, so the **same** finding surfaces under every namespace it runs in;
per-namespace finding counts therefore **overlap** (only the all-namespaces total is deduped). Resolves the
`namespaces[]` vs singular `namespace` mismatch (project audit finding #1).
```
finding_key       keyword       _id = hash(cluster_id+image_digest+scanner+cve_id+package_name+installed_version)
cluster_id        keyword
scanner           keyword
image_digest      keyword
image_repo        keyword
tag               keyword
namespaces        keyword[]    distinct namespaces the digest runs in — a digest can span several (D30 dedup); ns filter = array-contains
app               keyword
cve_id            keyword
package_name      keyword
installed_version keyword
severity          keyword/lc    verbatim in _source (D16) - display/evidence only
severity_canonical keyword      D46 (#274): the full-word canonical QUERY key (critical|high|medium|low|negligible|unknown) - filters+facets target this
severity_rank     byte          5..0 - sort/range key (findings only - OE-5)
cvss              float
fixable           boolean
fixed_version     keyword
epss              float          grype only (null for trivy)
kev               boolean        grype only
ptype             keyword        package type (M8d/B-1): "os" | verbatim-lowercase ecosystem; null until a v4 scan observes (D30 heals)
disagree          boolean        precomputed severity disagreement (D5a)
first_seen_at     date           full precision (not day-grain - D37/M13)
sla_clock_at      date           materialized D21 group clock (issue 363): min first_seen_at across the (cve_id, image_digest) group, cross-scanner, PRESENT rows - derived family like `disagree`, owned by services.sla_clock (recomputed per digest at commit; rebuild-state = backfill/heal). The overdue FILTER ranges on it against live-policy cutoffs; the VERDICT stays read-time (never stored - FR-10 instantness)
last_seen_at      date           full precision; freshness/stale timer reads this
last_scan_run_id  keyword        the run that last reported this finding (D37/C2)
last_scan_order   long           newer-scan-wins guard key: create/update no-op if scan_order ≤ this OR < digest watermark (D40/C-r3)
last_scan_at      date           committed run @timestamp (display)
present           boolean        false once a later committed scan for its (digest,scanner) omits it (D37/C2)
resolved_at       date           when reconcile-on-commit flipped present→false (nullable)
state             keyword        human cache: open|acknowledged|not_affected|risk_accepted|resolved|stale
vex_justification keyword        CISA five (required iff not_affected)
assignee          keyword
notes             text
pre_stale_status  keyword        prior state, for revert on re-push or once confirmed gone; while stale, decision projection keeps it current (issue 705)
state_decision_id keyword        projection provenance (M5c): the decision that set `state`; null = human/direct (direct action outranks rules); expiry-refresh finds projected findings by it
schema_version    short
```

### `javv-scan-watermarks` - per-digest committed-scan watermark (D40/keystone)
The serialization point that makes newer-scan-wins safe **including creates** (per-doc `findings` state can't
guard a finding that doesn't exist yet). 1 doc per `(cluster, scanner, image_digest)`. At commit the backend
**CAS-bumps** `max_committed_scan_order = max(current, my_scan_order)`; if `my_scan_order < max_committed_scan_order`
the run is stale → **skip all cache writes** (history is immutable/idempotent and ordered by `scan_order`, so
stale history is harmless). `_id = hash(cluster_id + scanner + image_digest)`. Mutable, no rollover; bounded by
live fleet (prune alongside `findings`).
```
cluster_id              keyword   tenant filter
scanner                 keyword
image_digest            keyword
max_committed_scan_order long     the watermark - guards both create and update of findings (D40/C-r3)
max_committed_scan_at    date     committed run @timestamp (display)
schema_version          short
```

### `javv-scan-orders` - the authoritative `scan_order` allocation counter (D45)
1 doc per `(cluster_id, scanner)` (`_id = <cluster_id>:<scanner>`) - the backend CAS-increments
`max_allocated_scan_order` (`_seq_no`/`_primary_term` guard) when the scanner `POST`s
`/api/v1/scan-runs` at cycle start, and returns the new order (pure Lamport sequence; never a clock,
never regresses; gaps from crashed cycles are harmless). **Separate from the watermarks on purpose:**
watermarks are *derived* (rebuild-state wipes + recomputes them from the catalog); this counter is
*authoritative* - an allocated-but-uncommitted order is invisible to the catalog, so a naive rebuild
could re-issue it. **rebuild-state never touches this index**; the only self-heal is forward
(`max(committed) > counter` → bump up, never down). Mutable, no rollover, **no retention ever** (the one exception: deleting a whole cluster, issue 765, removes its counters);
**not in a snapshot today:** `DURABILITY_INDICES` (`admin/snapshot.py`) is `findings,javv-images-*,system-*,-system-sessions`. The forward-only self-heal keeps a restore safe for committed scans (issue 664). **Also holds the per-cluster `inventory_order` counter**
(M8a slice 2/#33): one doc per cluster under the reserved scanner key `__inventory__`
(`_id = <cluster_id>:__inventory__`, same shape/CAS; self-heal floor = max committed
`inventory_order` in `javv-inventory-runs`, allocated at cycle-END commit).
```
cluster_id               keyword   tenant filter
scanner                  keyword
max_allocated_scan_order long      the counter - strictly increasing per (cluster_id, scanner)
allocated_at             date      last allocation time (display/ops)
schema_version           short
```

### `system-decisions` - scoped human decisions (source of truth; lifecycle-stamped for time-travel)
1 doc per decision. **Immutable except `revoked_at`** (D39/H5-r2) - a scope/justification **or `expiry`** edit
is **revoke + create-new**, never an in-place rewrite (mutating `expiry` would rewrite past-T reconstruction).
`revoked_at` is the only post-hoc stamp and is forward-correct, so the role is not "create-only" but allows
only that one update, and time-travel stays correct. "Active at T" = `created_at ≤ T AND (revoked_at is null OR
revoked_at > T) AND (expiry is null OR expiry > T)`.
```
decision_id       keyword
type              keyword       risk_accepted|ignore_rule|not_affected
cve_id            keyword
scope             object        { namespaces: keyword[], images: keyword[] }  (empty = cluster-wide)
apply_both_scanners boolean     semantics pinned (D22)
scanner           keyword       required iff NOT apply-both — which scanner a scanner-specific decision is for (M5c/D22)
vex_justification keyword
justification     text
created_by        keyword       the accepting user (gated by can_accept_audit_final - SEC-2)
created_at        date          = effective_at for a create
expiry            date          nullable; IMMUTABLE after creation - change = revoke+create-new (D39/H5-r2)
revoked_at        date          nullable; the only post-hoc stamp (revocation is a forward event → time-travelable)
effective_at      date          edit (revoke+create) shares ONE effective_at: revoked_at(old)=created_at(new)=effective_at (D40/G-r3)
operation_id      keyword       ties the revoke+create pair; projection runs only after both land (D40/G-r3)
cluster_id        keyword
schema_version    short
```

### `system-users` / `system-roles` - identity + capability RBAC
```
# system-users
username          keyword
password_hash     keyword       argon2id (never logged); NULL for external (ldap|oidc) users
role              keyword       → resolves to a capability bundle in system-roles
capabilities      keyword[]     effective capabilities (denormalized for fast checks)
must_change       boolean       server-enforced first-login password change (SEC-6)
disabled          boolean
auth_source       keyword       local|ldap|oidc — the IdP seam (#27 kickoff design): external IdPs
                                replace credential verification/provisioning only, never sessions
external_id       keyword       IdP subject/DN; NULL for local users
created_at        date
# system-roles  (capability bundles - SEC-9)
role              keyword       e.g. viewer|triager|security_lead|admin
capabilities      keyword[]     e.g. can_triage, can_accept_audit_final, can_export, can_edit_dashboards,
                                can_manage_users, can_manage_retention, can_restore_snapshot,
                                can_drop_index, can_rebuild_state
```
*(Capability `can_accept_audit_final` gates risk-accept - SEC-2. Admin always holds all. Destructive caps
Admin-only + journaled.)*

### `system-tokens` - per-(cluster,scanner) ingest tokens (lifecycle + revocable)
```
token_hash        keyword       peppered SHA-256 of a 256-bit random token (compare_digest) - D38/M14
cluster_id        keyword       payload must match token scope (authz binding, SEC-3)
scanner           keyword       payload must match token scope (authz binding, SEC-3)
scope             keyword       "push:findings"
created_by        keyword
created_at        date
expiry            date          nullable
disabled          boolean
last_ingest_at    date          scanner-down guard
```

### `system-sessions` - server-side sessions (Auth & Session bolt - SEC-5)
```
session_id        keyword       httpOnly+Secure+SameSite cookie value (hashed)
user_id           keyword
created_at        date
expires_at        date          TTL
revoked           boolean       revoke-on-role-change / logout-all
```

### `system-config` · `system-tags` (planned) · `system-views` · `system-notifications` · `system-reports` · `system-report-chunks` · `system-jobs`
```
# system-config        : SLA policy, rollover/retention/staleness settings, snapshot-repo ref (creds in OS keystore, not here), scan_scope:<cluster_id> (D43), cluster-registry (D-5/M8c),
#                        cluster-retirement:<cluster_id> (issue 765: one per cluster ever retired, {retired_at, by, mode: manual|auto, returned_at}; un-retire stamps returned_at and keeps the doc, so the sweep counts silence from the return)
#                        cluster-delete:<cluster_id> (issue 778: {started_at, by, finished_at, rechecked_at}, written by a cluster delete before its first step and stamped finished_at after its last; while unfinished the cluster cannot be un-retired and the listing says delete_started. Kept as a tombstone: the retirement sweep re-runs the delete's data steps for a cluster nothing names any more, journaling a `cluster_delete_recheck` audit row with the counts before it deletes, and drops it after a second clean pass, or at once when the cluster is onboarded again. Issue 833: a token minted for the id drops a finished tombstone, a mint for an unfinished one answers 409, and a new delete of the id replaces a finished tombstone with its own marker)
#                        retirement-warned:<cluster_id> (issue 765: {silent_since} of the silence the settings admins were told about, so a dismissed notice, or a settings change that moves the dates, sends nothing again; a new silence sends again; deleted with the cluster's notices when it scans again or a return from retirement starts a new silence (a settings change keeps both), kept while it is retired, deleted with the cluster)
#                        doc shape: { key (= _id), value (opaque, not indexed), updated_at, updated_by }; the per-cluster docs of issues 765/778 also carry cluster_id, unmapped (_source only)
# system-tags          : { tag, kind: team|app|org, ... }   (planned: not created by bootstrap yet)
# system-views         : { view_id, name, description, preset, workbench, owner, created_at,
#                          updated_at, schema_version }
#                          (schema v2, M9f slice 4: `workbench` = the findings-table capture —
#                          {columns, dense, sort, order, window_days} — cluster-agnostic by shape:
#                          no cluster_id / absolute t is representable; opaque in _source like
#                          `preset`, never queried by innards. v1 docs simply lack the key.)
#                          (M8e/C-6 ruling, 2026-07-07: renamed from the pre-ruling `system-saved-views`
#                          per-user sketch — views are visible to ALL authenticated users; mutations are
#                          owner-or-admin. `preset` = the SearchFilters mirror, {enabled:false} in _source
#                          — presets are fetched by _id/list, never queried by their innards; card counts
#                          come from /findings/facets at render time, never stored.)
# system-notifications : { notification_id, user_id, type: sla_breach|assignment|report_ready|cluster_retiring, ref, cluster_id, created_at, read }
#                        cluster_retiring (issue 765): one per settings admin when a cluster enters its retirement warning window; ref = its retires_at; id derived from (cluster, user, silent_since)
# system-reports       : { report_id, kind: export|bulk_triage, status: pending|running|done|failed,
#                          params, requested_by, run_mode: now|offpeak, scheduled_for, cluster_id,
#                          bytes, chunk_count, expires_at, heartbeat_at, lease_expires_at, retry_count,
#                          attempt_id, worker, started_at, finished_at, as_of_t (export at a past T) }   job claim = optimistic concurrency (pending→running via
#                          seq_no/primary_term CAS) so replicas/retries can't double-run (D38/M17);
#                          attempt_id = fencing token - heartbeat + done CAS on it, so an expired-then-
#                          reclaimed slow worker can't double-publish (the bell reads only the done doc).
# system-report-chunks  : { report_id, attempt_id, seq, data }   the result BLOB, chunked (~5 MiB text
#                          slices) so a large export never exceeds http.max_content_length / bloats heap;
#                          `data` is an {enabled:false} un-indexed _source field (never analysed). Written
#                          under the drain's attempt_id; only the `done` attempt_id's chunks are canonical.
# system-jobs           : { kind: rebuild_state|staleness_sweep|lifecycle_sweep|findings_cleanup|
#                          cluster_retirement|session_sweep|report_sweep|report_drain
#                          (jobs/registry.py), status:
#                          idle|running|done|failed, requested_by, attempt_id, started_at,
#                          finished_at, heartbeat_at, result {enabled:false}, error }   the repair-
#                          actions surface (issue 406): _id = kind, so the index is bounded at #kinds
#                          docs by construction. Claim = seq_no CAS to running (a racing trigger 409s);
#                          attempt_id fences heartbeat/finalize like reports; a running doc whose
#                          heartbeat outlives JAVV_REPORT_LEASE_TTL_SECONDS reads as stale/reclaimable.
# -- M7 STORAGE DECISION (2026-07-07, #32): result blobs live IN OpenSearch (chunked), NOT an object
#    store. Fits the single-store / broker-free hard constraint; download via a backend endpoint
#    (`GET /api/v1/reports/{id}/download`) gated by the tenant read path + `expires_at` (410 once
#    expired) + a short-lived signed download token -- this SUPERSEDES SEC-10's S3/MinIO + presigned-URL
#    model for M7 (the token satisfies SEC-10's per-tenant + time-limited intent without object-store
#    creds). Retention = a `delete_by_query expires_at < now` sweep on these SMALL bounded ops indices
#    (the "drop whole indices, never delete_by_query" day-one rule targets the huge occurrence/images
#    time-series, not these). Orphan chunks (non-`done` attempt_id) swept alongside (D40/I-r3).
```

---

## Notes
- **Naming:** rollover (the M4 lifecycle sweep, a backend job on `JAVV_JOB_LIFECYCLE_SWEEP_CRON`,
  `_rollover`+`conditions` — not the ISM plugin; see
  PLAN D8) creates numbered backing indices behind a write-alias; the `-*` denotes the
  rolled series. Route append series on **immutable `cluster_id`**, never `cluster_name`.
- **A mutable index can be an alias.** After a breaking change, the name (for example `findings`) is
  an alias of a copy with the new mapping (`findings-v19`). Bootstrap reads the mapping of the index
  behind the alias. The steps are in `UPGRADES.md`, "A breaking change" (issue 261).
- **Every read carries a `cluster_id` filter** via one tenant-scoping repository helper (SEC-4) - including
  both steps of the point-in-time symmetric query and the export drain. **MVP tenant model (D38/H9):** all
  clusters are visible to any authenticated user - `cluster_id` is a **data filter applied on every
  read/agg/export** (guards accidental cross-cluster bleed), **not** a per-user auth boundary; per-user/role
  `allowed_cluster_ids` grants are **post-MVP** (would slot onto `system-users`/`system-roles`).
- **Snapshot/restore** (NFR-6): D36 plans two schedules, the small audit/decisions indices more often than
  the bulky append ones (DR RPO note). Only the first exists today: a snapshot (on demand, from
  **Settings › Data & OpenSearch**) holds `findings`, `javv-images-*` and `system-*`. The append series,
  `javv-scan-orders`, `javv-scan-watermarks` and `system-sessions` are in no snapshot: sign-out only
  sets `revoked`, so a restored copy would revive ended sessions (issue 892). Issue 664 holds the history of this
  choice and the open questions.
