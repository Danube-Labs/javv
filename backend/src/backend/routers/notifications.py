"""`/api/v1/notifications` (M7 slice 3, FR-16/D-3) — the bell feed, polled (no broker, NFR-9).

Strictly OWN-notifications: every query filters `user_id = principal` server-side, and mark-read
404s on anyone else's id (indistinguishable from missing — the IDOR rule). The badge count is
server-computed (`unread`) — the client never counts. The drain writes `report_ready` docs here;
`sla_breach`/`assignment` writers land with their owning bolts.
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from opensearchpy import NotFoundError

from backend.admin.cluster_registry import read_registry
from backend.auth.principal import Principal, get_current_principal
from backend.reports.models import NOTIFICATIONS_INDEX

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

_PAGE = 50  # newest N — the bell is a feed, not an archive
_PUBLIC = ("notification_id", "type", "ref", "cluster_id", "created_at", "read")


@router.get("")
async def list_notifications(request: Request, principal: Authenticated) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    own = {"term": {"user_id": principal.user_id}}
    result = await client.search(
        index=NOTIFICATIONS_INDEX,
        body={
            "size": _PAGE,
            "sort": [{"created_at": "desc"}],
            "query": {"bool": {"filter": [own]}},
        },
        params={"ignore_unavailable": "true"},
    )
    unread = await client.count(
        index=NOTIFICATIONS_INDEX,
        body={"query": {"bool": {"filter": [own, {"term": {"read": False}}]}}},
        params={"ignore_unavailable": "true"},
    )
    items = [{k: hit["_source"].get(k) for k in _PUBLIC} for hit in result["hits"]["hits"]]
    # the name at read time: a retired cluster is off the cluster list the web app holds, and a
    # rename after the notice shows (issue 787)
    names = await read_registry(client) if any(i["cluster_id"] for i in items) else {}
    for item in items:
        cid = item["cluster_id"]
        item["cluster_name"] = names.get(cid, cid) if cid else None
    return {"unread": int(unread["count"]), "items": items}


async def _own_or_404(client: Any, notification_id: str, principal: Principal) -> None:
    try:
        got = await client.get(index=NOTIFICATIONS_INDEX, id=notification_id)
    except NotFoundError:
        raise HTTPException(404, "notification not found") from None
    if got["_source"].get("user_id") != principal.user_id:
        # someone else's — indistinguishable from missing (IDOR rule)
        raise HTTPException(404, "notification not found")


@router.patch("/{notification_id}/read")
async def mark_read(
    request: Request, notification_id: str, principal: Authenticated
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    await _own_or_404(client, notification_id, principal)
    await client.update(
        index=NOTIFICATIONS_INDEX,
        id=notification_id,
        body={"doc": {"read": True}},
        params={"refresh": "true"},
    )
    return {"notification_id": notification_id, "read": True}


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    request: Request, notification_id: str, principal: Authenticated
) -> None:
    """Dismiss = hard delete of the OWN feed doc (the bell is a feed, not an archive — the
    audit trail is elsewhere by design). Same own-or-404 gate as mark-read."""
    client = cast(Any, request.app.state.opensearch)
    await _own_or_404(client, notification_id, principal)
    await client.delete(index=NOTIFICATIONS_INDEX, id=notification_id, params={"refresh": "true"})
