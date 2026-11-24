"""Scanner reads: freshness (#218) + provenance (M8c slice 1, #240).

`GET /api/v1/scanners/freshness` (major-audit D-1) — per-(cluster, scanner) data freshness for
M9a's "data as of T; scanner silent since T'" banner (FR-6/D20, audit m-7). Read-time compute off
`system-tokens.last_ingest_at` — deliberately NOT written by the M3 staleness sweep (the banner
is a view, not state). Disabled tokens still count: data freshness answers "when did data last
arrive", which token validity doesn't change. Multiple tokens per (cluster, scanner) → the max
stamp wins.

`GET /api/v1/scanners/provenance` (D41/D44) — per-(cluster, scanner) the scanner/vuln-DB versions
+ `effective_config` of the latest COMMITTED run, plus the last-N committed runs (image counts,
finding totals, started/finished). Catalog-first (R-CATALOG/D37): a scan-events doc IS the commit
marker (D39 commits it only after the run's appends land), so reading scan-events reads committed
runs by construction — an uncommitted run has no catalog row to surface. "Latest" is the max
`scan_order` (D40) resolved via `top_hits` sorted on the exact long — NEVER a `max` metric agg
(#257: float64 collapses pre-D45 time_ns-scale orders).

`GET /api/v1/scanners/ingest-failures` (issue 357) — one scanner's pushes the ingest route refused
after the token check, newest first, paged (`query/ingest_failures.py` for the paging contract).
The data behind scanner status's failed-ingests panel.

All three are session-auth reads through the tenant read path."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.query.ingest_failures import build_ingest_failures_body, decode_cursor, page_of
from backend.query.trends import pick_window
from backend.routers.findings import AsOf
from backend.routers.trends import Days, WindowSeconds
from backend.tenancy.read_path import tenant_search

router = APIRouter(prefix="/api/v1/scanners", tags=["scanners"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

# scanners are a small closed set (trivy|grype today); 50 is headroom, not a page size
_SCANNER_BUCKETS = 50


def build_freshness_body() -> dict[str, Any]:
    """Pure builder (unit-testable): max `last_ingest_at` per scanner, no hits."""
    return {
        "size": 0,
        "aggs": {
            "scanners": {
                "terms": {"field": "scanner", "size": _SCANNER_BUCKETS},
                "aggs": {"last": {"max": {"field": "last_ingest_at"}}},
            }
        },
    }


@router.get("/freshness")
async def scanner_freshness(
    request: Request, principal: Authenticated, cluster_id: ClusterId
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    resp = await tenant_search(
        client, index="system-tokens", cluster_id=cluster_id, body=build_freshness_body()
    )
    now = datetime.now(UTC)
    scanners: list[dict[str, Any]] = []
    aggs = resp.get("aggregations") or {}
    for bucket in aggs.get("scanners", {}).get("buckets", []):
        stamp: str | None = bucket["last"].get("value_as_string")
        silent: float | None = None
        if stamp is not None:
            last = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            silent = max(0.0, (now - last).total_seconds())
        scanners.append(
            {"scanner": bucket["key"], "last_ingest_at": stamp, "silent_for_seconds": silent}
        )
    scanners.sort(key=lambda row: row["scanner"])  # deterministic order for the UI/tests
    return {"cluster_id": cluster_id, "scanners": scanners}


_RUNS_PAGE = 1_000  # composite-agg page over (scanner, scan_run_id)
_PROVENANCE_FIELDS = (
    "scanner_version",
    "scanner_db_version",
    "scanner_db_built",
    "effective_config",
    "scan_run_id",
    "scan_order",
    "@timestamp",
)


def build_provenance_body() -> dict[str, Any]:
    """Pure builder: the latest committed scan-event per scanner — `top_hits` under a terms agg,
    sorted on the exact `scan_order` long (winner = newest ORDER, exactly like the live cache at
    commit time; `@timestamp` would resurrect out-of-order clocks, D40)."""
    return {
        "size": 0,
        "aggs": {
            "scanners": {
                "terms": {"field": "scanner", "size": _SCANNER_BUCKETS},
                "aggs": {
                    "latest": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"scan_order": "desc"}],
                            "_source": list(_PROVENANCE_FIELDS),
                        }
                    }
                },
            }
        },
    }


# wire name (the D16 canonical vocabulary) → the scan-events doc's bucket field
_SEVERITY_SUMS = (
    ("critical", "crit"),
    ("high", "high"),
    ("medium", "med"),
    ("low", "low"),
    ("negligible", "negligible"),
    ("unknown", "unknown"),
)


def build_runs_body(after: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure builder: one composite bucket per (scanner, scan_run_id) — image count (doc_count),
    finding totals (sums), started/finished (min/max on a DATE — epoch-ms < 2^53, exact in a
    metric agg, unlike scan_order), and the run's exact `scan_order` via `top_hits` `_source`
    (the JSON long, not a float64) as the recency key the caller sorts on."""
    composite: dict[str, Any] = {
        "size": _RUNS_PAGE,
        "sources": [
            {"scanner": {"terms": {"field": "scanner"}}},
            {"run": {"terms": {"field": "scan_run_id"}}},
        ],
    }
    if after is not None:
        composite["after"] = after
    return {
        "size": 0,
        "aggs": {
            "runs": {
                "composite": composite,
                "aggs": {
                    "findings": {"sum": {"field": "total"}},
                    "fixable": {"sum": {"field": "fixable"}},
                    # per-run severity mix (M9d slice 2): the doc buckets sum across the
                    # run's images — one scanner's own counts, never cross-scanner (FR-12)
                    **{sev: {"sum": {"field": field}} for sev, field in _SEVERITY_SUMS},
                    "started": {"min": {"field": "@timestamp"}},
                    "finished": {"max": {"field": "@timestamp"}},
                    "latest": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"scan_order": "desc"}],
                            "_source": ["scan_order"],
                        }
                    },
                },
            }
        },
    }


