# M8a - Per-scan snapshot append (occurrences + inventory manifest)

**Status:** tracked in [#33](https://github.com/Danube-Labs/javv-poc/issues/33) — live status on the GitHub issue/board

## Goal
On every **successful** scan, append a full immutable snapshot to
`javv-finding-occurrences-<cluster_id>-*` (one row per current finding), each row stamped with
`commit_key` + `scan_order` and an idempotent `_id`; commit through the `javv-scan-events` catalog
*after* per-item `_bulk` success and guarded by the per-digest watermark CAS; and write the
`javv-inventory-runs-<cluster_id>-*` commit manifest (one per inventory run, `inventory_order`,
written last). **No close events** - an absent vuln is simply not in later snapshots.

**Canonical refs:** [`PLAN §8 M8a`](../../../docs/engineering/PLAN.md) ·
`SPEC` FR-5b (per-scan snapshots / point-in-time) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md)
(`javv-finding-occurrences-<cluster_id>-*` **[OWNS mapping + lifecycle]**,
`javv-inventory-runs-<cluster_id>-*` **[OWNS mapping + lifecycle]**,
`javv-scan-events` [reads as catalog, owned by M4], `javv-scan-watermarks` **[CONSUMES, owned by M3]**) ·
decisions D18 (idempotent `_id`), D37 (R-CATALOG / `commit_key`), D39 (catalog-first, inventory manifest,
commit-then-cache), D40 (`scan_order`/`inventory_order` ordering + watermark CAS).

## Depends on
- M3 (owns + **creates** `javv-scan-watermarks` and the watermark-CAS contract; supplies `scan_order`,
  `commit_key`, and the commit-then-cache ordering this append plugs into). M8a **consumes** the
  watermark - it does **not** create it (AUDIT **I2**).
- M4 (owns the `javv-scan-events` catalog doc that certifies a snapshot as committed).
- **rebuild-state extension only:** M5c owns the **base** `backend/jobs/rebuild_state.py` (the
  human/decision arm); this bolt extends it with the scanner-presence arm. The presence + watermark
  rebuild needs only this bolt's `occurrences` + the catalog.

## Deliverables
The actual files/modules this bolt creates - **in the layered tree, not here** (paths proposed):
- `backend/src/backend/snapshots/occurrences.py` - build the full per-scan snapshot: one immutable row per
  current finding, `_id = hash(scan_run_id + finding_key)` (idempotent, D18), stamped `scan_order`
  (D40) + `commit_key` (D39) + as-of-then `severity`/`cvss`/`fixable` (no `severity_rank` here, D38).
  One `scan_run_id` + one `@timestamp` per scan (atomic/complete).
- `backend/src/backend/snapshots/commit.py` - the commit sequence: append occurrence rows via `_bulk` →
  **inspect `response["errors"]` + per-item status** → write the `javv-scan-events` catalog doc
  **after** per-item success (D39 commit-then-cache); a **clean scan writes zero occurrence rows** but
  still commits the catalog doc.
- `backend/src/backend/snapshots/watermark_guard.py` - **consumes** `javv-scan-watermarks`: before committing,
  CAS-check / bump `max_committed_scan_order`; a run whose `scan_order < watermark` is **stale → skip**
  (history is immutable + idempotent + `scan_order`-ordered, so stale history is harmless). Uses M3's
  helper; adds no new watermark fields (AUDIT I2).
- `backend/src/backend/snapshots/inventory_runs.py` - write the `javv-inventory-runs` commit manifest
  (`_id = inventory_run_id`, `inventory_order` D40/F-r3, `expected_count`/`written_count`,
  `status ∈ {committed, partial, failed}`), **written last** after the `javv-images` bulk for the run
  succeeds; `status=committed` iff `written_count == expected_count`.
