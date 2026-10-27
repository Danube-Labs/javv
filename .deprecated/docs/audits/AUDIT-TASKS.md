# Audit remediation — task tracker

> Consolidated backlog from the two independent audits of M4/M5a/M5b (2026-07-04): the Fable 5
> two-agent pass (`audit-2026-07-04-m4-m5a-m5b.md`) and the Codex pass (`../../.codex/audit_codex.md`).
> ~24 raw findings deduplicated + grouped into **7 tasks by where the fix lives** — each task is
> roughly one PR. Bolt-style: substance here, a tracker issue per task. **Both audits returned
> GO / no blockers** — nothing here blocks M5c; this is hardening + hygiene, sequenced below.

## Recommended order

1. **Task G** (#144) — doc/spec drift. Cheap, docs-only, **do before M5c** so the next bolt starts from correct instructions.
2. **Task A** (#138) — triage/audit correctness. Safety-critical; M5c extends this exact layer.
3. **Task D** (#141) — needs an operator decision (build vs defer) before it can be actioned.
4. **Tasks C / E / F** (#140 / #142 / #143) — hardening + ops robustness, any order.
5. **Task B** (#139) — rollover×idempotency; isolated, low-likelihood, do when convenient.

Cross-links: perf storm → #117 · risk register (e2e smoke, monoculture, TLS landmine) → #134.

---

## Task A — triage + audit-log correctness · **HIGH** · [#138](https://github.com/Danube-Labs/javv/issues/138)
The correctness cluster in `triage/service.py` · `decisions/lifecycle.py` · `audit/writer.py`.
- **M-1** — a `vex_justification`-only correction on an already-`not_affected` finding is silently dropped (the `patch.state != current_state` no-op guard eats it). Write + journal it.
- **M-2** — decision revoke/edit is check-then-act with no CAS → concurrent revokes overwrite the immutable `revoked_at`; concurrent edits leave two active decisions. CAS the revoke.
- **M-3** — D17 completeness under partial failure (**both agents found this**): audit rows append *after* the CAS write; a mid-flight failure orphans a change the retry can't repair. Journal-before-commit or re-emit on retry-no-diff; add the fault-injection test.
- **n-2 (carry-forward)** — M5c must register the new decisions endpoints in the standing RBAC/IDOR suite.

## Task B — append-series idempotency across rollover · **MAJOR** · [#139](https://github.com/Danube-Labs/javv/issues/139)
`index`-action idempotency (deterministic `_id`) holds only *within one backing index*. A retried envelope straddling a monthly rollover creates a duplicate scan-events/image doc (same `_id`/`commit_key`/`scan_order`) in the new index; wildcard reads match both → trend double-count. Dedup catalog/trend reads by `commit_key`; add the missing re-push-after-rollover test.

## Task C — auth hardening bundle · **MEDIUM** · [#140](https://github.com/Danube-Labs/javv/issues/140)
Use the security-and-hardening skill.
- **m-1** lockout map unbounded within the window → hard-cap + evict.
- **m-2** `revoke_all_for_user` UBQ has no conflict retry → a stolen session can survive logout-all. Retry to zero.
- **m-8** login-CSRF (`SameSite=Lax` doesn't stop a cross-site login POST) → double-submit token or accept + document.
- **m-10** "one session per browser" claimed but not implemented → revoke-prior-on-login or fix the claim.
- **Codex M3** `JAVV_TOKEN_PEPPER` dev default has no fail-fast → profile-aware startup guard.
- **n-1** `tenant_query` forwards `params` verbatim (`q=`/`global` agg could sidestep the filter) → guard before per-user cluster grants land.

## Task D — admin user/role management + role-change session revocation · **HIGH · DECISION NEEDED** · [#141](https://github.com/Danube-Labs/javv/issues/141)
Flagged by **both** audits (Fable m-9 / Codex High-1): M5a promises admin user/role endpoints + "role-change revokes sessions"; only login/logout/me/password shipped, and nothing calls the (existing, tested) `revoke_all_for_user`. Mitigation: caps/`disabled`/`must_change` re-read per request, so it's belt-not-load-bearing. **Operator picks:** (a) **defer** — mark the DoD items deferred to the admin-UI era, document in M5a Out-of-scope *(recommended)*; or (b) **build now** — capability-gated router that revokes sessions + keeps denormalized caps consistent, registered in the RBAC suite + tested.

## Task E — token admin polish · **MEDIUM** · [#142](https://github.com/Danube-Labs/javv/issues/142)
- **m-7** mint/rotate can't set `expiry` (mapped + enforced but unreachable) → add optional `expiry` to `MintRequest`.
- **Codex M2** token `cluster_id` shape unvalidated → one shared `cluster_id` validator/type across `MintRequest`, the CLI, scan-scope, decisions, and the envelope model.
- **Codex L1** token list unpaginated (`size: 10_000`) → explicit pagination or a documented hard cap.

## Task F — lifecycle / jobs robustness · **MEDIUM** · [#143](https://github.com/Danube-Labs/javv/issues/143)
- **m-3** disagreement recompute truncates at 10k findings/digest → assert `total < size` or page.
- **m-4** retention ages indices by client `@timestamp` → a backdated clock can delete recent data. Server-side append timestamp for the age decision.
- **m-5** one malformed knobs doc aborts the sweep for **all** clusters → per-cluster catch + default fallback.
- **m-6** `system-audit-log` never rolls over (rollover deferral undocumented) → add to `SERIES` rollover-only or record it.

## Task G — spec/doc drift sweep · **HIGH-leverage / LOW-effort — before M5c** · [#144](https://github.com/Danube-Labs/javv/issues/144)
Docs + a script; no product code. The bolts drive future work, so stale instructions mislead the next agent.
- **Codex High-2** stale `backend/app/…` paths in M2/M5c/M5d/M6/M7/M8a/M8b bolts → normalize to `backend/src/backend/…`.
- **Codex M1** V4 SPEC/INDEX-MAP still say `scan_order` "scanner-assigned" (the assumption D45 removed) → patch to backend-allocated; clarify `inventory_order`.
- **Codex M4** `check-versions.sh` misses backend ruff/pyright pins → extend the drift check.
- **Codex L2** CI comments are scaffold-era → update to backend/scanner-active, frontend-absent.

---

## Not tasks (status, no action)
- **Codex M5 / UI + deploy absent** — `frontend/` and `deploy/` don't exist yet; M9/M10 are not started. UI/Helm auditable only as design intent today. (Not a defect — expected by the plan.)
- **Verified-correct lists** from both audits (sessions, oracle discipline, tenant chokepoint, RBAC suite, per-scanner sanctity, bootstrap admin, token rotate) — recorded in the two source reports; no action.
