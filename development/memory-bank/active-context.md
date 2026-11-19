# Active context

As of: 2026-11-19

This file shows the open, held and next work on the date above. The live status is on GitHub:
issue 555 (the roadmap) and the 1.0.0 milestone. After each release, a docs PR updates this file.

## Where the project is

- The last release is 0.9.11 (2026-11-19): the text of the app in strict STE, and one page load
  before sign-in.
- The phase is hardening for 1.0 (issue 555, phase 3).

## Next

No issue is next. The operator chooses the next step from the tables below.

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
- Three texts of the app still say "could not": "Findings could not be loaded.", "Events could not
  be loaded." and the answer of a dashboard import that JAVV cannot read. The text test does not
  look for "could not" (after issue 1247).
- On the dev machine, `vitest run` shows no console output of a passing test without
  `--silent=false`. CI shows it. The cause is not known (issue 1246).

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
| 1177 | Research: what an app is, from Kubernetes labels, as a future triage column | Research |
| 1239 | Research: host vulnerabilities, a Hosts page for the packages of each node | Research |
| 903 | All clusters sends 3 requests for each cluster | After 1.0 |

## After 1.0

| Issue | What |
|---|---|
| 308 | Pod and workload mapping for findings |
| 664 | Scheduled backups, with scan history |
| 791 | Trivy and Grype apply the VEX export |
