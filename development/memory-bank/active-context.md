# Active context

As of: 2026-11-15

This file shows the open, held and next work on the date above. The live status is on GitHub:
issue 555 (the roadmap) and the 1.0.0 milestone. After each release, a docs PR updates this file.

## Where the project is

- The last release is 0.9.9 (2026-11-09). Release PR 1175 (0.9.10) is open. The milestone 0.9.10
  holds the work for it.
- The work of issues 1077, 1176, 1181, 1190, 1191 and 1197 is in `main`, for 0.9.10.
- The phase is hardening for 1.0 (issue 555, phase 3).

## Next, in this order, before release 0.9.10 (operator, 2026-11-15)

| Step | Issue | What | Plan |
|---|---|---|---|
| 1 | 1214 | The two note lines `.cap-note` and `.empty-note`: option 2, the equal part to `base.css` | The plan comment on the issue |
| 2 | 1205 | The finding page, the paths and the table heads: PR A, PR B, PR C1, PR C2 | Issue comment 6878381960. The rulings and their pictures are in `1205/settled/` on the branch `visual-assets` |
| 3 | 1199 | Nomad and Docker scans send the file paths of a finding | The issue body. The operator moved it into 0.9.10 on 2026-11-15 |

All three are in the milestone 0.9.10. Each step starts on the word of the operator.

## Held

| Issue | What | Note |
|---|---|---|
| 1193 | AI-assisted vulnerability research (alpha): an agent skill with network context | In the milestone 0.9.10. Step 1 waits for a go. The rulings are in `rulings.md`. |

## Loose ends

Small items that no issue tracks.

- The past-time words of the panel Top components (after issue 1176).
- `deploy/compose/.env.example` has the comment "OpenSearch's admin password:" two times (after issue 1155).
- The intro caption of video 1 keeps "It never merges them" (issue 1143). The operator changed only the label.

## Open, in the 1.0.0 milestone

| Issue | What |
|---|---|
| 131 | Single sign-on with OIDC or LDAP |
| 597 | Renovate major updates, the last step before 1.0 |
| 697 | A short video of the evolution of JAVV |

## Open, no milestone

| Issue | What | Note |
|---|---|---|
| 884 | A version stamp for the preferences that the browser keeps | Later |
| 903 | All clusters sends 3 requests for each cluster | After 1.0 |

## After 1.0

| Issue | What |
|---|---|
| 308 | Pod and workload mapping for findings |
| 664 | Scheduled backups, with scan history |
| 791 | Trivy and Grype apply the VEX export |
