# M5d - SLA/overdue + bulk triage

**Status:** tracked in [#30](https://github.com/Danube-Labs/javv-poc/issues/30) — live status on the GitHub issue/board

## Goal
Per-severity SLA policy + KEV override, read-time `overdue` computation, and **bulk triage
via `_bulk`** (202 + async for large sets) with one `system-audit-log` entry per bulk action
recording the **frozen `target_ids`**. Plus the risk-accept approval list. Concurrency-safe
under `retry_on_conflict`.

**Canonical refs:** [`PLAN §8 M5d`](../../../docs/engineering/PLAN.md) ·
`SPEC` FR-10 (SLA/overdue, KEV 24h, read-time vuln-age D21), FR-7 (bulk via `_bulk`, one audit entry/bulk),
FR-8 (approval list) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (`findings` `severity_rank`/`first_seen_at`/`kev`,
`system-config` SLA policy, `system-audit-log` `target_ids`/`result_hash`/`result_count`) ·
decisions D21 (vuln-age earliest `first_seen_at`), D38/H8 (frozen `target_ids`), SND-8 (`retry_on_conflict`).

## Depends on
- M5b (triage state machine + the `system-audit-log` writer/schema this bolt appends bulk rows into).
- M5c (decisions/projection — the risk-accept path the approval list surfaces).

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `backend/src/backend/sla/policy.py` — per-severity SLA days (CRIT 2 / HIGH 7 / MED 30 / LOW 90, editable) + **KEV override (24h)**; loaded from `system-config`.
- `backend/src/backend/sla/overdue.py` — **read-time** overdue derivation from vuln-age: group by `(cve_id, image_digest)`, earliest `first_seen_at` so a package bump doesn't reset the clock (D21); pure function of inputs.
- `backend/src/backend/sla/routes.py` — `GET`/`PUT /settings/sla` (Admin-gated, `can_manage_*`); registers into the M5a RBAC/IDOR suite.
- `backend/src/backend/triage/bulk.py` — bulk triage executor: `_bulk` apply across the affected set with `retry_on_conflict`; **202 + async** for large sets; **one** `system-audit-log` entry per bulk action with the **frozen `target_ids`** (not a selector/count) + `result_hash`/`result_count` (D38/H8).
- `backend/src/backend/triage/bulk_routes.py` — `POST /findings/bulk-triage` (selector in → frozen id-set → 202 + job ref); capability-gated.
- `backend/src/backend/decisions/approval_list.py` — risk-accept approval list endpoint (pending risk-accepts surfaced for `can_accept_audit_final` holders).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **SLA policy:** per-severity days resolve from `system-config`; KEV findings use the 24h override; editing the policy is Admin-gated and journaled.
- **Overdue (D21):** `overdue` is computed read-time from the **earliest `first_seen_at`** per `(cve_id, image_digest)`; a later package bump (new `installed_version`) does **not** reset the clock.
- **Bulk = one audit entry (FR-7/D38/H8):** a bulk action over N findings appends **exactly one** `system-audit-log` row carrying the **frozen `target_ids`** set (+ `result_hash`/`result_count`), never a selector or a per-finding fan-out of audit rows.
- **Async for large sets:** a large bulk action returns **202** and completes via the async path; a small set may apply inline — both produce the same single-audit-entry contract.
- **Concurrency (required, SND-8):** a bulk write racing concurrent single-triage/ingest on overlapping findings resolves via `retry_on_conflict` with no lost updates and a consistent final state.
- **Approval list:** only `can_accept_audit_final` holders see/act on pending risk-accepts.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** SLA-days resolver incl. KEV override; overdue calculator (frozen time; earliest-`first_seen_at` grouping; package-bump-doesn't-reset case); `target_ids` freezing + `result_hash` builder.
- **Integration (real OpenSearch):** bulk `_bulk` apply across a set → state updated on all + **one** `system-audit-log` row with frozen `target_ids`; 202/async path round-trip; SLA-policy edit persists + journals.
- **Concurrency (required — `retry_on_conflict`):** bulk action vs concurrent single-triage on overlapping `finding_key`s → both resolve via `retry_on_conflict`, no lost update, final state consistent, audit rows correct.
- **Golden fixtures:** overdue-at-T for a multi-version CVE (D21 clock-not-reset); single-bulk-audit-row shape with frozen `target_ids`/`result_count`.

## Out of scope (defer)
- SLA-breach **notifications** (bell) → FR-16 (M6 line); this bolt computes overdue, does not push notifications.
- Async **report/export** job infrastructure → M7 (`system-reports`); the bulk async path here is triage-apply only.
- Decision **precedence/projection** mechanics → M5c (consumed, not built here).

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates

- **2026-07-05 (drift sweep alongside the M5c kickoff — smaller deltas, same causes):**
  - New mutating endpoints (`/settings/sla`, `/findings/bulk-triage`) MUST register in
    `tests/security/test_rbac_idor_contract.py` (n-2 carry-forward; the build fails otherwise).
  - The audit writer is `backend/src/backend/audit/writer.py::append_field_change`; the
    **journal-before-commit** ruling (task A M-3, #138) applies to the bulk path's audit row too.
  - `system-config` knob precedent: `jobs/lifecycle.py`'s `LifecycleKnobs` (fleet doc + per-cluster
    override, read live per run) — the SLA policy should follow that pattern, and any new knob goes
    in `docs/CONFIGURATION.md` §6 same PR.
  - New jobs/sweeps use the shared `javv_common.logging` pipeline (#159); async bulk progress is a
    natural INFO line.
- **2026-07-05 (build ruling):** the **approval list** is a *review queue over ACTIVE risk-accept
  decisions* (`GET /api/v1/decisions/approvals`, `can_accept_audit_final`, soonest-expiring
  first) — NOT a pending-approval workflow: creation is already SEC-2-gated and no "pending"
  state exists in the model. Flagged on #30 at kickoff; revisit only if a two-step approval flow
  becomes a requirement.

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
