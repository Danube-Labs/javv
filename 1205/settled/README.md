# Issue 1205: settled UI changes

Each row is an operator ruling on built pictures (DESIGN.md section 8.5). The picture in the row is
the proof: it shows the ruled option, built on the real components and the dev data of cluster
alpha. The pictures are also on branch `visual-assets`, folder `1205/settled/`.

| Q | Ruling (operator, 2026-11-14) | Proof | Built in |
|---|---|---|---|
| Q1 | The head band of the finding page stays as today. Round 1 (B, label and value pairs) and round 2 (C, the risk facts in a side column) are rejected. | `q1-head-band-today.png` | Nothing to build. |
| Q5 | Paths on the Findings list: option B. The column comes after Package. The count is the button of the image page, and the row opens to list the paths. | `q5-findings-list-paths.png` | PR B of the plan |
| Q5 | The name stays "Paths". "Found in" and "Locations" are rejected. | `q5-findings-list-paths.png` | PR B of the plan |
| Q6 | The notes of the table heads: option C. The note joins the name in the head text on one line, for example "Severity mix · Trivy", at the full head color (9.25:1). No chips or buttons in a table head. Grouped two-row heads are rejected. | `q6-table-heads-one-line.png` | PR A of the plan |

## Still open

| Q | State |
|---|---|
| Q2 | The evidence as one row for each scanner (B2) "looks nice". The mark for a value that differs is open: round 3 shows no mark (M0), a note under the table (M1) and an icon in the cell (M2). |
| Layout | The Triage panel is the cause of the uneven rows. Round 3 shows E (Triage as one band under the head) and F (Triage in a side panel that opens from a strip). |
| Q4 and the paths text | Wait until the layout is settled. |

## Where the rounds are

- Round 1: issue 1205, comment 6878538508 (pictures `q*.png` in the parent folder).
- Round 2: comment 6879024862 (`r2-*.png`).
- Round 3: `r3-*.png`.
