# Rulings

The operator rulings that still apply, with the date and where to read them. A number is a GitHub
issue or PR. A ruling here does not replace the document that holds it: where a ruling changed a
document (`CLAUDE.md`, a rule file, `frontend/DESIGN.md`, `PLAN.md`), that document is correct.

The UI rulings for each screen are in [`frontend/DESIGN.md`](../../frontend/DESIGN.md) (section 8.5
for rulings on a built specimen, section 9 for the ruled exceptions) and in
[`handoff/docs/SCREENS.md`](../../handoff/docs/SCREENS.md). This file does not copy them.

## Releases

| Date | Ruling | Source |
|---|---|---|
| 2026-06-29 | release-please stays before 1.0. `feat` bumps the patch, a breaking change bumps the minor. | PR 49 |
| 2026-09-29 | The MVP release is 0.6 or 0.7, not 1.0. 1.0 comes after hardening, when JAVV installs with no help and has as few bugs as possible. | 555, PR 628 |
| 2026-09-29 | Renovate major updates are the last step before 1.0. | 555, 597 |
| 2026-10-10 | Each issue open on 2026-10-10 is in the 1.0.0 milestone, unless the operator moves it out. | 555 |
| 2026-10-14 | The release after 0.7.2 is 0.8.0, not the planned 0.7.3. | PR 853 |
| 2026-10-26 | 0.8.9 stays released. Release 0.9.0 follows with `Release-As: 0.9.0` and marks the changes of 0.8.9 as a minor release. | 1012 |
| 2026-10-14 | Nobody uses an older release of JAVV. A change needs no tool, no data migration and no "check your data" note for what an older release wrote. The same applies to stored shapes such as saved views (2026-10-20). | 854, 949 |
| standing | A release PR merges only on an explicit word from the operator. | 992 |

## Scope

| Date | Ruling | Source |
|---|---|---|
| 2026-09-25 | The team finishes everything not marked post-MVP before M10 starts. | 555 |
| 2026-10-09 | M10 rulings: build `NOTICE`. The VEX export is a record of triage decisions, with no promise that scanners apply it. No Prometheus alert rules. The sizing and multi-pod runbooks are pages of the docs site. | 41 |
| 2026-10-13 | VEX that Trivy and Grype apply (purl passthrough) is after 1.0. | 791 |
| 2026-10-15 | Plug and play means a compose setup script and a sign-in message for a refused cookie. No change to the Helm charts or the token steps. | 869 |
| 2026-10-15 | JAVV keeps only Trivy and Grype. | 865 |
| 2026-10-15 | The public ingest contract is a docs page only. | 327 |
| 2026-10-16 | Not planned: a maintenance switch in the frontend server (719), more settings panels (403), the scanner reads `imagePullSecrets` itself (403, 725). | 719, 403 |
| 2026-10-16 | Pod and workload mapping for findings is after 1.0. | 308 |
| 2026-10-17 | Scheduled backups are after 1.0, out of the 1.0.0 milestone. | 664 |
| 2026-10-17 | All clusters sends 3 requests for each cluster. The change waits until after 1.0. | 903 |
| 2026-10-20 | The charts keep the defaults of the official OpenSearch chart. Do not add jobs or policies for a risk that the upstream chart does not address. | 945 |
| 2026-10-27 | The repository `javv-poc` has the new name `javv`, with its full history, issues and numbers. This replaces the plan to clean the history and delete `javv-poc`. The placeholder repository is `javv-backup`. The release identity accepts both names. | 926, PR 1030 |

## Design and architecture

