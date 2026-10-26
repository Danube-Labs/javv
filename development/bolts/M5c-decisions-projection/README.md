# M5c - Decisions & projection (own gate)

**Status:** tracked in [#29](https://github.com/Danube-Labs/javv-poc/issues/29) — live status on the GitHub issue/board

## Goal
Make `system-decisions` the source of truth for scoped `risk_accepted` / `ignore_rule` /
`not_affected` calls (immutable except `revoked_at`; scope/justification/`expiry` edits are
revoke+create under one `effective_at`/`operation_id`), and project them onto findings' `state`
with the **precedence ladder + expiry-refresh + the pinned `apply_both_scanners` rule (D22)** through
a projection cache that can be rebuilt from source. **The gate verifies `apply_both`.**

**Canonical refs:** [`PLAN §8 M5c`](../../../docs/engineering/PLAN.md) ·
`SPEC` FR-8 (decisions / precedence / expiry-refresh / `apply_both`) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md)
(`system-decisions` **[OWNS mapping]**, `findings` [projected human-field cache, owned by M3]) ·
decisions D19 (projection-on-new-only at ingest), D22 (`apply_both_scanners` pinned),
D39 (`expiry`/scope edit = revoke+create), D40 (one `effective_at`+`operation_id`, projection after
both land).

## Depends on
- M5a (Auth & Session - `can_accept_audit_final` gates who may create a risk-accept decision; SEC-2;
  `get_current_principal()`).
- M3 (owns the `findings` cache + the projection engine seam - `backend/src/backend/projection/engine.py`).
  **This bolt CREATES `backend/jobs/rebuild_state.py`** (the human/decision-projection arm — rebuild-state
  was deferred out of M3 on 2026-07-03: M3 has neither `system-decisions`/`system-audit-log` nor
  `occurrences`. The scanner-presence arm is added later in **M8a**.)

## Deliverables
The actual files/modules this bolt creates - **in the layered tree, not here** (paths proposed):
- `backend/src/backend/decisions/models.py` - Pydantic v2 `system-decisions` request/doc models
  (`extra="forbid"` on requests): `type`, `cve_id`, `scope {namespaces[], images[]}`,
  `apply_both_scanners`, `vex_justification`, `justification`, `expiry` (nullable, **immutable**),
  lifecycle stamps (`created_at`, `revoked_at`, `effective_at`, `operation_id`).
- `backend/src/backend/decisions/service.py` - create / **revoke+create** edit / revoke flows: a scope,
  justification **or `expiry`** change is **revoke-old + create-new** sharing one `effective_at` and
  one `operation_id` (`revoked_at(old) = created_at(new) = effective_at`); projection is **deferred
  until both writes land** so "active at T" never sees a neither/both gap (D39/D40).
- `backend/src/backend/decisions/projection.py` - the precedence projector: resolves a finding's decision-driven
  `state` by **precedence (explicit-finding > image > namespace > cluster; direct action > auto-rule)**,
  applies **expiry-refresh** (an expired decision stops projecting; "active at T" =
  `created_at ≤ T AND (revoked_at null OR > T) AND (expiry null OR > T)`), and implements the **pinned
  `apply_both_scanners` rule (D22)**: matches on `(cluster, cve, scope)` ignoring scanner, projects onto
  each scanner's finding independently, each closes on its own, and a **scanner-specific decision
  outranks a both-scanners one for that scanner**.
- `backend/src/backend/decisions/reproject.py` - re-projection triggers: at **ingest (newly-created findings
  only**, vs cascading namespace/cluster rules - D19), at **decision-apply/revoke**, and on the
  **daily sweep** (expiry-refresh fallback - SND-9). Updates the `findings` human-field cache.
- `backend/src/backend/indices/decisions_template.py` - **owns** the `system-decisions` mapping
  (`dynamic:false`, INDEX-MAP fields, single index, no rollover; the role allows only the `revoked_at`
  post-hoc stamp - D39).
- `backend/jobs/rebuild_state.py` (**created here** - the base self-heal job; rebuild-state moved out
  of M3 on 2026-07-03) - rebuild the **decision projection** of the `findings` cache from
  `system-decisions` + `system-audit-log` source (the human/decision arm; M8a later adds the
  scanner-presence arm - D-r3). Reuses M3's merge field-allowlist (single source, CONTRACT §6).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**
(each an automated test, not a promise):
- **Gate (`apply_both`, D22):** a both-scanners decision on `(cluster, cve, scope)` projects onto each
  scanner's finding independently and each closes on its own; a **scanner-specific decision outranks**
  the both-scanners one for that scanner. (PLAN M5c gate.)
- Precedence holds: explicit-finding > image > namespace > cluster, and direct action > auto-rule -
  the most-specific active decision wins.
- Expiry-refresh: an expired decision stops projecting (finding reverts on the daily sweep); a decision
  is "active at T" exactly per the `created_at/revoked_at/expiry` window.
