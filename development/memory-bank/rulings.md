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
| 2026-11-09 | The page for a Docker host does not tell how to scan a host that also runs JAVV (D1 option B). The scan pages for Nomad and Docker name the JAVV release that their test used, and their file links stay on `main` (D2 option A). | 1161 |

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
| 2026-11-13 | A finding keeps the files where the scanner found it. The scanner sends each report row with its paths, and the backend joins the paths of the entries of one finding key (D1 B). The backend keeps the first 64 sorted paths and their full number, and a path has 1,024 characters at most (D2). Each path starts with `/`: the Trivy adapter adds it. The backend and the scanner ship in the same release, 0.9.10 (D4). The Findings grid read sent the number of paths only (D5). Issue 1205 replaced D5 on 2026-11-14: the Findings list has the Paths column. The look of the Paths column waits for a ruling on a built page (D3). | 1077 |
| 2026-11-13 | A scan of schema 3 or 4 does not report paths. JAVV stores `null` in both path fields, not an empty list and 0, as it does for `ptype`. Such an envelope that sends paths gets 422. The triage answer keeps the paths of its finding. | 1077 |
| 2026-11-13 | The Grype adapter sends all the locations of a match, also the package database files of an OS package. The Trivy adapter reads `PkgPath`, else the `Target` of a language result that names a file, never a label `Target`. The Nomad and Docker scan scripts get paths later, not in 0.9.10 (issue 1199). | 1077 |
| 2026-11-17 | The findings exports have the paths of a finding. The CSV has the columns `locations_total` and `locations`, with one path on each line of the cell (D1 A). Ingest refuses a control character in a path, so a new line splits the paths with no doubt. CycloneDX puts the paths in `component.evidence.occurrences[].location` (D2 A). OpenVEX has no field for a path and stays as it is. No new size limit (D3). | 1245 |
| 2026-11-07 | The docs give no Ingress example. The `javv` chart makes no Ingress, and the docs tell the user to put one in front (D3). | 1126 |
| 2026-11-19 | Before sign-in, `GET /auth/me` answers 401, and the browser logs one console line for it. The line stays: a 401 is the correct answer when the browser has no session, and the API does not change for it. | 1246 |
| 2026-11-19 | The backend and the two scanner images use the Alpine base of Python (`python:3.12-alpine`, since slice 5 `python:3.14-alpine`), not `python:3.12-slim`. On Debian, each image had about 227 OS findings with no fix. The images also leave out the package managers of their bases. | 1263 |
| 2026-11-19 | The backend and the two scanner images run Python 3.14, not 3.13. Since 2026-10, 3.13 gets only security fixes, as 3.12 does. 3.14 still gets bug fixes (end of life 2030-10). `requires-python` stays `>=3.12`, so ruff keeps its target. The stricter TLS check of Python 3.13 and later gets a note in `docs/UPGRADING.md` and no setting to turn it off. | 1263 |
| 2026-11-20 | Ingest refuses JSON nested deeper than 64 levels with 400 `bad_json`, before the parse (`json_too_deep`). Python 3.14 limits `json.loads` by the stack, so the cap gives one answer on each host. The cap is a rule of the ingest contract, not a setting. | 1263 |

## UI copy and look