| Date | Ruling | Source |
|---|---|---|
| 2026-07-08 | Six full words for severity (D46). | 274 |
| 2026-07-26 | A new panel that shows aggregated data loads its own data (DESIGN.md section 10). | PR 479 |
| 2026-07-31 | The Helm chart for the app has Services only. | 452 |
| 2026-10-02 | The backend runs its own background jobs on cron schedules (D47). | 691 |
| 2026-10-09 | Each operator page is in strict STE: its purpose first, then numbered tasks, then reference tables. No engineering references on operator pages. | 796 |
| 2026-10-17 | Security review: only a security lead makes or undoes a risk accept or an ignore rule. Account events in the audit log need `can_manage_users`. Snapshots leave out sessions. The frontend server sends a CSP. | 892 |
| 2026-10-24 | Dashboards: one document for each dashboard in `system-dashboards`, and the `can_edit_dashboards` permission. Sharing is private, everyone or a role. NDJSON export and import. At most 24 panels. A dashboard that you cannot see gives 404. | 440 |
| 2026-10-24 | Dashboard edit: a free grid that you move with the mouse (gridstack, `top` mode). No resize and no keyboard editing. Panels are short or tall. One scanner switch, with an override for each panel. | 440 |
| 2026-10-26 | Panel settings open in a popover next to the panel, with Cancel and Apply. | 440 |
| 2026-10-27 | At a past time, the SLA deadline of a finding uses the KEV value that its scan recorded. The KEV value of the row stays empty, the KEV filter gives 422 and the KEV count stays empty. Only the docs tell about the change, not the Findings screen. | 1000 |

## UI copy and look

| Date | Ruling | Source |
|---|---|---|
| 2026-07-09 | The UI font is Hanken Grotesk. | PR 295 |
| 2026-07-10 | Nuxt UI (the dashboard template) and Framework7 are the design references: their layout and motion, on JAVV tokens, never the libraries. | `.claude/rules/ui-design.md` |
| 2026-10-01 | No em dashes in UI copy. Copy is for users, not engineers: no decision codes, no internal names. No diagrams in the help inside the app. | 341, 652 |
| 2026-10-17 | New names, comments and text use plain words (step, not slice, and panel, not lens). Old names stay. | 543 |
| 2026-10-18 | Videos: the app in a window, a spotlight on the control, and a caption under the window. The pace lets a reader follow. No caption says what the screen does not show. | 699 |
| 2026-10-29 | The primary button is slate, not coral, because coral is in the red-orange of critical, KEV and "down". Coral stays for focus, links and the active page. A saved card opens its item from anywhere on the card. | 1004 |
| 2026-10-29 | Every control in a screen head is 30px high, the scanner switch too. Under each one is a 1px edge with no blur (option D). A soft blurred shadow read as a generic template. Role ids show as words. The other bordered buttons do not get the edge, because the change is too small to see. | 1039, 1043 |
| 2026-10-29 | A dashboard panel is as tall as its content on the read page and in edit mode (option B). The read page goes block by block: a Full panel alone, or two columns of Half panels. The gap is the grid gap across and down. The backend refuses only two panels that start on the same cell (E1). The preview in the Add panel window is as tall as its content too. | 1045 |
| 2026-10-29 | Every text box and dropdown has one look, the kit box, with as much shared code as possible. A window does not style a box of its own. | 1050 |
| standing | A choice between two looks comes as one picture with A and B side by side. | `frontend/DESIGN.md` section 8.5 |

## Process

| Date | Ruling | Source |
|---|---|---|
| 2026-06-28 | One issue for each bolt, with the label `bolt`, on the project board. | PR 42 |
| 2026-07-27 | One agent implements, an independent reviewer checks. The PR gives 6 handover items. | PR 482, PR 494 |
| 2026-07-28 | The plan names the spec file of each slice. | PR 494 |
| 2026-10-25 | A review has at most two rounds: the whole change, then the diff of the changes after round 1. | PR 1002 |
| 2026-10-26 | The bolts M0 to M10 are frozen as history. New work is one issue for each feature. This memory bank is in the repository. | 1012 |
| standing | No stacked PRs. Each PR bases on `main`. | `development/standards/git-workflow.md` |
| standing | No tool attribution and no session links in commits, PRs or issues. | `development/standards/git-workflow.md` |
