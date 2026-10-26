# M6 - Read/reporting + VEX export + as-of-T

**Status:** tracked in [#31](https://github.com/Danube-Labs/javv-poc/issues/31) — live status on the GitHub issue/board

## Goal
PIT+search_after search (faceted by scanner, composite aggs); trend endpoints over scan-events; expanded Contributors; streaming sanitized CSV; VEX export (OpenVEX/CycloneDX); the as-of-T read path — T=now short-circuits to materialized current-state. (T<now historical reconstruction is delivered by M8b's `as_of_t` composition; M6 delegates to it, and the full whole-app time-travel UI is gated on M8b.)

**Canonical refs:** [`PLAN §8 M6`](../../../docs/engineering/PLAN.md) · `SPEC` (FRs for M6) · [`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (indices touched).

## Depends on
M3, M4, M5c, M5b (system-audit-log — Contributors + audit-log replay read it), M5d (SLA policy +
`compute_overdue` — the grid's overdue decoration and Contributors' SLA-hit % read them). The T<now
time-travel portion additionally depends on M8b (`as_of_t`) — gated, not a blocker for M6's T=now core.

## Carried-in from M3 — reconcile refresh (audit #117)
**Measure-first task, do it at M6 kickoff.** `services/reconcile.py` calls `indices.refresh("findings")`
**once per ingest envelope** on the hottest index (load-bearing today: the just-merged findings must be
visible before reconcile decides who's absent). It's harmless while nothing reads `findings` — M6 is the
first read load that contends with it, so it's the first time it can storm. Marked with an in-code
`NOTE(#117)` at the refresh site. **Do:** load-test ingest at target `clusters × scanners × digests`, watch
OpenSearch `refresh` count/time; if flat, close [#117](https://github.com/Danube-Labs/javv-poc/issues/117)
with the numbers; if it storms, replace the per-envelope refresh with a **bounded reconcile**
(batch/debounce per `(cluster, scanner)` cycle, or `refresh=wait_for` on the merge writes). Don't fix blind.
The e2e smoke harness (`development/e2e/smoke.sh`) is the natural measurement rig.

## Carried-in from M5c/M5d — what already exists, consume it (don't rebuild)
- **Tenant chokepoint is built** — `tenancy/chokepoint.py` (`tenant_search`/`tenant_query`, SEC-4): it
  injects the `cluster_id` filter, refuses raw `?q=` and `global` aggs at any depth. Every M6 read/agg/
  export routes through it; M6 adds callers, not the chokepoint.
- **Overdue is read-time (M5d)** — decorate grid/search rows via `sla/overdue.py::compute_overdue`
  (pure; D21 group clock over `(cve_id, image_digest)`; handled states never overdue) with the policy
  from `sla/policy.py::read_sla_policy`. Never re-derive SLA logic inline.
- **Contributors SLA-hit %** computes against the live `SlaPolicy` (system-config `sla`), not
  hardcoded day thresholds.
- **Findings carry `state_decision_id` (M5c)** — projection provenance; expose it in search results and
  offer it as a filter facet (auto-ruled vs directly-triaged). Decisions carry `scanner`
  (required iff not apply-both).
- **`GET /api/v1/decisions/approvals` shipped in M5d** — the risk-accept review queue exists; M6's read
  surface links/consumes it, doesn't rebuild it.
- **Catalog-read discipline (R-CATALOG/D40):** any "latest state" read resolves the latest committed
  run via top-1-by-**`scan_order`** from `javv-scan-events-*` (inventory: `inventory_order`), never
  `@timestamp`, never "latest doc per key".
- **At kickoff, decide the M8b 1-day spike** (#134): whether to prove the `as_of_t` reconstruction
  seam early so M6's dispatcher lands against a verified interface.

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `backend/src/backend/query/search.py` — faceted PIT + `search_after` finding search (FR-12); filters by severity/state/scanner/assignee/KEV/fix-available/disagree; `from/size` only under 10k, PIT+`search_after` for deep paging (delete the PIT in `finally`).
- `backend/src/backend/query/aggs.py` — scanner-faceted aggregations; capped `terms` or **composite** aggs paginating via `after_key` (FR-12, NFR pin §). Pure DSL-builder, unit-tested on the emitted body.
- `backend/src/backend/query/trends.py` — trend endpoints over `javv-scan-events-*` (FR-5/FR-12; "new in 30d"); per-`cluster_id`, always-applied filter. **Dedup rule (audit task B, #139): a retry straddling a rollover leaves byte-identical sibling docs (same `commit_key`) in two backing indices — count committed scans via `cardinality(commit_key)` / dedup by `commit_key`, NEVER raw doc counts or sums over docs** (pinned by `tests/test_rollover_idempotency.py`).
- `backend/src/backend/query/contributors.py` — **Contributors (expanded)** over `system-audit-log`: resolved-over-time, median TTR, SLA-hit %, leaderboard (FR-15). Reads M5b's audit log.
- `backend/src/backend/api/search.py` — GET search/agg/trend/contributors endpoints; `extra="forbid"` request models; `cluster_id` via the **existing** `tenancy/chokepoint.py` `tenant_search` (SEC-4), entitlement on every fetch **and export** (IDOR). Follow [`standards/api-design.md`](../../standards/api-design.md) (paths/naming, opaque `next_cursor`, `as_of` param, response shape).
- `backend/src/backend/export/csv_stream.py` — streaming, **CSV-injection-sanitized** export from any lens, constant memory (FR-13 inline "run now" path); PIT+`search_after`, small pages.
- `backend/src/backend/export/vex.py` — **VEX export** serializing `state`/`vex_justification` → OpenVEX + CycloneDX, consumable by Trivy/Grype `--vex` (FR-22 export-only; import → v1.1).
- `backend/src/backend/query/as_of.py` — the **as-of-T dispatcher**: `T=now` short-circuits to materialized current-state (M3 cache); `T<now` **delegates to M8b's `backend/src/backend/query/as_of_t.py`** (does NOT reimplement reconstruction — D28/FR-23 boundary).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **T=now short-circuit:** every read endpoint with `T=now` reads the materialized current-state cache and **never** touches the append-log reconstruction path (assert no occurrences/audit-replay query is issued) — D28.
- **T<now delegates:** a `T<now` request routes to M8b's `as_of_t` (asserted at the seam); M6 contains no reconstruction logic of its own.
- Faceted search paginates deep results via PIT+`search_after` with the PIT deleted in `finally`; aggregations are **scanner-faceted** and never aggregate on `text` fields.
- Composite aggregations paginate correctly via `after_key` (no silently-capped buckets).
- **CSV export is injection-sanitized** (leading `=,+,-,@,\t,\r` neutralized) and streams in constant memory (no full-result buffering).
- **VEX export** round-trips a triaged finding's `state`/`vex_justification` into valid OpenVEX **and** CycloneDX that a Trivy/Grype `--vex` consumer parses (golden).
- Contributors metrics (TTR/SLA-hit %/leaderboard) compute from `system-audit-log` (M5b), not from live findings.
- Every read/agg/export carries an explicit `cluster_id` filter via the `tenant_search` chokepoint (negative test: cross-tenant leak is impossible — SEC-4/IDOR).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** search/agg/trend **DSL-builders** (assert emitted body incl. scanner facet + composite `after_key`); CSV sanitizer (each dangerous leading char); VEX serializer shape (OpenVEX + CycloneDX); the as-of-T **dispatch decision** (`T=now` → cache, `T<now` → delegate).
- **Integration (real OpenSearch):** PIT+`search_after` deep paging with PIT cleanup; faceted aggregations over seeded multi-scanner findings; trends over seeded `scan-events`; Contributors over seeded `system-audit-log`; `cluster_id` isolation by unique tenant.
- **Golden fixtures:** VEX export — a checked-in triaged finding → expected OpenVEX **and** CycloneDX documents (validated against a `--vex` consumer); a streaming-CSV fixture with injection-bait cell values → expected sanitized output.

## Out of scope (defer)
- **T<now historical reconstruction** → M8b (`as_of_t` composition: occurrences ≤ T ⋈ decisions-active-at-T + audit-log replay ≤ T + `javv-images` ≤ T). M6 only delegates.
- The **whole-app time-travel UI** (global picker rewinding every screen) → gated on M8b + M9c.
- **VEX import** → v1.1.
- Scheduled/throttled large exports + the `system-reports` queue → M7.
- Historical **all-clusters** dashboards → v1.1 `javv-metrics` rollup (limited until then).

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates
- **2026-10-09: the VEX goldens prove a valid file, not a scanner that applies it (issue 41):** the
  fixtures name a made-up image (`registry.local/team/app`, `sha256:vexgold01`), so running
  `trivy --vex` with them, as the 2026-07-06 entry below records, could only show that trivy
  parses the files. On a real image, neither trivy 0.75.0 nor grype 0.120.1 applies the export:
  both refuse the CycloneDX form, and both keep reporting a finding the OpenVEX form marks
  `not_affected`, because the package is written as `pkg:generic/...`. The export stays as a
  standard record of the triage decisions (operator ruling on issue 41); the fix is issue 791.
- **2026-07-06 (slices 5–7, one PR — closes the bolt):** CSV export = `export/sweep.py`
  (shared constant-memory PIT sweep, PIT deleted in `finally`) + `export/csv_stream.py`
  (sanitizer neutralizes leading `=`/`+`/`-`/`@`/tab/CR with a leading apostrophe; golden
  bait fixture) behind `GET /api/v1/findings/export.csv` (grid lens reused). VEX export =
  `export/vex.py` pure serializers (state→status mapping table + CISA→CycloneDX justification
  translation recorded in the module docstring) behind `GET /api/v1/findings/export.vex`
  (`format=openvex|cyclonedx`; **scanner filter required** — per-scanner is sacred); both
  goldens **validated against a real `trivy --vex` consumer** (OpenVEX via fs scan, CycloneDX
  via SBOM scan — CycloneDX VEX only applies to CycloneDX SBOM scans in trivy, a consumer
  restriction, not a document defect). As-of-T = `query/as_of.py`: `parse_as_of` (absent/
  `now`/**future→clamped-to-now**; naive/malformed→422) + the typed `AsOfTReader` protocol
  (one method per read surface) + `register_as_of_t` — per the kickoff ruling this seam +
  its contract tests **replace the M8b spike**. All six read surfaces dispatch; exports stay
  501 at past T even with a reader (export-at-T lands with M8b+M7). No new config knobs. synced against the shipped M5c/M5d + observability work —
  added M5d to *Depends on*; new *Carried-in from M5c/M5d* section (existing `tenancy/chokepoint.py`,
  `compute_overdue`/`SlaPolicy` consumption, `state_decision_id` on findings, the shipped
  `/decisions/approvals` route, the `scan_order` catalog-read rule, the M8b-spike kickoff decision);
  noted the e2e smoke harness as the #117 measurement rig.

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
