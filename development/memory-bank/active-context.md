# Active context

As of: 2026-10-30

This file shows the open, held and next work on the date above. The live status is on GitHub:
issue 555 (the roadmap) and the 1.0.0 milestone. After each release, a docs PR updates this file.

## Where the project is

- The last release is 0.9.3 (2026-10-29): role names in words, and one 30px height with a 1px
  edge for every control in a screen head (issue 1039).
- The phase is hardening for 1.0 (issue 555, phase 3).

## In progress

- Issue 1055: checks that keep the text boxes, search boxes and window buttons the same on every
  screen. PR A (the kit text box, text area and dropdown, PR 1058) is on main. PR B adds the kit
  search box and the lint rule against raw form fields. PR C adds a walk that compares the screens.
  Main also has issues 1049, 1050 and 1053 (the window heads, the boxes and the window buttons).
  The release PR for 0.9.4 (PR 1047) lists their PRs 1051, 1052 and 1054.
- Issue 1043, the same 1px edge on the other bordered buttons, is not planned: the operator ruled
  on 2026-10-29 that the change is too small to see. The issue lists the files that the change
  would touch.

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
| 1009 | A video for the page "Build a dashboard" | On the operator's word |
| 884 | A version stamp for the preferences that the browser keeps | Later |
| 903 | All clusters sends 3 requests for each cluster | After 1.0 |

## After 1.0

| Issue | What |
|---|---|
| 308 | Pod and workload mapping for findings |
| 664 | Scheduled backups, with scan history |
| 791 | Trivy and Grype apply the VEX export |
