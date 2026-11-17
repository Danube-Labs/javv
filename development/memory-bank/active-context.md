# Active context

As of: 2026-11-17

This file shows the open, held and next work on the date above. The live status is on GitHub:
issue 555 (the roadmap) and the 1.0.0 milestone. After each release, a docs PR updates this file.

## Where the project is

- The last release is 0.9.10 (2026-11-17): the paths of a finding on the screens and in the
  exports, a new layout for the finding page, two dashboard panels, and the word "vulnerability".
- The phase is hardening for 1.0 (issue 555, phase 3).

## Next

| Issue | What | Note |
|---|---|---|
| 1247 | The text of the app in strict STE: one pass over every screen | The plan comment of 2026-11-17 has six slices. Decisions D1 to D4 wait for the operator. |
| 1246 | Older open items: the camera of video 3, the `dueAt` warnings, the `uv run` question, a 401 before sign-in | Not urgent |

Each step starts on the word of the operator.

## Held

| Issue | What | Note |
|---|---|---|
| 1193 | AI-assisted vulnerability research (alpha): an agent skill with network context | No milestone since 2026-11-17. Step 1 waits for a go. The rulings are in `rulings.md`. |

## Loose ends

Small items that no issue tracks.

- The past-time words of the panel Top components (after issue 1176).
- `deploy/compose/.env.example` has the comment "OpenSearch's admin password:" two times (after issue 1155).
- The intro caption of video 1 keeps "It never merges them" (issue 1143). The operator changed only the label.
- A scheduled rebuild and scan of the published images: not needed now (operator, 2026-11-17, issue 1245).

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
