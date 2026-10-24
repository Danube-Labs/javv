"""GET /api/v1/contributors — triage-work metrics (M6 slice 4, FR-15).

Orchestrates `query/contributors.py`: one aggregation pass over `system-audit-log-*` (the
leaderboard + the handled-over-time series), one bounded fetch of the window's handling rows,
one findings lookup for the clocks/SLA inputs, then the pure `compute_ttr_sla`. All three reads
go through the tenant read path; the SLA verdicts use the LIVE policy (M5d). Same uniform
`as_of` seam as every read (D28).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.core.identifiers import ClusterId
from backend.core.metrics import EXPORT_BYTES, EXPORT_ROWS, LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.export.contributors_csv import stream_contributors_csv
from backend.query.contributors import (
    HANDLING_ACTIONS,
    build_actions_body,
    compute_team_totals,
    compute_ttr_sla,
    empty_totals,
)
from backend.routers.findings import AsOf, Authenticated, _reader_or_501, _reconstructed
from backend.sla.policy import read_sla_policy
from backend.tenancy.read_path import tenant_query, tenant_search

router = APIRouter(prefix="/api/v1/contributors", tags=["contributors"])
log = structlog.get_logger()

CanExport = Annotated[Principal, Depends(require_capability("can_export"))]

_AUDIT_PATTERN = "system-audit-log-*"
_ROWS_PAGE_SIZE = 10_000  # PIT page size for the handling-row walk (NOT a truncation ceiling)


async def _handling_rows(
    client: Any, cluster_id: str, days: int, anchor: datetime | None = None, prefix: str = ""
) -> list[dict[str, Any]]:
    """Every handling-action row in the window, PIT + `search_after` paged so TTR/SLA see the FULL
    window — never a silent 10k-truncated subset that would disagree with the exact leaderboard
    count (audit A-m4). Deterministic sort on `(@timestamp, event_id)`; PIT deleted in `finally`
    (the sweep pattern). The tenant filter is forced by `tenant_query` (SEC-4 — the PIT search
    carries no index name, so the body filter is the only guard)."""
    keep_alive = get_settings().search_pit_keep_alive
    pit_id = (
        await client.create_pit(
            index=f"{prefix}{_AUDIT_PATTERN}", params={"keep_alive": keep_alive}
        )
    )["pit_id"]
    rows: list[dict[str, Any]] = []
    try:
        search_after: list[Any] | None = None
        while True:
            body: dict[str, Any] = {
                "size": _ROWS_PAGE_SIZE,
                "query": {
                    "bool": {
                        "filter": [
                            {"terms": {"action": sorted(HANDLING_ACTIONS)}},
                            {"term": {"entity_type": "finding"}},
                            # anchored at a past T (M8b/D28): same walk, window ending at T.
                            # ALWAYS absolute dates, never `now`-math (the createWeight flake,
                            # see query/trends.py)
                            {
                                "range": {
                                    "@timestamp": (
                                        {
                                            "gte": (
                                                datetime.now(UTC).date() - timedelta(days=days)
                                            ).isoformat()
                                        }
                                        if anchor is None
                                        else {
                                            "gte": (
                                                anchor.date() - timedelta(days=days)
                                            ).isoformat(),
                                            "lte": anchor.isoformat(),
                                        }
                                    )
                                }
                            },
                        ],
                        "must_not": [{"term": {"actor": "system"}}],
                    }
                },
                "_source": ["actor", "finding_key", "@timestamp"],
                "sort": [{"@timestamp": "asc"}, {"event_id": "asc"}],
            }
            if search_after is not None:
                body["search_after"] = search_after
            body = tenant_query(cluster_id, body)  # SEC-4 — cluster filter on the index-less PIT
            body["pit"] = {"id": pit_id, "keep_alive": keep_alive}
            resp = await client.search(body=body)
            hits = resp["hits"]["hits"]
            rows += [h["_source"] for h in hits]
            if len(hits) < _ROWS_PAGE_SIZE:
                return rows
            search_after = hits[-1]["sort"]
    finally:
        await client.delete_pit(body={"pit_id": [pit_id]})  # the walk owns the PIT (D38)


async def _findings_for(
    client: Any, cluster_id: str, keys: list[str], prefix: str = ""
) -> dict[str, dict[str, Any]]:
    if not keys:
        return {}
    resp = await tenant_search(
        client,
        index=f"{prefix}findings",
        cluster_id=cluster_id,
        body={
            "size": len(keys),
            "query": {"bool": {"filter": [{"terms": {"finding_key": keys}}]}},
            "_source": ["finding_key", "first_seen_at", "severity", "kev"],
        },
    )
    return {h["_source"]["finding_key"]: h["_source"] for h in resp["hits"]["hits"]}


async def _payload(
    client: Any, *, cluster_id: str, days: int, as_of_t: datetime | None
) -> dict[str, Any]:
    """The screen's whole answer. Shared by the JSON read and the CSV export (issue 359) so the
    file can never carry different numbers from the screen it was exported from."""
    if as_of_t is not None:  # past T → M8b's reconstruction, never this route's query (D28)
        return await _reconstructed(
            _reader_or_501().contributors(client, cluster_id=cluster_id, t=as_of_t, days=days)
        )
    # no read-side refresh (audit A-m2/#191): the audit log is append-only; the leaderboard is a
    # metrics view (eventual consistency is fine), and triage writes already refresh
    resp = await tenant_search(
        client,
        index=_AUDIT_PATTERN,
        cluster_id=cluster_id,
        body=build_actions_body(days=days),
    )
    aggs = resp.get("aggregations")
    if not aggs:  # a cluster with no audit history yet
        return {"days": days, "leaderboard": [], "handled_over_time": [], "totals": empty_totals()}

    rows = await _handling_rows(client, cluster_id, days)
    findings = await _findings_for(
        client, cluster_id, sorted({r["finding_key"] for r in rows if r.get("finding_key")})
    )
    policy = await read_sla_policy(client)
    verdicts = compute_ttr_sla(rows, findings, policy=policy)
    by_action = {a["key"]: a["doc_count"] for a in aggs["by_action"]["buckets"]}
    totals = {
        "actions": sum(by_action.values()),
        "by_action": by_action,
        **compute_team_totals(rows, findings, policy=policy),
    }

    leaderboard = []
    for bucket in aggs["by_actor"]["buckets"]:
        actor = bucket["key"]
        v = verdicts.get(actor, {})
        leaderboard.append(
            {
                "actor": actor,
                "actions": bucket["doc_count"],
                "by_action": {a["key"]: a["doc_count"] for a in bucket["by_action"]["buckets"]},
                "handled": v.get("handled", 0),
                "median_ttr_seconds": v.get("median_ttr_seconds"),
                "sla_hit_pct": v.get("sla_hit_pct"),
            }
        )
    timeline = [
        {"date": b["key_as_string"], "count": b["doc_count"]}
        for b in aggs["handled_over_time"]["timeline"]["buckets"]
    ]
    return {
        "days": days,
        "leaderboard": leaderboard,
        "handled_over_time": timeline,
        "totals": totals,
    }


@router.get("")
async def contributors(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    return await _payload(
        cast(Any, request.app.state.opensearch),
        cluster_id=cluster_id,
        days=days,
        as_of_t=as_of_t,
    )


@router.get("/export.csv")
async def export_contributors_csv(
    request: Request,
    principal: CanExport,
    cluster_id: ClusterId,
    as_of_t: AsOf,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> StreamingResponse:
    """The prototype's Export CSV (issue 359): the leaderboard of the current window.

    `as_of` rides the SAME D28 seam as the JSON read because both go through `_payload` — the
    M8b reader when one is registered, 501 otherwise. Deliberately not the findings export's
    flat 501: this screen is rewindable, so its export inherits whatever the screen can answer.

    The cap check is a POST-count, not the audit/findings pre-count: the row count only exists
    once the aggregation has run, and there is no cheaper way to learn it. It is a backstop
    rather than a hot guard — the board is already bounded by its own terms-agg size, well
    under any sane `JAVV_EXPORT_MAX_ROWS`.
    """
    client = cast(Any, request.app.state.opensearch)
    payload = await _payload(client, cluster_id=cluster_id, days=days, as_of_t=as_of_t)
    board = payload["leaderboard"]
    max_rows = get_settings().export_max_rows
    if len(board) > max_rows:
        log.warning("inline export capped", cluster_id=cluster_id, cap=max_rows, format="contrib")
        LIMIT_REJECTIONS.labels("export_rows").inc()  # M-4 (#220)
        raise HTTPException(
            413,
            f"{len(board)} contributors exceed the inline export limit ({max_rows}) — "
            "narrow the window",
        )

    async def body() -> AsyncIterator[str]:
        # M-4 (#220): rows/bytes counted in the same finally the streamed exports use, so a
        # client that disconnects mid-download reports what ACTUALLY left the building
        rows, size = 0, 0
        try:
            for line in stream_contributors_csv(payload):
                rows += 1
                size += len(line)
                yield line
        finally:
            EXPORT_ROWS.labels("contributors_csv").inc(max(0, rows - 1))  # minus the header
            EXPORT_BYTES.labels("contributors_csv").inc(size)

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return StreamingResponse(
        body(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="javv-contributors-{stamp}.csv"'},
    )
