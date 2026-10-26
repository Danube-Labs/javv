# M8d - Package type in the envelope (`ptype`)

**Status:** tracked in #241 — live status on the GitHub issue/board (label `bolt`)

## Goal
Add the package type (`os` vs language ecosystem) to the scanner envelope and carry it through to
findings facets/columns, restoring the v4 Overview donut + Findings package-type facet (B-1 ruling,
2026-07-07, #237). **This touches the most carefully versioned contract in the system** — the
scanner envelope — and is a lockstep change: both adapters + `schema_version` bump + backend
acceptance in one coordinated release.

**Canonical refs:** [`PLAN §8 M8d`](../../../docs/engineering/PLAN.md) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (findings + occurrences mappings) ·
D16 (raw-fidelity normalizer — `ptype` follows the same verbatim-plus-normalized pattern as
severity) · [`SCREENS`](../../../handoff/docs/SCREENS.md) §§2–3 ·
[`DATA_MODEL`](../../../handoff/docs/DATA_MODEL.md) (ptype vocabulary note)

## Depends on
- None (parallel to M8a/M8b/M8c). Must land **before M9b/M9c** wire the facet/donut.

## Deliverables
- **Scanner:** both adapters emit `ptype` per finding — Trivy from `Results[].Class`/`Type`
  (`os-pkgs` → `os`, else the ecosystem string), Grype from `artifact.type`. Verbatim-lowercase,
  vocabulary pinned in a table in this bolt's PR (extend the D16 normalizer if the two scanners
  name the same ecosystem differently — that ruling goes in the PR, per-scanner values stay
  untouched in `_source`).
- **Envelope:** `schema_version` bump; golden envelope fixtures regenerated for both scanners.
- **Backend:** accept both schema versions during the transition (old = `ptype` absent → `null`);
  findings + occurrences mappings gain `ptype` keyword (INDEX-MAP + `MAPPING_VERSION` bump +
  bootstrap tests); `/findings` filter param + `/findings/facets` bucket + `/findings/groups`
  support; `docs/API.md` same PR.
- **Reingest caveat documented:** pre-M8d findings have `ptype: null` and aggregate as "unknown"
  until the next scan cycle re-observes them (scanner scans everything every cycle, D30 — so one
  sweep heals it). UI placeholder state until then (SCREENS §2).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- Old-schema envelope still ingests green (backward-compat test) — no flag day for scanners.
- Golden envelope round-trip (M1 gate) re-passes with the new field, both scanners.
- Facet counts per ptype are **per-scanner** buckets (never merged) — test.
- `versions.yaml` untouched (this is a schema change, not a version bump) — the published scanner
  images rebuild via the normal `scanner-images.yml` tag flow.

## Tests to write
- **Unit:** both adapters' ptype extraction (os vs ecosystem vs missing → null); normalizer rulings.
- **Integration:** ingest old + new schema side by side; facets bucket correctness; null bucket.
- **Golden fixtures:** regenerated `trivy-*.json` / `grype-*.json` envelope fixtures (new
  `schema_version`), plus one kept old-version fixture pinning backward-compat.

## Out of scope (defer)
- Backfilling `ptype` onto historical occurrence rows (append-only history stays untouched;
  current-state heals via the next sweep).
- Any UI work → M9b (facet/column) / M9c (donut).

## Updates
- **2026-07-08 · slice 2 (read path)** — `SearchFilters.ptype` term → `/findings?ptype=` (route
  param + `ExportParams` mirror, forced by the one-to-one test). Facets: `ptype` joins
  `FACET_FIELDS` with a per-field **`missing: "unknown"`** bucket (the B-1 reingest caveat made
  visible — pre-v4 nulls surface instead of vanishing; `_FACET_TERMS_SIZE` 16→32, ptype's
  ecosystem vocabulary is the widest). Groups: `ptype` joins `GROUP_FIELDS` (nulls skipped —
  drill-down semantics). As-of-T: unlike `kev`/`epss`, ptype **is recorded on occurrences**, so
  the reader treats it as a real reconstructed field — `_finding_row` passthrough, filterable
  (v3-era rows honestly drop out), facetable (unknown-bucket mirrored), groupable; `ptype`
  added to the I11 keystone's RECONSTRUCTABLE set (T=now reconstruction == cache on it too).
- **2026-07-08 · slice 1 (write path)** — the lockstep core. **Vocabulary ruling (the PR
  table):** `ptype` = `"os"` (Trivy `Class == "os-pkgs"`) or the scanner's verbatim-lowercase
  ecosystem string (Trivy `Type` → `python-pkg`/`node-pkg`/…; Grype `artifact.type` →
  `apk`/`deb`/`rpm`/`python`/…); **no cross-scanner folding of language ecosystems** — per-scanner
  is sacred and facet buckets never merge, so name alignment is cosmetic; the D16 normalizer
  extension stays unneeded until a real UI collision appears. Scanner `SCHEMA_VERSION` 3→4;
  backend accepts **`Literal[3, 4]`** — the one deliberate departure from current-envelope-only
  (D25/D35; v3 was a flag day, D44), because operators swap images at their own pace (D41):
  a v3 envelope stays green with `ptype: null`, and the next v4 sweep heals the cache nulls via
  the D31 merge (proven by a store test, not narrated). `ptype` is shape-constrained at the edge
  (`^[a-z0-9][a-z0-9+._-]*$`, ≤64 — untrusted input into a keyword facet). Mappings: findings +
  occurrences gain the keyword, MAPPING_VERSION **13**, INDEX-MAP rows same change. Golden
  regenerated at v4 (+ `envelope-trivy-v3-golden.json` pinned for the backcompat test). The
  2026-07-07/08 `schema_version` test-coupling notes below are **defused by dual acceptance** —
  v3-seeding helpers stay green, nothing broke on the bump.
- **2026-07-07** — hidden test coupling to check when bumping `schema_version`: the M7 report tests
  seed findings docs directly with a hardcoded `schema_version: 2` (the `_finding()` helpers in
  `backend/tests/test_report_drain.py` and `test_report_bulk_kind.py`) — grep for `schema_version`
  under `backend/tests/` and update every direct-seed helper in the same PR, or the suite breaks on
  the bump.

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