def _run_row(bucket: dict[str, Any]) -> dict[str, Any]:
    """One composite bucket → the wire shape for a committed run."""
    top = bucket["latest"]["hits"]["hits"][0]["_source"]
    return {
        "scan_run_id": bucket["key"]["run"],
        "scan_order": top["scan_order"],  # exact — read from _source, never a metric agg (#257)
        "images": bucket["doc_count"],
        "findings_total": int(bucket["findings"]["value"]),
        "fixable_total": int(bucket["fixable"]["value"]),
        "severity": {sev: int(bucket[sev]["value"]) for sev, _ in _SEVERITY_SUMS},
        "started_at": bucket["started"].get("value_as_string"),
        "finished_at": bucket["finished"].get("value_as_string"),
    }


@router.get("/provenance")
async def scanner_provenance(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    runs: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    index = f"javv-scan-events-{cluster_id}-*"

    resp = await tenant_search(
        client, index=index, cluster_id=cluster_id, body=build_provenance_body()
    )
    # a non-matching wildcard returns 200 with NO aggregations key — an unscanned cluster is a
    # real, empty answer (same guard as query/pit.py)
    latest_buckets = ((resp.get("aggregations") or {}).get("scanners") or {}).get("buckets", [])

    runs_by_scanner: dict[str, list[dict[str, Any]]] = {}
    after: dict[str, Any] | None = None
    while True:
        page = await tenant_search(
            client, index=index, cluster_id=cluster_id, body=build_runs_body(after)
        )
        agg = (page.get("aggregations") or {}).get("runs")
        if agg is None:
            break
        for b in agg["buckets"]:
            runs_by_scanner.setdefault(b["key"]["scanner"], []).append(_run_row(b))
        after = agg.get("after_key")
        if after is None or not agg["buckets"]:
            break

    scanners: list[dict[str, Any]] = []
    for bucket in latest_buckets:
        latest = bucket["latest"]["hits"]["hits"][0]["_source"]
        history = runs_by_scanner.get(bucket["key"], [])
        history.sort(key=lambda r: r["scan_order"], reverse=True)  # exact longs — Python sort
        scanners.append(
            {
                "scanner": bucket["key"],
                "scanner_version": latest.get("scanner_version"),
                "scanner_db_version": latest.get("scanner_db_version"),
                "scanner_db_built": latest.get("scanner_db_built"),
                "effective_config": latest.get("effective_config"),
                "last_run": {
                    "scan_run_id": latest["scan_run_id"],
                    "scan_order": latest["scan_order"],
                    "at": latest.get("@timestamp"),
                },
                "runs": history[:runs],
            }
        )
    scanners.sort(key=lambda row: row["scanner"])
    return {"cluster_id": cluster_id, "scanners": scanners}


@router.get("/ingest-failures")
async def scanner_ingest_failures(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    scanner: Literal["trivy", "grype"],
    as_of_t: AsOf,
    days: Days = None,
    window_seconds: WindowSeconds = None,
    size: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
) -> dict[str, Any]:
    """An append-only log read directly at any T (the window just ends there), so a past
    `as_of` needs no reconstruction and never 501s. `window_seconds` gives the exact range of
    the strip above the table (issue 1291)."""
    try:
        after = None if cursor is None else decode_cursor(cursor)
        days, window_seconds = pick_window(days, window_seconds, past=as_of_t is not None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    client = cast(Any, request.app.state.opensearch)
    body = build_ingest_failures_body(
        scanner=scanner,
        days=days,
        window_seconds=window_seconds,
        size=size,
        anchor=as_of_t,
        search_after=after,
    )
    resp = await tenant_search(
        client, index=f"javv-ingest-failures-{cluster_id}-*", cluster_id=cluster_id, body=body
    )
    return page_of(resp, size)
