"""Close a cursor walk early (issue 832): `POST /api/v1/cursors/close`.

A findings or audit walk holds an OpenSearch PIT and one of the caller's PIT slots until its last
page, or until the PIT's keep-alive ends. A list the user leaves, or a filter that starts a new
walk, would otherwise hold the slot for the whole horizon; the web app closes the walk here.

The route only closes a walk that one of the caller's own slots holds (`pit_guard.holds`). Any
other cursor, another user's, an ended walk's, or one from before a restart, answers the same 204
and never reaches OpenSearch: the PIT id inside a cursor is client input, and the slot is what
vouches for it. Nothing is read, so there is no `cluster_id`; nothing is changed but the caller's
own search, so there is no audit row.
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.auth.principal import Principal, get_current_principal
from backend.query import pit_guard
from backend.query.search import cursor_pit_id

router = APIRouter(prefix="/api/v1/cursors", tags=["cursors"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]


class CloseCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor: str = Field(min_length=1, max_length=4096)  # the read routes' own cursor bound


@router.post("/close", status_code=204)
async def close_cursor(request: Request, principal: Authenticated, body: CloseCursor) -> Response:
    try:
        pit_id = cursor_pit_id(body.cursor)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not pit_guard.holds(principal.user_id, pit_id):
        return Response(status_code=204)
    client = cast(Any, request.app.state.opensearch)
    await client.delete_pit(body={"pit_id": [pit_id]})  # a PIT already gone still answers 200
    pit_guard.release_pit(principal.user_id, pit_id)
    return Response(status_code=204)
