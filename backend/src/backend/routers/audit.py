"""GET /api/v1/audit (M8c slice 1, #240) — the journaled history, read plain-session (ruled
2026-07-07, #237): every triage action is already attributed in-row (D17/D32), so any
authenticated user may read the log. Feeds the M9d Audit screen + Contributors activity feed.

Cursor-paged with the A-m1 machinery (`query/audit.py`): opaque cursor, 410 on an expired PIT,
422 on a tampered cursor/bad order, 503 when the store is down — never a 500. Cursor-less pages
reserve a per-principal PIT slot (A-m12/#189), same budget as the findings grid."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import ConnectionTimeout

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.core.metrics import EXPORT_BYTES, EXPORT_ROWS, LIMIT_REJECTIONS, OS_REQUEST_ERRORS
from backend.core.settings import get_settings
from backend.export.audit_csv import count_audit_lens, stream_audit_csv
from backend.query import pit_guard
from backend.query.as_of import parse_as_of
from backend.query.audit import (
    AuditFilters,
    CursorExpired,
    audit_tenant_query,
    build_audit_facets_body,
    run_audit_search,
)
from backend.query.search import cursor_pit_id

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
log = structlog.get_logger()

Authenticated = Annotated[Principal, Depends(get_current_principal)]


def _reject_conflicting_modes(filters: AuditFilters) -> None:
    """A field is included OR excluded, never both (issue 349) — the same 422 the findings
    edge raises, so the negation surfaces answer a malformed request identically instead of
    silently ANDing a term with its own must_not into zero rows."""
    for name, inc, exc in (
        ("entity_type", filters.entity_type, filters.exclude_entity_type),
        ("action", filters.action, filters.exclude_action),
        ("actor", filters.actor, filters.exclude_actor),
    ):
        if inc is not None and exc is not None:
            raise HTTPException(422, f"{name} and exclude_{name} are mutually exclusive")


@router.get("")
async def read_audit_log(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor: Annotated[str | None, Query(max_length=128)] = None,
    finding_key: Annotated[str | None, Query(max_length=256)] = None,
    exclude_entity_type: Annotated[str | None, Query(max_length=64)] = None,
    exclude_action: Annotated[str | None, Query(max_length=64)] = None,
    exclude_actor: Annotated[str | None, Query(max_length=128)] = None,
    order: Annotated[str, Query(max_length=4)] = "desc",
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    as_of: Annotated[str | None, Query(max_length=64)] = None,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    try:
        until = parse_as_of(as_of)  # D28: absent/now = unbounded; a past T = lte bound
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    filters = AuditFilters(
        entity_type=entity_type,
        action=action,
        actor=actor,
        finding_key=finding_key,
        until=until,
        exclude_entity_type=exclude_entity_type,
        exclude_action=exclude_action,
        exclude_actor=exclude_actor,
    )
    _reject_conflicting_modes(filters)
    slot: pit_guard.Slot | None = None  # a cursor-less page opens a fresh PIT and takes a slot
    if cursor is None:
        try:
            slot = pit_guard.acquire(principal.user_id)  # A-m12/#189: bound concurrent PITs
        except pit_guard.PitCapExceeded as exc:
            log.warning("PIT cap reached for principal", format="audit_page")
            raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc
    try:
        out = await run_audit_search(
            client,
            cluster_id=cluster_id,
            filters=filters,
            size=size,
            order=order,
            cursor=cursor,
        )
    except CursorExpired as exc:  # A-m1: idled past keep_alive → 410 Gone, restart the walk
        pit_guard.release(principal.user_id, slot)
        if cursor is not None:  # the walk's PIT is gone, so its slot is too
            pit_guard.release_pit(principal.user_id, cursor_pit_id(cursor))
        raise HTTPException(410, str(exc)) from exc
    except ValueError as exc:  # tampered/undecodable cursor or bad order — 422, not a 500
        pit_guard.release(principal.user_id, slot)
        raise HTTPException(422, str(exc)) from exc
    except (OSConnectionError, ConnectionTimeout) as exc:  # A-m1: cluster down/slow → 503
        pit_guard.release(principal.user_id, slot)
        kind = "timeout" if isinstance(exc, ConnectionTimeout) else "conn"
        OS_REQUEST_ERRORS.labels(kind).inc()  # M-2 (#220)
        raise HTTPException(503, "search backend unavailable — retry") from exc
    except BaseException:
        pit_guard.release(principal.user_id, slot)
        raise
    walk = out["next_cursor"] or cursor
    pit_guard.settle(
        principal.user_id,
        slot,
        cursor_pit_id(walk) if walk else None,
        ended=out["next_cursor"] is None,  # the final page closed its PIT (D38)
    )
    return out


@router.get("/facets")
async def audit_facets(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor: Annotated[str | None, Query(max_length=128)] = None,
    exclude_entity_type: Annotated[str | None, Query(max_length=64)] = None,
    exclude_action: Annotated[str | None, Query(max_length=64)] = None,
    exclude_actor: Annotated[str | None, Query(max_length=128)] = None,
    as_of: Annotated[str | None, Query(max_length=64)] = None,
    interval: Annotated[str | None, Query(max_length=8)] = None,
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    """Rail counts for the audit screen (M9d rework): entity_type/action/actor terms under the
    same filters + D28 bound as the walk — the counts describe the current lens, server-side.
    With `interval` (day|hour) the response adds `activity`: the audit lens's events-over-time
    histogram across the picker window (quiet buckets included as zeros)."""
    client = cast(Any, request.app.state.opensearch)
    try:
        until = parse_as_of(as_of)
        filters = AuditFilters(
            entity_type=entity_type,
            action=action,
            actor=actor,
            until=until,
            exclude_entity_type=exclude_entity_type,
            exclude_action=exclude_action,
            exclude_actor=exclude_actor,
        )
        _reject_conflicting_modes(filters)
        body = build_audit_facets_body(filters, interval=interval, window_days=window_days)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        resp = await client.search(
            index="system-audit-log-*", body=audit_tenant_query(cluster_id, body)
        )
    except (OSConnectionError, ConnectionTimeout) as exc:
        kind = "timeout" if isinstance(exc, ConnectionTimeout) else "conn"
        OS_REQUEST_ERRORS.labels(kind).inc()
        raise HTTPException(503, "search backend unavailable — retry") from exc
    aggs = resp["aggregations"]
    activity = aggs.pop("activity", None)
    out: dict[str, Any] = {
        "facets": {
            field: [
                {"key": b["key"], "count": b["doc_count"], "by_scanner": {}} for b in agg["buckets"]
            ]
            for field, agg in aggs.items()
        }
    }
    if activity is not None:
        out["activity"] = [
            {"date": b["key_as_string"], "count": b["doc_count"]}
            for b in activity["buckets"]["buckets"]
        ]
    return out


@router.get("/export.csv")
async def export_audit_csv(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor: Annotated[str | None, Query(max_length=128)] = None,
    exclude_entity_type: Annotated[str | None, Query(max_length=64)] = None,
    exclude_action: Annotated[str | None, Query(max_length=64)] = None,
    exclude_actor: Annotated[str | None, Query(max_length=128)] = None,
    as_of: Annotated[str | None, Query(max_length=64)] = None,
) -> StreamingResponse:
    """The prototype's Export CSV (M9d): streams the current audit lens — decorated,
    injection-sanitized, constant-memory. Same inline bounds as the findings export: a cheap
    pre-count 413s over `JAVV_EXPORT_MAX_ROWS` before any PIT opens; the PIT slot is the
    principal's (429 at the cap) and is released when the stream ends."""
    client = cast(Any, request.app.state.opensearch)
    try:
        until = parse_as_of(as_of)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    filters = AuditFilters(
        entity_type=entity_type,
        action=action,
        actor=actor,
        until=until,
        exclude_entity_type=exclude_entity_type,
        exclude_action=exclude_action,
        exclude_actor=exclude_actor,
    )
    _reject_conflicting_modes(filters)
    max_rows = get_settings().export_max_rows
    n = await count_audit_lens(client, cluster_id=cluster_id, filters=filters)
    if n > max_rows:
        log.warning("inline export capped", cluster_id=cluster_id, cap=max_rows, format="audit")
        LIMIT_REJECTIONS.labels("export_rows").inc()  # M-4 (#220)
        raise HTTPException(
            413,
            f"{n} events exceed the inline export limit ({max_rows}) — narrow the filters",
        )
    try:
        slot = pit_guard.acquire(principal.user_id)
    except pit_guard.PitCapExceeded as exc:
        log.warning("PIT cap reached for principal", format="audit")
        raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc

    async def body() -> AsyncIterator[str]:
        # M-4 (#220): rows/bytes counted in the same finally that frees the PIT slot — a
        # client that disconnects mid-stream reports what was ACTUALLY streamed
        rows, size = 0, 0
        try:
            async for line in stream_audit_csv(client, cluster_id=cluster_id, filters=filters):
                rows += 1
                size += len(line)
                yield line
        finally:
            pit_guard.release(principal.user_id, slot)
            EXPORT_ROWS.labels("audit_csv").inc(max(0, rows - 1))  # minus the header line
            EXPORT_BYTES.labels("audit_csv").inc(size)

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return StreamingResponse(
        body(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="javv-audit-{stamp}.csv"'},
    )
