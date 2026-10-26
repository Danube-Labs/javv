# M0 - Scanner modules

**Status:** tracked in [#22](https://github.com/Danube-Labs/javv-poc/issues/22) — live status on the GitHub issue/board

## Goal
The drop-in, in-cluster scanner package: discover running images, scan each with **Trivy** and **Grype**
(per-scanner, never merged), normalize output, and push a hardened envelope to the backend. This is the data
source for everything downstream - no backend exists yet, so M0 is testable in isolation against fixtures.

**Canonical refs:** [`PLAN §8 M0`](../../../docs/engineering/PLAN.md) · `SPEC` FR-1/FR-2 ·
decisions **D16** (severity normalizer), **D30** (scan-all, local digest-dedup, no skip-unchanged),
**D37** (full-precision `last_seen_at`), **D40** (`scan_order`).

## Depends on
None. (Leaf bolt - start here.)

## Deliverables
A standalone Python package (runs in-cluster as a Job/CronJob, `Forbid` concurrency), top-level `scanner/`:
- `scanner/discovery.py` - enumerate running images per namespace/workload; **local digest-dedup**, scan ALL
  (no skip-unchanged).
- `scanner/adapters/trivy.py`, `scanner/adapters/grype.py` - drive each scanner, parse its JSON. **Kept separate.**
- `scanner/normalize.py` - **severity canonicalization** (each scanner's ramp → `crit/high/med/low`; the
  verbatim scanner word is preserved). EPSS/KEV captured where the scanner provides them (Grype).
- `scanner/envelope.py` - build the **current-only** envelope: `cluster_id`, `scanner`, `scan_run_id`,
  monotonic `scan_order`, full-precision `last_seen_at`, `schema_version`.
- `scanner/push.py` - POST to `/ingest/scan`: gzip, **backoff + jitter**, **dead-letter** on permanent failure,
  idempotent (deterministic content so a retried push double-counts nothing).
- **`Dockerfile.trivy` + `Dockerfile.grype`** - **one self-built image per scanner**, each with a **pinned
  scanner version** + the JAVV scanner entrypoint. JAVV owns these images for full control over scanner
  version / flags / supply chain. **Never the Trivy Operator / Starboard or any third-party operator.**
  (Helm/CronJob wiring → M10.)

> No backend yet - M0's push target is a fixture/mock; the real round-trip is M1's gate.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- A real Trivy envelope and a real Grype envelope are produced from checked-in sample scanner JSON and match
  golden expected output (severity bucketed, verbatim word kept, EPSS/KEV only where provided).
- Two scans of the same image with **no change** still emit a full envelope (no skip-unchanged - D30), with a
  new `scan_run_id` and a strictly greater `scan_order`.
- A push that fails permanently lands in the dead-letter sink; a transient failure is retried with backoff.
- **Live-cluster verification (PLAN §9, inherits v3 §9 "Scanner").** With the dev smoke target applied
  (`kubectl apply -f development/setup/seed-vuln-workloads.yaml` → the `javv-smoke` namespace), the scanner
  run against the real `alpha` k3d cluster confirms: discovery enumerates all three deployments; **digest-dedup
  collapses `vuln-nginx`'s 3 replicas to a single scan** (N pods → M<N scans - D30); and the trivy/grype
  adapters drive the **real binaries on a real image** and produce a real envelope with actual CVEs (proves the
  golden-fixture path matches live output). This is the integration smoke the fixture tests can't cover.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md). This bolt needs:
- **Unit:** severity normalizer per scanner (`negligible`/`unknown` kept as distinct buckets, not folded — "other" is a UI concern, D16; never crit); envelope
  builder (`scan_order` monotonic, `last_seen_at` full precision); dedup logic.
- **Golden fixtures:** `tests/fixtures/trivy-*.json` + `grype-*.json` → expected normalized envelope.
- **Unit:** push retry/backoff/dead-letter (mock transport; assert idempotent body).

## Out of scope (defer)
- The ingest endpoint + storage → **M1**.
- `commit_key`, occurrence snapshots, watermarks → stamped/consumed server-side in **M3 / M8a**.
- Helm packaging of the scanner (PVC cache, CronJob hygiene, RBAC) → **M10**.

## Updates
- **2026-06-30** — Spelled out the **live-cluster scanner verification** in the DoD. It was always required
  (PLAN §9 opens "As v3 §9 plus…", and v3 §9 mandates "Scanner: <local cluster> + a known-vulnerable
  image; confirm digest dedup") but was only implied by inheritance, not stated here. Added a dev smoke target
  manifest — `development/setup/seed-vuln-workloads.yaml` (3 deployments incl. a 3-replica nginx for the
  dedup check) — to apply into the `alpha` k3d cluster for that step. The skip-unchanged sub-clause from v3 §9
  is superseded by D30 (scan-all). No change to scope or deliverables; this is the integration layer of M0's
  existing "done", which the golden fixtures alone can't prove.
- **2026-06-30** — **M0 implemented** (PR #58), built TDD in slices: normalize → adapters → envelope →
  discovery → push → drivers/orchestrator → Dockerfiles → live verification. Package lives in `scanner/`
  (own uv project, dedicated CI gate). Live verification passed against `alpha`: nginx 3×→1 digest-dedup,
  distinct digests, and real trivy + grype envelopes with actual CVEs on `python:3.9.16-slim`
  (`JAVV_LIVE_VERIFY=1 uv run pytest tests/test_live_verify.py`). Implementation note: k8s reports
  **fully-qualified image refs** (`docker.io/library/nginx:1.21.6`) — discovery captures those verbatim.
- **2026-06-30** — **Scanner versioning (D41).** The scanner version is **build-time**: pinned via the
  Dockerfile `ARG` (`TRIVY_VERSION`/`GRYPE_VERSION`). The images are **published** to a registry (public once
  the repo is) and the **Dockerfiles stay public** (supply-chain transparency); a cluster operator changes the
  version by **swapping the published image tag** in their own deploy — JAVV never writes to clusters, and
  there is **no live in-app "version select"** (it doesn't survive multi-cluster). "Multiple versions" lives in
  CI as a **compatibility gate** (see the new bolt), not a runtime switch. The envelope now stamps
  **`scanner_version` + vuln-DB version/built** (self-reported by the binary) for read-only version display +
  audit. Full decision: PLAN **D41**. Deploy mechanics (Helm tag value, per-schema DB cache) → M10.
- **2026-10-06: the scanners' Helm/CronJob wiring is the `javv-scanner` chart** (M10, issue 725,
  slice 3): one CronJob per scanner, a vuln-DB cache volume per scanner, and the image named by digest
  in a published chart. Issue 754.

### 2026-10-26 — Frozen as history

The bolts M0 to M10 ended on 2026-10-09. This file is history now, not the spec of record. New work
follows one GitHub issue for each feature, with the plan and a spec file for each slice on the
issue. The timeline, the rulings that still apply and the open work are in the
[memory bank](../../memory-bank/README.md) (issue 1012).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
