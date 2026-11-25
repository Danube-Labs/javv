"""GET /api/v1/trends/* — the MVP trend surface (M6 slice 3, FR-5/FR-12).

- `/trends/scans` — committed scans per day per scanner over `javv-scan-events-<cluster_id>-*`,
  deduped via `cardinality(commit_key)` (task B, #139 — rollover-straddling retry duplicates
  are accepted in storage, NEVER counted twice at read).
- `/trends/findings` — the "new in Nd" series and its burn-down twin (resolved), per scanner,
  over the findings cache. No `present` filter: a finding that appeared and was tombstoned
  inside the window still counts as new that day. **`resolved` = SCAN-resolved** (audit A-m9):
  the series buckets `resolved_at`, which is stamped ONLY by reconcile (a finding the scanner
  stopped reporting) — a human `state=resolved` triage does NOT set it, so a manually-resolved
  finding is not in this burn-down. The response carries `resolved_semantics="scan_resolved"` so
  the M9c burn-down chart labels it accurately; human-resolution counting is a product decision
  deferred to M9c, not a bug.
- `/trends/ingest-failures` — pushes the ingest route refused after the token check, per bucket per
  scanner (issue 575), on `/trends/scans`'s exact axis so the two strips line up. An append-only
  log, so a past `as_of` just ends the window at T — no reconstruction, never a 501.
- `/trends/new-findings` — the findings first seen in each bucket, by severity, under the filters
  of `GET /findings` (issue 1292), with the bounds and bucket size of `/trends/scans`. `present`
  comes from the
  filters (the default counts the findings present now), and the window ends at now. A past
  `as_of` goes to the reader, which rebuilds the rows at T and counts daily buckets.

A range is `days` (whole UTC days) or `window_seconds` (the exact range of 2 days or less, at now
only, issue 1291). Each live read stops at the time of the request.

Tenancy: scan-events routing pins the per-cluster index pattern AND the tenant read path forces the
`cluster_id` body filter; findings reads carry it through the tenant read path alone. Same uniform
`as_of` seam as every read (D28: past T is 501 until the slice-7 dispatcher wires M8b).
"""

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.core.identifiers import ClusterId
from backend.query.search import conflicting_filter_pair
from backend.query.trends import (
    EXACT_MAX_SECONDS,
    EXACT_MIN_SECONDS,
    ScanFilters,
    build_findings_trend_body,
    build_ingest_failures_trend_body,
    build_new_findings_trend_body,
    build_scans_trend_body,
    pick_window,
)
from backend.routers.findings import (
    AsOf,
    Authenticated,
    Filters,
    _reader_or_501,
    _reconstructed,
    _sla_cutoffs,
    _Values128,
    _Values256,
    _Values512,
)
from backend.tenancy.read_path import tenant_search

router = APIRouter(prefix="/api/v1/trends", tags=["trends"])

# no default in the signature: 30 when the request names neither `days` nor `window_seconds`
# (pick_window), so a route can refuse a request that names both, also from an MCP tool
Days = Annotated[
    int | None,
    Query(
        ge=1,
        le=365,
        description=(
            "The range is in whole UTC days. With no range in the request, the range is 30 days."
        ),
    ),
]
# the exact length of a range of 2 days or less, at now only (issue 1291)
WindowSeconds = Annotated[
    int | None,
    Query(
        ge=EXACT_MIN_SECONDS,
        le=EXACT_MAX_SECONDS,
        description="The exact range is in seconds. It ends at the time of the request.",
    ),
]
Interval = Literal["day", "hour"]
# the type of `scanner` on /trends/findings: the MCP tool `trends` takes the parameters of both
# routes under one name, and refuses to start when their types differ
Scanner = Literal["trivy", "grype"] | None


def _scan_filters(
    namespace: _Values256 = None,
    exclude_namespace: _Values256 = None,
    image_repo: _Values512 = None,
    exclude_image_repo: _Values512 = None,
    tag: _Values128 = None,
    exclude_tag: _Values128 = None,
    untagged: bool | None = None,
    image_digest: Annotated[str | None, Query(max_length=128)] = None,
    scanner: Scanner = None,
    exclude_scanner: Scanner = None,
) -> ScanFilters:
    """The filters of /findings that a scan record holds (issue 1293), with the same names and
    caps. The route declares only these, so it never takes a filter that it does not apply."""
    filters = ScanFilters(
        namespace=namespace,
        exclude_namespace=exclude_namespace,
        image_repo=image_repo,
        exclude_image_repo=exclude_image_repo,
        tag=tag,
        exclude_tag=exclude_tag,
        untagged=untagged,
        image_digest=image_digest,
        scanner=scanner,
        exclude_scanner=exclude_scanner,
    )
    if (message := conflicting_filter_pair(vars(filters))) is not None:
        raise HTTPException(422, message)
    return filters


ScanFiltersDep = Annotated[ScanFilters, Depends(_scan_filters)]


def _guard_hourly(interval: str, days: int | None) -> None:
    # contract guard (audit 343): hourly × long spans is a cost setting no UI uses — 365d hourly
    # is ~8.8k materialized buckets per scanner per request. 31d hourly (744) stays cheap.
    if interval == "hour" and days is not None and days > 31:
        raise HTTPException(422, "interval=hour is limited to days<=31 — use daily buckets")


