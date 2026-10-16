# M10 - Polish & deploy

**Status:** tracked in [#41](https://github.com/Danube-Labs/javv-poc/issues/41) — live status on the GitHub issue/board

## Goal
Deploy and polish only. Production Helm chart (PVC vuln-DB cache, scanner CronJob hygiene, least-priv
scanner RBAC, snapshot wiring), the **NFR-11 vuln-DB mirror/cache** (PVC + scheduled refresh
CronJob), rollback strategy, operational runbooks (OpenSearch sizing, `_reindex` migration D25,
HA/multi-pod D23), and finalized VEX export + attribution. **CI is out of scope** — the pipeline
is scaffolded separately (`.github/workflows/ci.yml`, AUDIT C1) and must not block on M10.

**Canonical refs:** [`PLAN §8 M10`](../../../docs/engineering/PLAN.md) ·
`SPEC` NFR-2 (Helm/k8s, shard budget), NFR-3 (least-priv scanner RBAC), NFR-6 (snapshot/restore),
NFR-9 (CronJobs `Forbid`, no broker), **NFR-11 (vuln-DB mirror/cache + scheduled refresh + PVC)**, FR-22 (VEX export MVP) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (deploy touches no new index — ISM/snapshot repo refs) ·
decisions D23 (HA/multi-pod), D24 (off-peak export), D25 (`_reindex` runbook).

## Depends on
- **All prior bolts** (M0–M9f) — M10 packages and deploys the assembled system; it adds no new app logic beyond the vuln-DB cache wiring + VEX-export finalization.

## Deliverables
In the deploy tree, not here (paths proposed):
- `deploy/helm/javv/` — chart: API Deployment, scanner **CronJobs** (`Forbid` concurrency, D40/NFR-9), OpenSearch values. *(The snapshot-repo config moved to the hardening phase with issue 664, 2026-10-09.)* Each scanner's **image tag is a Helm value** (`scanners.trivy.tag` / `scanners.grype.tag`) the operator sets to a published, compatibility-checked pinned image — **version changes are a tag swap (GitOps), never an in-app switch** (D41); JAVV writes to no cluster. **Envelope lockstep (D44):** the envelope is *current-only* (schema v3) — the backend 422s older schema versions, so **scanner images and the backend must upgrade together** on any schema bump; the chart/runbook must upgrade them as one unit (never bump one side alone).
- `deploy/helm/javv/templates/vulndb-pvc.yaml` + `vulndb-refresh-cronjob.yaml` — **NFR-11 vuln-DB mirror/cache:** a shared **PVC** mounted by Trivy + Grype scanner jobs, refreshed by a **scheduled CronJob** (offline/air-gapped friendly; deterministic scans don't hit upstream DBs mid-run). **Cache is keyed per vuln-DB *schema*, not per binary** (D41): Trivy minors share schema v2, but **Grype v5↔v6 are incompatible** (and Grype <0.88 scans a frozen/EOL DB) — never let two incompatible-schema versions write one cache dir; warn/block EOL-schema picks. *(NFR-11 had no clear earlier home per AUDIT N11 — it lands here.)*
- `deploy/helm/javv/templates/scanner-rbac.yaml` — least-priv scanner ServiceAccount/Role (read-only workloads; namespace-scoped Secret read — NFR-3).
- **No CronJob manifests for backend jobs** (D47, see the 2026-10-03 entry under `## Updates`): the backend container runs staleness, lifecycle, findings cleanup, session sweep, report drain and report sweep on its own schedules, and rebuild state runs by hand. A scheduled snapshot is issue 664 (deferred). **Note:** M7 report *results* live in OpenSearch (chunked, `system-report-chunks`), so **no object store is needed for reports** — the `snapshot-repo config (S3/MinIO)` above is for OpenSearch snapshot/restore only (M2), not reports.
- Runbooks, as pages of the operator docs site (issue 639, ruled 2026-10-09): `docs/runbooks/opensearch-sizing.md` and `docs/runbooks/multi-pod.md` (D23). The rollback path is in `docs/UPGRADING.md` (2026-09-29); the `_reindex` runbook (D25) moved to the hardening phase the same day. **Restore/rollback note (D45):** restoring a snapshot restores an old `javv-scan-orders` counter — it self-heals **forward only** (`max(committed) > counter` → bump up) on the next allocation; never manually reset it backward (a regressed counter re-issues orders and the watermark CAS then silently drops newer scans).
  **Index bootstrap in k8s:** the API pod runs `backend/core/bootstrap.py` at startup (idempotent,
  version-gated, multi-pod-race-safe) — the default; if least-priv ever demands API pods that can't
  write mappings, move it to a Helm pre-install/pre-upgrade hook Job instead. Either way,
  **reindex-class migrations (field type changes) are never automatic at boot** — that's the
  `reindex-migration.md` runbook, an explicit operator job.
- VEX export (FR-22): documented as a standard OpenVEX / CycloneDX record of triage decisions. Making trivy and grype apply it is issue 791, after 1.0 (2026-10-09; neither applies it today).
- ~~`prometheus-rules.yaml`~~ **dropped (2026-10-09):** `/metrics` stays as it is; operators who scrape it
  build their own alerts.
- Attribution: the root `NOTICE`, and each scanner image carries its scanner's license files under
  `/licenses/` (vendored in `scanner/licenses/`, held by `backend/tests/test_notice.py`).
- The operator docs site (issue 639, joined this bolt 2026-09-29): built from the repo, `dev` published
  from `main`, a numbered version per release from `0.7`.

## Definition of Done
Every screen this bolt ships inherits the UI conventions settled in M9a-M9c: [`ui-foundations.md`](../../standards/ui-foundations.md) **Audit rules** (honest errors, contract guards, restorable state, the D28 semantics surface via `IngestLens`, provenance stamps on now-claims, silence-is-a-bug) and the shared M9 surfaces (filter module, table skin, kit controls) - reuse them, never re-solve.

Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated check):
- **Helm lint + template render** clean; `helm template` produces valid manifests for default + prod values.
- **vuln-DB cache (NFR-11):** PVC mounts in both scanner jobs; the refresh CronJob populates it; a scanner run with the offline/cached DB succeeds **without** reaching upstream (deterministic-test guarantee, testing.md "no calls to real vuln-DBs").
- Scanner CronJobs render with `concurrencyPolicy: Forbid` (D40/NFR-9); scanner RBAC is read-only + namespace-scoped (NFR-3) — asserted by an OPA/conftest or manifest test.
- ~~Snapshot repo + scheduled snapshot render and a restore drill passes~~ **moved to the hardening
  phase with issue 664 (2026-10-09).**
- Rollback is executable: a documented `helm rollback` path returns to the prior release (`docs/UPGRADING.md`,
  run by CI's `helm-app` job). The `_reindex` runbook (D25) moved to the hardening phase (2026-09-29).
- ~~VEX export accepted by `trivy --vex` / `grype` in an integration check~~ **dropped (2026-10-09):** neither
  scanner applies the export today; issue 791 (after 1.0).
- The docs site builds with `--strict` in CI, and each release publishes its numbered docs version
  (the `publish-docs` job in `release-please.yml`; `test_docs_site.py`).

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit/manifest:** `helm lint`; `conftest`/`kubeconform` over rendered templates (Forbid concurrency, scanner RBAC scope, PVC mount, resource limits).
- **Integration (real OpenSearch + k3s/kind):** vuln-DB cache CronJob populates PVC → offline scan succeeds; CronJob fires under `Forbid` (no overlap). *(The snapshot+restore drill moved with issue 664.)*
- **Golden fixtures:** a triaged finding set → expected OpenVEX + CycloneDX export documents (regression guard on FR-22 serialization; exists since M6, `backend/tests/test_export_vex.py`).

## Out of scope (defer)
- **CI pipeline creation (`.github/workflows/ci.yml`) → scaffolded SEPARATELY (AUDIT C1); NOT part of M10** — M10 must not wait on it.
- VEX **import** → v1.1 (FR-22).
- HA implementation (HA is not JAVV-built — NFR-9/D23; M10 documents multi-pod notes only).
- `javv-metrics` rollup for all-clusters historical dashboards → v1.1 (D38/M16).

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
- **2026-10-16: no maintenance switch (operator, issue 719 closed as not planned).** Kibana,
  Dependency-Track and DefectDojo have no such switch either. While the backend does not run, the
  frontend server already answers 502, the app shows "backend not answering", and scanners try
  again. `docs/DEPLOYING.md` "Known limits" now says what users and scanners see, and keeps the
  proxy recipe for the maintenance page.
- **2026-10-09: M10 closes with 0.7.0 (issue 41).** What shipped after the rulings below:
  - #792: the root `NOTICE`, and the trivy and grype license files in the scanner images.
  - #793: the operator docs site, built by Zensical from the repository, `dev` published from
    `main`.
  - #794: the sizing and scaling runbooks as pages of the site.
  - #795: the site's fixes (the mermaid diagram, readable tables, a dark theme, no em dashes), and
    `JAVV_TOKEN_PEPPER` renamed `JAVV_SECRET_KEY`, with the 0.7.0 upgrade steps in
    `docs/UPGRADING.md`. A deployment that still sets the old name stops at start.
  - The last PR: each release publishes its docs as its `major.minor` version and as `latest`, which
    the site opens on. Shown first on a scratch clone: `/` redirects to `latest/`, and `latest/`
    to `0.7/`.
  - **After 0.7.0, not in this bolt:** the operator docs in strict STE without internal references
    (issue 796, operator ruling: 0.7.0 does not wait for it), then the first bug hunt (issue 790).
- **2026-10-09: what is left of M10 (operator rulings on issue 41):**
  - **Prometheus alert rules: dropped.** `/metrics` stays as it is; operators who scrape it build
    their own alerts. The JAVV UI already shows scanner freshness, failed ingests and retiring
    clusters.
  - **VEX: a record, not a scanner input.** An experiment with trivy 0.75.0 and grype 0.120.1 on a
    real image showed that neither applies the export: both refuse its CycloneDX form, and both
    accept its OpenVEX form but keep reporting the finding, because the package is written as
    `pkg:generic/...` and trivy also expects Docker Hub as `index.docker.io`. The export is documented
    as a standard record of triage decisions; the fix (each scanner's own purl passed through
    ingest) is issue 791, after 1.0. The "verified consumable" deliverable and its check are dropped.
  - **Moved to the hardening phase:** issue 664 (scheduled snapshots and the restore drill) and issue
    739 (a registry login for private images). **After 1.0:** issue 719 (the maintenance switch).
  - **The sizing and multi-pod runbooks** become pages of the docs site (issue 639).
  - **What is left:** the NOTICE and the scanners' license files, the docs site, then the **0.7.0**
    release, which closes this bolt. The docs site's first numbered version is `0.7`, since 0.6
    shipped without one.
- **2026-10-06: the 0.6 releases (issues 752 and 754):**
  - **0.5.2 was never released.** Issue 715 slice 2 and the issue 736 fix are both first in
    `v0.6.0`, so no release ever ran a store with the six demo users. The 2026-10-05 entry's
    caveat for "0.5.2" never applied.
  - **0.6.0 published nothing.** Its tag and GitHub Release exist, but the release workflow's
    compose smoke lacked `JAVV_OPENSEARCH_ADMIN_PASSWORD`, which issue 729 made required. The fix
    (PR 753) also has the release workflow regenerate the chart READMEs on its own PR (issue
    752). The images and charts ship with the release after 0.6.0.
- **2026-10-05: the charts create and use javv (issue 729, slice 2):** `javv-opensearch` takes
  javv's password as a second Secret (`opensearch.javv.backend`, required like admin's). Its init
  container writes admin and javv into the users file, and the javv role and mapping come from
  the chart's `files/` (held equal to the compose file's `configs`) as a ConfigMap mounted over
  the image's demo ones. The `javv` chart signs in as `javv` with that Secret. The store's
  `helm test` checks javv's role and a refusal, and the Helm job fails on any 403 in the
  backend's log after the scanner cycle.
