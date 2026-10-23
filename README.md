<p align="center">
  <img src="design/brand/github/png/readme-hero-1280x360.png" alt="javv: Just Another Vulnerability Viewer" width="840">
</p>

<p align="center">
  <a href="https://github.com/Danube-Labs/javv-poc/releases"><img alt="Release" src="https://img.shields.io/github/v/release/Danube-Labs/javv-poc?sort=semver&color=EC7E54"></a>
  <a href="https://github.com/Danube-Labs/javv-poc/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Danube-Labs/javv-poc/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="LICENSE"><img alt="License: BSL 1.1" src="https://img.shields.io/badge/license-BSL--1.1-blue"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="Vue 3" src="https://img.shields.io/badge/Vue-3-42b883?logo=vuedotjs&logoColor=white">
</p>

<p align="center">
  <b>Kubernetes-runtime-native container-vulnerability triage.</b><br>
  Discovers what's <i>actually running</i> in your clusters, scans it with <b>Trivy and Grype</b>
  side by side, and gives <b>every vulnerability its own fully-audited triage lifecycle</b>: an
  immutable record of who changed what, and when. Plus rich dashboards, whole-app time-travel, and
  one-click CSV. Without the weight of a full ASPM platform.
</p>

<p align="center">
  <a href="https://danube-labs.github.io/javv-poc/latest/"><b>Docs</b></a> ·
  <a href="REPO-MAP.md">Repo map</a> ·
  <a href="development/RUNNING-THE-STACK.md">Run the stack</a> ·
  <a href="docs/API.md">API</a> ·
  <a href="docs/CONFIGURATION.md">Configuration</a> ·
  <a href="docs/engineering/ARCHITECTURE.md">Architecture</a>
</p>

<p align="center">
  <img src="docs/assets/demo.gif" alt="JAVV walkthrough: the cluster fleet, a cluster's findings, one CVE with its per-scanner evidence and audit trail, the approval queue, and the audit log" width="880">
</p>

<p align="center">
  <sub>
    The fleet · one cluster's findings · a single CVE, its per-scanner evidence and its own audit
    trail · the risk-accept queue · the journal. Real data from a two-cluster dev environment.
  </sub>
</p>

---

## Why

Vulnerability tooling splits into two worlds: **triage tools** (DefectDojo, Dependency-Track) with
rigid reporting, and **log-analytics dashboards** with no concept of auditing a finding. JAVV fills
the seam: a real triage lifecycle *and* exploratory dashboards, over what's live in your clusters.

Three things it does differently:

- **Scans what's running, not a registry.** JAVV discovers the images actually deployed in your
  clusters and scans those: the vulnerabilities you're exposed to right now, not a catalogue.
- **Two scanners, never merged.** Trivy and Grype run per-image and are kept side by side. JAVV
  never dedupes a CVE across scanners. Instead it **flags where they disagree**, so you see the
  blind spots a single-scanner tool hides.
- **Every vulnerability is auditable.** Each finding carries its own immutable history: a six-state
  triage lifecycle (+ VEX and risk-accept), every decision journaled with who, what, and when, plus
  **whole-app time-travel** that rewinds every screen to any point in the past. Most tools have no
  concept of auditing a single finding; here it's the core.

## Features

- **Runtime discovery**: scan the images live in your clusters. Choose what to scan by namespace, image and workload kind.
- **Per-scanner, side by side**: Trivy + Grype kept separate; disagreement is surfaced, never merged away.
- **Per-finding audit trail**: every vulnerability keeps its own immutable history, with each triage action, decision, and note journaled by who, what, and when, replayed in causal-revision order.
- **Triage lifecycle**: a six-state machine (five operator-settable; `stale` is set by the staleness sweep), VEX export (OpenVEX / CycloneDX), risk-accept, decisions that apply across scanners.
- **Whole-app time-travel**: a global picker rewinds *every* screen to any point ≤ now, reconstructed from the append logs.
- **Append-only audit log**: immutable, per-finding and per-user, exportable to CSV.
- **Multi-tenant + RBAC**: isolated by immutable `cluster_id`; capability-based roles, local auth + bootstrap admin.
- **Server-side everything**: every count and page comes from an OpenSearch aggregation, never computed on the client.
- **Dashboards & exports**: overview, running-images inventory, scanner status, contributors, approvals, SLA tracking, one-click CSV.
- **Data inspector + repair actions**: a read-only OpenSearch console and a small set of sanctioned, journaled maintenance jobs.
- **No external broker**: coordination is OpenSearch, and the backend runs its own background jobs on cron schedules. No Redis/Kafka/RabbitMQ, and no CronJob per job: one backend container and one frontend container.

