"""Liveness + readiness. `/healthz` is pure liveness — **no** OpenSearch dependency, always 200 as
long as the process is up. `/readyz` reflects OpenSearch reachability: 503 `degraded` when it does
not answer, so the app can stay up and degrade instead of crashing (observability.md).

A store that answers but is red, or read-only because its disk is past the flood-stage watermark,
is still 200, with `checks.store`: reads work, and a 503 would take the only backend pod out of
service through its readiness probe (issue 832). The UI shows a banner for it. A check that fails
leaves the answer at `ready`, counted and logged at most once per window."""

from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.core.errors import StoreWarnings
from backend.core.metrics import OS_REQUEST_ERRORS

router = APIRouter(tags=["health"])

# the indices JAVV owns, the patterns of its OpenSearch role
_JAVV_INDICES = "findings,javv-*,system-*"
# OpenSearch's block id for an index past the flood-stage disk watermark
_FLOOD_STAGE_BLOCK = "12"

_check_warned = StoreWarnings("store check failed", OS_REQUEST_ERRORS.labels("other").inc)


async def _store_state(client: Any) -> str | None:
    """`red`, `read-only`, or None. Red wins: part of the data is missing, not only writes."""
    if (await client.cluster.health()).get("status") == "red":
        return "red"
    state = await client.cluster.state(
        metric="blocks",
        index=_JAVV_INDICES,
        params={"ignore_unavailable": "true", "allow_no_indices": "true"},
    )
    blocked = state.get("blocks", {}).get("indices", {})
    if any(_FLOOD_STAGE_BLOCK in blocks for blocks in blocked.values()):
        return "read-only"
    return None


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    client = cast(Any, request.app.state.opensearch)
    try:
        reachable = await client.ping()
    except Exception:
        reachable = False
    if not reachable:
        return JSONResponse(
            status_code=503, content={"status": "degraded", "opensearch": "unreachable"}
        )
    try:
        store = await _store_state(client)
    except Exception as exc:  # noqa: BLE001 — the store answered the ping; reads can still work
        _check_warned.note(request, exc)
        store = None
    content: dict[str, Any] = {"status": "ready"}
    if store is not None:
        content["checks"] = {"store": store}
    return JSONResponse(status_code=200, content=content)