- **2026-10-05: JAVV signs in to OpenSearch with a least-privilege role (issue 729, slice 1,
  operator rulings on the plan):** the `javv` role holds what the backend calls and nothing more:
  its own indices (`findings`, `javv-*`, `system-*`), the `restored-*` copies a restore writes,
  snapshots and cluster health. Index delete is on `javv-*` only, and rollover on `javv-*` and
  `system-audit-log*`. Compose creates the `javv` user and role (inline `configs`, Compose 2.23.1+),
  and the backend signs in as `javv`. `JAVV_OPENSEARCH_PASSWORD` is now javv's, and a new
  `JAVV_OPENSEARCH_ADMIN_PASSWORD` sets the store's admin, which the backend never gets. Two code
  paths named no index and were refused by the role: the Data inspector's `_cat` reads (now scoped
  to JAVV's indices) and the write-alias check (now asks the series' own backing indices). CI's
  compose job runs `opensearch-role-walk.sh`, every surface as `javv` plus five refusals. The
  charts follow in slice 2.
- **2026-10-05: a release publishes the charts (issue 725, slice 4, operator rulings on the plan):**
  `Publish charts` in `release-please.yml`, after `Publish app images`: `publish-charts.sh`
  packages the three charts, checks each carries the release version, and pins the scanner images
  in `javv-scanner` by the digests their tags name at the release, each after `cosign verify`
  against `scanner-images.yml`'s identity (an unsigned one stops the release). It pushes them to
  `oci://ghcr.io/danube-labs/charts`, signs each chart digest (cosign keyless, no SBOM: a chart has
  no packages), then pulls and verifies each signed out. CI's Helm job runs the same packaging
  against a local registry on every PR. DEPLOYING, UPGRADING and the chart READMEs install from
  `oci://`.
