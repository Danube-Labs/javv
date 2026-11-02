# Security (engineering side)

How JAVV keeps its own code, secrets and supply chain safe. **Reporting a vulnerability, scope and
supported versions** are in the root [`SECURITY.md`](../../SECURITY.md); dependency rules are in
[dependency-policy.md](dependency-policy.md). This file is the threat model and the checks that
enforce it.

## Trust boundaries

| Boundary | Untrusted input | Main risks |
|---|---|---|
| **Ingest** (`POST /api/v1/ingest/*`, machine tokens) | scanner output, compressed, from inside monitored clusters | forged or cross-tenant pushes, oversized or zip-bomb bodies, malformed payloads, flooding |
| **Human API + UI** (sessions) | every request parameter, saved views, notes | privilege escalation, reading another tenant's data (IDOR), query-DSL injection |
| **OpenSearch** | nothing directly, but every query is built from the two above | a missing `cluster_id` filter leaks another tenant |
| **Supply chain** | dependencies, base images, GitHub Actions, the scanner binaries we package | a compromised or vulnerable upstream reaching a published artifact |

## The ingest surface

The only endpoint that parses data a monitored cluster produces. What protects it, in request order:

1. **Rate limit per presented token**, before the token is checked (`routers/ingest.py`,
   `JAVV_INGEST_RATE_LIMIT_PER_MINUTE`): past it, a 429.
2. **Token check:** tokens are stored only as peppered SHA-256 hashes and compared in constant time
   (`core/security.py`, `hmac.compare_digest`). A 401 is metric-only, never a log line, so an
   unauthenticated sender can't choose our log volume (`.claude/rules/logging.md`).
3. **Size caps**, compressed and after decompression (`JAVV_INGEST_MAX_COMPRESSED_BYTES`,
   `JAVV_INGEST_MAX_BODY_BYTES`): a zip bomb stops at the cap with a 413.
4. **Strict schema:** the envelope model is `extra="forbid"` (`models/envelope.py`), so unknown
   fields are a 422, and scanner vocabulary is canonicalized at the boundary.
5. **Scope binding:** a token belongs to one `(cluster, scanner)`; a payload claiming another is
   refused (`scope_mismatch`). Everything is routed on the **token's** scope, never the payload's.
6. **Refusals past the token check are recorded** for the failed-ingests view (issue 357), with
   sender-chosen text capped and stripped of control characters.

JAVV never writes to the clusters it monitors; the scanners push to it.

## Humans, tenants and queries

- **Sessions** are server-side, stored as peppered hashes, with a 24-hour lifetime
  (`JAVV_SESSION_TTL_HOURS`). Passwords are at least 12 characters (`auth/passwords.py`), failed
  logins lock out per username (`auth/lockout.py`), and the bootstrap admin must change its
  password before doing anything else.
- **Authorization is by capability**, checked server-side on every mutating route. New mutating
  routes join the RBAC/IDOR registry test (`backend/tests/security/test_rbac_idor_contract.py`).
- **Tenant isolation is in the query layer:** reads go through `tenant_search`
  (`tenancy/read_path.py`), which forces the `cluster_id` filter; indices are routed on the
  immutable `cluster_id`, never the relabelable name.
- **Query DSL is built from structures, never string concatenation.** The data inspector is a
  read-only allowlist and journals every query.

## Secrets

- **Never in the repo.** Real values live in the deployment's secret store; dev values in a local,
  untracked env file.
- **`JAVV_SECRET_KEY`** hashes every ingest token and session id, and signs download links. A production process refuses
  to start on the dev default (`core/settings.py`, `assert_production_ready`). Rotating it
  invalidates every token and session.
- **The bootstrap admin password** is only a first-login credential; it must be changed at once.
- **Logs** go through the shared logger, whose redaction processor replaces bearer tokens and
  secret-looking keys with `[REDACTED]` (`libs/javv-common`). Never pre-format a secret into a
  message string.

## The checks that run

| Check | Where | On failure |
|---|---|---|
| GitHub secret scanning + push protection | repo settings | the push is blocked |
| gitleaks, full history, the repo's `.gitleaks.toml` | CI **Secret scan** job, every PR and push | the job fails |
| Dependency audit (`npm audit`, `pip-audit`) | CI, every PR and push | report-only for now ([dependency-policy.md](dependency-policy.md)) |
| GitHub vulnerability alerts → Renovate security PRs | repo settings + Renovate | a PR, fixed within the [policy's](dependency-policy.md) deadline |
| RBAC/IDOR registry | backend tests | CI fails |
| Ingest round trip: each supported scanner version's real output pushed into a real backend, the store checked against it: the findings counts against the history rows, and the stored report entries against the sent ones | `scanner-images.yml` compat job + `development/scripts/check-ingest-roundtrip.sh` | the job fails, and publish needs it |
| SBOM + report-only Grype pass over the scanner images | `.github/workflows/scanner-images.yml` | reported, not blocking |
| cosign keyless signature + signed SBOM attestation of each published image, by digest | `scanner-images.yml` and `release-please.yml` (the app images, issue 615) via `.github/actions/sign-image` | the publish fails; an image is never left pushed and unsigned by a green run |

## When something is found

A vulnerability in JAVV's own code: fix it on a private advisory when it is exploitable (the
process in [`SECURITY.md`](../../SECURITY.md)), otherwise a normal issue labelled `security`. A
leaked secret: **rotate it first**; deleting the commit does not un-leak it.