## Architecture

```mermaid
flowchart TB
    subgraph CLUSTER["Your cluster · one per cluster_id"]
        direction TB
        SCAN["Python scanner module<br/>Trivy + Grype adapters, one JAVV-built image each<br/>run as CronJobs, kept per-scanner and never merged"]
    end

    subgraph JAVV["JAVV · central, never writes to a monitored cluster"]
        direction TB
        API["FastAPI async backend<br/>server-side aggregations"]
        STORE[("OpenSearch · single store<br/>findings · append logs · audit · config")]
        UI["Vue 3 frontend<br/>PrimeVue · Pinia · ECharts"]
        API <--> STORE
        API --> UI
    end

    SCAN -->|"scan envelopes<br/>token-authenticated ingest"| API
```

Ingest is authenticated with a per-cluster bearer token that is **scope-bound**: a token cannot push
another cluster's data. JAVV only ever receives pushes, so it needs no credentials for, and no
network path into, the clusters it reports on.

Deploy: **docker compose on one machine**, or **Helm charts on Kubernetes**
([`docs/DEPLOYING.md`](docs/DEPLOYING.md)). Full detail on layers, data flow, and the index
model lives in [`docs/engineering/ARCHITECTURE.md`](docs/engineering/ARCHITECTURE.md) and
[`docs/engineering/INDEX-MAP.md`](docs/engineering/INDEX-MAP.md).

## Running it

