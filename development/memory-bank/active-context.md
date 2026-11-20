# Active context

As of: 2026-11-20

This file shows the open, held and next work on the date above. The live status is on GitHub:
issue 555 (the roadmap) and the 1.0.0 milestone. After each release, a docs PR updates this file.

## Where the project is

- The last release is 0.9.11 (2026-11-19): the text of the app in strict STE, and one page load
  before sign-in.
- The phase is hardening for 1.0 (issue 555, phase 3).
- `main` holds the work of issue 1263 for the next release (0.9.12). The backend and the two scanner
  images run on `python:3.14-alpine` and leave out the package managers of their bases. The four
  images and both scanners have 88 findings, against 1,517 on 0.9.11 (one scanner database for both,
  2026-11-20). Python 3.14 checks TLS certificates more strictly, and `docs/UPGRADING.md` has a note
  for it. Ingest refuses JSON nested deeper than 64 levels.

## Next

- Release 0.9.12 (PR 1266), on the word of the operator.
- Then issue 1263 closes after a new scan of the deployment that reported the 1,360 findings.

Apart from these, the operator chooses the next step from the tables below.

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
- `/readyz` logs nothing when the ping to OpenSearch fails. A certificate that changes after the
  start shows only as 503 `unreachable` (after issue 1263).
- The docs do not tell how a scanner trusts a private CA for an `https` backend (after issue 1263).
- Two library warnings stop a run of the suite with `-W error::DeprecationWarning`: the unset
  `asyncio_default_fixture_loop_scope` of pytest-asyncio, and `enable_cleanup_closed`, which
  opensearch-py passes to aiohttp (after issue 1263).
- In the A/B rig of issue 1263, the peak memory of the backend on Python 3.14 was 238 MiB, against
  216 MiB on 3.12, in one run. The cause is not known.

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
