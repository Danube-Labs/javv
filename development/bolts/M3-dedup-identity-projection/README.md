# M3 - Dedup/identity + staleness + projection

**Status:** tracked in [#25](https://github.com/Danube-Labs/javv/issues/25) — live status on the GitHub issue/board

## Goal
Highest-risk bolt. Turn idempotent appends into correct current-state: partial-doc merge
(scanner fields only), backend-allocated scan_order (D45) + per-digest watermark CAS guarding BOTH
create and update, commit-then-cache ordering, reconcile-on-commit, projection-on-new,
and two-timer staleness. (The **rebuild-state** self-heal job is **deferred out of M3** — its data
sources don't exist here; built later split across **M5c** (human/decision arm) + **M8a**
(scanner-presence arm). See Updates.)

**Canonical refs:** [`PLAN §8 M3`](../../../docs/engineering/PLAN.md) · `SPEC` (FRs for M3) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (javv-scan-watermarks **[OWNS]**, javv-findings,
javv-finding-occurrences, javv-scan-events) · decisions D16, D19, D20, D31, D37–D40.

## Depends on
- M1 (index bootstrap + ingest skeleton).

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `backend/src/backend/ingest/merge.py` — partial-doc merge; scanner-field allowlist, human/triage fields untouched (D31, D16).
- `backend/src/backend/ingest/scan_order.py` + `POST /api/v1/scan-runs` — **backend-allocated** monotonic `scan_order` (**D45** — amends D40's source; never a clock): per-`(cluster_id, scanner)` counter doc CAS in **`javv-scan-orders`** (own tiny mutable index — authoritative, rebuild never touches it; separate from the *derived* watermarks), token-scoped, fail-closed scanner fetch at cycle start (replaces the scanner's `time.time_ns()` mint in `scanner/envelope.py new_scan_run`). **Creates + owns `javv-scan-orders`** (bootstrap template + MAPPING_VERSION bump, same as the watermarks index).
- `backend/src/backend/ingest/watermark.py` — per-`(cluster,scanner,digest)` `max_committed_scan_order` CAS; guards create AND update (D40). **Creates + owns `javv-scan-watermarks`** (resolves the M3/M8a ownership overlap).
- `backend/src/backend/ingest/commit.py` — commit-then-cache ordering: append occurrences+images → commit scan-events → merge findings last (D39).
- `backend/src/backend/ingest/reconcile.py` — reconcile-on-commit: flip `present=false` on findings the new run omits; cache-only, history stays tombstone-free (D37/D38).
- `backend/src/backend/projection/engine.py` — projection-on-new-only (D19).
- `backend/jobs/staleness.py` — two-timer staleness (D20).
- ~~`backend/jobs/rebuild_state.py` — rebuild-state self-heal~~ → **deferred out of M3.** Base job (human/decision arm) created in **M5c** (needs `system-decisions`/`system-audit-log`); scanner-presence arm added in **M8a** (needs `occurrences`, D-r3). M3's crash recovery is the stateless full re-scan every cycle (D30 — "the next cycle catches up").
- Index template for `javv-scan-watermarks` (`dynamic:false`) — **register it in
  `backend/core/bootstrap.py` + bump `MAPPING_VERSION`** (the versioned boot-time bootstrap from M1);
  don't hand-roll a separate creation path.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- Out-of-order scan: an older `scan_order` never creates OR updates a retired finding (D40 keystone).
- Clean rescan: a resolved CVE drops from "now" immediately (`present=false`), not next cycle.
- reconcile-on-commit flips `present=false` on omitted findings; no tombstones in history.
- Partial-doc merge: scanner fields update; human triage fields (`state`, `vex_justification`) untouched.
- Watermark CAS rejects a stale create AND a stale update; `committed_run_ts ≤ last_scan_at` is a no-op.
- _(rebuild-state's DoD is deferred: the presence + watermark rebuild from `occurrences` + `scan-events` is an **M8a** keystone; the human/decision-projection rebuild is an **M5c** keystone. Neither's source exists in M3.)_

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** merge field-allowlist; `scan_order` ordering; projection precedence (`apply_both`, expiry).
- **Integration (real OpenSearch):** watermark CAS create+update; commit-then-cache ordering; reconcile `present=false`; partial merge.
- **Golden fixtures:** out-of-order scan, clean-rescan, reconcile `present=false` (the testing.md keystones — kept here so the contract isn't lost when this stub was expanded).
- **Concurrency (required, AUDIT I10):** two writers race the same `(cluster,scanner,digest)` with inverted `scan_order` → CAS rejects the loser on create AND update; final state == newer scan regardless of arrival order; reconcile-to-zero-conflicts.

## Out of scope (defer)
- Snapshot/occurrence history append → M8a. Point-in-time query → M8b. (M3 maintains the cache + current-state; the append history and time-travel reads are the M8 line.)
- **rebuild-state self-heal job → deferred (M5c + M8a)** (2026-07-03). Human/decision arm needs `system-decisions`/`system-audit-log` (D17) → **M5c**; scanner-presence arm needs `occurrences` (PLAN §D-r3) → **M8a**. Neither source exists in M3; M3's crash recovery is the stateless full re-scan every cycle (D30). See Updates.

## Before coding
**Read [`CORRECTNESS-CONTRACT.md`](CORRECTNESS-CONTRACT.md) first** — the one-page distillation of every
rule this bolt must honor (identity keys, ordering, CAS semantics, write order, reconcile, merge
allowlist, rebuild invariant, the keystone tests). Pre-split into stacked PRs per
[`git-workflow.md`](../../standards/git-workflow.md):
**scan-order allocation (D45)** → merge → watermark CAS → commit-then-cache → reconcile → staleness.
(rebuild-state was the planned 7th slice → **deferred** to M5c + M8a; see Updates.) **M3 implementation
is complete at the staleness slice.**

> **`scan_order` source — SETTLED (D45, 2026-07-03).** The wall-clock `time.time_ns()` mint is replaced by
> a **backend-allocated sequence**: `POST /api/v1/scan-runs` CAS-increments a per-`(cluster_id, scanner)`
> counter doc and returns 1, 2, 3, … — can never regress regardless of node clocks (CronJob pods
> reschedule across nodes, so "monotonic on one host" was not a safe assumption). Fail-closed like the
> D43 scope fetch. Built as this bolt's FIRST slice — everything downstream trusts the order.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates

- **2026-07-03 — rebuild-state deferred out of M3; M3 implementation complete at the staleness slice.**
  The planned 7th slice (`jobs/rebuild_state.py`) has **two arms with different data sources, neither
  of which exists in M3**: the **human/decision** arm rebuilds from `system-decisions` +
  `system-audit-log` (D17) → created in **M5c**; the **scanner-presence** arm rebuilds from
  `occurrences` + `scan-events` (PLAN §D-r3) → added in **M8a**. Its keystone (#6: reproduce identical
  findings + presence + watermarks from the logs) is therefore unsatisfiable in M3 — only the
  watermarks are reconstructable from `scan-events` here. M3's crash recovery is already the
  **stateless full re-scan every cycle** (D30 — the contract's own "rebuild-state _or the next cycle_
  catches up"). The six shipped slices (allocation → merge → watermark CAS → commit-then-cache →
  reconcile → staleness) are the whole M3 implementation. Downstream docs updated: PLAN milestone table
  + §D-r3, CORRECTNESS-CONTRACT §9/#6/ladder, M5c + M8a READMEs. Mirrored on
  [#25](https://github.com/Danube-Labs/javv/issues/25).

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