def _pick(
    days: int | None, window_seconds: int | None, as_of_t: Any
) -> tuple[int | None, int | None]:
    try:
        return pick_window(days, window_seconds, past=as_of_t is not None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _series(
    by_scanner: dict[str, Any], *, metric: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    """{scanner: [{date, <metric|count>}]} — metric names a sub-agg, None = the doc count."""
    key = metric or "count"

    def point(b: dict[str, Any]) -> dict[str, Any]:
        return {"date": b["key_as_string"], key: b[metric]["value"] if metric else b["doc_count"]}

    return {s["key"]: [point(b) for b in s["timeline"]["buckets"]] for s in by_scanner["buckets"]}


@router.get("/scans")
async def scans_trend(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    filters: ScanFiltersDep,
    days: Days = None,
    window_seconds: WindowSeconds = None,
    interval: Interval = "day",
) -> dict[str, Any]:
    days, window_seconds = _pick(days, window_seconds, as_of_t)
    _guard_hourly(interval, days)
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:  # past T → M8b's reconstruction, never this route's query (D28)
        # the reader reconstructs DAILY only (MVP) — `interval` is a live-path setting; the
        # reader's payload rides verbatim (the dispatch pin)
        return await _reconstructed(
            _reader_or_501().trends_scans(
                client, cluster_id=cluster_id, t=as_of_t, days=cast(int, days), filters=filters
            )
        )
    index = f"javv-scan-events-{cluster_id}-*"
    resp = await tenant_search(
        client,
        index=index,
        cluster_id=cluster_id,
        body=build_scans_trend_body(
            days=days, window_seconds=window_seconds, interval=interval, filters=filters
        ),
    )
    # a cluster with no scan-events yet matches zero indices — no aggregations at all
    aggs = resp.get("aggregations")
    series = _series(aggs["by_scanner"], metric="scans") if aggs else {}
    return {"series": series, "days": days, "window_seconds": window_seconds, "interval": interval}


@router.get("/findings")
async def findings_trend(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    days: Days = None,
    split: Literal["scanner", "severity"] = "scanner",
    scanner: Literal["trivy", "grype"] | None = None,
) -> dict[str, Any]:
    days = cast(int, _pick(days, None, as_of_t)[0])  # daily only: no exact window here
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:
        if split != "scanner":  # the M8b reader reconstructs per-scanner only (MVP; like the
            raise HTTPException(422, "split=severity is not available at a past T")  # A-m1 422s
        return await _reconstructed(
            _reader_or_501().trends_findings(client, cluster_id=cluster_id, t=as_of_t, days=days)
        )
    # no read-side refresh (audit A-m2/#191): reads observe committed state; writers refresh
    resp = await tenant_search(
        client,
        index="findings",
        cluster_id=cluster_id,
        body=build_findings_trend_body(days=days, split=split, scanner=scanner),
    )
    aggs = resp["aggregations"]
    return {
        "new": _series(aggs["new"]["by_key"]),
        "resolved": _series(aggs["resolved"]["by_key"]),
        "resolved_semantics": "scan_resolved",  # A-m9: resolved_at is reconcile-only, not triage
        "days": days,
        "split": split,
    }


@router.get("/ingest-failures")
async def ingest_failures_trend(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    days: Days = None,
    window_seconds: WindowSeconds = None,
    interval: Interval = "day",
) -> dict[str, Any]:
    days, window_seconds = _pick(days, window_seconds, as_of_t)
    _guard_hourly(interval, days)
    client = cast(Any, request.app.state.opensearch)
    resp = await tenant_search(
        client,
        index=f"javv-ingest-failures-{cluster_id}-*",
        cluster_id=cluster_id,
        body=build_ingest_failures_trend_body(
            days=days, window_seconds=window_seconds, anchor=as_of_t, interval=interval
        ),
    )
    # a cluster that never had a push refused matches zero indices — no aggregations at all
    aggs = resp.get("aggregations")
    series = _series(aggs["by_scanner"]) if aggs else {}
    return {"series": series, "days": days, "window_seconds": window_seconds, "interval": interval}


@router.get("/new-findings")
async def new_findings_trend(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
    days: Days = None,
    window_seconds: WindowSeconds = None,
    interval: Interval = "day",
) -> dict[str, Any]:
    days, window_seconds = _pick(days, window_seconds, as_of_t)
    _guard_hourly(interval, days)
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:  # past T → the reader rebuilds the rows at T, daily only (D28)
        return await _reconstructed(
            _reader_or_501().trends_new_findings(
                client, cluster_id=cluster_id, t=as_of_t, days=cast(int, days), filters=filters
            )
        )
    body = build_new_findings_trend_body(
        filters,
        days=days,
        window_seconds=window_seconds,
        interval=interval,
        sla_cutoffs=await _sla_cutoffs(client, filters),
    )
    resp = await tenant_search(client, index="findings", cluster_id=cluster_id, body=body)
    series = _series(resp["aggregations"]["by_severity"])
    return {"series": series, "days": days, "window_seconds": window_seconds, "interval": interval}
