# M4 - Logs layer (scan-events) + retention

**Status:** tracked in [#26](https://github.com/Danube-Labs/javv/issues/26) — live status on the GitHub issue/board

## Goal
Own the `javv-scan-events-<cluster_id>-*` logs layer end-to-end: the immutable per-`(image,
scanner, scan)` append doc (carrying severity-count trends, the **backend-allocated** `scan_order`
ordering key (D45) and the `commit_key` 4-tuple, with an idempotent `_id`) — **already written by
M1/M3's ingest path; M4 takes ownership and asserts it**; add the missing lifecycle: **write
aliases (audit n-2)** + the **lifecycle CronJob** (rollover + per-cluster `retention_days`
drop-whole-index delete); and precompute the scanner-disagreement flags consumed downstream.

**Canonical refs:** [`PLAN §8 M4`](../../../docs/engineering/PLAN.md) ·
`SPEC` FR-5 (logs/trends), FR-11 (scanner disagreement), FR-19 (lifecycle/retention) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (`javv-scan-events-<cluster_id>-*`
**[OWNS mapping + lifecycle]**) · decisions D5a/D5b (disagreement), D18 (idempotent `_id`),
D26 (configurable rollover/retention), D38 (`scanner` is a field, not the index name),
D40 (`scan_order`, never `@timestamp`).

## Depends on
- M1 (index bootstrap + ingest skeleton - the request path this appends from). **The
  `javv-scan-events-*` / `javv-images-*` templates already live in `backend/core/bootstrap.py`
  (versioned, run at app startup) — evolve them THERE with a
  `MAPPING_VERSION` bump; don't create a parallel template-management path.**
- M3 (**backend-allocated** `scan_order` source (D45) - `backend/src/backend/services/scan_orders.py`
  behind `POST /api/v1/scan-runs` - and `commit_key` construction; both are already stamped onto the
  scan-events doc by `services/ingest.py`).

## Already landed (M1–M3) — M4 asserts + takes ownership, doesn't rebuild
- **Scan-events doc builder** — `backend/src/backend/services/ingest.py` (`build_docs` +
  `ingest_envelope`) already appends the doc per `(image, scanner, scan)`: idempotent
  `_id = hash(scan_run_id|image_digest|scanner)` (D18); `scan_order` (D40/D45) + the `commit_key`
  4-tuple (D37) stamped; **`effective_config`** carried (D44/FR-25, `enabled:false` mapping,
  `_source`-only); a **clean scan still commits a `total:0` doc** (D30). If M4 extracts it into its
  own module while taking ownership, behavior must be preserved bit-for-bit (it's the commit marker).
- **Counts + the `total = Σ buckets` invariant** — enforced at the edge by the `IngestCounts`
  validator in `models/envelope.py` (also checks `total == len(findings)`). No separate
  severity-counts module needed.
- **Index template** — the `javv-scan-events-*` mapping lives in `core/bootstrap.py`
  (`_SCAN_EVENTS_PROPERTIES`, `dynamic:false`, versioned `MAPPING_VERSION`); **evolve it there**
  (resolves AUDIT **I1** in place — no parallel template module). The disagreement fields
  (`disagree`, `trivy_count`/`grype_count`) are already mapped, just never populated.

## Deliverables
The actual files/modules this bolt creates - **in the layered tree, not here** (paths proposed,
matching the real `backend/src/backend/` layout):
- **Write aliases (audit n-2, ordering constraint: land before or with rollover).**
  `services/ingest.py` hardcodes the write targets as `javv-scan-events-<cluster>-000001` /
  `javv-images-<cluster>-000001` — correct only until rollover exists. Create a write alias per
  append series (`is_write_index`), point ingest at the alias, and let rollover retarget it.
- `backend/src/backend/jobs/lifecycle.py` - the **lifecycle CronJob** (daily, `Forbid`; sibling to
  `jobs/staleness.py`): per managed series alias, (1) **rollover** via `_rollover`+`conditions`
  (doc-count/age/size — OpenSearch evaluates the conditions server-side, the job pulls the
  trigger), then (2) **retention** — drop whole expired NON-write backing indices at the
  per-cluster `retention_days` (never `delete_by_query`, never the write index; age = newest
  `@timestamp`, not `creation_date`). Knobs are tier-③ runtime config in `system-config`
  (fleet-wide `lifecycle` + per-cluster `lifecycle:<cluster_id>` override, D26/M9e; interim CLI on
  the module). **Deliberately NOT the ISM plugin** — see `## Updates` 2026-07-03 (mechanism
  decision, settled with the operator).
- `backend/src/backend/services/disagreement.py` - precompute (a) per-finding **severity**
  disagreement flag and (b) per-image **count** disagreement (`trivy_count` / `grype_count` /
  `count_delta`); per-scanner, **never summed/merged** (D5a/D5b, FR-11). The mapped fields exist;
  this adds the compute. *(Computed here; consumed by M9b/M9d - cross-link N10.)*

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**
(each an automated test, not a promise):
- *(already green — keep as regression)* Every ingest appends exactly one scan-events doc per
  `(image, scanner, scan)`; re-ingesting the same scan is idempotent (same `_id` → no duplicate)
  (FR-5/D18).
- *(already green — keep as regression)* A **clean scan** writes a doc with all buckets `0` and
  `total:0` (so the commit catalog is complete).
- *(already green — keep as regression)* The `total = Σ severity buckets` invariant holds on every
  emitted doc (invariant-checked).
- *(already green — keep as regression)* Each doc carries the M3-supplied `scan_order` and the
  correct `commit_key` 4-tuple; ordering reads sort by `scan_order`, **never `@timestamp`** (D40).
- The index template matches INDEX-MAP exactly (`dynamic:false`, field types) - fails on drift
  (AUDIT I1/I9).
- **Ingest writes go through the write alias (n-2):** after a rollover, new docs land in the new
  backing index with no code change — proven by a rollover-then-ingest integration test.
- The lifecycle sweep rolls on the configured doc/age/size knobs; `retention_days` drops a whole expired
  index per `cluster_id` and never touches live ones (no `delete_by_query`, never the write index).
- Severity-disagreement and count-disagreement (`count_delta`) flags are computed per-scanner and never
  summed across scanners (FR-11/D5b).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** severity-bucket counter + `total = Σ buckets` invariant; `commit_key` construction (exact
  4-tuple hash); `disagreement.py` flag logic (severity mismatch; `count_delta` sign/magnitude;
  single-scanner = no flag); the scan-events doc builder body (assert emitted `_source` + `_id`).
- **Integration (real OpenSearch):** ingest → one scan-events doc appears per `(image, scanner, scan)`;
  re-ingest is idempotent (no dup `_id`); template applied is `dynamic:false` and matches INDEX-MAP;
  the lifecycle sweep rolls on the configured knob; `retention_days` drops a whole expired index and
  leaves current indices intact.
- **Golden fixtures:** Trivy + Grype envelopes for the same image → expected severity counts
  (scan-events), the `count_delta` pair (**images doc** — per INDEX-MAP, not scan-events) and both
  `disagree` flags - per-scanner, never merged; a **clean envelope** → a `total:0` doc.

## Out of scope (defer)
- Full per-scan finding snapshots + the commit-catalog *read* (R-CATALOG) → M8a/M8b. (M4 writes the
  catalog *doc*; M8a writes the occurrence rows it certifies and M8b reads it.)
- Trend/aggregation read endpoints over scan-events → M6.
- Surfacing disagreement flags in the UI → M9b/M9d (consumer; N10 cross-link).
- VEX export over the logs → M6.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates

- **2026-10-06: the backend runs these jobs itself (D47, issue 691):** the CronJobs this
  bolt names were never built. The backend starts each job on its cron schedule
  (`JAVV_JOB_<KIND>_CRON`, `jobs/scheduler.py`); `python -m backend.jobs.<name>` still runs one
  by hand. Issue 754.
- **2026-07-03 — pre-kickoff refresh against the M0–M3 reality.** M1/M3 already built the
  scan-events doc builder (idempotent `_id`, `scan_order`, `commit_key`, `effective_config`,
  clean-scan `total:0`), the counts invariant, and the index template — moved to a new *Already
  landed* section; M4 asserts + takes ownership instead of rebuilding. Fixed stale refs:
  `scan_order` is **backend-allocated** (D45, `POST /api/v1/scan-runs`), not scanner-assigned;
  paths now match the real `backend/src/backend/` layout; dropped the parallel
  `scan_events_template.py` deliverable (template evolves in `core/bootstrap.py`, AUDIT I1
  resolved in place). Added the **write-alias deliverable (audit n-2, #26 comment)** with its
  ordering constraint — aliases must land before/with rollover, or rollover strands the
  hardcoded `-000001` writes. Remaining net-new work: aliases, lifecycle job,
  disagreement compute.

- **2026-07-03 — mechanism decision (D8/D26 execution): lifecycle CronJob, not the ISM plugin**
  (settled with the operator at M4 kickoff; options laid out on #26). The D8 *contract* is
  unchanged — numbered backing indices behind a write alias, rollover on doc/age/size, retention =
  drop-whole-index, never `delete_by_query` — only the *executor* changed. Why: ISM's rollover
  action needs a per-index `plugins.index_state_management.rollover_alias` **setting** whose value
  is per-cluster; one shared template can't emit it, and the rollover-created next index wouldn't
  inherit it (fix = per-cluster template machinery + component-template restructure). ISM policy
  edits also don't live-apply (`change_policy` fan-out vs D26's UI-editable knobs), and per-cluster
  `retention_days` doesn't fit one static policy (a retention job would be needed anyway). The
  `_rollover`+`conditions` API is evaluated server-side by OpenSearch either way (the Curator
  model, battle-tested for multi-tenant lifecycles; Elastic's own data-stream escape hatch is
  closed to us — `op_type=create` breaks D18 idempotent re-ingest). Rollover precision = job
  cadence (daily), noise at monthly-rollover scale. PLAN D8 + INDEX-MAP notes updated in the same
  PR. Merged `core/ism.py` + `jobs/scan_events_retention.py` into one `jobs/lifecycle.py`.

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