**On one machine:** [`deploy/compose/`](deploy/compose/) starts OpenSearch, the backend and the
frontend with `docker compose up -d`, on the images the release publishes, and scanners in any
cluster push to it. **On Kubernetes:** the `javv-opensearch` and `javv` charts, and `javv-scanner`
in each cluster you scan. The guide for both, including http or https and pointing scanners at
JAVV, is **[`docs/DEPLOYING.md`](docs/DEPLOYING.md)**, also on the
[docs site](https://danube-labs.github.io/javv-poc/latest/) with configuration, sizing, upgrades and the
API.

**From source**, for development: bring the stack up by hand (backend + UI against a local OpenSearch, or the full end-to-end path
with real Trivy/Grype scanning a live k3d cluster) by following
**[`development/RUNNING-THE-STACK.md`](development/RUNNING-THE-STACK.md)** (paths A / B / F). On a
fresh Ubuntu host, `bash development/setup/setup-dev.sh` installs every prerequisite first
(idempotent; verify readiness with `preflight.sh`).

## Documentation

**Operator docs: <https://danube-labs.github.io/javv-poc/latest/>**. Deploying, configuration, sizing and
scaling, upgrading, release notes, the API and the ingest contract, published from the files in
this repository whenever they change on `main`.

**Canonical engineering set ([`docs/engineering/`](docs/engineering/)):**

| Doc | What |
|---|---|
| [PLAN.md](docs/engineering/PLAN.md) | Decisions, data model, milestones |
| [SPEC.md](docs/engineering/SPEC.md) | Functional + non-functional requirements (FR/NFR) |
| [ARCHITECTURE.md](docs/engineering/ARCHITECTURE.md) | Layers, data flow, diagrams (Mermaid) |
| [INDEX-MAP.md](docs/engineering/INDEX-MAP.md) | Source of truth for every OpenSearch index + mapping |
| [FLOW-EXAMPLE.md](docs/engineering/FLOW-EXAMPLE.md) | Worked ingest / query / time-travel examples |
| [AUDIT-RESPONSE.md](docs/engineering/AUDIT-RESPONSE.md) | External-audit findings and their resolutions |

**Supporting:**

| Path | What |
|---|---|
| [REPO-MAP.md](REPO-MAP.md) | **Repository map**: what every folder is + reading order |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Setup, house conventions, the gates a PR must pass |
| [SECURITY.md](SECURITY.md) | How to report a vulnerability in JAVV (privately), and what's in scope |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Contributor Covenant 3.0: how we work together, and how to report a concern |
| [docs/API.md](docs/API.md) | The shipped HTTP surface at a glance (auth regimes, capabilities) |
| [docs/DEPLOYING.md](docs/DEPLOYING.md) | Deploy JAVV: docker compose on one machine or the Helm charts on Kubernetes, and connect the scanners |
| [docs/UPGRADING.md](docs/UPGRADING.md) | Move a running JAVV to a newer release |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every configuration setting: its default, what it does, where you set it |
| [development/RUNNING-THE-STACK.md](development/RUNNING-THE-STACK.md) | Bring the stack up by hand (backend / full-stack / frontend) |
| [docs/research/](docs/research/) | Stack best-practices, tooling/MCP, audits backing v4 |
| [design/](design/) | Brand source of record (logos, tokens, guide) |

## Stack & toolchain

Python 3.12 · FastAPI (async) · AsyncOpenSearch · Pydantic v2 · Vue 3 (`<script setup>`) · PrimeVue ·
Pinia · vue-echarts. OpenSearch is the single store. Open-source components throughout.

Gate-tool versions (the ones that decide lint/type/test results, so local matches CI) are pinned in
**[`versions.yaml`](versions.yaml)** (D42). Bump them there; `development/setup/setup-dev.sh` reads
it directly and `development/scripts/check-versions.sh` drift-checks every consumer.

| Tool | Role | Version |
|---|---|---|
| Python | Backend runtime | 3.12 |
| [uv](https://docs.astral.sh/uv/) | Python package/venv manager | `toolchain.uv` in [`versions.yaml`](versions.yaml) |
| [ruff](https://docs.astral.sh/ruff/) | Lint + format (backend) | `toolchain.ruff` in [`versions.yaml`](versions.yaml) |
| [pyright](https://microsoft.github.io/pyright/) | Type check (backend) | `toolchain.pyright` in [`versions.yaml`](versions.yaml) |
| Node.js | Frontend runtime / toolchain | `toolchain.node` in [`versions.yaml`](versions.yaml) |
| Vite · Vitest · ESLint/oxlint · stylelint · vue-tsc | Build, tests, lint/type gates (frontend) | from [`frontend/package.json`](frontend/package.json) |
| OpenSearch | Single datastore | pinned in [`versions.yaml`](versions.yaml) |
| [Trivy](https://trivy.dev/) · [Grype](https://github.com/anchore/grype) | Scanners (per-scanner, never merged) | pinned in [`versions.yaml`](versions.yaml) |
| kubectl · helm · [k3d](https://k3d.io/) | Local k8s (k3s-in-Docker) | latest |

### Supported versions

The externally-owned scanners + datastore JAVV pins and supports live in
[`versions.yaml`](versions.yaml) (D41/D42). Renovate watches it, the **compatibility gate**
(`scanner-images` CI) validates a new scanner version before it's published, and a drift check keeps
the Dockerfiles + dev compose in step. To change support, edit `versions.yaml`.

<!-- --8<-- [start:supported-versions] -->
| Component | Current | Also supported |
|---|---|---|
| Trivy | 0.76.0 | 0.76.1, 0.70.0 |
| Grype | 0.120.1 | 0.114.0 |
| OpenSearch | 3.9.0 | n/a |
<!-- --8<-- [end:supported-versions] -->

Scanner images are published per supported version as
`ghcr.io/danube-labs/javv-scanner-{trivy,grype}:<ver>`; an operator pins/swaps a tag in their own
deploy (JAVV never changes versions in a running cluster). Each published image is signed (cosign
keyless) with a signed SBOM attestation: [how to verify one](scanner/README.md#verify-a-published-image).

## License

JAVV is **source-available** under the [Business Source License 1.1](LICENSE):

- **Free to use, modify, and self-host**, including in production, for any team or company.
- **What you may not do:** offer JAVV itself to third parties as a hosted/managed service (i.e. sell JAVV-as-a-service).
- **Time-delayed open source:** on the Change Date (**2030-06-10**) this version automatically converts to the **Apache License 2.0**.

Bundled/invoked tools (Trivy, Grype, OpenSearch) remain under their own Apache-2.0 licenses with
attribution. For other licensing arrangements, contact Danube Labs.