- A scope/justification/`expiry` **edit** is revoke+create under one `effective_at`/`operation_id`;
  `expiry` is never rewritten in place; projection runs **only after both writes land** (no
  neither/both gap at any T) (D39/D40).
- Re-projection runs on newly-created findings only at ingest (cascading namespace/cluster rules are
  *not* re-applied to unchanged findings) (D19).
- `rebuild_state` reproduces an identical decision projection of the `findings` cache from
  `system-decisions` source (self-heal).
- Creating a risk-accept decision requires `can_accept_audit_final` (SEC-2) - rejected otherwise.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** the precedence projector as a **pure function** (decisions + finding → projected `state`):
  precedence ladder, expiry-refresh boundary (active just-before / inactive just-after `expiry`),
  "active at T" window, and the `apply_both` independence/override rule; request-model `extra="forbid"`.
- **Integration (real OpenSearch):** create→project→revoke round-trip on `findings`; revoke+create edit
  lands both docs before projection (no intermediate gap); `can_accept_audit_final` gate enforced;
  daily-sweep expiry-refresh updates the cache; `rebuild_state` reconstructs the same projection.
- **Golden fixtures (the invariants this bolt is most exposed on - AUDIT line for M5c):**
  - **Precedence ladder:** overlapping cluster/namespace/image/explicit decisions on one finding →
    expected winning `state`.
  - **`apply_both` (D22):** a both-scanners decision projects independently onto Trivy + Grype findings,
    each closes on its own; add a scanner-specific decision → it **overrides** for that scanner only,
    the other scanner still follows the both-scanners decision.
  - **Expiry:** a decision active at T1 / expired by T2 → finding projected accepted at T1, reverted at
    T2; revoke+create `expiry` edit yields a stable past-T reconstruction (no `expiry` rewrite).
- **Concurrency (required - the revoke+create pair relies on ordered atomicity, D40/G-r3):** a reader
  evaluating "active at T" while a revoke+create edit is mid-flight never observes a neither/both
  window for the same `(cve, scope)`; projection is applied only after both writes for the
  `operation_id` land.

## Out of scope (defer)
- VEX two-field `state`/`vex_justification` machine + the `system-audit-log` write per action → M5b.
- SLA/overdue + bulk decision application → M5d.
- As-of-T read reconstruction that joins decisions-active-at-T into the historical view → M6/M8b
  (M5c maintains the *current* projection cache + the rebuild; the time-travel join is the M6/M8 line).
- The scanner-field partial-doc merge of `findings` (decisions touch only human/projected fields) → M3.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates

- **2026-07-05 (pre-kickoff drift sweep — M5b + audit tasks A/E + #159 changed this bolt's ground):**
  1. **`decisions/models.py` + `decisions/service.py` won't be created — they exist** as
     `backend/src/backend/decisions/lifecycle.py` (M5b slices 3–4, hardened by audit task A #138):
     `DecisionPayload` (now carrying `cluster_id: ClusterId` — the task-E shared shape, missing from
     the model list above), and create / revoke / edit with one `effective_at`+`operation_id`,
     **CAS'd revoke** (`if_seq_no`/`if_primary_term`), **edit-loser compensation** (a lost race
     revokes its own successor), new-doc-first write order (overlap over gap), and D17 journaling.
     This bolt BUILDS ON lifecycle.py; it does not re-create models/service.
  2. **`indices/decisions_template.py` won't be created** — the `system-decisions` mapping is owned
     by `core/bootstrap.py` (since M5b). Any mapping change = bump `MAPPING_VERSION` (now **7**) +
     INDEX-MAP + the in-code upgrade note.
  3. **The "M3 projection engine seam" (`projection/engine.py`) never materialized** — M3's real
     seam is `services/merge.py`'s field allowlists (`HUMAN_FIELDS`/`SCANNER_FIELDS`, CONTRACT §6).
     The projector is created fresh here (`decisions/projection.py`) and must write findings
     **only through `HUMAN_FIELDS`** so merge and rebuild can't diverge.
  4. **No HTTP routes exist for decisions yet** — this bolt creates `routers/decisions.py`, and
     every new mutating endpoint MUST register in `tests/security/test_rbac_idor_contract.py`
     (n-2: the build fails otherwise).
  5. **Journal-before-commit (task A M-3 ruling)** governs any new audited write path added here:
     audit row first (predicted `revision`), CAS write after; an orphan ROW is replay-tolerated,
     an orphan CHANGE never.
  6. **Observability (#156/#159):** new sweeps/jobs use the shared `javv_common.logging` pipeline
     (`JAVV_LOG_LEVEL`); state-changing ops leave an INFO line (the lifecycle sweep's roll/drop
     lines are the pattern). Jobs live at `backend/src/backend/jobs/` with the `__main__` CLI
     pattern (`lifecycle.py`/`staleness.py`) — `rebuild_state.py` follows it.
  7. Baseline: 312 backend tests; `tests/test_decisions.py` already pins the lifecycle incl. the
     revoke/edit race contracts — extend it, don't duplicate it.

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
