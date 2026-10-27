# M5b - VEX two-field state machine + the audit-log spine

**Status:** tracked in [#28](https://github.com/Danube-Labs/javv/issues/28) — live status on the GitHub issue/board

## Goal
The triage state machine over the two-field VEX model (`state` + `vex_justification`,
6 states) with validated transitions, and the structured **`system-audit-log` writer** that this
bolt **owns** — the immutable human-state timeline that M5d (bulk), M6
(Contributors/time-travel), and M8/M9 all read. (The index *template* already landed with M5a's
thin auth appender — this bolt owns the row contract + replay semantics and absorbs that
appender.) Every triage action is journaled (D17); triage writes use `refresh=wait_for`;
decisions are immutable + lifecycle-stamped (edit = revoke+new).

> ⚠️ **Do not use hardcoded config.** Every knob this bolt introduces (a `JAVV_*` env var, a
> `system-config` key, a tunable limit) goes to [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md)
> **in the same PR** — default · how it's set · UI-controllable or not. Contract constants
> (schema versions, capability names, index names) are exempt but must be justified in-code.

**Canonical refs:** [`PLAN §8 M5b`](../../../docs/engineering/PLAN.md) ·
`SPEC` FR-7 (VEX two-field model, 6 states), FR-8 (decisions immutable + lifecycle) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (`system-audit-log` **[OWNS — creates the structured schema]**,
`findings` `state`/`vex_justification`/`assignee`/`notes` fields, `system-decisions` lifecycle fields) ·
decisions D32 (structured audit-log), D17 (every action journaled), D40/H-r3 (`revision` causal ordering),
D39/H5-r2 (decisions immutable except `revoked_at`), D40/G-r3 (revoke+create `effective_at`/`operation_id`).

## Depends on
- M5a (**built**): `get_current_principal()` + `require_capability` (`auth/principal.py` /
  `auth/capabilities.py`), the `can_triage` / `can_accept_audit_final` bundles already seeded in
  `system-roles`, the tenant chokepoint (`tenancy/chokepoint.py`), and the **standing RBAC/IDOR
  suite** (`tests/security/test_rbac_idor_contract.py`) every new mutating endpoint registers into.
- M3 (**built**): the `findings` cache whose human fields this bolt mutates; CAS guard semantics.

## Already landed (M5a) — M5b builds ON these, doesn't recreate them
- **`system-audit-log-*` index template** — in `core/bootstrap.py` (`_AUDIT_LOG_PROPERTIES`,
  `dynamic:false`, `MAPPING_VERSION` 5) with the full INDEX-MAP schema; evolve it THERE (+ version
  bump, per the documented procedure at the constant). Writes go through the `system-audit-log`
  **write alias** (M4 convention, `ensure_write_alias`).
- **Thin auth appender** — `auth/audit.py` (login/logout/pwd_change/token_mint/token_revoke rows,
  `AUDIT_SCHEMA_VERSION = 1`). The M5b writer **absorbs it** (same rows, richer machinery); audit
  rows version independently of the ingest envelope — M5b owns bumps.
- **The human-field contract** — `services/merge.py` `HUMAN_FIELDS` is the allowlist ingest never
  touches (`state`/`vex_justification`/`assignee`/`notes`/`pre_stale_status`); the triage service
  is their ONLY writer. `disagree` is a third family owned by `services/disagreement.py` — triage
  must not write it either. M3's staleness sweep owns `stale`/`pre_stale_status` transitions.

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed,
matching the real `backend/src/backend/` layout):
- `backend/src/backend/audit/writer.py` — the **structured audit writer** (D32), absorbing M5a's
  thin `auth/audit.py` appender: the row model (`event_id`, `actor`, `action`, `entity_type`,
  `entity_id`, `finding_key`, `target_ids`, `target_selector`, `result_hash`/`result_count`,
  `field`/`field_type`, `revision`, `old_value`/`new_value`(`_json`), `decision_id`,
  `schema_version` — per INDEX-MAP, mapping already pinned) + append-only discipline: one row per
  field change via `op_type=create`; replay-deterministic ordering by `(@timestamp, event_id)`,
  same-`(entity,field)` by `revision` (D40/H-r3, D39/H6-r2 — no monotonic `seq`). **Dependency of
  M5d/M6/M9d.** *(SEC-1's create-only OpenSearch role is a deploy control — Helm/M10; in code the
  append-only property holds by construction.)*