| Date | Ruling | Source |
|---|---|---|
| 2026-07-09 | The UI font is Hanken Grotesk. | PR 295 |
| 2026-07-10 | Nuxt UI (the dashboard template) and Framework7 are the design references: their layout and motion, on JAVV tokens, never the libraries. | `.claude/rules/ui-design.md` |
| 2026-10-01 | No em dashes in UI copy. Copy is for users, not engineers: no decision codes, no internal names. No diagrams in the help inside the app. | 341, 652 |
| 2026-10-17 | New names, comments and text use plain words (step, not slice, and panel, not lens). Old names stay. | 543 |
| 2026-10-18 | Videos: the app in a window, a spotlight on the control, and a caption under the window. The pace lets a reader follow. No caption says what the screen does not show. | 699 |
| 2026-11-03 | The dashboard video is one video of 6.5 minutes and about 14 MB. It shows every capability of dashboards. The limit of the other videos stays at 6 MB. The spotlight comes on only when its screen shows. | 1009 |
| 2026-11-14 | The Paths column (option B2 on built pictures): one number for each finding of a row, never added (`0 · 11`). A row with one path opens too. A row with no path shows `0 paths`, and a scan with no paths shows `-`. The list is on white, with the chip of the scanner at the head of each block and the sentence in ink at 13px. The chevron of a control that opens in place points down. A chevron that points right opens another page. On the image page the column comes after Package. | 1077 |
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
| 2026-11-08 | Docker hosts push with the two containers of `deploy/docker/compose.yaml` (issue 1155), one for each scanner, on the JAVV scanner images. The place in JAVV is the Compose project, else the container name. The scan reads the image from the Docker daemon by its image ID. The scan containers skip the label `javv.scan=true`. The Compose file and the Nomad jobs are examples: the scripts do the work, and their scan and push parts stay the same. | 1155 |
| 2026-11-08 | The words of the app are true for each source of scans: the Kubernetes chart, a Nomad job and a Compose file. The scanner cards say "set where it runs", not "operator-managed (GitOps)". The Glossary tells what **Namespace** is for Nomad and Docker, and the label stays (D3 option A). The app says "vulnerability database", not "vuln DB", and no "cross-merge" or "digest-deduped". | 1152 |
| standing | A choice between two looks comes as one picture with A and B side by side. | `frontend/DESIGN.md` section 8.5 |
| 2026-11-09 | The Guide addresses the reader as "you", and a step is a command. It has no "we", "our" or "I", and it names no reader in the third person ("a user", "an admin"). A permission names the role that you need. JAVV, a screen or the data is the subject of a description. Other people stay in the third person only as the data of a screen. | 1142 |
| 2026-11-14 | A rewrite of text for a reader starts with the skill `ste80-humanizer`, which finds the signs of model text. `docs-voice.md` stays the source of the rules, and `ste-lint.py` with exit 0 stays the gate. | 1205, PR 1206 |
| 2026-11-14 | The 3 lists of Settings keep their page when an action reads the list again (`keepPage` of `usePagedSlice`). A number format is `fmt` and a day label is `dayLabel`, both in `lib/format.ts`. | 1190 |
| 2026-11-14 | Each piece of code or style that moves to a shared module gets a functional test in the browser, before and after the move. | 1190 |
| 2026-11-14 | The style rules test checks each property of a shared rule, except a size that a component keeps: the padding of `.empty-row` and the bottom margin of `.screen-head`. | 1190 |
| 2026-11-14 | The ink color of a strong table cell is in `.tbl td.strong`. The selector stops at the cell, so a strong CVE link keeps its own color. A test showed that `.tbl .strong` changed the links of Findings and the Audit log. | 1190 |
| 2026-11-15 | The cell of the approval list has its own class, `.approval-actions`, not the shared `.row-actions`. That class is on the table cell, not on a group of buttons in a cell. | 1190 |
| 2026-11-15 | The first-run text of the image page keeps its padding of `48px 16px` in its card, as a ruled exception of the style rules test. Another component that sets the padding of `.first-run` fails. | 1190 |
| 2026-11-15 | A filter row has one hover, `--control-hover-bg`, in the filter list, in Add filter and in the Columns menu. The Columns menu had `--panel`, which the ruling of 2026-07-28 calls invisible. | 1190 |
| 2026-11-14 | A note in a table head is head text. It joins the name after ` · ` on one line, in the color of the head (9.25:1), for example `Severity mix · Trivy` (Q6 option C, on built pictures). A table head has no chips, no buttons and no second head row. The old note was `--soft` on the slate band, 2.19:1. | 1205 |
| 2026-11-14 | The Findings list has the Paths column, after Package (Q5 option B, on built pictures). Its name stays "Paths". A row with a path opens under itself, as on the image page, and the list read sends `locations=true` while the column shows. This replaces D5 of issue 1077, where the list read sent the number of paths only. | 1205 |
| 2026-11-15 | The Paths column of the Findings list shows by default. A user who moved columns before gets Paths after Package. A column that a stored order does not have goes after the column before it in the default order. A hide of Paths reads nothing. A show reads the page again only when the rows on screen came from a read without their paths (option 3). | 1205 |
| 2026-11-14 | The finding page has a head row: the head band and a Triage cell of 300 px side by side. The cards follow at full width: the evidence, Affected components, then Decisions and Activity side by side (G2 with the quick buttons, on built pictures). This replaces the ruling of 2026-07-17, where Triage stood next to the evidence at the same height (issue 434). | 1205 |
| 2026-11-16 | The Triage cell holds Assigned to, the four state buttons, "Note and more…" and Save. "Note and more…" opens `PopoverShell` with the dark head of a window. The lines that explain the state are in that panel. The Undo line and the save error stay in the cell. A click on Not affected opens the panel at the reason. The risk acceptance window keeps its title. The legend box of the Triage panel is gone (questions 1 B with B2, 2 A and 3 A, on built pictures). | 1205 |
| 2026-11-16 | The finding page has three panels in its head row: the head band, the evidence and the Triage cell, on built pictures. Nothing is lost. The evidence keeps one row for each field and one column for each scanner. This replaces the ruling of round 3 (B2, one row for each scanner), which cut off EPSS and Last seen in a panel. The CVSS, EPSS and SLA tiles go under the facts of the head band. The panel of "Note and more…" opens under the cell when no side has room. | 1205 |
| 2026-11-16 | The package name in the head band opens the panel "Packages with this CVE" (P1 with the look M1, 2026-11-14). The panel lists each package of the CVE on this image. The panel has the dark head of a window. A click opens the finding of that package. The evidence card has no line for the other packages. The text of the evidence card is the text of the text round, group 1. | 1205 |
| 2026-11-16 | Affected components on the finding page has a new line under its title. The line is `The scanners also found ID in these packages and images of cluster NAME.` ID is the ID of the page, and NAME is the name of the selected cluster. The line shows the ID because many IDs are not CVE IDs. The note under the table is gone. Only the line of a cut list stays there. | 1205 |
| 2026-11-16 | The package menu of the finding page is S1 with the dark blue head, on built pictures. It is a panel on the kit dropdown, in place of the panel M1 of 2026-11-14. The list stops at about 9 rows and scrolls, and a filter box shows for more than 8 packages. Each row has the package, its version and its scanners. The menu lists every package of the CVE on the image, and the page always shows the package of its link (issue 1227). | 1205, 1227 |
| 2026-11-16 | The text and the order of the package menu. The filter box says `Filter packages`, and a filter with no match says `No package matches.` A cut list says `This menu shows N packages. The image has more.`, and the count has a `+`. The list keeps the order of the names, and it scrolls to the current package on open. A link to a package that the image does not have says `This image has no finding of ID in PACKAGE VERSION at the selected time.`, then two causes, each in a sentence of its own (STE80, 2026-11-16). | 1205, 1227 |
| 2026-11-16 | The app calls the ID of a finding a vulnerability, because many IDs are not CVE IDs (GHSA, GO, DLA and others). A title or a button says "this vulnerability", for example `Decisions on this vulnerability`. A label says "vuln" only where "vulnerability" is cut off or makes a column wider at 1440 px. These labels are the top bar hint, the Findings search box and the column `Unique vulns` of Top components. A text that is true only of CVE IDs keeps "CVE": the EPSS entry of the glossary. The guard `vulnerability-word.spec.ts` fails "CVE" as a word in the app and in `docs/use`. The field `cve_id`, the filter key `cve` and the panel ID `top-cves` do not change. The text of the MCP server says "vulnerability" too, and a test of `test_mcp_endpoint.py` fails "CVE" as a word in the answer of tools/list. The tool name `top_cves` does not change, because an agent calls a tool by its name. | 1224 |
| 2026-11-16 | A long package name in the head band of the finding page keeps one line. It takes the free space and ends with an ellipsis, and its full name is the hover text (B1). The count and the chevron of the package button never wrap. A row of the package menu keeps its ellipsis and gets the full name as hover text (M1). The plain name of one package follows the same rule. The cut name of the evidence panel is issue 1231. All on built pictures. | 1229 |
| 2026-11-16 | The two scanner columns of the evidence card on the finding page have the same width. Both stay in view. A long package name there keeps one line and ends with an ellipsis. Its full name is the hover text (E1, like B1 of the head band). The other values of the card wrap where they must, so the table never scrolls sideways. On built pictures, over W3 and W4, which wrap the name. | 1231 |
| 2026-11-16 | The e2e gate is the built app against the seeded store, as in CI (D1). A spec that reads only must also pass when it runs alone against the dev stack. `testing.md` §4 names the specs that write and never run against the dev store. `page-errors.spec.ts` accepts the hook name of a development build of Vue and the link of a production build (P1). `keyboard-rows.spec.ts` opens the first image with a Trivy finding and accepts any vulnerability ID in the address (K1). | 1223 |
| 2026-11-17 | The four popovers (the Triage panel, Panel filters, Panel settings and the package menu) open with the genie motion `t-pour`: the card pours out of the tip of its arrow with a round reveal. It opens in 380 ms (`--dur-pour`) and closes in 200 ms. It is a ruled exception to the motion rules: a third duration, a `clip-path` motion and a new class (decision 5, on built videos). The other menus keep `t-pop`. | 1240 |
| 2026-11-17 | A popover has no border line. Its edge is `--pop-drop`, a soft 1 px shadow all around and a drop under it, which follows the arrow too (E2, on built pictures). The arrow has no border, and the card sits on whole pixels. The package menu takes the same edge with `.dd-menu--band`. The other menus keep their line. | 1240 |
| 2026-11-17 | The label column of the evidence card on the finding page is 92 px wide, and a cell has 8 px at each side (N, on built pictures). At 1280 px, a state tag and a severity chip then keep one line, and the table does not scroll sideways. The other options were a state tag on two lines (W) and three panels only from 1440 px (B). | 1231 |
| 2026-11-17 | The Nomad and Docker push scripts send schema 5 with the file paths of a finding. They use the path rules of the scanner package. When a script drops paths, it logs one warning `paths left out of <image>` with two counts and no path (P1). The proof of the change ran both scripts on a live Docker host and a live Nomad 2.1.1 agent (L2). | 1199 |
| 2026-11-15 | `.cap-note` is the line under a list cut at a limit. `.empty-note` is the line of a list with no rows. `base.css` holds only their color and the size of `.cap-note` (option 2). Each place keeps its own margin, because the margin follows the place of the line. No user sees a change. | 1214 |
| 2026-11-20 | Each chart tooltip is DOM nodes from `charts/chartTooltip.ts`, never an HTML string. The policy of the frontend server keeps `style-src` with no `'unsafe-inline'`, because an inline style lets an injection change the page. The tooltip writes each text with `textContent`, and base.css gives the layout. The donut tooltip is one row with a dot, the name, the value in bold and the share (D1). Research and a test in Chromium and Firefox are on the issue. | 1272 |
| 2026-11-17 | The text of the app is in strict STE, with one name for each thing: the term list of `docs-voice.md` (D1). The database is "the database", not "the store". The panel titles "Scan ingest activity" and "Failed ingests" stay. | 1247 |
| 2026-11-17 | A hint, a note or an empty text in the app is a full sentence. A label, a column head and a button keep a short form, in plain words (D2 A). | 1247 |
| 2026-11-17 | The text of the app keeps "check" as a verb (D3 B). | 1247 |
| 2026-11-17 | The videos and the README GIF get one new recording, after the last slice of the text pass. That recording has its own PR (D4 A). | 1247 |
| 2026-11-17 | The text pass of issue 1247 replaces the words of some older copy rulings. These are the four health banners (2026-10-02, 2026-10-12, 2026-10-13) and the alert of a refused filter (2026-10-23). The sign-in line of a session that the browser did not keep (2026-10-15) is one too. The new texts are in strict STE and say "database". The tone, the place and the behaviour of each ruling stay. | 1247 |
| 2026-11-18 | The text of the app makes no promises. It says what a page does now, and it names no future release. The notices for a past time on All clusters and Scanner status say that the page cannot show a past time. | 1247 |
| 2026-11-18 | Slices S1 to S3 of issue 1247 go up as one PR of 146 files. One review page holds every changed string, with the pictures of main and of the change. | 1247 |
| 2026-11-18 | Slices S4 and S5 of issue 1247 join the same PR. One PR of 204 files holds all of the text pass. The text test then has no exceptions. | 1247 |
| 2026-11-19 | The camera rule of the videos stays. After a click, the new screen shows at the old zoom for the result hold, and then the camera moves to the next box. A window can be partly out of the view for that time. | 1246 |

