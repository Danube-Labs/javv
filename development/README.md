# JAVV - Development setup

Getting a fresh machine ready to build JAVV. For *what* we're building, see the canonical design in
[`docs/engineering/`](../docs/engineering/) (start with `PLAN.md`). This file is purely the dev-environment
and local-loop guide.

> Target host: **Ubuntu 24.04 (x86_64)**. Docker must already be installed and running. Everything else is
> installed by [`development/setup/setup-dev.sh`](setup/setup-dev.sh).

---

## 1. One-shot setup

```bash
# from the repo root
./development/setup/setup-dev.sh
```

The script is **idempotent** - re-run it any time; it skips tools already present. It needs `sudo` for the
`apt` and `/usr/local/bin` steps and will prompt for it (or run the whole thing under `sudo`).

### What it installs

| Group | Tools | Why |
|---|---|---|
| **Build floor** | `build-essential` (gcc/make), `python3-venv`, `python3-pip`, `unzip`, `ca-certificates` | Compile native deps; venvs |
| **Python toolchain** | `uv` / `uvx` (Astral), `ruff` | Env + dependency management; lint + format |
| **JS toolchain** | Node.js 22 LTS + `npm`/`npx`, `pyright` (global) | Frontend build; type checker; `npx`-based MCP/codegen tools |
| **k8s / dev cluster** | `kubectl`, `helm`, `k3d` | Local k3s-in-Docker clusters (per-`cluster_id` testing), Helm deploys |
| **Scanners** | `trivy`, `grype` | The two scanner adapters JAVV drives (**never merged** - per-scanner) |
| **Git/CI** | `gh` (GitHub CLI) | PR/issue workflow against `Danube-Labs/javv-poc` |

**Not installed by the script** (do these manually when needed):

- **MCP servers** (Serena, OpenSearch, Context7, …) - wire up per
  [`docs/research/TOOLING-AND-MCP.md`](../docs/research/TOOLING-AND-MCP.md) with `claude mcp add …`. `uvx`/`npx` are
  prerequisites and the script installs both.
- **OpenSearch** - for local dev, run the pinned single-node container (security off, `:9200`):
  `docker compose -f development/setup/opensearch-dev.yml up -d`. In-cluster deploy comes with M10.

### After it runs

- **Docker group:** k3d talks to the Docker daemon. If `docker ps` needs `sudo`, add yourself to the group
  once and re-login: `sudo usermod -aG docker "$USER"`.
- Confirm the toolchain: `uv --version && ruff --version && node --version && kubectl version --client && helm version && k3d version && trivy --version && grype version`.

---

## 2. Local Kubernetes dev cluster

Per [`docs/research/K8S-DEV-CLUSTER.md`](../docs/research/K8S-DEV-CLUSTER.md), **k3d** (k3s-in-Docker) is the primary
local driver - no nested virtualisation, clusters spin up in seconds, each with a distinct `kube-system`
UID (= JAVV's immutable `cluster_id`). **One cluster is enough for day-to-day dev** - spin up a single one:

```bash
k3d cluster create alpha --servers 1 --agents 0 -p "8081:80@loadbalancer"

# its cluster_id — JAVV routes indices on this kube-system namespace UID
kubectl --context k3d-alpha get namespace kube-system -o jsonpath='{.metadata.uid}'; echo

# teardown
k3d cluster delete alpha
```

> **Need the multi-cluster story?** Only when you're validating per-`cluster_id` behavior (index
> routing, tenant-scoped reads, same-name namespaces across tenants). The ready-made second tenant
> is `beta` — small (3 ns / 4 workloads, one namespace name shared with alpha on purpose):
> `k3d cluster create beta --servers 1 --agents 0` + `seed-beta-workloads.yaml`, full loop in
> [`RUNNING-THE-STACK.md`](RUNNING-THE-STACK.md) §B6. Don't run extras by default; one keeps the VM light.

Give the VM ≥2 vCPU / ≥4 GB / ~30 GB disk (image layers + scanner DBs). k3d clusters share the host
kernel - fine for functional testing, **not** for benchmarking scan throughput.

### Scanning the cluster (Trivy / Grype)

> **Packaging decision (hard rule):** JAVV ships **two scanner images it builds itself** - one Dockerfile
> for Trivy, one for Grype (pinned scanner version + JAVV entrypoint), run in-cluster as **CronJobs**.
> We do **NOT** use the **Trivy Operator** / Starboard or any third-party operator. Own Dockerfiles = full
> control over scanner version, flags, and supply chain, and clean **per-scanner** isolation. Ingest is
> **scanner JSON, per-scanner, never merged.**

Supported scanner versions are pinned in **[`versions.yaml`](../versions.yaml)** (single source of truth,
D42); JAVV builds + publishes one image per scanner per version (M0b) as
`ghcr.io/danube-labs/javv-scanner-{trivy,grype}:<ver>`. The package itself runs a scan cycle via
`python -m scanner` (see [`scanner/README.md`](../scanner/README.md)). For **local dev** you can just use the
CLIs to produce the JSON the backend ingests. First give the scanners something to find - apply the checked-in
**dev smoke target** (3 deployments of deliberately-old images, incl. a 3-replica nginx so digest-dedup has
something to collapse):

