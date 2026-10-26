# M8e - Server-side saved views (`system-views`)

**Status:** tracked in #242 — live status on the GitHub issue/board (label `bolt`)

## Goal
Durable, shareable saved filter views — a product selling point (C-6 ruling, 2026-07-07, #237).
New `system-views` index + CRUD endpoints; the M9f Saved-views screen consumes them. View
definitions are tiny filter serializations — the **counts** shown on view cards remain server
aggregations (`/findings/facets`), so no server-side-everything rule is touched.

**Canonical refs:** [`PLAN §8 M8e`](../../../docs/engineering/PLAN.md) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (**new index — add it there first**,
design-integrity rule) · D17 (journaled mutations) ·
[`SCREENS §6`](../../../handoff/docs/SCREENS.md) ·
[`DATA_MODEL`](../../../handoff/docs/DATA_MODEL.md) (view shape)

## Depends on
- None (parallel to the other M8x). Must land **before M9f** wires the screen; M9b's "Save view"
  toolbar button posts here too.

## Deliverables
- **Index:** `system-views` — `dynamic:false`, explicit mapping (`view_id`, `name`, `description`,
  `preset` as a serialized filter object, `owner` keyword, `created_at`/`updated_at`); INDEX-MAP
  entry + `MAPPING_VERSION` bump + bootstrap + bootstrap tests. Single small index, no rollover,
  never dropped by retention (mutable-family rules).
- **Endpoints** (`backend/src/backend/routers/views.py`): `GET /api/v1/views` (session; all views
  visible to all authenticated users) · `POST /api/v1/views` (session; owner = principal) ·
  `PATCH /api/v1/views/{view_id}` · `DELETE /api/v1/views/{view_id}` (**owner-or-admin**; 403
  otherwise — the IDOR case). Presets validated at the edge (`extra="forbid"`; filter values
  against the closed vocabularies — lowercase severities incl. `negligible`, 6 states).
- Mutations journaled (D17, journal-before-commit per A-M5).
- RBAC/IDOR registry rows · `docs/API.md` rows (same PR).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- IDOR test: non-owner PATCH/DELETE → 403; admin override works; owner immutable after create.
- Preset round-trip test: saved preset → Findings query params → identical results (the deep-link
  contract SCREENS §6 requires).
- Garbage preset (unknown severity/state/field) → 422, never stored.

## Tests to write
- **Unit:** preset validation (closed vocabularies, forbid extras); ownership rules.
- **Integration (real OpenSearch):** CRUD lifecycle; owner/admin/other matrix; journal rows
  present; bootstrap idempotency with the new index.
- **Golden fixtures:** one canonical preset serialization pinned (guards accidental format drift —
  presets outlive UI versions).

## Out of scope (defer)
- Per-view sharing ACLs / private views (all views visible to all users in MVP).
- View folders/tags; default-view-per-user; UI → M9f.

## Updates
- **2026-07-08 · slice 2 (owner-or-admin mutations + round-trip)** — `PATCH/DELETE
  /api/v1/views/{view_id}`: owner OR `can_manage_settings` (admin `*` covers it); anyone else =
  the 403 IDOR case; `owner` is **unrepresentable** in the patch body (`extra=forbid` — not just
  forbidden, unwritable); both journal-FIRST with the frozen before/after riding the row (a
  deleted view stays auditable). PATCH is a **seq_no-CAS** whole-doc update — a concurrent edit
  is 409 reload-and-retry, never a silent lost update (raced-PATCH test). Golden preset
  serialization pinned (`view-preset-golden.json` — drift breaks every stored view). The §6
  deep-link round-trip proven: a stored preset's non-null fields ARE `/findings` query params
  and return identical rows to the direct query. **Side-find while proving the round-trip
  (NOT M8e's, filed separately):** the grid severity filter term-matches the verbatim-lc word
  (`critical`/`medium`) while the canonical vocabulary says `crit`/`med` — real ingested rows
  don't match a `crit` filter; M6-era, latent because route tests seed canonical words directly.
- **2026-07-08 · slice 1 (store + create/list)** — **naming ruling:** the brief +
  DATA_MODEL (C-6 docs) say `system-views`; INDEX-MAP carried a pre-ruling
  `system-saved-views` per-user sketch — the ruled name **`system-views`** wins and the
  INDEX-MAP row was rewritten first (design-integrity rule), with the real shape (all-visible,
  owner-or-admin, `preset` `{enabled:false}` — fetched by `_id`/list, never queried by innards).
  **`preset: {filters, q}`** (DATA_MODEL sketch): `q` deliberately dropped — no server text
  query exists (the chokepoint refuses `q=`, SEC-4) and the §6 deep-link contract is
  query-params-only; preset = the **SearchFilters mirror** (mirror-tested, the ExportParams
  pattern — `ptype` from M8d joins automatically). Closed-vocabulary validation at the edge
  (lowercase canonical severities incl. `negligible` via `SEVERITY_RANK`, the 6 `STATES`,
  `Literal` scanners, the M8d ptype shape; `extra="forbid"`); garbage 422, never stored.
  Create is journal-first (`view_create` row, D17/A-M5, `cluster_id="fleet"` — a preset carries
  no cluster). MAPPING_VERSION **14**. POST is EXEMPT-listed (any authenticated user saves;
  owner = principal); slice 2's PATCH/DELETE carry the owner-or-admin IDOR matrix.

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
