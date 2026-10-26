# Timeline

How JAVV got to this point. Each part gives its dates and the issues or PRs to read for the details.
A number in this file is a GitHub issue or PR of `Danube-Labs/javv-poc`.

## 1. Design (2026-06-13 to 2026-06-29)

- The design went through four versions. Versions 1 to 3 are frozen in `.deprecated/`. Version 4 is
  the live design in [`docs/engineering/`](../../docs/engineering/): `PLAN.md` (the decisions
  D1 to D47, the data model, the milestones), `SPEC.md` (the requirements) and `ARCHITECTURE.md`.
- Design audits changed the decisions: `docs/engineering/AUDIT.md` (2026-06-21, D28 to D36) and
  the rounds in `docs/engineering/AUDIT-RESPONSE.md` (D37 to D40).
- The repository got its process before the code: release-please, Renovate, commitlint, the CI
  gate, pre-commit hooks, `REPO-MAP.md`, and one GitHub issue for each bolt on a project board
  (PRs 9 to 59).

## 2. The bolts (2026-06-28 to 2026-10-09)

Each bolt has a brief in [`development/bolts/`](../../development/bolts/) and a tracking issue with
the label `bolt`. On 2026-10-26 the bolts became history (issue 1012): each bolt README ends with
an Updates entry that says so, and work after M10 follows one issue for each feature.

| Bolt | Issue | Closed | What it built |
|---|---|---|---|
| M0 | 22 | 2026-06-30 | The scanner package: discovery, Trivy and Grype adapters, the envelope, the push |
| M0b | 60 | 2026-07-01 | The scanner images, published, and the compatibility CI (D41) |
| M1 | 23 | 2026-07-02 | The backend skeleton, the index bootstrap, the hardened ingest, observability |
| M2 | 24 | 2026-07-02 | Snapshot and restore |
| M3 | 25 | 2026-07-03 | Scan order (D45), partial merge (D31), the watermark CAS (D40), reconcile, staleness (D20) |
| M4 | 26 | 2026-07-04 | The scan-events logs, rollover and retention for each cluster, scanner disagreement (D5) |
| M5a | 27 | 2026-07-04 | Passwords, sessions, lockout, the bootstrap admin, capability RBAC (D33), the tenant filter |
| M5b | 28 | 2026-07-04 | The VEX triage state machine and the structured audit writer (D1, D32) |
| M5c | 29 | 2026-07-05 | Decisions and their projection onto findings (D3, D4, D17, D22) |
| M5d | 30 | 2026-07-05 | SLA and overdue, bulk triage, the risk-accept approval list (D6) |
| M6 | 31 | 2026-07-05 | Search, facets, groups, trends, contributors, CSV and VEX export |
| M7 | 32 | 2026-07-07 | Scheduled export: the queue, the drain, the download, the bell (D24) |
| M8a | 33 | 2026-07-07 | An occurrence snapshot for each scan, and the inventory commit |
| M8b | 34 | 2026-07-07 | Reads at a past time (D28) |
| M8c | 240 | 2026-07-07 | The reads the UI needed: audit log, scanner provenance, running images, cluster registry |
| M8d | 241 | 2026-07-08 | The package type in the envelope |
| M8e | 242 | 2026-07-08 | Saved views on the server |
| M9a | 35 | 2026-07-08 | The frontend: scaffold, tokens, the API client, the shell, the filter module |
| M9b | 36 | 2026-07-10 | The findings grid, the finding detail and the triage panel |
| M9c | 37 | 2026-07-11 | Overview, All clusters, Running images |
| M9d | 38 | 2026-07-13 | Audit log, scanner status, contributors, approvals |
| M9e | 39 | 2026-07-16 | The Settings area, with Data and OpenSearch |
| M9f | 40 | 2026-07-17 | Search, the bell, saved views, RBAC in the UI, empty states |
| M10 | 41 | 2026-10-09 | The app images, docker compose, three Helm charts, signed releases, the docs site |

Audits during the bolts:

- Issues 138 to 144 (2026-07-04): triage and audit correctness, auth hardening, user and role admin.
- Issues 185 to 192 (2026-07-06): input checks, export limits, read robustness. It ended in 0.3.0.
- Issue 224 (2026-07-07): the M9 bolt READMEs changed to match the backend before the UI started.
- Issue 343 (2026-07-11) and the F-numbered findings (2026-07-13): honest error states, owner checks
  on reports, CSV formula neutralization, large views split into panels (issue 384).

## 3. Between M9f and M10 (2026-07-18 to 2026-10-02)

The pre-M10 gate (issue 555, phase 1): the team finishes everything not marked post-MVP before M10 starts.

- 2026-07-18 to 2026-08-03: the data inspector and its repair actions (issue 406), the jobs lease
  (issue 459), filter negation and click to exclude (issue 349), the browser log beacon
  (issue 453), the PR review protocol (implementer and reviewer, PR 482), and `CLAUDE.md` split
  into path rules (PR 480).
