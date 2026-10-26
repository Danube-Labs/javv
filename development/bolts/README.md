# Bolts - the build, milestone by milestone

> **Frozen as history (2026-10-26, issue 1012).** The bolts M0 to M10 ended on 2026-10-09, when
> M10 shipped. These folders do not change any more. New work follows one GitHub issue for each
> feature, with the plan and a spec file for each slice on the issue
> ([git-workflow.md](../standards/git-workflow.md)). The timeline, the rulings that still apply
> and the open work are in the [memory bank](../memory-bank/README.md).

One folder per **FIRE bolt** from [`PLAN.md` §8](../../docs/engineering/PLAN.md). Each holds a
**README only** - the execution brief (goal, deliverables, definition of done, tests). The shared rules live
in [`../standards/`](../standards/).

> **Planning/tracking only - no code here.** Milestones are a *delivery* axis, not a code-organization axis
> (M3 edits the same `services/` M1 created). Code lands in the layered tree: `backend/` · `frontend/` ·
> `scanner/` · `deploy/`. A bolt folder just says *what done looks like* and links to the code it produces.

**Authoring policy:** every bolt carries a full brief (goal · deliverables · DoD · tests), from
[`../standards/bolt-readme-template.md`](../standards/bolt-readme-template.md). There are no new bolts.

**Don't rewrite a bolt's brief once it's written** — treat the Goal/Deliverables/DoD/Tests sections as the
**spec of record**. Record progress, scope changes, and corrections as **dated entries appended under the
bolt's `## Updates` log** (`### YYYY-MM-DD — <what changed / why>`, newest last) rather than silently
editing the original. If the brief itself genuinely must change, make the edit *and* note it in an Update
entry so the history stays honest. (This keeps an audit trail and pairs with the bolt's tracking issue.)

## Order & dependencies
Order: **scanners → backend core → durability → identity/triage → read → history → frontend → deploy.**

> **Live status lives on GitHub** (AUDIT.md N8) — one **issue per bolt** (label `bolt`) on the
> **[JAVV bolts board](https://github.com/orgs/Danube-Labs/projects/1)**; each bolt README links its tracking
> issue, and merging a bolt's PR with `Closes #<n>` moves the card to Done. This table is the
> **dependency/order map** only — no status column, so nothing drifts.

| Bolt | Title | Depends on |
|------|-------|-----------|
| **M0** | Scanner modules | - |
| **M0b** | Scanner image publish + compatibility CI | M0 |
| **M1** | Backend skeleton + indexes + ingest + observability | M0 |
| **M2** | Snapshot/restore (durability early) | M1 |
| **M3** | Dedup/identity + staleness + projection *(highest risk)* | M1 |
| **M4** | Logs layer (scan-events) + retention | M1, M3 |
| **M5a** | Auth & Session *(prereq for all mutations)* | M1 |
| **M5b** | VEX two-field state machine | M5a |
| **M5c** | Decisions & projection | M5a, M3 |
| **M5d** | SLA/overdue + bulk | M5b, M5c |
| **M6** | Read/reporting + VEX export + as-of-T | M3, M4, M5c |
| **M7** | Scheduled / throttled export | M6 |
| **M8a** | Per-scan snapshot append | M3, M4 |
| **M8b** | Point-in-time query API | M8a |
| **M8c** | M9-prep session reads (audit · provenance · inventory · cluster registry) | M8b (shares its query layer) |
| **M8d** | Package type in the envelope (`ptype`) | - (lands before M9b/M9c) |
| **M8e** | Server-side saved views (`system-views`) | - (lands before M9f) |
| **M9a** | Shell + tokens + filter module | M6 |
| **M9b** | Findings grid + detail/triage *(core loop gate)* | M9a, M5b |
| **M9c** | Overview / all-clusters / images | M9b, M8b |
| **M9d** | Audit / approvals / contributors / scanner-status | M9b, M5d |
| **M9e** | Settings: Data & OpenSearch + Scanning | M9a, M2, M4 |
| **M9f** | Cross-cutting (search, bell, saved views, RBAC, empty states) | M9b |
| **M10** | Polish & deploy | all |