- **Owns** the `javv-finding-occurrences-<cluster_id>-*` template (`dynamic:false`, INDEX-MAP
  fields, 1 primary shard, monthly rollover) — registered in `backend/core/bootstrap.py`
  (+ `MAPPING_VERSION` bump, the versioned boot-time bootstrap from M1) — **plus lifecycle**: give
  the series write aliases (M4's `services/aliases.py`) and add it to `SERIES` in M4's
  `jobs/lifecycle.py` (rollover + per-cluster drop-whole-index retention — no ISM plugin; see the
  M4 README `## Updates` mechanism decision).
- **Owns** the `javv-inventory-runs-<cluster_id>-*` template (`dynamic:false`) + the same
  lifecycle registration. (Both resolve AUDIT **I1**.)
- **Extension to `backend/jobs/rebuild_state.py` — the scanner-presence arm (D40/D-r3, moved out of
  M3 on 2026-07-03).** The base job (human/decision projection arm) is created in **M5c**; this bolt
  **adds the scanner-presence arm**: reconstruct the `findings` presence fields (`present`,
  `last_scan_order`, `last_scan_at`, `last_scan_run_id`, `resolved_at`) **and** the
  `javv-scan-watermarks` from the append logs (catalog order, committed runs only) — landed here
  because it replays **`occurrences`** (this bolt's per-finding history), which don't exist earlier.
  **Reuses M3's merge field-allowlist + watermark/reconcile helpers** (single source — must not
  diverge, CORRECTNESS-CONTRACT §6/§9), and **never touches `javv-scan-orders`** (authoritative, not
  derived — D45). On-demand + after a detected crash; k8s CronJob `Forbid`. (Why not M3: M3 has no
  `occurrences`; its crash recovery is the stateless full re-scan every cycle, D30.)

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**
(each an automated test, not a promise):
- A successful scan appends one occurrence row per current finding, each with `scan_order` +
  `commit_key` + idempotent `_id`; re-running the same scan writes no duplicates (D18).
- The catalog (`scan-events`) doc is written **only after** per-item `_bulk` success; a partial bulk
  failure leaves the snapshot **uncommitted** (no catalog doc) so it is never read as "latest" (D39).
- A **clean scan** writes **zero** occurrence rows but still commits the catalog doc (so R-CATALOG
  reads it as clean, not as the prior snapshot).
- The watermark CAS rejects a stale (`scan_order < max_committed_scan_order`) run - it appends/commits
  no cache-visible state (M8a consumes M3's watermark; does not create it - I2).
- The inventory manifest is `_id = inventory_run_id`, carries `inventory_order`, is written **last**,
  and is `status=committed` **iff** `written_count == expected_count`; a partial run stays `partial`.
- Both created templates are `dynamic:false` and match INDEX-MAP exactly - fail on drift (I1/I9).
- **rebuild-state** reproduces an **identical** findings scanner-presence cache + watermarks from the
  append logs alone (`occurrences` + `scan-events`, catalog order, committed runs only) — a golden
  test, not an opinion (CORRECTNESS-CONTRACT §9); it **never** writes `javv-scan-orders` (D45).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** occurrence-row builder (`_id`, `commit_key`, `scan_order`, as-of-then severity, **no**
  `severity_rank`); inventory-manifest builder (`status` from `written_count == expected_count`);
  `_bulk`-error inspection helper (commit blocked on any per-item failure).
- **Integration (real OpenSearch):** full snapshot append round-trip; commit-then-cache **ordering**
  (catalog doc absent until `_bulk` per-item success); clean scan = zero occurrence rows + committed
  catalog doc; watermark CAS skips a stale run (consuming M3's index); inventory manifest written last,
  `partial` when a `javv-images` write is short.
- **Golden fixtures:** real scan envelope → expected occurrence rows + catalog doc + inventory
  manifest; a **clean rescan** → zero occurrence rows (the C1 zero-finding guard backing M8b);
  per-scanner, never merged.
- **Concurrency (required - the design relies on watermark serialization, AUDIT I10):** two successful
  commits for the same `(cluster, scanner, image_digest)` with **inverted `scan_order`** race the
  watermark CAS → the stale run commits no cache-visible state, the newer run wins, and **occurrence
  history is complete and immutable regardless of arrival order** (stale rows are harmless, never read
  as "latest" because the catalog orders by `scan_order`).

## Out of scope (defer)
- The point-in-time **read** API (forward R-CATALOG two-step + symmetric "images with CVE-Y at T") → M8b.
- Maintaining the `findings` current-state cache / reconcile-on-commit / `present=false` → M3.
- `javv-images` inventory **row** writes (M8a writes only the *manifest* certifying them) → the image
  ingest path; M8a depends on that bulk having landed before the manifest commits.

## Updates
- **2026-07-07 (slice 4 — BOLT COMPLETE)** — the AUDIT I10 keystone, whole-spine edition
  (`test_commit_race_keystone.py`): two full `ingest_envelope` runs for one digest with inverted
  `scan_order`, both deterministic inversion and true concurrency. Invariants regardless of
  arrival order: the stale run commits zero cache-visible state, the newer run owns presence,
  occurrence history is complete (both snapshots) + both catalog docs committed, the watermark
  lands on the newer order, and slice-3's rebuild writes exactly nothing over the post-race cache
  (incremental and reconstruction can't disagree). DoD sweep: all brief items covered by
  automated tests across slices 1–4; no new config knobs introduced by this bolt.
- **2026-07-07 (slice 3)** — rebuild-state scanner-presence arm landed (`rebuild_scanner_presence`
  alongside M5c's decision arm; `__main__` runs both). Derivation, not replay: per digest the
  latest committed run R defines presence, a finding's last appearance L freezes its presence
  fields, and `resolved_at` = the timestamp of the first committed run after L — provably
  identical to the incremental merge+reconcile output (golden test). Watermarks overwrite
  in-place (no gap for the NotFound/create race) with a fail-safe: an empty catalog never
  mass-drops watermarks. Found + filed **#257**: `max` metric aggs return doubles, so pre-D45
  `time.time_ns()`-scale scan_orders collapse (53-bit mantissa) — the arm uses exact composite
  keys; `scan_orders._max_committed` has the same latent bug.
- **2026-07-07 (slice 2)** — inventory manifest landed: `inventory_run_id := scan_run_id` (no
  second identity), new machine route `POST /api/v1/inventory-runs` called at cycle END (the
  scanner's `scan_all` gained an injectable `commit_fn`; best-effort — a failed commit just leaves
  the run uncertified). `written_count` is counted **server-side** from `javv-images` docs, never
  client-reported. Manifests are **immutable + idempotent**: a retry returns the original manifest
  with its original `inventory_order` (no partial→committed upgrade — runs are certified once).
  `inventory_order` = per-cluster counter in `javv-scan-orders` under the reserved key
  `__inventory__` (committed-manifest self-heal floor); INDEX-MAP notes it. `MAPPING_VERSION` → 12.
  **Scanner images need a republish** (entrypoint change) via the normal tag flow.
- **2026-07-07 (slice 1)** — occurrences append landed in the D39 spine: rows are built FROM
  `build_docs` output (identity single-sourced with the cache path, never re-derived), appended
  between the images bulk and the catalog commit doc. Spec addition: occurrences carry
  **`ingested_at`** (server-stamped) like scan-events/images — the lifecycle sweep ages by
  `max(@timestamp, ingested_at)` and the retention clock must not trust a client timestamp
  (task F m-4); INDEX-MAP updated in the same change. `MAPPING_VERSION` → 11.
- **2026-07-07 (kickoff)** — slice plan + the S2 wire note (cycle-end `POST /api/v1/inventory-runs`
  + scanner entrypoint change, `inventory_run_id := scan_run_id`) recorded on
  [#33](https://github.com/Danube-Labs/javv-poc/issues/33).

### 2026-10-26 — Frozen as history

The bolts M0 to M10 ended on 2026-10-09. This file is history now, not the spec of record. New work
follows one GitHub issue for each feature, with the plan and a spec file for each slice on the
issue. The timeline, the rulings that still apply and the open work are in the
[memory bank](../../memory-bank/README.md) (issue 1012).

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