- `backend/src/backend/triage/state_machine.py` — the 6-state model `{open, acknowledged, not_affected, risk_accepted, resolved, stale}` × `vex_justification` (CISA five, **required iff `not_affected`**); validates allowed transitions; `resolved` manual-only; `stale` system-only (the M3 staleness sweep is its writer); "false positive" = `not_affected` + component/code-not-present justification.
- `backend/src/backend/triage/service.py` — single triage action (assign/note/acknowledge/risk_accept/not_affected/resolve/reopen): **CAS on the finding** (`retry_on_conflict`/409-retry), `refresh=wait_for` on the write, then **exactly one** `system-audit-log` append per action incl. the resulting `revision`. Writes ONLY the `HUMAN_FIELDS` allowlist (merge.py is the contract).
- `backend/src/backend/routers/triage.py` — `PATCH /api/v1/findings/{finding_key}/triage` (+ assign/note/ack); capability-gated (`can_triage`; risk-accept additionally `can_accept_audit_final` — both bundles already seeded); **registers into the M5a standing RBAC/IDOR suite** (`tests/security/test_rbac_idor_contract.py` — the presence check fails the build otherwise).
- `backend/src/backend/decisions/lifecycle.py` — decision immutability helper: any scope/justification/`expiry` edit is **revoke+create-new** under one `effective_at` + `operation_id`, `revoked_at(old)=created_at(new)=effective_at`; only `revoked_at` is a post-hoc stamp (D39/H5-r2, D40/G-r3). Creates the **`system-decisions` mutable index** in `bootstrap.MUTABLE_INDEXES` (+ `MAPPING_VERSION` bump) per INDEX-MAP. *(Decision precedence/projection itself is M5c; this bolt owns only the immutable-write discipline + its audit journaling.)*

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **State machine:** every allowed transition succeeds and every disallowed transition is rejected; `vex_justification` is required iff `state=not_affected` and rejected otherwise; `resolved` is manual-only; `stale` cannot be set by a human action.
- **One-action-one-entry (D17):** each triage action (incl. acknowledge/assign/note) appends **exactly one** `system-audit-log` row with the correct `action`, `actor`, `entity_id`/`finding_key`, `field`/old/new, and the finding's resulting `revision`.
- **`refresh=wait_for`:** a read immediately after a triage write reflects the new state (no race window in tests).
- **CAS/concurrency:** concurrent triage writes to the same finding resolve via `retry_on_conflict`/409-retry to a consistent final state with one audit row per successful action.
- **Audit-log replay determinism (D32/D40):** replaying rows for a `(entity, field)` in `(@timestamp, event_id)` order with `revision` tiebreak reconstructs the correct latest-wins human state.
- **Decision immutability (D39/H5-r2):** an `expiry`/scope edit produces a revoke+create pair sharing one `effective_at`/`operation_id`; no in-place mutation of a committed decision except `revoked_at`.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** transition table (allowed/disallowed matrix); `vex_justification` required-iff-`not_affected` rule; audit-row builder (asserts emitted structured fields incl. `revision`).
- **Integration (real OpenSearch):** triage write → `findings` CAS + `refresh=wait_for` visibility + single `system-audit-log` append; revoke+create decision pair lands atomically (projection deferred until both land).
- **Concurrency (required):** two writers race the same finding (inverted order) → `retry_on_conflict` resolves; final state consistent; exactly one audit row per winning action.
- **Golden fixtures:** structured `system-audit-log` row per `action` enum (the M6/M9d contract — frozen here so downstream replay can't drift); audit-replay reconstructs human-state-at-T for a multi-edit finding.

## Out of scope (defer)
- Decision **precedence + expiry-refresh + `apply_both`** projection → **M5c** (this bolt owns only immutable decision writes + their journaling).
- SLA/overdue + bulk triage → **M5d** (single-action triage only here).
- Contributors/time-travel **reads** over `system-audit-log` → M6 (this bolt produces the log; M6 consumes it).

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates

- **2026-07-04 — pre-kickoff refresh against the M0–M5a reality.** The `system-audit-log-*`
  template + a thin auth-event appender landed with M5a (see the #28 heads-up): dropped the
  `audit/template.py` + separate `schema.py` deliverables — the writer owns the row contract and
  absorbs `auth/audit.py`; the mapping evolves in `core/bootstrap.py` (documented procedure at
  `MAPPING_VERSION`, now v5). Marked M5a deps as built with real paths (`require_capability`,
  seeded `can_triage`/`can_accept_audit_final` bundles, chokepoint, the standing RBAC/IDOR suite
  the triage routes must register into). Fixed stale `backend/app/` paths; SEC-1's create-only
  role reframed as a deploy control (append-only holds by construction in code); noted the
  `system-decisions` index creation lands here (bootstrap + version bump); added the explicit
  **no-hardcoded-config stamp** (banner under Goal). Scope itself is unchanged — the bolt is
  fully doable on the M0–M5a base.

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
