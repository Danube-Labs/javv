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
| 2026-11-05 | Release 0.9.6 waits until we build and test all steps of the MCP endpoint. Thus 0.9.6 ships the MCP tokens and the endpoint together. | 1096 |
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
| 2026-10-30 | Filters on a dashboard panel: five panels read findings counts. They take the filters of Findings, in the shape of a saved view. Riskiest images and Triage activity get filters in a separate issue (decision 1). | 999, 1063 |

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
| 2026-10-31 | A filter value past the top 32: the server finds the values of one list that contain a text (`contains` on `GET /api/v1/findings/facets`). A search sends at most 32 values, with the note "More values match. Type more letters." Every screen uses one search helper, in two PRs (D1 A, D2, D3 A2). The first PR is Findings, the panel settings and Images. The second is the Audit log User list and the Approvals Approver list. A list at its cap in the filter list has a search box of its own, with the same search as the menu. Its note points to the box (Q1 B, on full-page pictures). | 1064 |
| 2026-10-31 | A filtered Riskiest images panel uses a top-images read. The store ranks the images and sends only the rows of the panel (D1 B). | 1063 |
| 2026-10-31 | A stored panel keeps its Audit log filters in a second field, `audit_filters`. Only Triage activity takes it (D2 A). | 1063 |
| 2026-10-30 | A dashboard panel takes a filter on the field that it lists. Its facets read asks with `all_filters=true`, so "Namespace is not kube-system" takes that row out. The Findings filter list keeps the rule of issue 949 (decision 4 B). | 999 |
| 2026-11-02 | JAVV counts findings: one CVE in one package version, in one image, from one scanner. Ingest keeps one finding for each finding key, and the last entry of a repeated finding wins. The scan event keeps the number of report entries in `report_entries`. Runs stored before 0.9.5 keep their counts. The rule "Send each finding one time" of the ingest contract stays as advice. | 1076 |
| 2026-11-05 | MCP endpoint for AI agents: an admin with `can_manage_tokens` makes a static MCP token. Each token is its own principal `mcp:<name>`, reads all clusters, and has a level: read, write (`can_triage`) or write and risk accept (`can_accept_audit_final` too). Each token has an expiry, 90 days at most. The endpoint is off by default (`JAVV_MCP_ENABLED`). OAuth comes later, with issue 131. | 1096 |
| 2026-11-05 | The read tools cover each read route, and a test keeps the cover complete. There are four write tools, and a token sees only the tools of its level. No tool takes query DSL or index names. No tool for the queued bulk change: the agent makes the selection smaller. | 1096 |
| 2026-11-05 | The endpoint is `/api/v1/mcp`, with no session. It takes 2026-07-28 and an `initialize` of 2025-11-25, 2025-06-18, 2025-03-26 or 2024-11-05. It does not check `Host`. A request with an `Origin` header gets 403. Each paged tool keeps one open search for each token. | 1096 |
| 2026-11-05 | A page of findings in a tool has 20 rows by default and 25 at most: an agent client refused an answer of 92,789 characters. The defaults are 60 requests a minute and 50,000 characters an answer. | 1096 |
| 2026-11-05 | A revoke of an expired MCP token works. A revoke of a revoked token gets 409. A rotate of a revoked or expired token gets 409, and a revoke wins against a rotate. | 1096 |
| 2026-11-05 | Each tool call writes one audit row, "MCP tool call", that only a user with `can_manage_users` sees. The `token_mint` row and `created_by` of the token name the admin who made it. The operator accepts store text in the log line of a tool error, as for a backend 500. | 1096 |
| 2026-11-05 | A `not_affected` decision for a smaller scope has precedence over a risk accept for a larger scope, for an agent as on the screens. | 1096 |
| 2026-11-07 | `compose.yaml` names the JAVV images by tag, with no digest. The compose steps pull, check the signature of the digest that the pull got, then start (D2). | 1125 |
| 2026-11-07 | `helm install scanner` uses `--wait`, so a cache volume that does not bind stops the install (D3). | 1125 |
| 2026-11-07 | The scanner CronJobs get no `startingDeadlineSeconds`. The docs and the NOTES tell that a schedule during the pause of a manual cycle runs a second cycle at the resume (D2). | 1126 |
| 2026-11-07 | The docs give no Ingress example. The `javv` chart makes no Ingress, and the docs tell the user to put one in front (D3). | 1126 |

## UI copy and look