## AI vulnerability research (alpha)

The plan of the agent skill is in issue 1193. The issue body has the current state, and the comments have the full text of each ruling.

| Date | Ruling | Source |
|---|---|---|
| 2026-11-12 | 1. "Internal" lowers the urgency of a CVE. It seldom makes the risk zero: with no NetworkPolicy, each pod can reach each other pod. | 1193 |
| 2026-11-12 | 2. Exposure goes through other services, for example internet → Keycloak → Postgres. The answer gives the full path, ingress and egress, not one connection. | 1193 |
| 2026-11-12 | 3. Workload modelling is not a JAVV task. JAVV gives the CVE and its location. A flow tool gives the network. The agent reads the cluster itself. | 1193 |
| 2026-11-12 | 4. The agent reads the cluster with `kubectl`. No Kubernetes MCP server. | 1193 |
| 2026-11-12 | 5. The skill only reads. It does not touch Secrets. | 1193 |
| 2026-11-12 | 6. A flow tool that runs on each node is acceptable as an optional module, off by default. | 1193 |
| 2026-11-12 | 7. The POC uses a built scenario on the dev cluster alpha, with known answers. | 1193 |
| 2026-11-12 | 8. An answer passes when four parts are true. The exposure class and the path agree with the known answer. Each claim cites a tool output. Missing data shows as "unknown". The answer has no invented facts. | 1193 |
| 2026-11-12 | 9. Each answer starts with the scan date of each scanner, from the event with the highest `scan_order` in `image_timeline`. The skill does not look up KEV or EPSS by CVE id. When the scan is old, the skill can tell the person what to check. | 1193 |
| 2026-11-12 | 10. The flow module uses the upstream image of the tool, pinned by digest in `versions.yaml` and bumped by Renovate. CI checks its cosign signature before a bump merges. JAVV does not build the image again. No image with code comes from a registry at run time. | 1193 |
| 2026-11-12 | 11. The skill first answers 10 questions with the JAVV MCP endpoint and `kubectl` only. The evals have two arms: without and with flow data. If flow data changes fewer than 2 of the 10 answers, the alpha has no flow module. | 1193 |
| 2026-11-12 | 12. The skill reads the names of env keys only, never their values, and no ConfigMaps. It names a read-only ClusterRole with no access to secrets, configmaps, `pods/exec`, `pods/log`, `pods/proxy` or `pods/portforward`. Ruling 14 adds an optional Role for `pods/log`. The flow tool pushes OTLP to a collector in the cluster and opens no port on the nodes. The agent reads flow data through the JAVV MCP endpoint. | 1193 |
| 2026-11-12 | 13. A stored edge has the cluster, the server port, and the first and last time seen. Each side is an image digest and a namespace. The destination can also be an external class. JAVV stores no workload names (issue 308). The collector maps owners to digests with the pod list that the scanner already reads. | 1193 |
| 2026-11-13 | 14. The skill can read the access logs of the ingress controller, with consent. An optional Role gives `get` on `pods/log` in the namespace of the ingress controller only. The skill asks before each read. A filter on the machine of the person sends only the client address, the host and a count to the agent. Reads of configuration need no question. Secrets, ConfigMaps, `pods/exec`, `pods/proxy` and `pods/portforward` stay forbidden. | 1193 |
| 2026-11-12 | Step 0 rule: a workload is public when an entry point to it is public. The skill finds exposure from the entry points (LoadBalancer or NodePort Services, Ingress, Gateway routes), not from the callers. One call from the internet in the flow data shows exposure. No call in the window does not show that the workload is private. | 1193 |
| 2026-11-12 | Step 0 rule: keep the server port, drop the client port. A client port makes a new series for each connection. | 1193 |

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
| 2026-11-19 | Each new image build gets a test of the old and the new images side by side. The test covers function, logs, speed and the rest. The rig is `development/e2e/image-ab.sh`, run by hand for now. Its report goes in the PR body. | 1263 |