- 2026-08-04 to 2026-09-24: no merges.
- 2026-09-25 to 2026-09-29: plain words in code and docs (issue 543), expired sessions removed
  (issue 532), failed ingests recorded and shown (issue 357), the date-bomb sweep and the weekly
  shifted-clock run (issue 533), the supply chain (issue 552: Renovate, SHA-pinned actions,
  gitleaks, Scorecard), signed scanner images (issue 74), the docs brought back in line with the
  code (issue 588), and the release plan: the MVP is 0.6 or 0.7, then hardening, then 1.0 (PR 628).
- 2026-10-01 to 2026-10-02: the About and Guide pages (issue 341), a design review (issues 659,
  674, 681), and the backend runs its own background jobs (issue 691, D47).

## 4. M10 and the MVP release (2026-10-03 to 2026-10-09)

- The app images and docker compose (issue 452), the three Helm charts (issue 725), signed images
  with SBOMs (issue 615), and the deploy guide (issue 329).
- 0.6.0 was cut on 2026-10-06 but published nothing. 0.6.1 was the first release that published
  the images and the charts (after PR 753 changed the release workflow).
- Cluster retirement (issues 765, 778) and a reset for a forgotten password (issue 761).
- The operator docs site (issue 639), with the operator pages in strict STE (issue 796).
- M10 closed on 2026-10-09 with release 0.7.0. The rulings of that day are in `rulings.md`.

## 5. Hardening for 1.0 (2026-10-09 to now)

On 2026-10-10 each open issue went into the 1.0.0 milestone (issue 555, phase 3).

- **Bug hunt** (issue 790, 2026-10-09 to 2026-10-14): a fresh install as a stranger, upgrades with
  real data, failures on purpose, hostile ingest input, and a review of the PRs with no recorded
  review. Area issues 817 and 829 to 833. All its changes shipped in 0.8.0.
- **Docs passes:** issue 857 (all docs against 0.8.0), issue 939 (the docs site), and the strict
  STE pass (issue 796).
- **Plug and play** (issue 869): a compose setup script, and a sign-in message when the browser
  refuses the cookie.
- **Upgrades** (issue 261): a release only adds to the mappings, keeps a removed route for one
  release, and the Compose job tests an upgrade and a rollback across releases.
- **Private registries** (issue 739): a registry login that the scanner chart mounts.
- **Security review of 0.8.2** (issue 892): who can undo a risk accept, account events in the audit
  log, sessions out of snapshots, a CSP on the frontend server.
- **The app feels responsive** (issue 902): a loading bar, early page code, a short page fade.
- **Triage videos** (issue 699): six videos and their pages in Use JAVV on the docs site.
- **Plain audit text** (issues 909 to 912, 918, 931, 933).
- **Filters with several values** (issues 949, 950, 952), then follow-up bugs (issues 961, 962,
  965, 969, 975, 979, 980, 983, 984).
- **Roles and permissions:** the Roles card shows what each role can do (issue 990), a separate
  `can_export` permission (issue 243).
- **Composable dashboards** (issue 440, 2026-10-24 to 2026-10-26): a catalog of panels that load
  their own data, `system-dashboards` with private, everyone or role sharing, a
  `can_edit_dashboards` permission, list, read, export and import, then edit mode on a gridstack
  grid with a popover for panel settings. PRs 996, 1001, 1002, 1003, 1007, 1008, 1010.
  These changes shipped in 0.8.9 (2026-10-26). Release 0.9.0 marks them as a minor release.

## 6. Releases

Each release in `CHANGELOG.md`, with what it brought. `CHANGELOG.md` has the full list of changes.

