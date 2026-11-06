# Active context

As of: 2026-11-06

This file shows the open, held and next work on the date above. The live status is on GitHub:
issue 555 (the roadmap) and the 1.0.0 milestone. After each release, a docs PR updates this file.

## Where the project is

- The last release is 0.9.6 (2026-11-06): an MCP server for AI agents, with MCP tokens of three
  levels, an audit row for each tool call, and a docs page "Use the MCP server" (issue 1096).
- The phase is hardening for 1.0 (issue 555, phase 3).

## In progress

- Issue 1108: install 0.9.6 from zero by the published docs, with docker compose and with Helm,
  and scanners in a Kubernetes cluster. It starts on the word of the operator.

## Held

- Issue 1077: a finding shows the files where the scanner found it. The plan changed after issue
  1076, and its decisions D1 to D5 wait for the operator. Priority low since 2026-11-03.

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
