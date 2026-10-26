# Active context

As of: 2026-10-26

This file shows the open, held and next work on the date above. The live status is on GitHub:
issue 555 (the roadmap) and the 1.0.0 milestone. After each release, a docs PR updates this file.

## Where the project is

- The last release is 0.8.9 (2026-10-26). It holds composable dashboards (issue 440), the Roles
  card (issue 990) and the `can_export` permission (issue 243).
- Release 0.9.0 comes next. It has no code changes after 0.8.9: it marks the 0.8.9 changes as a
  minor release (operator, 2026-10-26).
- The phase is hardening for 1.0 (issue 555, phase 3).

## In progress

- **Issue 1012:** the memory bank is in (PR 1013). Next: the bolts frozen as history, then a docs
  pass over each live Markdown file against the code.

## Open, in the 1.0.0 milestone

| Issue | What |
|---|---|
| 131 | Single sign-on with OIDC or LDAP |
| 597 | Renovate major updates, the last step before 1.0 |
| 697 | A short video of the evolution of JAVV |
| 999 | Filters on a dashboard panel |

## Open, no milestone

| Issue | What | Note |
|---|---|---|
| 1000 | At a past time, a KEV finding gets the SLA deadline of its severity | The operator decides later |
| 1004 | Tidy the cards of Dashboards and Saved views | After issue 440, on the operator's word |
| 1009 | A video for the page "Build a dashboard" | On the operator's word |
| 1011 | Segmented controls have no name for screen readers | Found during issue 440 |
| 884 | A version stamp for the preferences that the browser keeps | Later |
| 903 | All clusters sends 3 requests for each cluster | After 1.0 |

## After 1.0

| Issue | What |
|---|---|
| 308 | Pod and workload mapping for findings |
| 664 | Scheduled backups, with scan history |
| 791 | Trivy and Grype apply the VEX export |
| 926 | Development moves to `Danube-Labs/javv` |
