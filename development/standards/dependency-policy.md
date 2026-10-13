# Dependency policy

How JAVV's dependencies are pinned, updated, audited and merged. The **why Renovate** and the
release mechanics live in [releases.md](releases.md); this file is the policy they follow. Rulings
by the operator on issue 552 (2026-09-27).

## Where each version lives

| What | Pinned in | Updated by |
|---|---|---|
| Scanners (Trivy, Grype) and OpenSearch | `versions.yaml` (D42), drift-checked by `development/scripts/check-versions.sh` into the scanner Dockerfiles, the bake defaults, the dev compose file, the CI service images, and the docs that state the versions (README *Supported versions*, `docs/CONFIGURATION.md`, the verify example in `scanner/README.md`) | Renovate's `versions.yaml` custom manager. Renovate doesn't edit the docs or the bake defaults, so a bump PR fails the Versions drift check until `check-versions.sh --fix` is run on it and pushed. Merging a scanner bump publishes its signed image (`scanner-images.yml`) |
| Gate toolchain (uv, ruff, pyright, pre-commit, helm-docs) | `versions.yaml` `toolchain:`. `development/scripts/helm-docs.sh` runs the pinned helm-docs image. CI's `setup-uv` and `development/setup/setup-dev.sh` read it directly; ruff and pyright are also pinned in each `pyproject.toml` dev-deps and uv in the tag of the uv image the scanner Dockerfiles copy from (pinned by digest), all drift-checked by `check-versions.sh` | Renovate's `versions.yaml` custom manager; each tool's other pins come in the same PR |
| Node (major only) | `versions.yaml` `toolchain.node`, repeated in each CI `setup-node` `node-version` (drift-checked by `check-versions.sh`) and as a range in `frontend/package.json` `engines` (not checked) | Renovate, one PR for `versions.yaml` and CI; a major waits for approval on the dashboard |
| Python (minor) | `.python-version` in `backend/` and `scanner/`, and the `FROM python:` tag in both scanner Dockerfiles, pinned by digest; `requires-python` in each `pyproject.toml` is only the floor. `check-versions.sh` holds the other copies to `backend/.python-version` | Renovate, one PR for the `.python-version` files and the Dockerfile tags (held on 3.12, see Updates); it also refreshes the base-image digest when the image is rebuilt |
| Python libraries (backend, scanner, `libs/javv-common`) | each `pyproject.toml` + `uv.lock` | Renovate (uv) |
| Frontend packages | `frontend/package.json` + `package-lock.json` | Renovate (npm) |
| pre-commit hooks | `.pre-commit-config.yaml` `rev:`; the ruff hook is drift-checked against `versions.yaml` `toolchain.ruff` by `check-versions.sh` | Renovate (pre-commit manager); the ruff hook comes in the same PR as the other ruff pins |
| The official `opensearch` Helm chart (the `javv-opensearch` chart's dependency) | `deploy/helm/javv-opensearch/Chart.yaml` and `Chart.lock`, with the chart vendored in its `charts/` folder so a render needs no network. The OpenSearch image tag and `appVersion` are set from `versions.yaml` and drift-checked; the chart's own version is not, since its version and the OpenSearch it ships can differ | Renovate's Helm manager, in the `opensearch` group, refreshing the vendored archive in the same PR (`helmUpdateSubChartArchives`) |
| GitHub Actions | the workflow files, by **full commit SHA** with the release in a comment | Renovate (`helpers:pinGitHubActionDigests`) |
| CI supply-chain tools: gitleaks (Secret scan), syft (the SBOM of both publish jobs), the scanner-images self-scan grype, and cosign (image signing) | `versions.yaml` `supply_chain:`, read directly by the workflows. syft and grype run in jobs that can sign, so they are pinned by image digest (`tag@sha256:`, issue 833); the self-scan grype's tag is held equal to `scanners.grype.current` by `check-versions.sh`. gitleaks's checksum stays in `ci.yml` as `GITLEAKS_SHA256` | Renovate, which moves a digest with its tag and both grype pins in one PR; a gitleaks PR fails the Secret scan until `GITLEAKS_SHA256` is updated from the release's `checksums.txt` |

## Updates

- **Renovate is the updater.** Dependabot security *updates* stay off (#469); GitHub's
  vulnerability *alerts* stay on, and Renovate turns them into PRs.
- **Regular updates run daily.** Renovate opens them grouped as `renovate.json` defines (GitHub
  Actions in one PR, non-major dev dependencies in one PR).
- **Security fixes open immediately**, outside any schedule, labelled `security`.
- **Major updates wait for approval.** Renovate lists them under "Pending Approval" on the
  Dependency Dashboard and opens one only when its box is ticked. The MVP ships on the current
  majors; they are taken one at a time as the last step before 1.0. Security fixes never wait. That covers
  dependencies we list ourselves; one that only a library pulls in (a *transitive* one, in the
  lockfile but in no `package.json` / `pyproject.toml`) gets no security PR from Renovate.
- **Lockfiles are refreshed weekly** (lock file maintenance, Monday before 4am UTC): one PR that
  moves every transitive dependency in every lockfile to the newest version its ranges allow. That is
  how a transitive fix lands within the 7-day window; the dashboard checkbox runs it early.
- **Python stays on 3.12** (images, `.python-version`) until a deliberate upgrade;
  Renovate is held below 3.13.
- **Nothing merges itself.** Every Renovate PR is merged by the operator like any other PR,
  after CI is green. No automerge rule exists and none is added without a new ruling.

## How fast a vulnerable dependency must be fixed

"Production dependency" = anything that ships: backend, scanner and `libs/javv-common` runtime
dependencies, the frontend's runtime (non-dev) packages, the scanner images' base and pinned
scanners, and the OpenSearch version.

| Advisory | In a production dependency | Dev-only (tests, build, lint) |
|---|---|---|
| Critical or high | fix PR **merged within 7 days** of the advisory appearing (a Renovate security PR, a GitHub alert, or the CI audit) | next regular batch, at least monthly |
| Moderate or low | next regular batch, at least monthly | next regular batch, at least monthly |

When no fixed version exists yet, or the advisory does not apply to how JAVV uses the package, say
so on an issue (labels `security` + `dependencies`) with the reason and a date to look again. That
issue is the exception record; there is no silent ignore list.

## The CI dependency audit

The audit job runs `npm audit` (frontend) and `pip-audit` (backend, scanner, libs) on every PR and
push to `main`. It is **report-only** for now: findings go to the job summary and the job never
fails. Revisit making it a gate once Renovate has been running for a while (operator, issue 552).

## Adding a new dependency

Before adding one, in the PR description:
- **Need:** why the existing stack or the standard library doesn't already cover it.
- **Health:** maintained (recent releases, open issues answered), a known publisher, and a licence
  that allows JAVV to ship it under its own Business Source License 1.1 (`LICENSE`).
- **Cost:** size and transitive footprint; for npm, any install script it runs.
- Pin it through the lockfile like everything else; never a floating URL or a git branch.