| Release | Date | What it brought |
|---|---|---|
| 0.9.0 | 2026-10-26 | No code changes after 0.8.9. It marks the 0.8.9 changes as a minor release (ruling of 2026-10-26) |
| 0.8.9 | 2026-10-26 | Composable dashboards (issue 440), the Roles card (issue 990) and the `can_export` permission (issue 243). Release 0.9.0 marks these changes. |
| 0.8.8 | 2026-10-23 | Filter counts and pairs (issues 975, 979, 980, 983) |
| 0.8.7 | 2026-10-23 | Filters take several values (issues 949, 950, 952) |
| 0.8.6 | 2026-10-20 | The audit log names each action (issue 933) |
| 0.8.5 | 2026-10-19 | Plain audit field names (issue 931). A docs folder for each release (issue 925) |
| 0.8.4 | 2026-10-19 | The loading bar and page motion (issue 902). Changes to the activity card |
| 0.8.3 | 2026-10-17 | Scan scope by owner kind (issue 891) |
| 0.8.2 | 2026-10-16 | Compose setup script (issue 869), private registries (issue 739) |
| 0.8.1 | 2026-10-15 | Guide section heads. A scheduled bulk triage checks its patch (issue 854) |
| 0.8.0 | 2026-10-14 | The bug hunt (issue 790). Planned as 0.7.3, renamed on 2026-10-14. |
| 0.7.2 | 2026-10-11 | Bug hunt changes: a fresh install, refused reads, scans by digest |
| 0.7.1 | 2026-10-10 | Bug hunt changes: navigation, the temporary password session, empty replies |
| 0.7.0 | 2026-10-09 | M10 closes. `JAVV_SECRET_KEY`. A docs version for each release |
| 0.6.3 | 2026-10-09 | A dependency update only |
| 0.6.2 | 2026-10-08 | Cluster retirement (issue 765) and a reset for a forgotten password (issue 761) |
| 0.6.1 | 2026-10-06 | The MVP release: the first that published the images and the charts, signed |
| 0.6.0 | 2026-10-06 | The three Helm charts, the javv user in OpenSearch. This release published nothing. |
| 0.5.1 | 2026-10-04 | The app images and docker compose (issue 452) |
| 0.5.0 | 2026-10-03 | The backend runs its own background jobs (D47, issue 691). Crash and maintenance pages |
| 0.4.13 | 2026-10-02 | Three layout changes |
| 0.4.12 | 2026-10-02 | Rows open from the keyboard. Filters use the names that users see |
| 0.4.11 | 2026-10-02 | Status colors, a page for unknown addresses |
| 0.4.10 | 2026-10-01 | Plain UI copy: no em dashes, no decision codes |
| 0.4.9 | 2026-10-01 | Each screen fits at 1024, 1366 and 1920 |
| 0.4.8 | 2026-10-01 | The About and Guide pages. The scanner push checked in CI |
| 0.4.7 | 2026-09-29 | Signatures on the scanner images (issue 74) |
| 0.4.6 | 2026-09-27 | Browser logs reach the backend. Failed ingests recorded and shown (issue 357) |
| 0.4.5 | 2026-07-30 | Click to exclude, more CSV exports, the package filter |
| 0.4.4 | 2026-07-27 | Filter negation and the unassigned flag (issue 349) |
| 0.4.3 | 2026-07-26 | The scanner checks that it reached the cluster it was told |
| 0.4.2 | 2026-07-19 | The jobs lease guards both doors (issue 459) |
| 0.4.1 | 2026-07-18 | The data inspector and its repair actions (issue 406) |
| 0.4.0 | 2026-07-17 | M9f: empty states, command palette, the bell, saved views v2 |
| 0.3.11 | 2026-07-17 | Cluster in the URL, CVE detail, cleanup window for each cluster |
| 0.3.10 | 2026-07-16 | M9d and M9e: audit log, scanner status, contributors, approvals, settings |
| 0.3.9 | 2026-07-11 | M9c: Running images. Grid and chip work |
| 0.3.8 | 2026-07-11 | M9c: Overview and All clusters |
| 0.3.7 | 2026-07-10 | M9b: the findings grid and triage. The UI kit, motion and toasts |
| 0.3.6 | 2026-07-10 | M9a: the frontend scaffold, the API client, the shell, the filter module |
| 0.3.5 | 2026-07-08 | M8d package type, M8e saved views, full-word severities (D46) |
| 0.3.4 | 2026-07-08 | M8b and M8c: past-time reads, audit read, running images, cluster registry |
| 0.3.3 | 2026-07-07 | M8a: occurrence snapshots and the inventory commit |
| 0.3.2 | 2026-07-07 | M7: the report queue, drain, download and the bell |
| 0.3.1 | 2026-07-07 | Scanner freshness read, settings checked at start, more metrics. M7 starts |
| 0.3.0 | 2026-07-06 | End of the audit wave (issues 185 to 192) |
| 0.2.16 | 2026-07-06 | Changes from the audit wave (issues 185 to 192) |
| 0.2.15 | 2026-07-05 | M6: CSV and VEX export, the past-time seam |
| 0.2.14 | 2026-07-05 | M6: contributors. One log line for each request |
| 0.2.13 | 2026-07-05 | M6: trends |
| 0.2.12 | 2026-07-05 | M6: faceted search and group paging |
| 0.2.11 | 2026-07-05 | M6 starts: an ingest conflict no longer gives a 500 |
| 0.2.10 | 2026-07-05 | M5d: SLA, bulk triage, the approval list |
| 0.2.9 | 2026-07-05 | M5c: decisions and projection |
| 0.2.8 | 2026-07-05 | The shared logging library |
| 0.2.7 | 2026-07-05 | Changes from the first audit (issues 138 to 144) |
| 0.2.6 | 2026-07-04 | M5b: the triage state machine and the audit writer |
| 0.2.5 | 2026-07-04 | M5a: passwords, sessions, lockout, bootstrap admin, capability RBAC |
| 0.2.4 | 2026-07-04 | M4: write aliases, retention sweep, scanner disagreement flags |
| 0.2.3 | 2026-07-03 | M3: scan order, partial merge, watermark CAS, reconcile, staleness |
| 0.2.2 | 2026-07-02 | The envelope carries the effective config (schema v3, D44) |
| 0.2.1 | 2026-07-02 | M2 snapshot and restore. Scan flags and scan scope as settings (D43) |
| 0.2.0 | 2026-07-02 | M1: the backend skeleton, index bootstrap, hardened ingest, observability |
| 0.1.2 | 2026-07-01 | The envelope carries the observed topology (schema v2) |
| 0.1.1 | 2026-07-01 | A scan failure of one image no longer stops the cycle |
| 0.1.0 | 2026-06-30 | First release: the M0 scanner package and the M0b image publish (PR 58, PR 63) |
