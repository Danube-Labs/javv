"""Dashboard files (issue 440, slice S6): export and import as NDJSON, one dashboard on each line
and a summary line (D5). Mounted before `routers/dashboards.py`, so `export.ndjson` is not read
as a dashboard id.

The export gives only what the caller can see, and needs no `can_export`: a dashboard is a
layout, not findings (D7). A line carries no owner, author or time, so a shared file names nobody.

The import makes the caller the owner of each new dashboard, and the session sets the authors
(D6, risk 3): those fields of a file are ignored. Each line goes through `DashboardFields`, the
model of a create, and gets its own result; an id that exists is 409 for that line, and `copy`
gives every line a new id. All lines are checked before the first write, so a file over the
limit writes nothing."""

import json
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, Response
from opensearchpy.exceptions import ConflictError
from pydantic import Field, ValidationError

from backend.core.metrics import LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.routers.dashboards import (
    DASHBOARD_SCHEMA_VERSION,
    DASHBOARDS_INDEX,
    MAX_DASHBOARDS,
    Authenticated,
    CanEdit,
    DashboardFields,
    create_doc,
    visibility_query,
)

router = APIRouter(prefix="/api/v1/dashboards", tags=["dashboards"])
log = structlog.get_logger()

_ID_PATTERN = r"^[0-9a-f]{32}$"  # the ids that create gives (uuid4 hex)
# the fields the session sets: a file's values are dropped, never stored (D6)
_SET_BY_SESSION = frozenset(
    {"owner", "created_by", "created_at", "updated_by", "updated_at", "revision"}
)
_SUMMARY_KEYS = frozenset({"exported_count", "missing_ids"})
NDJSON = "application/x-ndjson"


class ImportLine(DashboardFields):
    """One line of a file: the fields of a create, and the id it was exported with."""

    dashboard_id: str = Field(pattern=_ID_PATTERN)
    schema_version: Literal[1] = DASHBOARD_SCHEMA_VERSION


_MAX_KEYS = len(ImportLine.model_fields) + len(_SET_BY_SESSION)


class _TooWide(ValueError):
    pass


