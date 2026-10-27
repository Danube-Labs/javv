# M0b - Scanner image publish + compatibility CI

**Status:** tracked in [#60](https://github.com/Danube-Labs/javv/issues/60) — live status on the GitHub issue/board

> Sequences **between M0 and M1**. M0 builds the scanner package + Dockerfiles; this bolt makes the
> self-built images **publishable and compatibility-checked** so operators can pin/swap a known-good tag (D41).

## Goal
Build and **publish** the pinned, self-built Trivy/Grype images (a small **compatible set** of versions), each
gated by a **CI compatibility test** that runs the candidate scanner binary through the JAVV adapters and
asserts the golden contracts still hold. This is where "multiple scanner versions" actually lives — a CI
gate, **not** a runtime switch (D41). The operator later swaps the published tag in their own deploy (M10).

**Canonical refs:** `PLAN` **D41** · `SPEC` FR-2/FR-3 (scan/ingest), NFR-11 (DB cache) ·
M0 (#22, the adapters + golden fixtures + Dockerfiles this gates).

## Depends on
- **M0** (#22) — the `scanner/` package, golden contracts, and `Dockerfile.trivy`/`Dockerfile.grype`.

## Deliverables
- **Matrix build** (`docker buildx bake` + GHA matrix) of one Dockerfile per scanner across the compatible
  versions (`--build-arg TRIVY_VERSION`/`GRYPE_VERSION`) → tagged images `…-trivy:<ver>`, `…-grype:<ver>`.
- **Compatibility test** (CI): run each **candidate** real binary on a fixed image, feed output
  through the adapters, and assert the contracts — severity canonicalization (D16), EPSS/KEV capture,
  envelope shape, and **provenance present** (`scanner_version` + DB fields). **Green → publish as compatible.**
- **Publish** to the registry (GHCR) on green; images **public once the repo is public**; Dockerfiles stay
  public for supply-chain transparency. Each build pushes a **moving `:<ver>`** tag (latest build of that
  scanner version) **+ an immutable `:<ver>-<git-sha>`** tag, with OCI labels (`org.opencontainers.image.
  version`/`revision`/`source`, `javv.scanner`). **Scanner image release ≠ JAVV release** (D41): publishing
  is its own track (`scanner-v*` tag / dispatch), independent of release-please's `v*` app tags — a new
  scanner version or a base-layer rebuild ships without bumping JAVV; the `-<git-sha>` tag/label ties each
  image to the JAVV commit that built its entrypoint.
- **`versions.yaml`** (repo root, D42) — the single source of truth for the compatible set (**current + 1-2 prior**, not 5), each with an explicit
  EOL; **per-vuln-DB-schema** awareness (Grype v5↔v6 incompatible; Grype <0.88 = frozen DB).
- Supply-chain: image **scan + SBOM (+ optional signing)** of the published scanner images themselves.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- The matrix builds **both** images for every version in the compatible set; `docker build --check` clean.
- The **compat gate fails the build** when a candidate scanner's output breaks an adapter/golden contract
  (proven with a deliberately-incompatible pin or a recorded drift case) — a red gate **blocks publish**.
- A **published** image runs `python -m scanner` and produces a valid envelope (smoke against the seed target).
- Compatible set + EOL policy documented; an EOL-DB-schema version is flagged (not silently shipped).

## Tests to write
- CI compat matrix: per compatible `(scanner, version)`, real-binary → adapters → contract asserts (incl. provenance).
- A negative case: an incompatible/old pin makes the gate red (so the gate is proven to bite).
- Publish smoke: pull the built image, run it against the dev smoke target, assert a non-error envelope.

## Out of scope (defer)
- Helm chart / CronJob deploy + the **per-schema PVC DB cache** → **M10** (the operator wires the tag there).
- The read-only version display in the UI → **M9d / M9e**.
- The ingest endpoint that accepts the provenance fields → **M1** (`extra="forbid"` coupling, D41).

## Updates
- **2026-07-01** — First GHCR publish dispatched from `main` @ `70a057c` ([run 28480042666](https://github.com/Danube-Labs/javv/actions/runs/28480042666)):
  8 tags live (`javv-scanner-{trivy,grype}:<ver>` + `:<ver>-<sha>`), full pipeline green. The M0/M0b
  retrospective ([`../M0-scanners/RETROSPECTIVE.md`](../M0-scanners/RETROSPECTIVE.md)) then surfaced
  **deferred DoD items closed silently** — issue **#60 reopened** to track them: SBOM + image-scan
  (+ optional cosign) of the published images; **EOL + per-vuln-DB-schema annotations in `versions.yaml`**
  (flag, don't silently ship an EOL/frozen-DB version); automated **publish-smoke**; `docker build --check`
  in CI. Pickup TBD (focused M0b follow-up vs. fold into M10 supply-chain).
- **2026-07-01 (follow-up)** — the four deferred items above implemented in `scanner-images.yml` + `versions.yaml`:
  - **Supply-chain (point 1):** `syft` SBOM + `grype` self-scan of our *own* published images, **report-only**
    (never blocks the publish; SBOM + scan uploaded as a CI artifact). **Signing (`cosign`) deliberately deferred
    until the repo/images are public** — keyless cosign would record digests + CI identity in the public Rekor
    log; tracked on #60.
  - **DB policy (point 2):** **no invented EOL dates** — Trivy/Grype publish none. `versions.yaml` now records the
    *factual* `vuln_db` compatibility per scanner (Trivy schema v2, **fails loud** on an incompatible DB; Grype
    schema v6 since 0.88.0, `min_live_version: 0.88.0` because schema v5 EOL'd 2026-03-06 and old Grype runs it
    **silently**). New gate `development/scripts/check-scanner-db-policy.sh` (wired into `versions.yml`) fails CI
    if a supported version would run a frozen/incompatible DB.
  - **Publish-smoke (point 3):** runs **before** publish — bake `--load` → run each built image's entrypoint
    (`scanner.compat`, exercising the image's real binary + package + wiring, which the runner-side compat gate
    does *not*) → only `--push` if green, so a broken image never gets a public tag.
- **2026-09-28** — **Signing shipped (issue 74)**, the one item deferred above until the repo was public. After the
  push, each image's digest comes from the bake metadata; `syft` makes the SBOM of that digest, and the reusable
  `.github/actions/sign-image` runs keyless `cosign sign` + `cosign attest --type spdxjson` on it. The publish job
  alone has `id-token: write`; any signing error fails the job. cosign is pinned in `versions.yaml`
  `supply_chain.cosign`. Verify steps: `scanner/README.md` § *Verify a published image*. The app images (#452)
  reuse the same action.
- **2026-09-29** — **Publish on merge** (operator ruling, option A of three). `scanner-images.yml` now also
  publishes on a push to `main` that changes an image's inputs, so every version `versions.yaml` lists as supported
  has a signed image; tag and manual dispatch still work. A job-level concurrency group keeps two merges from
  interleaving their pushes of the moving `:<ver>` tags. Deploys should pin the fixed `:<ver>-<sha>` tag, because
  a scanner-code merge moves `:<ver>` (M10's chart).
  - **`docker build --check` (point 4):** new `lint-dockerfiles` job on both Dockerfiles; `publish` now
    `needs: [compat, lint-dockerfiles]`.
- **2026-10-06: "M10's chart" is the `javv-scanner` chart** (issue 725, slice 3). A published
  chart names each scanner image by the digest its tag pointed at when the release was made, so a
  later republish of `:<ver>` does not change what a release runs. Issue 754.

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
