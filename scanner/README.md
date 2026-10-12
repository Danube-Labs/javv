# JAVV scanner

In-cluster vulnerability scanner. Discovers running images, scans each with **Trivy** and **Grype**
(per-scanner, **never merged**), normalizes severity, builds a current-only envelope (stamped with the
scanner's self-reported version provenance), and pushes it to the backend.
Bolts: M0 (`development/bolts/M0-scanners/`, #22) · M0b publish/compat (`…/M0b-scanner-image-publish/`, #60).

```
discovery → adapters(trivy|grype) → normalize → envelope (+scanner_version) → push
```

## Run it
The package is the CronJob entrypoint — one cycle = discover → scan → envelope → push:
```bash
JAVV_SCANNER=trivy JAVV_BACKEND_URL=http://backend JAVV_TOKEN=<ingest token> python -m scanner
```
| Env | Meaning |
|---|---|
| `JAVV_SCANNER` | `trivy` \| `grype` — which scanner this Job runs (default `trivy`) |
| `JAVV_BACKEND_URL` | ingest endpoint base (default `http://localhost:8000`) |
| `JAVV_TOKEN` | the ingest bearer token for this `(cluster, scanner)` (`push:findings` scope). **Effectively required**: without it the scan-scope fetch is refused and every cycle is skipped |
| `JAVV_LOG_LEVEL` | `debug` \| `info` \| `warning` \| `error` (default `info`); JSON lines on the same pipeline as the backend |
| `JAVV_CLUSTER_ID` | tenant id; defaults to the live `kube-system` namespace UID. Set = **asserted**: a mismatch with the cluster actually reached refuses the cycle (exit 2) |
| `JAVV_KUBE_CONTEXT` | out-of-cluster only — which kubeconfig context to scan (default: the current one) |
| `JAVV_DEAD_LETTER` | dead-letter sink path (default `<scanner>.dead-letter.jsonl`) |

### The image runs as non-root
Both images run as `65532:65532` with `python -m scanner` (the project venv) as the entrypoint, and
write only to the vuln-DB cache (`/var/cache/javv/<scanner>`), the dead-letter file (`/var/lib/javv`) and
`/tmp`. So they run with a read-only root filesystem (issue 632). Mounts there must be writable by that
UID; a kubeconfig mounted for an out-of-cluster run must be readable by it. Paths and overrides:
[`docs/CONFIGURATION.md`](../docs/CONFIGURATION.md), "Scanner settings".

Scan tuning (`JAVV_TRIVY_*`: severities, scanners, package types, ignore-unfixed, timeout;
`JAVV_GRYPE_*`: only-fixed, scope, scan timeout) and every default are in
[`docs/CONFIGURATION.md`](../docs/CONFIGURATION.md), "Scanner settings" to "Grype settings". Unset means the pinned default command; a
garbage value exits 2 at startup.

### What one cycle asks the backend first
Before discovering anything, the cycle makes two calls, and both **fail closed**: if either is
unavailable the cycle is skipped (logged at `error`, exit 0) and nothing is scanned.
1. `GET /api/v1/scan-scope` — the cluster's scan scope (D43): namespace allow/deny globs, excluded
   image globs, ignored owner kinds. Discovery filters on it before any pull. A fetched *empty* scope
   means scan everything; an unreachable backend means scan nothing.
2. `POST /api/v1/scan-runs` — the backend allocates this cycle's `scan_order` (D45).

At the end, `POST /api/v1/inventory-runs` certifies the cycle's inventory (best effort; a failure leaves
the run uncertified and is logged as a warning).
## Trivy and Grype are two separate CronJobs
Each scanner is its own self-built image (`Dockerfile.trivy`, `Dockerfile.grype`, pinned binary) run as its
**own CronJob** — independent, never merged. Each emits its own envelope stream with a monotonic `scan_order`
per `(cluster, scanner)`. They may run at the same wall-clock time but neither knows about the other;
disagreement (e.g. Trivy=0 vs Grype=73 on the same image) is **signal**, not an error. `concurrencyPolicy:
Forbid` is **per-CronJob**, which keeps each scanner's `scan_order` monotonic (D40). Within one run, images
are scanned **sequentially** (stateless; intra-run parallelism is a possible later optimization).

## Versions & publishing (M0b / D41–D42)
- **Supported versions** live in [`/versions.yaml`](../versions.yaml) (single source of truth) — `current` +
  a small set of prior versions per scanner. Edit there; Renovate watches it.
- **Compatibility gate:** `python -m scanner.compat --scanner trivy` drives the real binary against a
  CVE-bearing image (`python:3.9.16-slim`, pinned by digest and served from our own GHCR copy, made by
  `.github/workflows/compat-fixture.yml`) and asserts the JAVV adapter contracts
  (provenance present, findings parse, severities canonical, envelope builds). CI runs it per supported
  version; green → publishable.
  - **`--push`** (issue 631) runs that image through the **real cycle** instead of stopping at a local
    envelope: scope fetch, backend-allocated `scan_order`, the push client, the inventory commit. It reads
    `JAVV_BACKEND_URL`, `JAVV_TOKEN` and `JAVV_CLUSTER_ID` (required here, since there's no cluster to
    derive it from) and fails if the backend refuses the envelope or the inventory run isn't committed.
    `--summary out.json` writes what was sent (`scan_run_id`, per-severity `counts`, `scanner_version`),
    so a check can compare the store against it. CI does this per supported version: the compat job starts a
    backend on an OpenSearch service and runs `development/scripts/check-ingest-roundtrip.sh`.
- **DB-compat policy:** `versions.yaml` records each scanner's factual `vuln_db` compatibility (no invented
  EOL). `development/scripts/check-scanner-db-policy.sh` fails CI if a supported version would run a frozen/
  incompatible vuln DB — e.g. Grype < 0.88.0 (schema v5, EOL 2026-03-06, runs silently).
