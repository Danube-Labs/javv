# M8c - M9-prep session reads (audit · provenance · inventory · cluster registry)

**Status:** tracked in #240 — live status on the GitHub issue/board (label `bolt`)

## Goal
Four thin, session-gated, read-only endpoints over data the backend already writes, so every M9
screen has a shipped data source. Falls out of the v5 design rulings (#237,
`handoff/docs/SCREENS.md` BLOCKED register). Pure reads — no new index (the D-5 registry is
one *document* in the existing `system-config`).

**Canonical refs:** [`PLAN §8 M8c`](../../../docs/engineering/PLAN.md) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (`system-audit-log`, `javv-scan-events`,
`javv-images`/`javv-inventory-runs`, `system-config` — read-only) · decisions D32 (audit shape),
D37/R-CATALOG (latest = via commit catalog), D39/D40 (`inventory_order`, committed-only), D41/D44
(provenance + `effective_config` stamps), D-5 ruling (cluster registry) ·
[`SCREENS`](../../../handoff/docs/SCREENS.md) §§1, 7, 10–12, 13.2/13.8

## Depends on
- Nothing unshipped. Must **check overlap with M8b** before building the inventory read — it is
  the `T=now` special case of M8b's point-in-time API; spec them to share the query layer, not
  collide.

## Deliverables
- `backend/src/backend/routers/audit.py` — `GET /api/v1/audit?cluster_id=…&entity_type=…&actor=…&cursor=…`:
  **plain session** (ruled 2026-07-07), cursor-paged (existing PIT machinery), ordered
  `(@timestamp, event_id)`, filters on `entity_type`/`action`/`actor`. Feeds the M9d Audit screen
  + Contributors activity feed.
- Scanner provenance read (extend `routers/scanners.py`): per `(cluster, scanner)` the **latest
  committed** scan-event's `scanner_version` / `scanner_db_version` / `scanner_db_built` +
  `effective_config` + last-N runs (counts, durations). Latest goes **through the commit catalog**
  (R-CATALOG), never latest-doc. Feeds Scanner status (M9d) + Settings→Scanning (M9e).
- `backend/src/backend/routers/images.py` — `GET /api/v1/images?cluster_id=…`: rows from the
  latest **complete** inventory run (`status=committed`, ordered by `inventory_order`); per-image
  repo/tag/namespace/replicas/first-last-seen. Clean images (zero findings) MUST appear. Feeds
  Running images (M9c) + the All-clusters Replicas column.
- Cluster registry: seed/read a `system-config` cluster-registry doc (`cluster_id` +
  `cluster_name`) + `GET /api/v1/clusters`; rename write (admin, `can_manage_settings`,
  journaled per D17). `cluster_name` is display-only — **never a query key** (hard constraint).
- RBAC/IDOR registry rows for every new route · `docs/API.md` rows (same PR) ·
  `docs/CONFIGURATION.md` if any knob appears (none expected).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- Every new read carries the explicit `cluster_id` filter through the tenancy chokepoint (test per route).
- Provenance read proven catalog-first: a newer *uncommitted* scan-event never surfaces (test).
- Inventory read returns only the latest **complete** run: a partial/running inventory never leaks (test).
- Audit read ordering `(@timestamp, event_id)` pinned by test; cursor 410/422 semantics match A-m1.

## Tests to write
- **Unit:** query-builders for all four reads (filters, sort, paging clauses).
- **Integration (real OpenSearch):** tenant isolation per route; catalog-first provenance;
  committed-only inventory; zero-findings image present; registry rename journaled + visible.
- **Golden fixtures:** none new — reuse existing scan-event/inventory fixtures.

## Out of scope (defer)
- Point-in-time (`T<now`) variants of these reads → M8b.
- Any write beyond the registry rename; notifications (M7 slice 3 / D-3); scan-scope session read (M9e / D-2).

## Updates
- **2026-07-08 · slice 2 (images + cluster registry)** — `GET /api/v1/images`
  (`routers/images.py`): the M8b overlap resolved as REUSE — `query/pit.py`'s
  `running_images_at` split into `latest_committed_inventory` + `images_for_inventory_run`
  (behavior unchanged; both gained an explicit `cluster_id` term on top of the per-cluster index
  name), the route composes them at `t=now`, and a parity test pins route rows == reader rows.
  `inventory: null` (no committed run — unknown) stays distinct from a committed-empty run.
  Cluster registry (`routers/clusters.py`, D-5): ONE `system-config` doc
  (`_id="cluster-registry"`, `value` = `{cluster_id → cluster_name}` inside the enabled:false
  blob — zero mapping churn, no new index); `GET /api/v1/clusters` = token-derived ids ∪
  registry, name defaults to the id; `PUT /api/v1/clusters/{cluster_id}/name` =
  `can_manage_settings`, journal-FIRST (D17/#188, `action=cluster_rename` with the old→new
  pair), and the registry write is a **seq_no-CAS guarded RMW** (D40 rule — two concurrent
  renames of different clusters both land; contended past 5 retries → 503, journaled, retry
  re-drives). RBAC/IDOR registry row added for the rename; `cluster_name` stays display-only.
- **2026-07-08 · slice 1 (audit + provenance)** — `GET /api/v1/audit` (`query/audit.py` +
  `routers/audit.py`): plain-session, fixed `(@timestamp, event_id)` pair-sort in ONE direction
  (`?order=`, desc default — replay stays asc in `query/human_at.py`), A-m1 machinery reused
  verbatim (`encode_cursor`/`decode_cursor` from `query/search.py`; a findings cursor is rejected
  as an audit cursor via the `s` field), per-principal PIT slots (A-m12). `GET
  /api/v1/scanners/provenance` extends `routers/scanners.py`: latest = terms-on-scanner +
  `top_hits` sorted on the exact `scan_order` long (a scan-events doc IS the commit marker, so
  scan-events reads ARE committed-only by construction — the DoD "uncommitted never surfaces"
  test plants ghost occurrence rows with a newer order and proves them invisible); last-N runs =
  composite over `(scanner, scan_run_id)` with sum/min/max sub-aggs (dates are epoch-ms < 2^53 —
  exact in metric aggs) + the run's exact order via `top_hits` `_source`, sorted in Python
  (**never a `max` agg on `scan_order`**, #257 — pinned by an adjacent-giant-orders test at
  ~1.75e18). No registry rows needed: both reads are non-mutating (the registry gates mutations);
  slice 2's rename registers under `can_manage_settings`.

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
