# Golden scanner fixtures

Real Trivy and Grype JSON captured from live scans, then **trimmed** to a small,
deterministic, severity-stratified subset (structure + metadata preserved). Tests read
these frozen files — they never call a live scanner or vuln-DB (`testing.md`: deterministic).

| Fixture | Image | Notes |
|---|---|---|
| `trivy-python-3.9.16-slim.json` | `python:3.9.16-slim` (Debian) | Trivy finds CVEs — spans CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN |
| `grype-python-3.9.16-slim.json` | `python:3.9.16-slim` | Grype matches — spans Critical…Negligible/Unknown; some carry EPSS |
| `trivy-alpine-3.14.json` | `alpine:3.14` (EOL) | **0 findings** — alpine secdb has no advisories for the EOL release |
| `grype-alpine-3.14.json` | `alpine:3.14` | 73 matches (NVD-based) |
| `trivy-paths.json` | `node:16-slim`, `tomcat:9.0.50-jdk11`, `rancher/local-path-provisioner:v0.0.36` | Trivy 0.76.2. The file paths of a finding (issue 1077): a Debian package with no path, Node.js and Java packages with `PkgPath` under a label `Target`, and one CVE in two Go binaries with the file in `Target` |
| `grype-paths.json` | the same three images | Grype 0.121.1. A Debian package with its package database files, a jar, an npm package, and one CVE in two Go binaries |

The alpine pair is the **per-scanner disagreement** case JAVV exists to surface: same
image, Trivy=0 vs Grype=73 → disagreement flag, **never merged**. It also exercises the
adapter's empty-results path.

## Regenerate
```bash
trivy image --quiet --scanners vuln --format json -o <out>.json <image>
grype <image> -o json > <out>.json
# then trim to a small stratified subset (see the trim used in the M0 PR history)
```
The two `*-paths.json` files keep the `Packages` of the kept entries only, so they stay small.
Tags are pinned; bump deliberately. The point is "old enough to have findings," not "latest."
