"""The findings export surface (M6 slices 5–6, FR-13/FR-22).

- `GET /api/v1/findings/export.csv` — the inline "run now" CSV path: streams the current
  lens (same `SearchFilters` the grid uses) row by row over the constant-memory PIT sweep,
  every cell injection-sanitized (`export/csv_stream.py`). Scheduled/throttled exports and
  the `system-reports` queue are M7.
- `GET /api/v1/findings/export.vex` — OpenVEX / CycloneDX VEX document (slice 6).

Both need `can_export` (issue 243: the viewer reads but does not export); each cluster is
readable by every such principal (MVP tenant model). `cluster_id` is REQUIRED and forced
into the sweep by the tenant read path — entitlement is re-checked on the export exactly
like any fetch (IDOR, api-design tenant rule). `as_of`: exports describe current state;
a past T is 501 until the M8b reconstruction can feed an export (D28).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.core.identifiers import ClusterId
from backend.core.metrics import EXPORT_BYTES, EXPORT_ROWS, LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.export.csv_stream import stream_csv
from backend.export.sweep import count_lens, sweep_findings
from backend.export.vex import to_cyclonedx, to_openvex
from backend.query import pit_guard
from backend.routers.findings import AsOf, Filters

router = APIRouter(prefix="/api/v1/findings", tags=["exports"])
log = structlog.get_logger()

CanExport = Annotated[Principal, Depends(require_capability("can_export"))]


async def _enforce_export_bounds(
    client: Any, *, cluster_id: str, filters: Any, principal: Principal, fmt: str
) -> pit_guard.Slot:
    """Shared inline-export guards (audit A-M6/A-m12/#189): 413 if the lens exceeds the row cap
    (checked BEFORE any PIT/stream via a cheap count), then reserve a per-principal PIT slot (429
    if the principal is at its concurrent-PIT cap). The caller releases the slot when done."""
    max_rows = get_settings().export_max_rows
    n = await count_lens(client, cluster_id=cluster_id, filters=filters)
    if n > max_rows:
        log.warning("inline export capped", cluster_id=cluster_id, cap=max_rows, format=fmt)
        LIMIT_REJECTIONS.labels("export_rows").inc()  # M-4 (#220)
        raise HTTPException(
            413,
            f"{n} findings exceed the inline export limit ({max_rows}) — "
            "narrow the filters, or use M7's scheduled export",
        )
    try:
        return pit_guard.acquire(principal.user_id)
    except pit_guard.PitCapExceeded as exc:
        log.warning("PIT cap reached for principal", format=fmt)
        raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc


@router.get("/export.csv")
async def export_csv(
    request: Request,
    principal: CanExport,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
) -> StreamingResponse:
    if as_of_t is not None:
        # exports describe current state until M8b reconstruction can feed a sweep (D28);
        # the AsOfTReader protocol carries no export surface yet — deliberate, not a gap
        raise HTTPException(501, "export at a past as_of lands with M8b reconstruction")
    client = cast(Any, request.app.state.opensearch)
    # no read-side refresh (audit A-m2/#191): reads observe committed state; writers refresh
    slot = await _enforce_export_bounds(
        client, cluster_id=cluster_id, filters=filters, principal=principal, fmt="csv"
    )

    async def _guarded() -> AsyncIterator[str]:
        # the slot reserved above is held for the life of the stream and freed when it ends —
        # success, error, or a client that disconnects mid-stream (the generator's finally runs).
        # M-4 (#220): rows/bytes counted in the same finally — a disconnected client's export
        # reports what was ACTUALLY streamed, not what was asked for.
        rows, size = 0, 0
        try:
            async for line in stream_csv(client, cluster_id=cluster_id, filters=filters):
                rows += 1
                size += len(line)
                yield line
        finally:
            pit_guard.release(principal.user_id, slot)
            EXPORT_ROWS.labels("csv").inc(max(0, rows - 1))  # minus the header line
            EXPORT_BYTES.labels("csv").inc(size)

    return StreamingResponse(
        _guarded(),
        media_type="text/csv; charset=utf-8",
        headers={
            # cluster_id shape is edge-validated (lowercase alnum/hyphen) — header-safe
            "Content-Disposition": f'attachment; filename="findings-{cluster_id}.csv"'
        },
    )


@router.get("/export.vex")
async def export_vex(
    request: Request,
    principal: CanExport,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
    format: Literal["openvex", "cyclonedx"] = "openvex",
) -> dict[str, Any]:
    if as_of_t is not None:
        raise HTTPException(501, "export at a past as_of lands with M8b reconstruction")
    if filters.scanner is None:
        # per-scanner is sacred: a VEX document speaks for ONE scanner's findings — two
        # scanners' verdicts are never merged into one advisory (hard constraint)
        raise HTTPException(422, "VEX export requires a scanner filter (per-scanner is sacred)")
    client = cast(Any, request.app.state.opensearch)
    # no read-side refresh (audit A-m2/#191): reads observe committed state; writers refresh
    slot = await _enforce_export_bounds(
        client, cluster_id=cluster_id, filters=filters, principal=principal, fmt=format
    )
    try:
        findings = [
            doc async for doc in sweep_findings(client, cluster_id=cluster_id, filters=filters)
        ]
        serialize = to_openvex if format == "openvex" else to_cyclonedx
        EXPORT_ROWS.labels(format).inc(len(findings))  # M-4 (#220); bytes n/a — JSON response
        return serialize(
            findings,
            cluster_id=cluster_id,
            scanner=filters.scanner,
            generated_at=datetime.now(UTC),
        )
    finally:
        pit_guard.release(principal.user_id, slot)
