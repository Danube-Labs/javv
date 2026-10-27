# Audit remediation — M5c / M5d / M6 (2026-07-06 two-model audit)

**Status:** tracked on GitHub issues (label `audit`) — one issue per task below.

Fix-it bolts for every finding from the 2026-07-06 two-model independent audit (Codex + Fable) of
`6b8516d..f8393fa`. Full evidence lives in the three audit reports; this folder is the **execution
layer** — one self-contained guide per task, each ≈ one PR, sized for a single implementer (Opus
4.8) to pick up and finish without re-reading the whole audit.

**Read first:**
[`docs/audits/audit-2026-07-06-m5c-m5d-m6-UNION.md`](../../../docs/audits/audit-2026-07-06-m5c-m5d-m6-UNION.md)
(the reconciled operator view) · the per-model reports (`-codex.md`, `-fable.md`) · the live backlog
[`docs/audits/remaining_audit_items.md`](../../../../docs/audits/remaining_audit_items.md).

## Tasks

| # | Issue | Task | Findings | Priority | Guide |
|---|-------|------|----------|----------|-------|
| 1 | [#185](https://github.com/Danube-Labs/javv/issues/185) | Input-validation: triage + decision vocabularies | A-M1, A-M2, A-m7, A-m8, A-n(caps) | high | [task-1](task-1-input-validation.md) |
| 2 | [#186](https://github.com/Danube-Labs/javv/issues/186) | Projection concurrency — `reproject_cve` guarded RMW | A-M3, A-m10 | high | [task-2](task-2-reproject-cas.md) |
| 3 | [#187](https://github.com/Danube-Labs/javv/issues/187) | SLA D21 group-clock sibling truncation | A-M4 (both passes) | high | [task-3](task-3-d21-group-clock.md) |
| 4 | [#188](https://github.com/Danube-Labs/javv/issues/188) | Audit-log completeness (D17) + last-admin race | A-M5 (both passes), A-m3 | high | [task-4](task-4-audit-completeness.md) |
| 5 | [#189](https://github.com/Danube-Labs/javv/issues/189) | Export & read-path DoS bounding | A-M6 (both), A-Mc ⚠️, A-m12 | high | [task-5](task-5-export-dos-bounding.md) |
| 6 | [#190](https://github.com/Danube-Labs/javv/issues/190) | Contributors correctness | A-m4 (both), A-m5 | medium | [task-6](task-6-contributors.md) |
| 7 | [#191](https://github.com/Danube-Labs/javv/issues/191) | Read-path robustness — cursor errors + refresh storm | A-m1, A-m2 | medium | [task-7](task-7-read-robustness.md) |
| 8 | [#192](https://github.com/Danube-Labs/javv/issues/192) | Hardening & hygiene batch | A-m6, A-m9, A-m11, A-m13, A-n | low | [task-8](task-8-hardening-batch.md) |

**Task 5's A-Mc was decided (2026-07-06): bounded-synchronous** — delete the async 202 path, apply
synchronously up to `JAVV_BULK_INLINE_LIMIT` (5000), 413 above, hard-cap the freeze at
`JAVV_BULK_MAX_TARGETS` (10000). Truly-huge scheduled bulk defers to M7. No open rulings remain; the
guide is a single concrete path.

## Recommended order

1. **Task 1 → 2 → 3** first — these produce invalid VEX exports, live 500s on races, and a silently
   wrong headline SLA number *today*. Highest user-visible correctness impact.
2. **Task 4** (audit integrity is a correctness contract, D17) and **Task 5** (DoS bounding) next.
3. **Task 6, 7** as capacity allows.
4. **Task 8** batches the small stuff — pick it up alongside any bolt touching those files.

Each task is independent (different files) except: Task 2 and Task 8's "reproject assert" overlap
in `decisions/reproject.py` (Task 2 owns that file — A-m10 moved into Task 2's guide); Task 5 and
Task 7 both touch PIT lifecycle (Task 5 = concurrency cap, Task 7 = error handling — coordinate the
`query/search.py` edits if done in parallel).

## Conventions every task MUST follow (do not skip)

These are the DoD floor on top of [`definition-of-done.md`](../../../../development/standards/definition-of-done.md):

- **TDD.** Every fix lands with a test that FAILS before it and passes after. For the reproduced
  race (Task 2) the failing test already exists and is flaky-red — pin it green. Use the
  `test-driven-development` skill.
- **Logging — the shared library ONLY.** `structlog.get_logger()` on the `libs/javv-common`
  pipeline; add domain-event / anomaly log lines where these fixes introduce a new failure mode
  (e.g. "reproject retried to N conflicts", "export capped at N rows", "sibling clock fetch
  truncated"). **Never `print()`, never `logging.getLogger()`, never a private setup**
  ([observability.md §1](../../../../development/standards/observability.md)). Query strings / OpenSearch bodies /
  tokens never logged; redaction stays broad (fix call sites, never the regex).
- **Every new knob → `docs/CONFIGURATION.md` in the same PR.** Tasks 5 and 6 introduce `JAVV_*`
  env knobs (specified in their guides) — add the row (default · how set · UI-controllable) the
  moment you add the setting to `core/settings.py`. If a limit *can* be a knob, make it one and
  document it rather than hardcoding.
- **Tenancy & per-scanner stay sacred.** Every read/agg/export keeps its `cluster_id` filter via
  the `tenant_search`/`tenant_query` chokepoint; never merge scanners.
- **Mapping changes** (none expected here) → `MAPPING_VERSION` (8) + INDEX-MAP + in-code history
  comment. **New mutating endpoint** → the RBAC/IDOR contract registry
  (`tests/security/test_rbac_idor_contract.py`). None of these tasks should add a mutating route,
  but Task 5's durable-bulk option might — flag it if so.
- **Commit hygiene.** Subject lowercase after `type(scope):` (commitlint rejects an uppercase-first
  subject — `fix(m5c): …` not `Fix(m5c): M-3 …`); types `feat|fix|chore|docs|test|refactor` (no
  `perf`). One `Refs #<task-issue>` per PR (these are audit tasks, not a bolt — do not write
  `Closes #66`).

## Labels

Issues carry `audit` + a `priority:*` + `security` where relevant (authz / DoS / audit-integrity).
NOT the `bolt` label — that is reserved for the M0–M10 build milestones; these are remediation
tasks, same convention as the #138–#144 wave.