- **Publish pipeline** (`.github/workflows/scanner-images.yml`): runs on **every merge to `main` that changes an
  image's inputs** (`versions.yaml`, the Dockerfiles/bake file, scanner source and dependencies, the shared lib),
  so a merged scanner bump has its signed image minutes later; also on a `scanner-v*` tag or manual dispatch.
  Builds locally → **publish-smoke**
  (runs each image's entrypoint before pushing) → pushes → **SBOM (`syft`) + self-scan (`grype`, report-only)**
  uploaded as a CI artifact → **cosign keyless signature + signed SBOM attestation**, both by the pushed digest
  ([verify one](#verify-a-published-image)).
- **Published images:** `ghcr.io/danube-labs/javv-scanner-{trivy,grype}:<ver>` (moving) + `:<ver>-<git-sha>`
  (immutable) with OCI labels. **Scanner image release ≠ JAVV release** — versions are changed by swapping the
  published image tag in your deploy; JAVV never changes versions in a running cluster (D41).

### Verify a published image
Every image the publish pipeline pushes is signed with **cosign keyless**: the certificate comes from the
workflow's GitHub OIDC identity and is logged in the public Rekor transparency log. Each image also carries
a **signed SPDX SBOM attestation**. Both bind to the image digest, not a tag. To check one with cosign 3.x
(the version CI signs with, `versions.yaml` `supply_chain.cosign`):

```bash
IMAGE=ghcr.io/danube-labs/javv-scanner-trivy:0.75.0
IDENTITY='^https://github\.com/Danube-Labs/javv-poc/\.github/workflows/scanner-images\.yml@refs/(heads/main|tags/scanner-v.+)$'
ISSUER=https://token.actions.githubusercontent.com

cosign verify "$IMAGE" --certificate-identity-regexp "$IDENTITY" --certificate-oidc-issuer "$ISSUER"
cosign verify-attestation "$IMAGE" --type spdxjson \
  --certificate-identity-regexp "$IDENTITY" --certificate-oidc-issuer "$ISSUER" > /dev/null && echo "SBOM attestation OK"
```

The identity accepts only builds from this repo's `main` or a `scanner-v*` tag, so an image built from any
other branch fails verification. Images published before signing started (issue 74) carry no signature; the
next publish signs forward, it never re-pushes old tags.

## Runtime & failure modes
Status: ✅ implemented (M0/M0b; M10's CronJobs, vuln-DB cache and RBAC in the `javv-scanner` chart, `deploy/helm/javv-scanner`).

| Scenario | What happens | Mechanism / decision | Status |
|---|---|---|---|
| Push fails transiently (429/5xx, network) | Retry with **exponential backoff + jitter**; same envelope re-sent | only flow control without a broker | ✅ |
| Push fails permanently (other 4xx, retries exhausted) | Envelope written to a **dead-letter sink** (`*.dead-letter.jsonl`); run continues | nothing silently lost | ✅ |
| Push "timed out" but backend got it | Safe re-push — gzipped body is byte-identical; backend **upserts by deterministic `_id`** | idempotent appends (D18); server-side M1 | ✅ / M1 |
| Backend down at cycle start | Scope fetch fails → cycle **skipped** before any scan (logged at `error`, exit 0) | fail-closed scan scope (D43) | ✅ |
| Backend lost mid-cycle | Pushes retry → dead-letter; the cycle finishes (exit 0); "running at T" still shows last committed run | commit-then-cache: no push = no partial state (D39) | ✅ / M1 |
| An image cannot be scanned (its registry no longer serves it, the scanner exits non-zero, the scan times out) | The image is **skipped** and logged at `warning` with the scanner's own error text; the rest of the cycle runs. The image is **left out of the inventory run's expected count**, so the run still commits: the image leaves Running images and its findings go stale on the normal timer. Nothing on screen names it; the reason is in this log. **If no image scanned at all**, the run keeps the discovered count and stays partial, so the last good inventory keeps answering instead of an empty one | a failed scan must not freeze the inventory (issue 633) | ✅ |
| Clean image (0 vulns) | **Still emits a full envelope** (`total:0`) | no skip-unchanged (D30); catalog needs the marker | ✅ |
| Pod pending / digest unresolved | Image **ignored this cycle**, retried next once `image_id` resolves | discovery requires a `sha256:` digest | ✅ |
| Pod started by tag (`repo:tag`) | Scanned by the `repo@sha256:…` reference in `image_id`, the image that runs; the tag is the name shown and the one that scope globs match. If the registry no longer has that digest (the tag moved and the old image was deleted), the image is skipped and logged, as for any image that cannot be pulled. An `image_id` with no repository (a bare `sha256:…`) leaves the tag as the pull | the tag can have moved since the pod started (issue 833, B5) | ✅ |
| Pod started by digest (`repo@sha256:…`) | Scanned by the `repo@sha256:…` reference in `image_id`: containerd reports `status.image` as the bare config id there, which names nothing. If another pod runs the same digest by tag, that tag is the name shown | a pull needs a repository name (issue 817) | ✅ |
| N replicas of one image | Scanned **once**, attributed to all locations | digest-dedup (D30) | ✅ |
| Same digest across namespaces | One scan target spanning both | dedup keyed on digest | ✅ |
| kube API unreachable at start | Discovery raises → run fails fast → next CronJob retry | injected client; fail-fast | ✅ / 🏗 retry |
| Scanner crashes mid-run | Committed pushes stand (idempotent); next CronJob run re-scans from scratch | stateless, scan-ALL (D30) | ✅ / 🏗 schedule |
| A run overruns the next schedule | Next run is **skipped** (not queued); a run is stopped after `activeDeadlineSeconds` | `concurrencyPolicy: Forbid` → monotonic `scan_order` | ✅ chart |
| Vuln-DB unavailable (offline) | The cycle's refresh fails, logs a warning, and the scan uses the **cached DB from the scanner's own volume**; with none cached, the cycle fails | a cache volume per scanner, refreshed by the scanner's own binary (per-schema, D41) | ✅ chart |
| Trivy vs Grype disagree | Both kept verbatim, **never merged** | per-scanner sacred | ✅ |

**"Fails to push, then what?"** transient → backoff retry; permanent → dead-letter (preserved for replay);
either way the backend never sees a partial commit, and the next cycle re-scans and re-pushes anyway because
the scanner holds no state.

## Provenance (D41)
Each envelope stamps the scanner's self-reported **`scanner_version`** (+ vuln-DB version/built where the
scanner provides it — Grype yes, Trivy's standalone JSON no). It's ingested for the read-only scanner-status
version view + audit version matrix; the binary is the source of truth for "what actually ran."

## Dev
```bash
cd scanner
uv sync --all-extras --dev
uv run pytest && uv run ruff check . && uv run pyright
```
Unit tests run against frozen golden fixtures in `tests/fixtures/` (no network). Two **guarded** integration
suites are skipped by default:
- `JAVV_LIVE_VERIFY=1 uv run pytest tests/test_live_verify.py` — discovery + real scans against the k3d
  `alpha` cluster (needs the `javv-smoke` seed workloads).
- `JAVV_COMPAT_VERIFY=1 uv run pytest tests/test_compat.py` — runs the real installed binaries through the
  compatibility gate.