| Date | Ruling | Source |
|---|---|---|
| 2026-07-09 | The UI font is Hanken Grotesk. | PR 295 |
| 2026-07-10 | Nuxt UI (the dashboard template) and Framework7 are the design references: their layout and motion, on JAVV tokens, never the libraries. | `.claude/rules/ui-design.md` |
| 2026-10-01 | No em dashes in UI copy. Copy is for users, not engineers: no decision codes, no internal names. No diagrams in the help inside the app. | 341, 652 |
| 2026-10-17 | New names, comments and text use plain words (step, not slice, and panel, not lens). Old names stay. | 543 |
| 2026-10-18 | Videos: the app in a window, a spotlight on the control, and a caption under the window. The pace lets a reader follow. No caption says what the screen does not show. | 699 |
| 2026-11-03 | The dashboard video is one video of 6.5 minutes and about 14 MB. It shows every capability of dashboards. The limit of the other videos stays at 6 MB. The spotlight comes on only when its screen shows. | 1009 |
| 2026-10-29 | The primary button is slate, not coral, because coral is in the red-orange of critical, KEV and "down". Coral stays for focus, links and the active page. A saved card opens its item from anywhere on the card. | 1004 |
| 2026-10-29 | Every control in a screen head is 30px high, the scanner switch too. Under each one is a 1px edge with no blur (option D). A soft blurred shadow read as a generic template. Role ids show as words. The other bordered buttons do not get the edge, because the change is too small to see. | 1039, 1043 |
| 2026-10-29 | A dashboard panel is as tall as its content on the read page and in edit mode (option B). The read page goes block by block: a Full panel alone, or two columns of Half panels. The gap is the grid gap across and down. The backend refuses only two panels that start on the same cell (E1). The preview in the Add panel window is as tall as its content too. | 1045 |
| 2026-10-29 | The head of every window is dark blue, the band of the table heads and of the side panel head. The close button on it has the colors of the sidebar collapse button. | 1049 |
| 2026-10-29 | Every text box and dropdown has one look, the kit box, with as much shared code as possible. A window does not style a box of its own. | 1050 |
| 2026-10-29 | The form fields outside the windows use the kit box too: the time picker, the Inspect path box and the sign-in page. The search boxes have one shared style with the hover wash (D1 option A). The command palette keeps its own row. | 1053 |
| 2026-10-29 | In every window, Cancel, Close or Done is the ghost button. The button that does the work is primary (D2 option B). | 1053 |
| 2026-10-29 | The kit has its own text box, text area and dropdown pieces. A lint rule refuses a raw form field outside the kit, with a reason on each place that stays raw (G1 option B). | 1055 |
| 2026-10-29 | The test of the window footers stays the check for the footer buttons. `ModalShell` keeps its footer slot (G2 option A). | 1055 |
| 2026-10-30 | The rows-per-page list of the pager is the small kit dropdown. It keeps the size and the mono text of the pager. It takes the kit corner and focus ring (B3 option A, on built pictures). | 1055 |
| 2026-10-30 | A filtered panel shows a "N filters" button on the corner of its card. A click opens a popover with the filters and "Open in Findings" (decision 2 C). | 999 |
| 2026-10-30 | The panel settings show the filter bar of Findings for the filters of the panel (decision 3 B). | 999 |
| 2026-11-06 | The Settings section "AI agents (MCP)" has two cards (Endpoint, Tokens), a date box for the expiry and the `cpu` icon. It uses the token window of Access & tokens. Both token sections show a toast when the browser blocks the clipboard. | 1096 |
| 2026-11-06 | The Guide section "AI agents (MCP)" shows for every user, with the URL in the copy box. The docs page gives the settings of VS Code and Cursor from their own documentation, with a line that says we did not test them. The text of `can_manage_tokens` names scanner tokens and MCP tokens. | 1096 |
| 2026-11-07 | A window has no border line, only its shadow. The token window has the primary Copy button next to the token and only Done in the footer. The beige box of a value to copy stays (D3 option G). | 1127 |
| 2026-11-07 | The table of the Roles card is flush in its card (`.set-flush`), as the other 7 tables of Settings (D2 option B). | 1127 |
| 2026-11-07 | The section menu of Settings and the Guide takes the hover and press fills of the kit. The selected row keeps the press fill, with coral text (D4 option B). | 1127 |
| 2026-11-07 | The scope strip above each Settings page is a white card, as the other Settings cards. The scope color stays on the badge (D6 option C). | 1127 |
| 2026-11-08 | The verb is Delete: a saved view (a `Delete` button in the card footer and a window that asks first), a dashboard and the bin icon of a panel. A delete window keeps the slate primary button, with no danger color (R3, R9). | 1140 |
| 2026-11-08 | Each control that closes something or clears a value is the kit's `UiCloseButton`: "✕", the hover wash and line with coral text. A slate head takes its dark look (R2). | 1140 |
| 2026-11-08 | The hint of a Settings row with a wide box stops at 75 characters, not at the full width (R10). The namespace boxes wear the kit box, with its hover and focus. | 1140 |
| 2026-11-08 | The image page has one band of three columns: Running now, Findings of the scanner and Build history (option B1). Findings opens Findings on the digest and the scanner, with a new Digest filter. Build history opens the card under the band, closed when the page opens (R5 to R7). | 1140 |
| 2026-11-08 | Slate (`--slate2`) marks first place on the podium, the "SLA met" dot and the activity charts (`CHART_ACCENT`). The coral hover line of a card stays (R8, decision 3 option B). | 1140 |
| 2026-11-08 | "All scanners" adds the counts of the two scanners, as a finding includes its scanner (issue 1076). The words say so: `Trivy and Grype together. A CVE that both report counts once for each.` The UI does not say "never merged" (R4, decision 1 option a). | 1140 |
| 2026-11-08 | Access & tokens is an Organization section: its table shows the tokens of every cluster (R1). The two token buttons have the `control` size and say `Create token`, and the token pages say "create", not "mint" or "make" (R11). | 1140 |
| 2026-11-08 | JAVV has no off-peak window. The tabs of the export window are `Run now` and `In the background`, and the button on Findings says `Export`. PLAN D24 and SPEC FR-13 keep their text, with an "as built" note. | 1140 |
| 2026-11-08 | Nomad clusters push with two periodic jobs in `deploy/nomad/` (issue 1155), one for each scanner, on the JAVV scanner images. The place in JAVV is the Nomad job ID in the namespace `default`, else `<namespace>/<job ID>`, and a periodic run counts as its parent job. The job skips itself and takes the digest from the scanner output. Its Nomad token comes from workload identity, and its JAVV token from a Nomad variable. `expected_count` follows the rule of the JAVV scanners. The page names the Nomad version of the test. | 1155 |
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
| 2026-11-06 | The docs and the issues can name an agent client that a user connects to JAVV, for example Claude Code, Codex, VS Code or Cursor. They still name no model, and no tool as the author or the reviewer of the work. | 1110 |
