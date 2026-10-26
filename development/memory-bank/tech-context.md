# Tech context

This file says where each technical fact is. Versions change often, so this file gives the file
that holds them, not the numbers.

## Stack

| Part | Technology | Where to look |
|---|---|---|
| Backend | Python 3.12, FastAPI (async), AsyncOpenSearch (`opensearch-py`), Pydantic v2 | [`backend/pyproject.toml`](../../backend/pyproject.toml) |
| Frontend | Vue 3 (`<script setup lang="ts">`), PrimeVue, vue-echarts, Pinia, Vue Router, Vite | [`frontend/package.json`](../../frontend/package.json) |
| Store | OpenSearch, the only store | [`versions.yaml`](../../versions.yaml), [`docs/engineering/INDEX-MAP.md`](../../docs/engineering/INDEX-MAP.md) |
| Scanners | Trivy and Grype, in our own images | [`scanner/`](../../scanner/), [`versions.yaml`](../../versions.yaml) |
| Logging | One structlog pipeline for Python, one logger for the browser | [`libs/javv-common/`](../../libs/javv-common/), [`frontend/src/lib/logger.ts`](../../frontend/src/lib/logger.ts), [`.claude/rules/logging.md`](../../.claude/rules/logging.md) |
| Deploy | docker compose, or three Helm charts | [`deploy/compose/`](../../deploy/compose/), [`deploy/helm/`](../../deploy/helm/), [`docs/DEPLOYING.md`](../../docs/DEPLOYING.md) |
| Docs site | Zensical, one folder for each release | [`docs-site/`](../../docs-site/) |

`backend/pyproject.toml` keeps FastAPI below the next minor version on purpose. A minor version once
changed how FastAPI keeps its routers, and the RBAC check found no routes (see the comment in `backend/pyproject.toml`).

## Repository

[`REPO-MAP.md`](../../REPO-MAP.md) tells what each folder holds and which file has the authority.
A test in CI (`development/scripts/check-docs-drift.sh`) makes sure that it lists each workflow,
each CI job and each script.

## The dev stack

[`development/RUNNING-THE-STACK.md`](../../development/RUNNING-THE-STACK.md) has the full steps.
In short:

| Part | Port | Notes |
|---|---|---|
| OpenSearch | 9200 | `development/setup/opensearch-dev.yml`. One node, so it stays yellow. |
| Backend | 8000 | No reload. Restart it after a backend change, a merge or a branch switch. |
| Frontend (Vite) | 5173 | Sends `/api` and `/auth` to the backend. Restart it after `npm run gen:api`. |

A backend pytest run that uses the dev store leaves test data. Clean it with
`development/scripts/clean-dev-store.sh`. Throwaway stores for tests use other ports, so the dev
data stays safe.

## Gates

Run the exact commands that CI runs, and use the exit code, not the printed text.

| Stack | Commands |
|---|---|
| Backend | `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright` (whole tree), `uv run pytest -n 2 -m "not serial"` then `uv run pytest -m serial` |
| Frontend | `npm run lint`, `npm run test:ci` (type check, then unit tests with coverage) |
| Contract | `development/scripts/check-docs-drift.sh` (API.md, CONFIGURATION.md and the REPO-MAP list against the code) |
| Versions | `development/scripts/check-versions.sh` (`versions.yaml` against the Dockerfiles and compose) |
| UI design | `node .claude/skills/impeccable/scripts/detect.mjs <files>` (the copy in the repository, never `npx`) |

The suite budget is in [`development/standards/testing.md`](../../development/standards/testing.md).

## CI

[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs on each PR. Its jobs are:
Commitlint, Secret scan, javv-common, Backend static, Backend, App images, Compose stack, two Helm
jobs, Scanner, Frontend, Frontend smoke, Docs site and Dependency audit. The other workflows are
listed in [`REPO-MAP.md`](../../REPO-MAP.md) ("`.github/` - automation").

## Releases

[`development/standards/releases.md`](../../development/standards/releases.md) has the rules.

- release-please makes one release PR from the conventional commits on `main`.
- Before 1.0, `feat` bumps the patch version and a breaking change bumps the minor version. A
  different version needs a `Release-As:` footer in the commit itself.
- A release publishes the app images and the three charts, signed, and the docs of that release.
- The scanner images publish and sign on each merge that changes them
  (`.github/workflows/scanner-images.yml`).

## Dependencies

Renovate opens the dependency PRs, with the labels `dependencies` and `housekeeping`.
[`development/standards/dependency-policy.md`](../../development/standards/dependency-policy.md)
gives the fix deadlines. A major version waits for the step before 1.0 (issue 597, the Dependency
Dashboard).

## Tools for agents

[`docs/research/TOOLING-AND-MCP.md`](../../docs/research/TOOLING-AND-MCP.md) lists the MCP servers
(Serena, OpenSearch, Context7, Playwright) and how to install them. The repository has its own
skills, commands and hooks in [`.claude/`](../../.claude/). The Bash guard
(`.claude/hooks/guard_bash.py`) refuses `git add -A` and `pkill -f`.
