# Issue 1205: settled UI changes

Each row is an operator ruling on built pictures (DESIGN.md section 8.5). The picture in the row is
the proof: it shows the ruled option, built on the real components and the dev data of cluster
alpha. The pictures are also on branch `visual-assets`, folder `1205/settled/`.

| Q | Ruling (operator, 2026-11-14) | Proof | Built in |
|---|---|---|---|
| Q1 | The head band of the finding page stays as today. The operator rejected round 1 (B, label and value pairs) and round 2 (C, the risk facts in a side column). | `q1-head-band-today.png` | Nothing to build. |
| Q5 | Paths on the Findings list: option B. The column comes after Package. The count is the button of the image page, and the row opens to list the paths. | `q5-findings-list-paths.png` | PR B of the plan |
| Q5 | The name stays "Paths". The operator rejected "Found in" and "Locations". | `q5-findings-list-paths.png` | PR B of the plan |
| Q2 | The evidence: one row for each scanner (B2), the direction of the prototype. A value that differs gets no extra mark (M0): the two values show it. Ruled on round 3. | `q2-evidence-rows.png` | PR C of the plan |
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

## Still open

Nothing in the UI and the text. The operator plans the PRs next.

## Where the rounds are

- Round 1: issue 1205, comment 6878538508 (pictures `q*.png` in the parent folder).
- Round 2: comment 6879024862 (`r2-*.png`).
- Round 3: comment 6879278530 (`r3-*.png`).
- Round 4: comment 6879683168 (`r4-*.png`).
- Round 5: comment 6879978982 (`r5-*.png`).
- Text round: comments 6880398386, 6880583694 (a correction), 6880711120 and 6881237662 (`t1-*.png`, `t2-*.png`, `t3-*.png`).
- Package menu: comment 6881679933 (`t4-package-menu.png`).