- **2026-10-05: the release signs the app images (issue 615, before issue 725 slice 4, operator):**
  `Publish app images` makes an SPDX SBOM of each pushed digest with syft, signs and attests it with
  `.github/actions/sign-image` (cosign keyless, the scanner images' design from issue 74), then runs
  `cosign verify` and `verify-attestation` signed out. `id-token: write` is on that job only.
  `docs/DEPLOYING.md` "Verify the images" gives the commands. Slice 4 signs the charts in the same run.
- **2026-10-05: the `javv-scanner` chart (issue 725, slice 3, operator rulings on the slice 3
  plan):** one CronJob per scanner (`Forbid`, stopped after 5 h 30 min, no retry until the next
  schedule), each with its own token Secret, settings, image and vuln-DB cache. This replaces two
  lines of the deliverables above:
  - **NFR-11's cache is one `ReadWriteOnce` volume per scanner, refreshed at the start of every
    cycle,** not one volume both scanners share plus a refresh CronJob. Four Jobs on one volume work
    only on `ReadWriteMany` storage or a single node. Each cycle's init container refreshes the DB
    with the scanner's own image (so the schema matches, D41), from the vendor's source or the one
    in `vulnDb`; the scan then runs with updates off, so a cycle reads one DB and calls nothing
    upstream mid-scan. The install runs the same refresh once as a Job, which also binds the volume
    for `helm install --wait`.
  - **NFR-3's scanner RBAC grants no Secret read:** `list` pods and `get` the `kube-system`
    namespace, the two calls a cycle makes. Private registries are issue 739.

  The image tag is `versions.yaml`'s scanner version (drift-checked), pulled `Always` since JAVV
  republishes it; a digest pins one build, and slice 4 writes the scanner digests into the chart
  it publishes. CI installs the chart in a second kind cluster that pushes to the `javv` chart, and
  one cycle of each scanner lands.
- **2026-10-05: the `javv` chart (issue 725, slice 2, operator rulings on the slice 2 plan):**
  `deploy/helm/javv` runs the backend (one replica, `strategy: Recreate`, issue 691) and the frontend
  as Services only, with every backend setting under `backend.config` by its environment name,
  held to the code by the same test as the compose file. The pepper and the bootstrap password come
  from a Secret, OpenSearch's password by reference to the `javv-opensearch` chart's Secret, and
  `opensearch.caSecret` mounts the store's CA and turns certificate checking on. The startup probe
  allows 300 s. The frontend server gets `JAVV_BACKEND_CONNECT_TIMEOUT` (5 s, connecting only): an
  address whose pod is gone but still listed never answers, and the request would hang. The
  banner reads a 503 as "store down" only when the backend sent it (its JSON), on the `/readyz` poll
  and in the API client, so an ingress's 503 page reads as "backend down". CI installs the chart
  next to a store with a cert-manager certificate, signs in, stops the backend (502), and runs an
  upgrade and a `helm rollback`: the Definition of Done's `helm rollback` line.
- **2026-10-05: three Helm charts, not one (issue 725, operator rulings of 2026-10-04):** the
  `deploy/helm/javv/` chart of the deliverables above becomes three charts in `deploy/helm/`,
  installed separately: `javv-opensearch` (the store), `javv` (backend and frontend) and
  `javv-scanner` (the scanner CronJobs, RBAC and the vuln-DB cache, issue 714's list), published to
  `oci://ghcr.io/danube-labs/charts` on every release. Each carries the JAVV release as its
  version, with `appVersion` recording what is inside. CI runs `ct lint` and `ct install` in kind
  (`deploy/helm/ct.yaml`, every `ci/*-values.yaml` one install plus the chart's `helm test`), and a
  pytest render check per chart. Slice 1 is `javv-opensearch`: a wrapper around the official
  `opensearch` chart (vendored, Renovate refreshes it), one node with the compose file's settings
  and its security plugin on, `admin` as the only password user (an init container writes the
  users file, issue 736), and demo certificates by default or your own from a Secret or
  cert-manager, with hot reload. The `helm template` + `helm lint` Definition-of-Done line is met
  by `ct lint` and the render checks.
- **2026-10-05: compose's OpenSearch has one password user, `admin` (issue 736):** OpenSearch's demo
  security setup also loads six users whose passwords are their own names (`readall` can search
  every index), and no setting turns them off. The compose `opensearch` service's entrypoint keeps
  only `_meta` and `admin` in the image's `internal_users.yml` before the image's own entrypoint
  runs; the demo setup still checks the password's strength and sets `admin` from `.env`. Found
  while planning the charts (issue 725); the `javv-opensearch` chart will do the same. A store
  first started from `main` between issue 715 slice 2 and this fix keeps the six users until the
  `UPGRADING.md` password change runs once. 0.5.1 and earlier run OpenSearch with its login off;
  this fix lands before the release that carries issue 715 slice 2 (0.5.2), or that release's
  notes must say its store has the six users until that password change runs.
- **2026-10-04: compose runs OpenSearch with its login on (issue 715, operator ruling on issue 725):**
  the backend signs in to a secured OpenSearch (`JAVV_OPENSEARCH_USERNAME`, `_PASSWORD`, `_CA_BUNDLE`,
  `_VERIFY_CERTS`, one client factory in `core/opensearch_client.py`), and `deploy/compose/compose.yaml`
  drops `DISABLE_SECURITY_PLUGIN`. The store uses OpenSearch's demo certificates and an admin
  password from `.env` (`JAVV_OPENSEARCH_PASSWORD`, shared with the backend, which skips the
  certificate check with one warning). OpenSearch's own audit log is off (`noop`), since it
  writes a daily index nothing deletes with ISM off. Until now, compose (issue 452) ran its store
  with the security plugin off. A 0.5.x store upgrades in place; changing the password later takes OpenSearch's
  `securityadmin.sh` (`docs/UPGRADING.md`). A narrower OpenSearch role than `admin` is issue 729.
- **2026-10-04: a release publishes the app images (issue 452, slice 4):** the `Publish app images`
  job in `release-please.yml` runs in the release's own run. It builds `javv-backend` and
  `javv-frontend` under the release version (`development/scripts/build-app-images.sh`, OCI version,
  revision and source labels), smokes the release's compose file on them, pushes them to GHCR, writes
  both digests out for signing (issue 615), and fails the run with a note on the release if any
  step fails. `deploy/compose/compose.yaml` now names the published images, and release-please
  bumps their tags with `version.py` and `version.ts`. The chart takes the same images.
- **2026-10-03 — docker compose first, the chart after (issue 452, operator):** JAVV ships as a
  frontend container and a backend container that reach each other by address, plus OpenSearch.
  The frontend container's own server forwards `/api`, `/auth` and `/readyz` to the backend, so
  nothing (nginx, an ingress, a gateway) is required in front, and the chart ships no Ingress.
  `deploy/compose/compose.yaml` runs the whole stack on one machine with every setting listed at its
  default; `docs/DEPLOYING.md` is the guide. The Helm chart is built from it afterwards: one backend
  replica with `strategy: Recreate` (issue 691: one backend; a rolling update would briefly run two),
  which supersedes the `maxSurge: 1` of the 2026-09-29 entry. Split out: the scanner manifests
  (issue 714), a secured OpenSearch (issue 715), the maintenance page without a proxy (issue 719).
- **2026-10-03 — backend jobs are not CronJobs (D47, issue 691):** the chart renders no CronJob for a
  backend job. The backend container runs staleness, lifecycle, findings cleanup, session sweep,
  report drain and report sweep itself, each on its `JAVV_JOB_<KIND>_CRON` schedule;
  `JAVV_SCHEDULER_ENABLED=false` stops them ([`CONFIGURATION.md` §1](../../../docs/CONFIGURATION.md)).
  Rebuild state has no schedule; it runs by hand or from the Data inspector. This supersedes the
  `cronjob-*.yaml` deliverable and the `report-drain` + `report-sweep` CronJobs of the 2026-07-07 entry.
  The chart still ships CronJobs for the two scanners (`Forbid`, D40/NFR-9) and for the vuln-DB refresh
  (NFR-11). A scheduled snapshot is issue 664, deferred.
- **2026-09-29 — how the chart runs the upgrade (issue 261):** the backend keeps bootstrapping the
  indices in its own startup; there is no Helm pre-upgrade hook Job. The chart (issue 452) must set:
  - the backend `strategy` to `RollingUpdate` with `maxUnavailable: 0` and `maxSurge: 1`;
  - `readinessProbe` → `/readyz`, `livenessProbe` → `/healthz`;
  - a `startupProbe` whose budget covers bootstrap against a slow store;
  - `JAVV_BOOTSTRAP_ON_STARTUP` left at its default.

  The reasons and the full table are in
  [`docs/engineering/UPGRADES.md`](../../../docs/engineering/UPGRADES.md). The chart PR fills in the
  Helm section of [`docs/UPGRADING.md`](../../../docs/UPGRADING.md) with the real commands.
- **2026-09-29 — the operator docs site joins this bolt (issue 639, operator):** MkDocs Material on
  GitHub Pages, built from the repo's markdown, with one docs version per release. A GitHub Wiki was
  rejected because it sits outside PR review and has no versions. The site uses the `github.io` address
  until the move to `javv` after 1.0. A `dev` version publishes from `main` once the site PR merges,
  and `0.6` is the first numbered version.
- **2026-09-29 — the scanner CronJobs' security context (issue 632):** the images now run as
  `65532:65532` and write only to `/var/cache/javv/<scanner>` (vuln-DB cache), `/var/lib/javv` (dead
  letter) and `/tmp`. The chart sets `runAsNonRoot: true`, `runAsUser/runAsGroup: 65532`,
  `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`; the
  vuln-DB PVC (NFR-11) mounts at `/var/cache/javv`, with `emptyDir` for `/var/lib/javv` and `/tmp`.
  A manifest test pins it, next to the scanner RBAC scope test.
- **2026-09-29 — M10 ends in the MVP release, not 1.0 (operator):** the release that closes this
  bolt is `0.6.0` or `0.7.0` (a `Release-As:` footer). `1.0.0` follows a hardening phase: plug-and-play
  install, the rest of the upgrade story (issue 261), bug burn-down, then the Renovate majors last.
  From issue 261 this bolt needs only the version endpoint, `UPGRADING.md`, and how bootstrap runs
  during a Helm upgrade. The Definition-of-Done line on the **`_reindex` migration runbook** moves to
  the hardening phase; the `helm rollback` half of that line stays here.
- **2026-07-12 — settled visual contracts (v0.3.9, PRs #348/#350) — polish must not re-litigate:**
  chip language A (derived hues, severity escalation, the one depth treatment), the chart
  escalation ramp (`--sev-*-chart`, critical/high test-pinned to the solids), the cursor
  contract (arrow everywhere, grab on drag surfaces, PrimeVue neutralized), pins-are-identity-only
  reorderable grids, and left-anchored data cells are all operator-ruled and gate-enforced
  (contrast gate, style ratchet, tokens pins). The polish pass verifies against DESIGN.md §2/§5 +
  `ui-foundations.md` §Audit rules — deviations need a new ruling, not taste. The dev seed
  cluster (`development/setup/seed-vuln-workloads.yaml`, 5 namespaces / ~13 images) is the
  UI-scale fixture for the final walk.
- **2026-07-07** — M7 storage decision (#32): M10 now also renders **`report-drain` + `report-sweep`**
  CronJobs (deferred from M7). Report results are stored **in OpenSearch** (chunked), so M10 provisions
  **no object store for reports** — S3/MinIO stays snapshot-only (M2). The download is a backend endpoint
  (`GET /api/v1/reports/{id}/download`), not a presigned object URL; no report-storage secrets/creds.