```bash
kubectl apply -f development/setup/seed-vuln-workloads.yaml   # → namespace javv-smoke
kubectl -n javv-smoke get pods                               # 5 pods, 3 distinct images
# teardown:  kubectl delete -f development/setup/seed-vuln-workloads.yaml
```

This is the scan target for M0's live-cluster verification (`PLAN §9`). For a throwaway one-off instead:
`kubectl --context k3d-alpha create deployment vuln --image=python:3.4-slim` (EOL → many CVEs).

```bash
# Trivy — emits the JSON JAVV ingests (scanner=trivy)
trivy image -f json -o trivy-python.json python:3.4-slim     # one image → JSON
trivy k8s --context k3d-alpha --report summary cluster        # scan everything running in the cluster

# Grype — the second per-scanner stream (scanner=grype)
grype python:3.4-slim -o json > grype-python.json
syft python:3.4-slim -o json | grype --output json            # SBOM → grype (optional)
```

| Tool | What it is | Role for JAVV |
|---|---|---|
| `trivy` CLI | scanner binary, JSON out | Baked into **`Dockerfile.trivy`** (JAVV-built); `scanner=trivy` |
| `grype` CLI (+ `syft` SBOM) | scanner binary, JSON out | Baked into **`Dockerfile.grype`** (JAVV-built); `scanner=grype` |
| ~~Trivy Operator~~ | third-party in-cluster operator | **Not used** — JAVV owns the scanner images |

Keep the two scanners **separate**: never merge a CVE across Trivy and Grype (per-scanner is sacred).
The two Dockerfiles + the scanner package land in **M0**; image build/publish + the compatibility gate in
**M0b** (`python -m scanner.compat`); their CronJobs in the `javv-scanner` chart (**M10**, issue 725).

---

## 3. Repo layout

**[`REPO-MAP.md`](../REPO-MAP.md) maps every folder**; the top level in one screen:

```
backend/          FastAPI service (routers · services · query · jobs · … - see backend/README.md)
frontend/         Vue 3 app (<script setup lang="ts">) · PrimeVue · vue-echarts · Pinia
scanner/          the in-cluster scanner package + Dockerfile.{trivy,grype}
libs/javv-common/ the shared logging pipeline (backend + scanner)
versions.yaml     pinned external versions (scanners, OpenSearch, toolchain) - single source of truth (D42)
deploy/           compose/ (one machine) and helm/ (the javv, javv-opensearch and javv-scanner charts)
docs/             canonical design (engineering/), API.md, CONFIGURATION.md, research/
docs-site/        the operator docs site (zensical), built from the docs pages
development/      this guide, setup/, standards/, scripts/, e2e/, memory-bank/, video/, bolts/ (history)
design/           the brand source of record
handoff/          the UI reference (docs/ current, v4/ frozen)
```

---

## 4. Quality gates & dev loop

Run what CI runs before pushing. The commands, per component:

```bash
# Backend - from backend/ (needs OpenSearch; see backend/README.md)
uv run ruff check . && uv run ruff format --check . && uv run pyright   # pyright tree-wide, no path args
uv run pytest -n 2 -m "not serial" && uv run pytest -m serial

# Scanner - from scanner/  ·  shared lib - from libs/javv-common/
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest

# Frontend - from frontend/
npm run lint && npm run test:ci      # not `npm run test`: test:ci adds the coverage floor
```

CI also runs gates with no local equivalent you'd run every time: the **contract gate** (the
committed `frontend/openapi.json` and generated client must match the backend; fix with
`export_openapi` + `npm run gen:api`), the **docs-drift** check (`development/scripts/check-docs-drift.sh`),
the **Frontend smoke** (a built app against a seeded backend), commitlint, the gitleaks secret scan and
the report-only dependency audit. `versions.yml` checks every consumer against `versions.yaml`.

Static floor: **ruff + pyright** (Python), **vue-tsc + ESLint + oxlint + stylelint** (Vue).

---

## 5. Where to read next

| Doc | What |
|---|---|
| [`docs/engineering/PLAN.md`](../docs/engineering/PLAN.md) | Decisions (D1-D47), data model, milestones (M0-M10) |
| [`docs/engineering/INDEX-MAP.md`](../docs/engineering/INDEX-MAP.md) | **Source of truth** for every OpenSearch index + mapping - read before touching any index |
| [`docs/research/STACK-BEST-PRACTICES.md`](../docs/research/STACK-BEST-PRACTICES.md) | Day-one engineering rules (async client, mappings, `_bulk`, Vue patterns) |
| [`docs/research/TOOLING-AND-MCP.md`](../docs/research/TOOLING-AND-MCP.md) | MCP servers + tooling, ranked, with install commands |
| [`docs/research/K8S-DEV-CLUSTER.md`](../docs/research/K8S-DEV-CLUSTER.md) | Dev/test cluster options (local k3d + remote) |
