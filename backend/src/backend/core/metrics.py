"""Prometheus metrics (D9 + major-audit #220). Exposed at /metrics.

Rules that keep this useful (02-metrics-endpoint.md):
- **Bounded labels only** — route TEMPLATES (never raw paths), closed reason/kind/site sets.
  A label that can carry attacker-chosen strings is a cardinality bomb.
- **Storage-free scrape** — nothing here queries OpenSearch; /metrics keeps working during an
  OpenSearch outage, which is exactly when it's needed.
- Single-process registry: we run one uvicorn worker. If M10 ever goes multi-worker, this needs
  `prometheus_client.multiprocess` (env dir + registry swap) — do not add workers without it.
"""

import time
from typing import Any

from fastapi import FastAPI, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# --- ingest (M1/D9) -----------------------------------------------------------

INGEST_ACCEPTED = Counter("javv_ingest_accepted_total", "Envelopes accepted", ["scanner"])
INGEST_REJECTED = Counter("javv_ingest_rejected_total", "Envelopes rejected", ["reason"])
# issue 357: a rejection the failed-ingests table will never show — its record write failed
INGEST_FAILURES_UNRECORDED = Counter(
    "javv_ingest_failures_unrecorded_total",
    "Post-auth ingest rejections whose failed-ingest record could not be written",
    ["reason"],
)
FINDINGS_WRITTEN = Counter(
    "javv_ingest_findings_written_total", "Finding docs written", ["scanner"]
)

# --- M-1: the request histogram (#220) -----------------------------------------

