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

## Still open

| Q | State |
|---|---|
| Q4 text, groups 1 and 2 | The evidence card and the rest of the Triage cell and panel text: waiting for the operator. |
| Other packages | Three options for the links to the other packages of the CVE (P1 switcher, P2 tabs, P3 badges): comment 6880711120. |

## Where the rounds are

- Round 1: issue 1205, comment 6878538508 (pictures `q*.png` in the parent folder).
- Round 2: comment 6879024862 (`r2-*.png`).
- Round 3: comment 6879278530 (`r3-*.png`).
- Round 4: comment 6879683168 (`r4-*.png`).
- Round 5: comment 6879978982 (`r5-*.png`).
- Text round: comments 6880398386, 6880583694 (a correction) and 6880711120 (`t1-*.png`, `t2-*.png`, `t3-*.png`).
