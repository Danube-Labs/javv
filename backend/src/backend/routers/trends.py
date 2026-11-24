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

Tenancy: scan-events routing pins the per-cluster index pattern AND the tenant read path forces the
`cluster_id` body filter; findings reads carry it through the tenant read path alone. Same uniform
`as_of` seam as every read (D28: past T is 501 until the slice-7 dispatcher wires M8b).
"""

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request

from backend.core.identifiers import ClusterId
from backend.query.trends import (
    build_findings_trend_body,
    build_ingest_failures_trend_body,
    build_new_findings_trend_body,
    build_scans_trend_body,
)
from backend.routers.findings import (
    AsOf,
    Authenticated,
    Filters,
    _reader_or_501,
    _reconstructed,
    _sla_cutoffs,
)
from backend.tenancy.read_path import tenant_search

router = APIRouter(prefix="/api/v1/trends", tags=["trends"])

Days = Annotated[int, Query(ge=1, le=365)]
Interval = Literal["day", "hour"]


def _guard_hourly(interval: str, days: int) -> None:
    # contract guard (audit 343): hourly × long spans is a cost setting no UI uses — 365d hourly
    # is ~8.8k materialized buckets per scanner per request. 31d hourly (744) stays cheap.
    if interval == "hour" and days > 31:
        raise HTTPException(422, "interval=hour is limited to days<=31 — use daily buckets")


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
    days: Days = 30,
    interval: Interval = "day",
) -> dict[str, Any]:
    _guard_hourly(interval, days)
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:  # past T → M8b's reconstruction, never this route's query (D28)
        # the reader reconstructs DAILY only (MVP) — `interval` is a live-path setting; the
        # reader's payload rides verbatim (the dispatch pin)
        return await _reconstructed(
            _reader_or_501().trends_scans(client, cluster_id=cluster_id, t=as_of_t, days=days)
        )
    index = f"javv-scan-events-{cluster_id}-*"
    resp = await tenant_search(
        client,
        index=index,
        cluster_id=cluster_id,
        body=build_scans_trend_body(days=days, interval=interval),
    )
    # a cluster with no scan-events yet matches zero indices — no aggregations at all
    aggs = resp.get("aggregations")
    series = _series(aggs["by_scanner"], metric="scans") if aggs else {}
    return {"series": series, "days": days, "interval": interval}


@router.get("/findings")
async def findings_trend(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    days: Days = 30,
    split: Literal["scanner", "severity"] = "scanner",
    scanner: Literal["trivy", "grype"] | None = None,
) -> dict[str, Any]:
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
    days: Days = 30,
    interval: Interval = "day",
) -> dict[str, Any]:
    _guard_hourly(interval, days)
    client = cast(Any, request.app.state.opensearch)
    resp = await tenant_search(
        client,
        index=f"javv-ingest-failures-{cluster_id}-*",
        cluster_id=cluster_id,
        body=build_ingest_failures_trend_body(days=days, anchor=as_of_t, interval=interval),
    )
    # a cluster that never had a push refused matches zero indices — no aggregations at all
    aggs = resp.get("aggregations")
    series = _series(aggs["by_scanner"]) if aggs else {}
    return {"series": series, "days": days, "interval": interval}


@router.get("/new-findings")
async def new_findings_trend(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
    days: Days = 30,
    interval: Interval = "day",
) -> dict[str, Any]:
    _guard_hourly(interval, days)
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:  # past T → the reader rebuilds the rows at T, daily only (D28)
        return await _reconstructed(
            _reader_or_501().trends_new_findings(
                client, cluster_id=cluster_id, t=as_of_t, days=days, filters=filters
            )
        )
    body = build_new_findings_trend_body(
        filters, days=days, interval=interval, sla_cutoffs=await _sla_cutoffs(client, filters)
    )
    resp = await tenant_search(client, index="findings", cluster_id=cluster_id, body=body)
    series = _series(resp["aggregations"]["by_severity"])
    return {"series": series, "days": days, "interval": interval}
