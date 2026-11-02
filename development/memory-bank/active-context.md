# Active context

As of: 2026-11-02

This file shows the open, held and next work on the date above. The live status is on GitHub:
issue 555 (the roadmap) and the 1.0.0 milestone. After each release, a docs PR updates this file.

## Where the project is

- The last release is 0.9.4 (2026-10-30): the kit search box, the lint rule against raw form
  fields, release notes with a What's new section, and the window heads and boxes (issues 1045,
  1049, 1050, 1053, 1055, 1061).
- The phase is hardening for 1.0 (issue 555, phase 3).

## In progress

- Issue 1076: JAVV counts findings, not the entries of a scanner report. PR A (PR 1080) is on
  main: ingest keeps one finding for each finding key, and the scan event keeps `report_entries`
  (mapping version 21). PR B adds the user guide text and the records.
- The release PR for 0.9.5 (PR 1066) waits for issues 1076 and 1063 (operator, 2026-11-02).
- Next: issue 1063 (filters on the Riskiest images and Triage activity panels), then issue 1077
  (the files where a scanner found a finding, mapping version 22).

## Open, in the 1.0.0 milestone

| Issue | What |
|---|---|
| 131 | Single sign-on with OIDC or LDAP |
| 597 | Renovate major updates, the last step before 1.0 |
| 697 | A short video of the evolution of JAVV |

## Open, no milestone

| Issue | What | Note |
|---|---|---|
| 1009 | A video for the page "Build a dashboard" | On the operator's word |
| 884 | A version stamp for the preferences that the browser keeps | Later |
| 903 | All clusters sends 3 requests for each cluster | After 1.0 |

## After 1.0

| Issue | What |
|---|---|
| 308 | Pod and workload mapping for findings |
| 664 | Scheduled backups, with scan history |
| 791 | Trivy and Grype apply the VEX export |
