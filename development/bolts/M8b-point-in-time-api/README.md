# M8b - Point-in-time query API

**Status:** tracked in [#34](https://github.com/Danube-Labs/javv/issues/34) — live status on the GitHub issue/board

## Goal
Forward (digest X at T = R-CATALOG two-step) + the symmetric two-step (catalog → commit_key set →
occurrences) query, and the whole-app as-of-T composition: occurrences ≤ T + images ≤ T +
audit-log replay ≤ T + decisions active at T (D28). T=now short-circuits to materialized current-state.

**Canonical refs:** [`PLAN §8 M8b`](../../../docs/engineering/PLAN.md) · `SPEC` (FRs for M8b) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (javv-scan-events, javv-finding-occurrences,
javv-inventory-runs, system-audit-log, decisions) · D28, D37–D40.

## Depends on
- M8a (occurrences + inventory-runs append + commit manifest).

## Deliverables
Paths proposed:
- `backend/src/backend/query/pit.py` — catalog-first two-step (latest committed run ≤ T by `scan_order`, then occurrences for that run); never "latest doc per key" (R-CATALOG).
- `backend/src/backend/query/as_of_t.py` — composes the four append logs at T (D28). **M6 delegates its T<now read path here** (see M6 split).
- `backend/src/backend/api/point_in_time.py` — GET endpoint; results labelled "as-scanned".

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- Exact CVE-list-at-T for a digest (golden).
- Clean rescan reads as clean at T — not as the prior snapshot.
- A digest that dropped CVE-Y by T does not appear.
- Results labelled as-scanned; per-cluster retention bounds the reachable T.
- **T=now (materialized) == replay-to-now (reconstructed)** — the two read paths agree (AUDIT I11).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Integration (real OpenSearch):** two-step catalog query; ordering by `scan_order`/`inventory_order`.
- **Golden fixtures:** ingest → triage → rescan → query at several T values, each == known-correct state (AUDIT I11); clean-rescan-at-T.
- **Consistency (AUDIT I11):** T=now vs replay-to-now produce identical findings (catches read-path divergence).

## Out of scope (defer)
- Historical all-clusters dashboards → v1.1 rollup (`javv-metrics`); per CLAUDE.md they're limited until then.

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

## Updates
- **2026-07-08 (slice 4 — BOLT COMPLETE)** — trends + contributors at T land; the reader
  registers in lifespan (all six protocol methods live; past-T reads stop being 501). Scans
  trend + contributors board = the SAME builders anchored at T (append logs are immutable —
  single source, no fork); the findings trend derives new/resolved from occurrences (the
  cache's `resolved_at` clears on reappearance, so the cache cannot answer history). **M7's
  as_of_t export unparked**: the drain reconstructs rows at T through the reader (paged,
  throttled) into the same CSV/VEX pipeline; an unanswerable filter (e.g. `kev`) fails the job
  loud with the reason. As-scanned labeling: unrecorded fields are null by construction —
  see the API.md note.
- **2026-07-08 (slice 3)** — the reader's findings trio + the I11 keystone (T=now
  reconstruction == materialized cache, field-for-field). Registration deferred to slice 4 so
  past-T trends stayed clean 501s. `pit.py` hardened for the empty-catalog wildcard shape.
- **2026-07-07 (slices 1–2)** — R-CATALOG primitives (#263: catalog-first two-step, symmetric
  CVE-at-T, running-images-at-T; top_hits/composite for #257-exact `scan_order`) + the human
  dimension (#264: audit replay under the revision/(@timestamp,event_id) contract, bulk
  target_ids expansion, state/vex pairing; decisions-active-at-T as a pure lifecycle filter).
  Store dates truncate to MILLISECONDS — captured instants in tests are padded 2ms.
- **2026-07-06** — audit A-m11 (#192): the M6 kickoff ruling (recorded on #31) replaced the standalone
  M8b spike with a typed seam — this bolt must **implement the `AsOfTReader` protocol**
  (`backend/src/backend/query/as_of.py`): the six methods `findings_page` · `findings_facets` ·
  `findings_groups` · `trends_scans` · `trends_findings` · `contributors` (return shapes MATCH the
  current-state responses — time-travel changes *when*, never the wire contract, FR-23), and
  **register it via `register_as_of_t(...)` at startup**. Until then every past-T read is `501`
  (`AsOfTUnavailable`) at the seam. **Re-validate every delegated input** — the current-state routes
  validate inside their body builders, but the past-T delegation forwards `filters`/`sort`/`by`/facet
  `fields` **raw**, so the reader must re-check them (raise `ValueError` → 422) or inherit a 500
  (the `AsOfTReader` docstring carries this contract). The protocol + its contract tests ARE the
  verified interface M8b lands against — no separate spike.
- **export-at-past-T is M7's**, not this bolt's (D28): the inline export routes 501 for a past
  `as_of_t`; a reconstructed-at-T export lands in M7's scheduled queue once this reader can feed the
  sweep. See the M7 README Updates.

### 2026-10-26 — Frozen as history

The bolts M0 to M10 ended on 2026-10-09. This file is history now, not the spec of record. New work
follows one GitHub issue for each feature, with the plan and a spec file for each slice on the
issue. The timeline, the rulings that still apply and the open work are in the
[memory bank](../../memory-bank/README.md) (issue 1012).
