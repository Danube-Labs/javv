# M9e - Settings: Data & OpenSearch + Scanning

**Status:** tracked in [#39](https://github.com/Danube-Labs/javv-poc/issues/39) — live status on the GitHub issue/board

## Goal
The whole **Settings** area per `SCREENS.md` §13: the Admin **Data & OpenSearch** panel
(per-`cluster_id` retention, rollover knobs, snapshot repo/schedule + manual snapshot/restore, the
read-only *OpenSearch runtime* card), the **Scanning** settings (two-timer staleness editor +
read-only per-scanner provenance/`effective_config` cards), **Scan scope**, **SLA policy**,
**Access & tokens**, **Users & roles**, **Cluster** — plus the settings sub-nav shell
(capability-hidden sections, save bar on editable sections only). *(The Ignore-rules → Decisions
redirect stub was REMOVED by operator ruling 2026-07-15 — see Updates; no 13.4 nav entry at all.)*
Retention is enforced by **dropping whole time-partitioned indices — never
`delete_by_query`** (hard constraint). Every destructive action is capability-gated and journaled.
*(The pre-v5 "CVE-audit panel" was STRUCK 2026-07-15 — see Updates: no prototype, no §13 section,
no FR; its content ships on finding detail + Approvals + Audit.)*

**Canonical refs:** [`PLAN §8 M9e`](../../../docs/engineering/PLAN.md) ·
`SPEC` FR-19 (Data & OpenSearch settings, D26), FR-6 (staleness timers D20),
NFR-6 (snapshot/restore + independent retention horizons) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (`system-config` **[reads/writes knobs]**, time-partitioned
append families `javv-finding-occurrences-*` / `javv-scan-events-*` / `javv-images-*` / `javv-inventory-runs-*`;
`system-audit-log-*` **keep long**; lifecycle knobs) · decisions D20, D26, D37/M12 (stale=flag; delete only on long retention).

## Depends on
- **M9a** (shell + tokens + reusable filter/form module; capability-gated client routing).
- **M2** (snapshot/restore backend + ISM policy application — the M2 restore gate; this panel drives it).
- **M3** (two-timer staleness machinery + `system-config` `staleness` doc whose knobs this panel edits — **backend shipped**: `jobs/staleness.py` sweep + `read/write_staleness_timers` + interim CLI).
- **M4** (lifecycle machinery + `system-config` `lifecycle` doc whose knobs this panel edits — **backend shipped**: `jobs/lifecycle.py` sweep + `read/write_lifecycle_knobs` + interim CLI; no ISM policy re-apply glue needed).

## Deliverables
In the layered tree, not here (paths proposed):
- `frontend/src/views/settings/DataOpenSearchView.vue` — per-`cluster_id` `retention_days`; rollover knobs (doc count / age / size; defaults ~40 GB / 30 d / 50 M docs); snapshot repo + schedule + manual snapshot/restore buttons. **Retention/rollover controls apply to the time-partitioned append families ONLY** — the mutable family (`findings`, `javv-scan-watermarks`, **`javv-scan-orders`** (D45 — no retention EVER, it's the authoritative order counter), `system-*`) must never be offered a rollover/drop control; `findings`' only cleanup is the separate LONG-window `delete_by_query` (D37/M12), not a retention drop.
- `frontend/src/views/settings/ScanningView.vue` — two-timer staleness editor (FR-6/D20); both windows editable; preview of resulting banner behavior. **Backend already shipped (M3):** the `system-config` `staleness` doc (`freshness_days` N=3, `scanner_down_days` M=7), `jobs/staleness.py` daily sweep, and `read/write_staleness_timers` + interim CLI — this bolt adds the UI + the RBAC-gated `PUT /settings/staleness` (capability-gated, journaled). The "scanner silent since T'" banner is a read-time view (computed from `last_ingest_at`), not written by the sweep. Per-scanner cards show the **read-only running version + DB freshness** (from the ingested `scanner_version`/DB provenance) — **not a version-select control**; the version is changed by swapping the published image tag (D41). Also shows the **read-only effective scan *tuning* flags + applied scope** from the `effective_config` stamp (**landed** — D44/FR-25, schema v3): read it off the latest committed scan-event doc's `_source` (the field is `enabled:false` — display-only, not aggregatable). Display only; tuning stays env/GitOps.
- `frontend/src/views/settings/ScanScopeView.vue` — **Scan scope editor (D43/FR-24, #94)**: per-cluster include/ignore **namespaces**, excluded **image globs**, ignored **kinds** → `PUT /api/v1/scan-scope`. Backend read path + `system-config` storage + interim CLI already shipped (PR #95); this bolt adds the UI + the RBAC-gated **`PUT /api/v1/scan-scope`** (capability-gated, journaled to `system-audit-log`). Semantics are fixed by FR-24: empty include = all, ignore wins, fail-closed scanner fetch.
- ~~`CveAuditView.vue`~~ — **STRUCK 2026-07-15** (operator ruling, row 24): no prototype screen, no
  §13 section, no FR — per-CVE disagreement/decision-provenance already ships on finding detail
  (evidence + Decisions card + activity), `/approvals`, and `/audit`.
- **The §13 panels previously missing from this list (spec-sync 2026-07-15):**
  `SlaPolicyView.vue` (13.3 — backend shipped incl. routes; gate is `can_manage_settings`),
  `TokensView.vue` (13.5 — shipped incl. rotate; raw-token-once mint modal),
  `UsersRolesView.vue` (13.6 — shipped; disable-never-delete, invite = temp password, 4 read-only
  capability bundles per A-4), `ClusterView.vue` (13.8 — rename shipped M8c; statics show
  `schema_version` 4), the **settings sub-nav shell** (capability-hidden sections, save bar on
  editable sections only). ~~The Ignore rules → Decisions redirect stub (13.4)~~ — shipped in
  slice 1, then **REMOVED entirely** (operator ruling 2026-07-15, against the built specimen):
  decisions live on `/approvals` + finding detail; a settings pointer earns its nav slot nothing.
- **Data panel additions (2026-07-15 rulings):** the retention card lists **every** index family —
  protected families render read-only with a hover/why (table row 23); a read-only **OpenSearch
  runtime** card (version, nodes/roles, heap, `discovery.type`, `path.repo`, security state) behind
  a new backend proxy read (§D ruling); the **report/export TTL** knob graduates from
  `JAVV_EXPORT_TTL_HOURS` into `system-config` (row 11, env stays the seed).
- **Freshness-banner rewire (row 14):** the FE banner reads the live staleness timers via the API;
  `VITE_FRESHNESS_BANNER_HOURS` is removed.
- `frontend/src/composables/useRetentionForm.ts`, `useSnapshotForm.ts` — pure validators/option-builders (unit-tested).
- Backend (if not delivered by M2/M4): `PUT /settings/retention`, `PUT /settings/rollover`, `POST /snapshots`, `POST /snapshots/{id}/restore`, `PUT /settings/staleness`, the **scan-scope session `GET`** (D-2) + `PUT /api/v1/scan-scope`, the **OpenSearch-runtime proxy read**, the **report-TTL knob** — capability-gated (`can_manage_retention`, `can_restore_snapshot`, `can_drop_index`, `can_manage_settings`) and journaled to `system-audit-log`.
- ~~ISM-policy apply/update glue~~ **not needed** (M4 mechanism decision): the panel just writes the
  `lifecycle`/`lifecycle:<cluster_id>` knob docs in `system-config` (M4's `read/write_lifecycle_knobs`);
  the daily `jobs/lifecycle.py` sweep reads them live and **drops whole indices** at horizon — an edit
  takes effect at the next sweep with no re-apply step.
- `backend/jobs/findings_cleanup.py` — the **long-window `findings` cleanup CronJob (D37/M12)**: `delete_by_query` on `findings` rows (+ their `javv-scan-watermarks` docs) whose image has been gone from inventory / `present=false` for the **long** retention window (a `system-config` knob this panel edits; independent of, and much longer than, the staleness timers). This is the job that bounds the `findings` plateau — **never** runs on the freshness timer, k8s CronJob `Forbid`, journaled to `system-audit-log`. *(Ownership was previously implied by D37/M12 but unowned — landed here because it pairs with the retention panel that configures it.)*

## Settings surface — full candidate table (2026-07-15, RULED — the cherry-pick record)

> Every config surface JAVV has (or the v4 prototype imagined), cross-checked against the code,
> `CONFIGURATION.md`, `SCREENS.md` §13 and the rulings (C-4/D41/D43/A-4). All rows RULED by the operator
> 2026-07-15 (this session); §Deliverables above reflects the rulings. Kept as the decision record.

**A. Ruled-in editable (§13) — backend built, mostly UI-only work**

| # | Pick | Section | Setting | Backend | Missing pieces |
|---|---|---|---|---|---|
| 1 | ruled ✔ | Data & OS | `retention_days` (per cluster, ONE window over the 4 append families) | ✅ M4 | route (`PUT /settings/retention`) |
| 2 | ruled ✔ | Data & OS | rollover `max_age_days`/`max_docs`/`max_size_gb` | ✅ M4 | route (`PUT /settings/rollover`) |
| 3 | ruled ✔ | Data & OS | snapshot repo ref · schedule · retained count · manual snapshot/restore | ✅ M2 machinery + CLI | routes (`POST /snapshots`, `…/restore`) |
| 4 | ruled ✔ | Scanning | staleness `freshness_days`/`scanner_down_days` (+ per-cluster override) | ✅ M3 | route (`PUT /settings/staleness`) |
| 5 | ruled ✔ | SLA | days per severity + KEV hours | ✅ incl. routes | UI only. Gate is `can_manage_settings` (admin bundle) — the prototype's "Security Lead can edit" copy is wrong |
| 6 | ruled ✔ | Scan scope | include/ignore namespaces · image globs · kinds · running-only | ✅ storage + scanner GET + CLI | **session `GET` (D-2, unowned until now — landed here)** + `PUT /api/v1/scan-scope` |
| 7 | ruled ✔ | Access & tokens | token list/mint/rotate/revoke (+ optional expiry at mint) | ✅ incl. routes | UI only (raw-token-once modal) |
| 8 | ruled ✔ | Users & roles | create / role change / disable / password-reset | ✅ incl. routes | UI only. Prototype deltas: **disable, never delete** (no delete API); "Invite" = create-with-temp-password; 4 capability **bundles**, not the 5-role matrix (A-4) |
| 9 | ruled ✔ | Cluster | `cluster_name` rename (`cluster_id` immutable) | ✅ M8c incl. route | UI only. Statics: ingest endpoint, API `/v1`, `schema_version` **4** (prototype says 3) |
| 10 | ruled ✔ | Data & OS | **findings long-window cleanup days** (D37/M12) | ❌ knob + job are THIS bolt's deliverable | `jobs/findings_cleanup.py` + knob + panel input |

**B. Graduation candidates — RULED 2026-07-15 (operator)**

| # | Pick | Setting | Today | Ruling |
|---|---|---|---|---|
| 11 | ✔ graduate | Report/export retention (`JAVV_EXPORT_TTL_HOURS`, 24h) | tier-② env | → `system-config` knob in the Data panel (M9e; env stays as the default seed) |
| 12 | ✘ defer | Session TTL (`JAVV_SESSION_TTL_HOURS`) | env | → post-MVP settings issue **#403** |
| 13 | ✘ defer | Login lockout (attempts/window) | env | → post-MVP settings issue **#403** |
| 14 | ✔ kill | FE freshness banner hours (`VITE_FRESHNESS_BANNER_HOURS`) | build-time env | M9e work item: the banner reads the live staleness timers via the API; the VITE var is removed (not graduated) |

**C. Prototype-only — RULED 2026-07-15 (operator)**

| # | Ruling | Prototype control | Reality | Fate |
|---|---|---|---|---|
| 15 | ✘ drop | Scanner **version select** | violates D41 | read-only provenance display (C-4) |
| 16 | read-only MVP | Scanner tuning writes (severities/ignore-unfixed/pkg-types/timeout/scope/only-fixed) | C-4: env/GitOps | MVP = the read-only `effective_config` card (already a deliverable); **writable tuning via the D43 fetch pattern → post-MVP settings issue **#403**. `CONFIGURATION.md` §3/§4 "Phase 2 UI" arrows reconciled to this |
| 17 | ✘ drop | Scanner **enable/disable** toggle | no such concept (both CronJobs always run, D30) | dropped |
| 18 | ✘ drop | **Schedule** section (scan interval, sweep time) | CronJob schedule = GitOps manifest; scanner-status already shows observed cadence | dropped. **Reasoning superseded for the backend's sweeps (issue 691, 2026-10-02):** they are no longer CronJobs; the backend runs them on cron schedules from env vars. The schedules are still not editable in the UI, so the section stays dropped; the scan interval is still the scanner CronJob's manifest |
| 19 | ✘ drop | Retry/backoff toggle | always-on ingest behavior | dropped |
| 20 | ✘ removed | **Ignore rules** table (+ KEV/EPSS always-surface override) | superseded by Decisions (V4-DELTA-2, §13.4) — live today on `/approvals`, finding detail's Decisions card, `/audit` | ~~redirect stub~~ → **no nav entry at all** (operator re-ruled 2026-07-15 against the built stub) |
| 21 | ✘ defer | **Vuln-DB config** (mirror/repo URLs, refresh cadence, skip-update, CA cert, max-built-age) | **entirely unbuilt** — not even env vars; only provenance display exists | → post-MVP settings issue **#403** (air-gapped mirrors) |
| 22 | ✘ defer | **Registries** (imagePullSecrets auto-resolve, known-registries list) | **entirely unbuilt**, unruled — §13.5 silently dropped it | → post-MVP settings issue **#403** (private-registry scanning) |
| 23 | ✔ single + read-only rows | **Per-purpose retention** (prototype drew 4 editable windows) | backend = ONE `retention_days` per cluster; audit-log rollover-only (task F m-6) | **RULED: the retention card lists EVERY index family** — the 4 append families share the one editable window; the protected families (`system-audit-log` "rolls, never dropped" · `findings` "cleaned by the separate D37 long window below" · `javv-scan-watermarks` "prunes with findings" · `javv-scan-orders` "never — authoritative order counter, D45" · `system-*`) render as **read-only rows with a hover/explanation** of why. Per-family editable windows stay post-MVP (time-travel reach = min(occurrences, images) — the footgun) |
| 24 | ✘ STRUCK | CVE-audit panel (`CveAuditView`) | no prototype screen anywhere, no §13 section, no FR; per-CVE disagreement/provenance already live on finding detail + `/approvals` + `/audit` | struck from Goal + Deliverables |

**D. Never-WRITABLE — but surfaced read-only where possible (RULED 2026-07-15):** version picks
(D41) · tuning writes (C-4) · OpenSearch static settings · secrets (never shown at all) · the
tier-② DoS/abuse ceilings · §8 frozen constants. **Operator ruling: anything unwritable that CAN
be displayed, IS displayed read-only with an explanation** — so the Data & OpenSearch panel gains a
read-only **"OpenSearch runtime" card** (new deliverable): version, node count/roles, JVM heap,
`discovery.type`, `path.repo`, security-plugin state — via a backend proxy read
(`GET _nodes`/`_cluster/settings` behind a new capability-gated endpoint; server-side everything,
the client never talks to OpenSearch). Full static-settings **drift-display** (live vs. desired +
"pending redeploy" banner, option (A) of the #39 research) stays post-MVP.

## Definition of Done
Every screen this bolt ships inherits the UI conventions settled in M9a-M9c: [`ui-foundations.md`](../../standards/ui-foundations.md) **Audit rules** (honest errors, contract guards, restorable state, the D28 semantics surface via `IngestLens`, provenance stamps on now-claims, silence-is-a-bug) and the shared M9 surfaces (filter module, table skin, kit controls) - reuse them, never re-solve.

Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test):
- **Retention = drop whole indices (keystone):** applying a `retention_days` change results in expired time-partitioned indices being **dropped whole** by the lifecycle sweep (`indices.delete`); a test asserts the retention path **never** issues a `delete_by_query` against append families (hard constraint).
- `stale` and **delete** are independent: changing the staleness timer flips the `stale` flag only; `findings`/occurrences docs are removed solely on the separate long retention window (D37/M12).
- Destructive actions (retention change, drop, restore) are **rejected without the matching capability** server-side (`can_manage_retention`/`can_drop_index`/`can_restore_snapshot`) and each appends a `system-audit-log` entry.
- Scan-scope writes (`PUT /api/v1/scan-scope`) are capability-gated + journaled; a round-trip test proves a UI-saved scope is what `GET /api/v1/scan-scope` then serves the scanner (D43/FR-24).
- Snapshot → restore round-trips against a real container (reuses/extends the M2 restore drill).
- Rollover-knob writes land in `system-config` (`lifecycle`/`lifecycle:<cluster_id>`) and are picked up by the next lifecycle sweep — asserted end-to-end (write knob → run sweep → behavior changed).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** retention/rollover/staleness form validators (against M4's `LifecycleKnobs` bounds).
- **Integration (real OpenSearch):** apply retention policy → expired index dropped whole, survivors intact; capability-gated 403 paths; snapshot/restore round-trip; staleness-timer flip changes flag without deleting docs.
- **Golden fixtures:** a retention config → expected `lifecycle` knob doc + the sweep's delete decision (regression guard that the action stays `delete` of the index, never `delete_by_query`).

## Out of scope (defer)
- Full index-management UI (per-index ILM browser) → v1.x (FR-19 note).
- Snapshot/restore backend internals + the restore gate → M2 (this bolt is the panel + glue).
- VEX import config → v1.1.

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates
- **2026-10-16: issue 403 closed as not planned (operator).** A check against the code on that
  date: rows 21 and 22 of the table above are no longer "entirely unbuilt". The `javv-scanner`
  chart sets the vulnerability database sources (`trivy.vulnDb.repository`, `.javaRepository`,
  `grype.vulnDb.updateUrl`, issue 741) and a registry login for private images
  (`<scanner>.registryAuth.existingSecret`, issue 739). The other deferred rows stay as they are:
  scanner tuning stays in the chart (row 16), session time and sign-in lock stay deployment
  settings (rows 12 and 13), retention stays one window for each cluster (row 23), and the
  OpenSearch card shows only live values (section D). To read the `imagePullSecrets` of each pod,
  the scanners must read Secrets, and issue 725 ruled that out.
- **2026-10-06: the backend runs these jobs itself (D47, issue 691):** the CronJobs this
  bolt names were never built. The backend starts each job on its cron schedule
  (`JAVV_JOB_<KIND>_CRON`, `jobs/scheduler.py`); `python -m backend.jobs.<name>` still runs one
  by hand. Issue 754.
- **2026-07-16 (slice 5, bolt wrap) — the findings-cleanup sweep landed; M9e complete.**
  `run_findings_cleanup` in `jobs/findings_cleanup.py` (the knob shipped in slice 4): the ONE
  sanctioned `delete_by_query` on `findings` reaps rows `present=false` whose **`resolved_at`**
  (the reconcile "gone since" stamp — set by `services/reconcile.py`, cleared by the merge on
  re-appearance, rebuilt by rebuild-state) predates `now - cleanup_days`; unstamped absent rows
  are never deleted (fail-closed). Watermarks prune alongside (INDEX-MAP): only when
  `max_committed_scan_at` predates the same cutoff AND zero findings rows remain for the digest —
  a live clean image's watermark stays fresh via the per-cycle CAS bump; the delete is
  seq-no-guarded so a racing commit wins. Each run appends one `system-audit-log` row
  (`findings_cleanup_run`, counts in `new_value_json`). Entrypoint
  `python -m backend.jobs.findings_cleanup` (k8s CronJob `Forbid` = M10's manifest). Tests
  (`test_findings_cleanup.py`, real-store prefix-isolated): reap selectivity (present/stale/
  recent/unstamped all survive), live-knob pickup, idempotence, watermark prune matrix,
  history-untouched keystone, source tripwire (exactly one `delete_by_query`, never
  `indices.delete`), journal row. **DoD sweep re-checked:** every bullet has its automated test
  (lifecycle keystone + tripwire · stale⟂delete · RBAC 403s + journal · scan-scope round-trip ·
  restore drill · knob→sweep end-to-end). CONFIGURATION.md row flipped to shipped.
- **2026-07-15 (post-slice-3) — slice-5 re-review (operator-requested) + re-slice ruling:**
  both slice-5 halves verified still needed against code + design docs (`findings_cleanup.py`
  unbuilt, no other `delete_by_query` touches `findings`; D37/M12 + INDEX-MAP + this README's DoD
  all stand). **Ruling: the freshness-banner rewire (row 14) moves INTO slice 4** — slice 3 shipped
  the live staleness editor, so the build-time `VITE_FRESHNESS_BANNER_HOURS` banner now ignores
  what the panel edits (a user-visible inconsistency today); the rewire is small (the pure
  functions already take `thresholdS` as a parameter) and closes it. **Design point ruled with it:
  the banner uses the selected cluster's *effective* timers** (per-cluster overrides exist), not
  the fleet default. Slice 5 = `findings_cleanup.py` + bolt wrap only.
- **2026-07-15 (build-time, slice 3) — two operator rulings against built specimens:**
  1. **Ignore-rules nav entry REMOVED entirely** (supersedes the slice-1 redirect stub and table
     row 20's "stub" ruling): decisions live on `/approvals` + finding detail — a settings pointer
     earns its nav slot nothing.
  2. **Namespace scope lists are EXACT matches** (verified in `scanner/scope.py`:
     `namespace_allowed` is set membership) — `kube*` does NOT work there; globs apply only to
     `exclude_images` (`fnmatch`). UI hints now say so. Glob support for namespaces would be a
     scanner-side change — unowned, operator to rule if wanted.
- **2026-07-15 — pre-kickoff spec-sync (operator-driven, session review of code + docs + the v4
  prototype's 10 settings sub-pages):** full findings; the candidate table above (§Settings surface)
  is the cherry-pick sheet.
  1. **Deliverables were missing four §13-ruled panels**: SLA policy (13.3), Access & tokens (13.5),
     Users & roles (13.6), Cluster (13.8) — all with fully-shipped backends — plus the settings
     sub-nav shell itself (capability-hidden sections, save bar on editable sections only). The
     §13 heading explicitly says "users/tokens panels also M9e".
  2. **`CveAuditView` has no v5 contract** (no §13 section; per-CVE disagreement + decision
     provenance live on finding detail + Decisions). **STRUCK** (operator, 2026-07-15) — table row 24.
  3. **The scan-scope session read (D-2) was unowned** — the bearer `GET` stays scanner-only, so the
     ScanScopeView cannot render without it. Landed here as a deliverable (table row 6).
  4. **Prototype-vs-backend deltas found by reading all 10 prototype sub-pages** (table §C): version
     select + tuning writes + enable toggles + Schedule section + ignore-rules table + KEV-override
     toggle are ruled out (C-4/D41/V4-DELTA-2/D30); vuln-DB config and registries/imagePullSecrets are
     **entirely unbuilt and unruled** (v1.x issue candidates); per-purpose retention (4 windows) vs
     the backend's single per-cluster window needs a ruling (row 23); users panel = disable-not-delete,
     invite = temp-password; `schema_version` display is 4; SLA edit gate is `can_manage_settings`,
     not "Security Lead".
  5. **Graduation candidates** (env → `system-config`, table §B): report TTL (recommend yes),
     session TTL + login lockout (recommend defer), and `VITE_FRESHNESS_BANNER_HOURS` should be
     **replaced** by an API read of the live staleness timers, not graduated.
  6. **Cross-doc drift to fix in the same spec-sync PR:** `CONFIGURATION.md` §6 tokens row says
     "M9a UI" and users row says "unowned (M9x)" — both are M9e per §13; §3/§4 "✅ Phase 2 (#91)"
     arrows contradict §7/C-4 (tuning is read-only forever) — reconcile to C-4; `SPEC` FR-19's
     "JAVV applies/updates the ISM policies" is superseded by the M4 mechanism (sweep drops whole
     indices, no ISM); `INDEX-MAP` line ~351's `system-config` comment predates D43/M8c (missing
     `scan_scope:<cluster_id>` + `cluster-registry`).
  7. **Not a drift (verified):** this README's v4-prototype fidelity path is correct — `handoff/docs/`
     has no prototype, only the SCREENS/DATA_MODEL docs layered over the v4 jsx; port the v4
     markup, then apply the §13 deltas. `docs/API.md` is accurate for everything shipped.
- **2026-07-12 — v0.3.9 reusables (task 92 + chip language A, PRs #348/#350):** settings is
  form/status-heavy — the relevant solved surfaces:
  - **Kit controls only** (DESIGN.md §5 table): `UiButton` (primary now carries the depth
    treatment), `UiSegControl` (coral selection), `UiField`, `ModalShell` for the destructive
    confirms. Every destructive action toasts (audit rule 3) and is journaled.
  - **Chips (language A):** job/retention/staleness statuses use the QUIET register —
    `HealthChip`'s dot-and-word grammar or `StateTag`'s soft-tint+dot pill; the depth
    treatment is reserved for true alarms. Never a hand-rolled status pill.
  - **Contract guards (audit rule 2):** every numeric knob (retention days, timer windows)
    guards at the input AND omits-not-emits in the builder; honest 4xx copy via a
    `failureCopy`-style map, never "check the backend connection" for a user-input error.
  - Any table this bolt grows (audit-log panel, snapshot list) rides the shared skin +
    reorder grammar — see the M9d 2026-07-12 entry for the port checklist.
- **2026-07-07 — backend↔UI drift rulings (major audit #224, 05 §C-4):** the v4 prototype's Settings
  shows **editable** trivy/grype config, schedule, vuln-DB settings and a `config.versions` scanner
  version **selector — that selector violates D41** (version is build-time, operator-swapped via
  image tag; JAVV never writes to monitored clusters). Ruling: Settings→Scanning is **read-only
  display** of the latest envelope's `effective_config` + provenance, with an "operator-managed
  (GitOps)" affordance; editable in MVP = SLA policy, users/roles/tokens, scan scope (the existing
  D43 deliverable above), retention windows. No version picker anywhere.

- **2026-07-03 — scan-scope UI + tuning display added to deliverables.** D43/FR-24 (PR #95) made scan
  scope UI-configurable and named M9e the UI owner: this bolt now delivers `ScanScopeView.vue` + the
  RBAC-gated `PUT /api/v1/scan-scope` (read path + CLI already shipped). The ScanningView per-scanner
  cards additionally display the read-only effective *tuning* flags from the joint schema-v3
  `effective_config` stamp (#91). Mirrored on [#39](https://github.com/Danube-Labs/javv-poc/issues/39).
- **2026-07-03 — the `effective_config` stamp LANDED (D44/FR-25, schema v3).** Scan-events docs now
  carry `{tuning, scope}` in `_source` (`enabled:false` — not aggregatable). The per-scanner cards
  read it from the latest committed scan-event; trivy DB freshness is also populated now (#96).
- **2026-07-03 — staleness-timer BACKEND landed in M3 (D20).** The two-timer machinery this panel edits
  is built: `system-config` `staleness` doc (`freshness_days` N=3 / `scanner_down_days` M=7), the daily
  `jobs/staleness.py` sweep (per-finding + scanner-down + hold + revert-on-return), and
  `read/write_staleness_timers` + interim CLI. `ScanningView.vue` now only needs the UI + RBAC-gated
  `PUT /settings/staleness`. Depends-on updated M4→M3. Mirrored on
  [#39](https://github.com/Danube-Labs/javv-poc/issues/39).

- **2026-07-07 — v5 design rulings (#237):** contract = `SCREENS.md` §13. Settings→Scanning's
  read-only provenance/`effective_config` display shares the **M8c provenance read** with M9d's
  scanner-status screen (one endpoint, two consumers). §13.8 Cluster: **`cluster_name` is
  editable** — D-5 ruled the `system-config` registry in (**M8c** ships read + journaled rename;
  display-only, never a query key). **A-4 ruled**: Users & roles panel renders exactly 4
  capability bundles; no 5th role seeded.

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
> **Frontend analog (M9a+):** `logger` from `frontend/src/lib/logger.ts` — structured, leveled,
> backend-shaped lines; raw `console.*` in app code is ESLint-banned. Threshold: `VITE_LOG_LEVEL`
> ([CONFIGURATION.md §2b](../../../docs/CONFIGURATION.md)); never log tokens/cookies/bodies (NFR-5).

## Design & fidelity (standing rule)
> Before touching any screen: read **`frontend/DESIGN.md`** — the binding agent contract
> (tokens-only styling, **Hanken Grotesk** UI face, the **AA contrast floor** (`--soft` minimum
> for text; `--muted` never colors words), route-`meta: {wide}` for grid screens, §9 ruled linter
> exceptions). Build **with the prototype open** per DESIGN.md §8: port the matching
> `handoff/v4/prototype/app/*.jsx` markup + CSS onto tokens — never restyle from memory — and
> name the ported component/classes in the PR. **Port structure, never palette: tokens.css
> supersedes the prototype's colors/fonts/text sizes** (the contrast gate
> `frontend/src/__tests__/contrast-gate.spec.ts` enforces the values; DESIGN.md §8 has the rule). Reuse the shared modules (M9a filter module,
> M9b chip set, the banners); never re-implement them. Verify UI deltas with **`/visual-test`**
> and run **`npx impeccable detect`** on rendered-HTML dumps of changed screens (fix real
> findings; §9 exceptions stand). The **`/impeccable`** skill (critique · typeset · layout ·
> harden) is available for design decisions — its product register applies.
> **VISUAL FEEDBACK IS A MUST** (operator 2026-07-10): every interactive element ships with
> visible hover (wash + border, never border-only), pressed and focus states — the global rule
> in base.css + DESIGN.md §2 are binding; feedback-less controls fail review.
