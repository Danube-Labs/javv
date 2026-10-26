# JAVV backend

FastAPI (async) + `AsyncOpenSearch`. Ingests the scanner envelope and serves the read, triage,
reporting and admin API. Every number comes from an OpenSearch aggregation (server-side; no raw
findings to the client). Started as bolt **M1** (`development/bolts/M1-backend-skeleton/`, #23).

The HTTP surface is documented in [`docs/API.md`](../docs/API.md); every setting in
[`docs/CONFIGURATION.md`](../docs/CONFIGURATION.md); every index in
[`docs/engineering/INDEX-MAP.md`](../docs/engineering/INDEX-MAP.md).

## Layout
```
src/backend/
  main.py       app factory (create_app)
  core/         settings · lifespan · bootstrap (versioned indexes/templates) · errors · logging ·
                metrics · rate limits · security headers
  routers/      the HTTP layer, one module per resource (ingest, findings, triage, decisions,
                exports, reports, trends, views, admin, auth, …)
  models/       the ingest envelope
  services/     ingest pipeline: merge, reconcile-on-commit, watermarks, disagreement, SLA clock
  snapshots/    per-scan occurrences + inventory-run certification (point-in-time reads)
  query/        OpenSearch query builders: search, aggs, paging (PIT + search_after), trends, as_of
  tenancy/      the tenant read path (every read carries an explicit cluster_id)
  dashboards/   the catalog of the dashboard panels that a saved dashboard can hold
  triage/       the state machine, single and bulk triage
  decisions/    scoped decisions, projection onto findings, reproject
  sla/          SLA policy and overdue
  audit/        the append-only audit-log writer
  auth/         sessions, passwords, lockout, capabilities, the bootstrap admin
  export/       CSV and VEX streams
  reports/      the scheduled-export queue: claim, lease, chunked storage, download tokens
  admin/        scan scope, snapshot repo, report TTL settings, the cluster registry,
                cluster retirement and delete
  jobs/         the background jobs (staleness, lifecycle, findings_cleanup, cluster_retirement,
                report_drain, report_sweep, session_sweep, rebuild_state), their shared lease, and the
                scheduler that runs them inside the backend
  repositories/ the `_bulk` helper (per-item status, 429/503 backoff)
  tools/        export_openapi (the frontend contract snapshot)
```

## Bootstrap

The app bootstraps on every start (`core/lifespan.py`): ping OpenSearch → create or upgrade the
indexes and templates → seed the default roles and the bootstrap admin → serve. An unreachable
OpenSearch fails fast. It is safe on every boot: unchanged versions are a no-op and the
concurrent-create race is handled. `JAVV_BOOTSTRAP_ON_STARTUP=false` turns it off (tests do).
To run it by hand: `uv run python -m backend.core.bootstrap`.

Additive mapping changes: edit INDEX-MAP + `bootstrap.py` and bump `MAPPING_VERSION`. A field
**type change** is a reindex migration, never automatic.

## Manual end-to-end test (the full pipeline, verified 2026-07-02)

Real scanner → token-authed ingest → OpenSearch. Prereqs: dev OpenSearch on :9200, k3d `alpha`
up with the `javv-smoke` seed workloads (`kubectl apply -f development/setup/seed-vuln-workloads.yaml`).

```bash
# 1. bootstrap the indexes (idempotent)
cd backend && uv run python -m backend.core.bootstrap

# 2. start the backend
uv run uvicorn backend.main:app --port 8000    # (or & for background)

# 3. mint an ingest token for the cluster (raw token prints ONCE — only its hash is stored)
CID=$(kubectl --context k3d-alpha get namespace kube-system -o jsonpath='{.metadata.uid}')
TOKEN=$(uv run python -m backend.core.tokens --cluster "$CID" --scanner trivy)

# 4. run a real scan cycle against the cluster, pushing to the backend
cd ../scanner
JAVV_SCANNER=trivy JAVV_BACKEND_URL=http://localhost:8000 JAVV_TOKEN="$TOKEN" \
  uv run python -m scanner
# → the last JSON log line is "cycle complete" with scanned / delivered / dead_lettered counts

# 5. see the findings (severity agg; lc normalizer folds scanner casing)
curl -s 'localhost:9200/findings/_search?size=0' -H 'Content-Type: application/json' \
  -d "{\"query\":{\"term\":{\"cluster_id\":\"$CID\"}},
       \"aggs\":{\"sev\":{\"terms\":{\"field\":\"severity\"}}}}" | jq '.aggregations.sev.buckets'

# 6. observability: counters incremented, and the OpenAPI/Swagger UI
curl -s localhost:8000/metrics | grep javv_ingest_          # accepted/rejected/findings_written
open http://localhost:8000/docs                             # live API reference (or /openapi.json)
```

The full HTTP surface + metrics are documented in [`docs/API.md`](../docs/API.md); `/docs` is the
live source of truth.

Failure modes worth testing by hand: no/garbage token → **401** (generic); a token minted for
`grype` pushing a trivy envelope → **403** (scope binding); a >10 MiB compressed body or a zip
bomb → **413**; an envelope with an extra field → **422** (`extra="forbid"`). Repeat step 4 —
counts stay stable (deterministic `_id`s → idempotent re-push).

## Inspecting OpenSearch by hand

Dev OpenSearch is `http://localhost:9200`, security off. `| jq` prettifies.

```bash
curl -s 'localhost:9200/_cat/indices/findings,system-tokens,javv-*?v'   # JAVV indices + doc counts
curl -s 'localhost:9200/findings/_mapping' | jq                         # every field + type
curl -s 'localhost:9200/_index_template/javv-scan-events' | jq          # per-cluster template
curl -s 'localhost:9200/findings/_count' | jq                           # doc count
curl -s 'localhost:9200/findings/_search?size=10' | jq '.hits.hits[]._source'   # first 10 docs

# filter: critical findings in one namespace (array-contains on namespaces[])
curl -s 'localhost:9200/findings/_search' -H 'Content-Type: application/json' -d '{
  "query": {"bool": {"filter": [
    {"term": {"severity": "critical"}},
    {"term": {"namespaces": "javv-smoke"}},
    {"term": {"present": true}}
  ]}}}' | jq '.hits.hits[]._source'

# aggregation: findings per severity (the lc normalizer folds scanner casing)
curl -s 'localhost:9200/findings/_search?size=0' -H 'Content-Type: application/json' \
  -d '{"aggs": {"by_severity": {"terms": {"field": "severity"}}}}' \
  | jq '.aggregations.by_severity.buckets'
```

## Dev
```bash
cd backend
uv sync --all-extras --dev
uv run ruff check . && uv run pyright       # pyright tree-wide: no path args, as CI runs it
uv run pytest -n 2 -m "not serial"           # what CI runs: parallel first,
uv run pytest -m serial                      # then the tests that must run alone
```
The suite needs OpenSearch (`JAVV_OPENSEARCH_URL`, default `http://localhost:9200`) and leaves test
residue in it: sweep it afterwards with `development/scripts/clean-dev-store.sh`, or point the run at
a throwaway store. Budget and rules: [`development/standards/testing.md`](../development/standards/testing.md).