def _narrow(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    # each unknown key is its own error: 320,000 of them in one panel cost 5 s and 370 MB
    if len(pairs) > _MAX_KEYS:
        raise _TooWide
    return dict(pairs)


def _export_line(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "dashboard_id": doc["dashboard_id"],
        "schema_version": doc["schema_version"],
        **{k: doc[k] for k in DashboardFields.model_fields},
    }


@router.get("/export.ndjson")
async def export_dashboards(
    request: Request,
    principal: Authenticated,
    dashboard_id: Annotated[list[str] | None, Query(max_length=MAX_DASHBOARDS)] = None,
) -> Response:
    client = cast(Any, request.app.state.opensearch)
    wanted = list(dict.fromkeys(dashboard_id or []))
    query: dict[str, Any] = visibility_query(principal)
    if wanted:
        query = {"bool": {"filter": [query, {"terms": {"dashboard_id": wanted}}]}}
    resp = await client.search(
        index=DASHBOARDS_INDEX,
        body={
            "query": query,
            "size": MAX_DASHBOARDS,
            "sort": [{"name": "asc"}, {"dashboard_id": "asc"}],
        },
        params={"ignore_unavailable": "true"},
    )
    docs = [h["_source"] for h in resp["hits"]["hits"]]
    found = {d["dashboard_id"] for d in docs}
    # not found and not visible read the same, as the 404 of ruling Q3
    summary = {"exported_count": len(docs), "missing_ids": [i for i in wanted if i not in found]}
    lines = [json.dumps(_export_line(d), separators=(",", ":")) for d in docs]
    lines.append(json.dumps(summary, separators=(",", ":")))
    return Response(
        content="\n".join(lines) + "\n",
        media_type=NDJSON,
        headers={"Content-Disposition": 'attachment; filename="dashboards.ndjson"'},
    )


async def _read_capped(request: Request, cap: int) -> bytes:
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > cap:  # enforced while reading: the header may lie
            log.warning("dashboard import too large", limit_bytes=cap)
            LIMIT_REJECTIONS.labels("dashboard_import").inc()
            raise HTTPException(413, f"the file is larger than {cap} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _field_errors(exc: ValidationError) -> list[dict[str, Any]]:
    # the place and the reason, never the value the file sent (issue 842)
    return [
        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
        for e in exc.errors(include_url=False)
    ]


def _split(raw: bytes) -> list[tuple[int, bytes]]:
    """(line number, text) of each line that is not empty. NDJSON ends a line only at `\\n`:
    `splitlines` also ends one at U+2028, which a JSON string may hold."""
    return [
        (number, line.rstrip(b"\r"))
        for number, line in enumerate(raw.split(b"\n"), start=1)
        if line.strip()
    ]


def _error(msg: str, type_: str) -> list[dict[str, Any]]:
    return [{"loc": [], "msg": msg, "type": type_}]


def _parse_line(text: bytes) -> ImportLine | list[dict[str, Any]] | None:
    """The checked line, its errors, or None for the summary line of an export."""
    try:
        # -sig: an editor may save a BOM
        obj = json.loads(text.decode("utf-8-sig"), object_pairs_hook=_narrow)
    except UnicodeDecodeError:
        return _error("not valid UTF-8", "unicode_decode")
    except _TooWide:
        return _error(f"an object has more than {_MAX_KEYS} fields", "too_many_fields")
    except (json.JSONDecodeError, RecursionError):
        return _error("not valid JSON", "json_invalid")
    if not isinstance(obj, dict):
        return _error("not an object", "dict_type")
    obj = cast(dict[str, Any], obj)
    if "exported_count" in obj and set(obj) <= _SUMMARY_KEYS:
        return None
    try:
        return ImportLine.model_validate({k: v for k, v in obj.items() if k not in _SET_BY_SESSION})
    except ValidationError as exc:
        return _field_errors(exc)


def _too_many(lines: int) -> HTTPException:
    log.warning("dashboard import too many lines", lines=lines, limit=MAX_DASHBOARDS)
    LIMIT_REJECTIONS.labels("dashboard_import").inc()
    return HTTPException(413, f"the file has more than {MAX_DASHBOARDS} dashboards")


@router.post(
    "/import",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {NDJSON: {"schema": {"type": "string"}}},
        }
    },
)
async def import_dashboards(
    request: Request,
    principal: CanEdit,
    copy: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    # a form can post text/plain with the session cookie; it cannot post this type
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != NDJSON:
        raise HTTPException(415, f"the import takes {NDJSON}")
    client = cast(Any, request.app.state.opensearch)
    raw = _split(await _read_capped(request, get_settings().dashboard_import_max_bytes))
    # counted before any line is parsed: parsing 4 MiB of short lines blocks the loop for seconds
    if len(raw) > MAX_DASHBOARDS + 1:  # + the summary line of an export
        raise _too_many(len(raw))
    lines = [(n, line) for n, text in raw if (line := _parse_line(text)) is not None]
    if len(lines) > MAX_DASHBOARDS:
        raise _too_many(len(lines))

    results: list[dict[str, Any]] = []
    for number, line in lines:
        if isinstance(line, list):
            results.append({"line": number, "status": 422, "errors": line})
            continue
        dashboard_id = uuid4().hex if copy else line.dashboard_id
        exists = await client.exists(index=DASHBOARDS_INDEX, id=dashboard_id)
        if exists:
            results.append({"line": number, "dashboard_id": dashboard_id, "status": 409})
            continue
        fields = DashboardFields.model_validate(
            line.model_dump(include=set(DashboardFields.model_fields))
        )
        try:
            await create_doc(client, principal, fields, dashboard_id)
        except ConflictError:  # made between the check and the write
            results.append({"line": number, "dashboard_id": dashboard_id, "status": 409})
            continue
        results.append({"line": number, "dashboard_id": dashboard_id, "status": 201})

    counts = {s: sum(1 for r in results if r["status"] == s) for s in (201, 409, 422)}
    return {
        "results": results,
        "created": counts[201],
        "conflicts": counts[409],
        "invalid": counts[422],
    }
