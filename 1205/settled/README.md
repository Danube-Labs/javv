# Issue 1205: settled UI changes

Each row is an operator ruling on built pictures (DESIGN.md section 8.5). The picture in the row is
the proof: it shows the ruled option, built on the real components and the dev data of cluster
alpha. The pictures are also on branch `visual-assets`, folder `1205/settled/`.

| Q | Ruling (operator, 2026-11-14) | Proof | Built in |
|---|---|---|---|
| Q1 | The head band of the finding page stays as today. The operator rejected round 1 (B, label and value pairs) and round 2 (C, the risk facts in a side column). | `q1-head-band-today.png` | Nothing to build. |
| Q5 | Paths on the Findings list: option B. The column comes after Package. The count is the button of the image page, and the row opens to list the paths. | `q5-findings-list-paths.png` | PR B of the plan |
| Q5 | The name stays "Paths". The operator rejected "Found in" and "Locations". | `q5-findings-list-paths.png` | PR B of the plan |
| Q2 | Replaced on 2026-11-16 by the three panels (see below). The evidence: one row for each scanner (B2), the direction of the prototype. A value that differs gets no extra mark (M0): the two values show it. Ruled on round 3. | `q2-evidence-rows.png` | PR C of the plan |
| Layout | Triage moves out of the run of cards into its own cell next to the head band (G2 with quick buttons). The cell holds Assigned to, the four state buttons and Save. "Note and more…" opens a menu panel (`PopoverShell`) next to the cell, with the note, the reason for "Not affected", Risk-accept and Save. The cell and the panel share one draft. The cards under the head take the full width: the evidence, Affected components, then Decisions and Activity side by side. Ruled on round 5. | `layout-triage-cell.png` | PR C of the plan |
| Q6 | The notes of the table heads: option C. The note joins the name in the head text on one line, for example "Severity mix · Trivy", at the full head color (9.25:1). No chips or buttons in a table head. The operator rejected grouped two-row heads. | `q6-table-heads-one-line.png` | PR A of the plan |
| Q4 text | Affected components and the paths text: the new sentences of the text round (group 3). This includes "JAVV counts it as one finding" and the OS package lines for Trivy and Grype. Ruled on the text round. | `text-affected-and-paths.png` | PR A (paths text) and PR C |
| Q4 text | Decisions on this CVE and Activity on this finding: the new sentences of the text round (group 4). Ruled on the text round. | `text-decisions-activity.png` | PR C of the plan |
| Q4 text | The Triage panel has no legend box ("Fixed" and "Stale"). The Guide tells the same in "Scans and freshness", and a Stale finding shows its own block. Ruled on text round step 2. | `text-panel-no-legend.png` | PR C of the plan |
| Other packages | The other packages of the CVE on this image: option P1. The package name in the head band opens a menu with each package of the CVE on this image. A count ("4 on this image") shows next to the name. A click opens the finding of that package. The note at the bottom of the evidence card goes. The operator rejected P2 (tabs) and P3 (badges), and the underlined links of the first try. | `page-ruled-first-screen.png`, `packages-options.png` | PR C of the plan |
| Q4 text | The evidence card (group 1). The line under the title is `Each row shows the values that one scanner sent.` The operator removed `JAVV does not change them`: it explains nothing. The note "Scanners agree on severity…" goes. The note for scanners that disagree is `The scanners give different severities. Each row shows the severity that its scanner sent.` | `page-ruled-first-screen.png` | PR C of the plan |
| Q4 text | The Triage cell and panel (group 2) use the text of comment 6880398386. This includes "Save", the line under Save, "Add a note for Activity…" and "Accept the risk of this CVE…". It also includes the blocks of a Stale finding, of a Risk accepted finding and of a role that cannot change a risk acceptance. "Note and more…" stays. | `text-triage-cell-and-panel.png` | PR C of the plan |
| Package menu | The menu of P1 has the look M1: the kit panel `PopoverShell` beside the package name. It has an arrow, the title "Packages with this CVE", the image and a close button. The current package has a check mark. The operator rejected the first menu (too close to the card) and M2 (a dropdown with a gap and a deep shadow). | `package-menu-m1.png` | PR C of the plan |
| PR B, 2026-11-15 | Paths on the Findings list shows by default. A user who moved columns before gets it after Package. A hide of Paths reads nothing, and a show reads the page again only when the rows on screen lack their paths (option 3). | Examples in the session, no picture: the rulings are about reads and order, not looks. | PR 1219 |
| PR C1, 2026-11-16 | The lines that explain the state go in the panel of "Note and more…" (1B). These are the history line, the two role lines and the blocks of a Risk accepted and a Stale finding. The Undo line and the save error stay in the cell (B2), because they answer a save in the cell. | `c1-ruled-choices.png`, `c1-save-lines-in-cell.png` | PR C1 |
| PR C1, 2026-11-16 | A click on Not affected in the cell opens the panel at the reason (2A). | `c1-ruled-choices.png` | PR C1 |
| PR C1, 2026-11-16 | The risk acceptance window keeps the title "Risk-accept this CVE" (3A). | `c1-ruled-choices.png` | PR C1 |
| PR C1, 2026-11-16 | The head of the "Note and more…" panel is dark blue, as the head of a window. `PopoverShell` gets a property that a panel must turn on, so the other panels keep their light head. When the arrow points from the head, the arrow is dark blue too. | `c1-ruled-choices.png` | PR C1 |
| PR C1, 2026-11-16 | The text of the state lines in strict STE is the 11 rows of comment 6909666536. The rows include the history line, the role lines, the Undo line and the save errors. | `c1-ruled-choices.png` | PR C1 |
| PR C1, 2026-11-16 | Three panels in the head row: the head band, the evidence and the Triage cell (option X). Nothing is lost. The evidence keeps one row for each field and one column for each scanner. This replaces Q2 B2 (one row for each scanner), which cut off EPSS and Last seen in a panel (option Y). The CVSS, EPSS and SLA tiles go under the facts. | `c1-three-panels-options.png`, `c1-three-panels-menu.png` | PR C1 |
| PR C1, 2026-11-16 | "Packages with this CVE" has the dark blue head of a window. The menu and the text of the evidence card move from PR C2 to PR C1 with the three panels. | `c1-three-panels-menu.png` | PR C1 |
| PR C1, 2026-11-16 | "Note and more…" stays on in history and for a role without triage. The panel tells why the controls are off, as for a triager on a Risk accepted finding. | `c1-ruled-choices.png` | PR C1 |
| PR C2, 2026-11-16 | Affected components, the line under the title: `The scanners also found ID in these packages and images of cluster NAME.` ID is the ID of the page (a CVE, GHSA or GO ID). The note under the table goes. Comment 6910056927. | No picture: a text ruling. | PR C2 |

## Still open

Nothing in the UI and the text. The word for an ID that is not a CVE ID is issue 1224.

## Where the rounds are

- Round 1: issue 1205, comment 6878538508 (pictures `q*.png` in the parent folder).
- Round 2: comment 6879024862 (`r2-*.png`).
- Round 3: comment 6879278530 (`r3-*.png`).
- Round 4: comment 6879683168 (`r4-*.png`).
- Round 5: comment 6879978982 (`r5-*.png`).
- Text round: comments 6880398386, 6880583694 (a correction), 6880711120 and 6881237662 (`t1-*.png`, `t2-*.png`, `t3-*.png`).
- Package menu: comment 6881679933 (`t4-package-menu.png`).
- PR C1 questions: comments 6908924347 (kickoff), 6909055761 (pictures `c1-q*.png`), 6909666536
  (the text table) and 6910056927 (the rulings).