# search-API-shaped buckets; 30s = the OpenSearch client timeout ceiling
_DURATION_BUCKETS = (0.005, 0.025, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
HTTP_REQUEST_DURATION = Histogram(
    "javv_http_request_duration_seconds",
    "Request duration by route template",
    ["method", "route", "status"],
    buckets=_DURATION_BUCKETS,
)
# probes + self-scrape dominate volume and skew p99 — excluded by ruling (02 §M-1)
_UNTIMED_PATHS = frozenset({"/metrics", "/healthz", "/readyz"})

# --- M-2: OpenSearch dependency health ------------------------------------------

OS_REQUEST_ERRORS = Counter(
    "javv_opensearch_request_errors_total",
    "OpenSearch request failures by kind",
    ["kind"],  # conn | timeout | 429 | 5xx | other — closed set, map the rest to other
)
OS_BACKOFF_RETRIES = Counter(
    "javv_opensearch_backoff_retries_total",
    "Per-item 429/503 bulk retries — the only flow control without a broker; its rate IS the"
    " saturation signal",
)
SLA_CLOCK_MISSING = Counter(
    "javv_sla_clock_missing_total",
    "Findings pages hitting rows without a materialized sla_clock_at (issue 363) — the agg"
    " fallback served them; a sustained rate means run rebuild-state to backfill",
)
STORED_SETTING_UNKNOWN_FIELDS = Counter(
    "javv_stored_setting_unknown_fields_total",
    "Stored-setting reads that dropped fields this release doesn't know (issue 640) — non-zero"
    " after a rollback means a newer release saved that setting; `setting` is the kind, not the"
    " per-cluster doc id, so the series stay bounded",
    ["setting"],
)
CONFIG_WARNINGS = Counter(
    "javv_config_warnings_total",
    "Start-ups whose settings leave a connection weaker than it looks (issue 715): OpenSearch"
    " certificates not checked, or its password sent over plain http; `setting` names the"
    " variable",
    ["setting"],  # JAVV_OPENSEARCH_VERIFY_CERTS | JAVV_OPENSEARCH_URL
)

# --- M-3: concurrency-control churn ----------------------------------------------

CAS_CONFLICTS = Counter(
    "javv_cas_conflicts_total",
    "seq_no/primary_term CAS conflicts by site — early warning for multi-writer contention (D40)",
    ["site"],  # watermarks | scan_orders | reproject | report_claim (M7 slice 2) |
    # inventory_orders | reconcile | merge (issue 510 — the commit-race drain loops) |
    # retirement (issue 765: an un-retire that lost to a concurrent retire)
)

# --- M-4: limit pressure ----------------------------------------------------------

LIMIT_REJECTIONS = Counter(
    "javv_limit_rejections_total",
    "Requests rejected by a configured bound",
    # pit_cap | export_rows | bulk_targets | bulk_inline | client_events — one counter, one label
    ["limit"],
)
PITS_OPEN = Gauge(
    "javv_pits_open", "Open PIT slots across principals (per pod, like the guard itself)"
)
EXPORT_ROWS = Counter("javv_export_rows_total", "Rows actually streamed", ["format"])
EXPORT_BYTES = Counter("javv_export_bytes_total", "Bytes actually streamed", ["format"])

# --- M-5: auth signals -------------------------------------------------------------

AUTH_FAILURES = Counter(
    "javv_auth_failures_total",
    "Authentication/authorization failures by reason — NEVER labeled by username (PII + unbounded)",
    # bad_credentials | locked_out | expired_session | missing_capability | must_change
    ["reason"],
)


# --- M-6: background jobs (issue 691) ----------------------------------------------

JOB_RUNS = Counter(
    "javv_job_runs_total",
    "Scheduled background-job runs by kind and outcome",
    ["kind", "outcome"],  # kind: jobs/registry.py (closed set) · outcome: done | failed | skipped
)
JOB_LAST_SUCCESS = Gauge(
    "javv_job_last_success_timestamp_seconds",
    "Unix time of the kind's last successful scheduled run in this process (0 until one succeeds)",
    ["kind"],
)
SCHEDULER_TICK_ERRORS = Counter(
    "javv_scheduler_tick_errors_total",
    "Scheduler ticks that failed before a job could start (the store was away); a sustained"
    " rate means no job is running",
)
RETIREMENT_HELD = Counter(
    "javv_cluster_retirement_held_total",
    "Retirement sweeps that retired nothing because no cluster had a scan accepted within its"
    " scanner-down timer (issue 765): that points at JAVV itself, an outage or a rejected"
    " scanner version",
)
CLUSTER_DELETE_LEFTOVERS = Counter(
    "javv_cluster_delete_leftovers_total",
    "Deleted clusters whose next-night pass found rows written after the delete (issue 778), a"
    " push in flight or a job running at the time; the pass removed them",
)
STORE_UNAVAILABLE = Counter(
    "javv_store_unavailable_total",
    "Requests answered 503 because OpenSearch was not reachable or still starting (issue 832)",
)
CLUSTER_DELETE_RECHECK_FAILURES = Counter(
    "javv_cluster_delete_recheck_failures_total",
    "Retirement sweeps whose pass over deleted clusters failed (issue 778); the run's retirements"
    " stand and the next run passes again",
)
CLUSTER_DELETE_INCOMPLETE = Counter(
    "javv_cluster_delete_incomplete_total",
    "Cluster deletes that stopped halfway and answered 503 (issue 765): a step stayed contended or"
    " the store was away; a retry finishes the delete",
)
RETIREMENT_NOTIFY_FAILURES = Counter(
    "javv_cluster_retirement_notify_failures_total",
    "Retirement sweep steps whose bell notifications could not be written or withdrawn (issue"
    " 765); the run's retirements stand and the next run tries again",
)


def install_http_metrics(app: FastAPI) -> None:
    """M-1 middleware. Route label = the matched route TEMPLATE (set in scope after routing);
    requests that match no route collapse into one `unmatched` series — never the raw path."""

    @app.middleware("http")
    async def _observe(request: Request, call_next: Any) -> Any:
        if request.url.path in _UNTIMED_PATHS:
            return await call_next(request)
        start = time.perf_counter()
        status = "500"  # an unhandled exception IS a 500 — recorded in the finally, then re-raised
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            HTTP_REQUEST_DURATION.labels(request.method, route, status).observe(
                time.perf_counter() - start
            )


__all__ = [
    "AUTH_FAILURES",
    "CAS_CONFLICTS",
    "CLUSTER_DELETE_INCOMPLETE",
    "CLUSTER_DELETE_LEFTOVERS",
    "CLUSTER_DELETE_RECHECK_FAILURES",
    "CONFIG_WARNINGS",
    "CONTENT_TYPE_LATEST",
    "EXPORT_BYTES",
    "EXPORT_ROWS",
    "FINDINGS_WRITTEN",
    "HTTP_REQUEST_DURATION",
    "INGEST_ACCEPTED",
    "INGEST_FAILURES_UNRECORDED",
    "INGEST_REJECTED",
    "JOB_LAST_SUCCESS",
    "JOB_RUNS",
    "LIMIT_REJECTIONS",
    "OS_BACKOFF_RETRIES",
    "OS_REQUEST_ERRORS",
    "PITS_OPEN",
    "RETIREMENT_HELD",
    "RETIREMENT_NOTIFY_FAILURES",
    "SCHEDULER_TICK_ERRORS",
    "generate_latest",
    "install_http_metrics",
]
