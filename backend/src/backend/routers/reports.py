"""`/api/v1/reports` (M7/#32) — enqueue + status for scheduled exports.

`POST` writes a `pending` `system-reports` doc; the off-peak drain (`jobs/report_drain`, a later
slice) claims it via OCC, streams the export through M6's engine, stores the result chunked in
OpenSearch, and rings the bell. Status/download are OWNER-scoped (`requested_by` must match the
principal; a foreign report_id 404s exactly like a missing one) — beyond that a scheduled export
is a read, gated like the M6 inline export (`get_current_principal`, no extra capability).
`cluster_id` is a required field, applied on the export query at drain time and re-checked on
download.

`GET /{report_id}` returns job status (the public view — never the raw params/attempt internals);
for a `done`, unexpired report it also mints the short-lived signed `download_token` (SEC-10
intent). `GET /{report_id}/download` streams the canonical chunks in `seq` order — session +
token + `expires_at` gated (**410** once expired; a dead link never serves stale bytes).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from opensearchpy import NotFoundError
from pydantic import ValidationError

from backend.auth.capabilities import accept_final_refusal, holds_accept_final
from backend.auth.principal import Principal, get_current_principal
from backend.core.metrics import LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.reports import download_token
from backend.reports.models import (
    DONE,
    REPORTS_INDEX,
    EnqueueReport,
    new_report_doc,
    public_report,
)
from backend.reports.storage import stream_chunks
from backend.triage.bulk import (
    SelectorTooBroad,
    count_risk_accepted,
    freeze_targets,
    risk_accept_refusal,
    validate_bulk_patch,
)
from backend.triage.bulk_routes import BulkPatch, BulkSelector
from backend.triage.state_machine import TransitionError

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]


def _bulk_part_errors(exc: ValidationError, part: str) -> RequestValidationError:
    # the same 422 as a field check of the body itself, so the value is not sent back
    return RequestValidationError(
        [
            {**error, "loc": ("body", "bulk_params", part, *error["loc"])}
            for error in exc.errors(include_url=False)
        ]
    )


@router.post("", status_code=201)
async def enqueue_report(
    request: Request, body: EnqueueReport, principal: Authenticated
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    report_id, doc = new_report_doc(body, requested_by=principal.user_id)

    if body.kind == "bulk_triage":
        # slice 5 (audit A-Mc): a scheduled bulk is a WRITE — capability regime mirrors the
        # inline bulk exactly (can_triage; +can_accept_audit_final when the patch risk-accepts),
        # checked BEFORE any store work.
        caps = principal.capabilities
        if "*" not in caps and "can_triage" not in caps:
            raise HTTPException(403, "bulk_triage reports require can_triage")
        assert body.bulk_params is not None  # the model validator guarantees the pairing
        try:
            # the drain copies every key onto each finding, so only the inline patch's fields
            # may pass (issue 854); a null field is dropped, as it always was here
            patch = BulkPatch.model_validate(body.bulk_params.patch).model_dump(exclude_none=True)
        except ValidationError as exc:
            raise _bulk_part_errors(exc, "patch") from exc
        accept_final = holds_accept_final(principal)
        if patch.get("state") == "risk_accepted" and not accept_final:
            raise accept_final_refusal("risk-accept requires can_accept_audit_final")
        try:
            selector = BulkSelector(**body.bulk_params.selector).model_dump(exclude_none=True)
        except ValidationError as exc:
            raise _bulk_part_errors(exc, "selector") from exc
        try:
            validate_bulk_patch(patch)
        except TransitionError as exc:
            raise HTTPException(422, str(exc)) from exc
        # freeze AT ENQUEUE (D38/H8 — a queue never carries a live selector). The freeze cap
        # still applies (bounded memory); the INLINE ceiling deliberately does not — scheduled
        # runs are the sanctioned path past it (the A-Mc lift).
        try:
            target_ids = await freeze_targets(
                client,
                body.cluster_id,
                selector,
                max_targets=get_settings().bulk_max_targets,
            )
        except SelectorTooBroad as exc:
            log.warning("bulk selector capped at enqueue", cluster_id=body.cluster_id)
            LIMIT_REJECTIONS.labels("bulk_targets").inc()
            raise HTTPException(413, str(exc)) from exc
        if "state" in patch and not accept_final:  # issue 892 ruling 6, as the inline bulk
            held = await count_risk_accepted(client, target_ids)
            if held:
                raise accept_final_refusal(risk_accept_refusal(held, len(target_ids)))
        doc["params"] = {
            "selector": selector,
            "patch": patch,
            "target_ids": target_ids,  # FROZEN — the drain applies exactly this set
            # the drain checks again for a risk-accept made after now, unless this is true
            "may_undo_risk_accept": accept_final,
        }

    # op_type=create: the id is fresh (uuid4), so this can't overwrite; refresh so a status read /
    # the drain sees it immediately (a single small ops write, not the read-side refresh storm)
    await client.index(
        index=REPORTS_INDEX, id=report_id, body=doc, params={"op_type": "create", "refresh": "true"}
    )
    out: dict[str, Any] = {"report_id": report_id, "status": doc["status"]}
    if body.kind == "bulk_triage":
        out["target_count"] = len(doc["params"]["target_ids"])
    return out


def _expired(doc: dict[str, Any]) -> bool:
    expires_at = doc.get("expires_at")
    return expires_at is not None and datetime.fromisoformat(expires_at) <= datetime.now(UTC)


def _require_owner(doc: dict[str, Any], principal: Principal) -> None:
    # own-report 404 (not 403): a foreign report_id must be indistinguishable from a missing one
    if doc.get("requested_by") != principal.user_id:
        raise HTTPException(404, "report not found")


@router.get("/{report_id}")
async def get_report(request: Request, report_id: str, principal: Authenticated) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    try:
        doc = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "report not found") from None
    _require_owner(doc, principal)
    view = public_report(doc)
    if doc.get("status") == DONE and not _expired(doc):
        # short-lived (15 min) — the bell/UI refetches this view for a fresh one (SEC-10 intent)
        view["download_token"] = download_token.mint(report_id)
    return view


@router.get("/{report_id}/download")
async def download_report(
    request: Request, report_id: str, token: str, principal: Authenticated
) -> StreamingResponse:
    client = cast(Any, request.app.state.opensearch)
    try:
        doc = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "report not found") from None
    _require_owner(doc, principal)
    if doc.get("status") != DONE:
        raise HTTPException(404, "report has no result (not done)")
    if _expired(doc):
        raise HTTPException(410, "download expired — re-run the export")
    if not download_token.verify(report_id, token):
        raise HTTPException(403, "invalid or expired download token — refetch the report status")

    fmt = (doc.get("params") or {}).get("format", "csv")
    media = "text/csv; charset=utf-8" if fmt == "csv" else "application/json"
    ext = "csv" if fmt == "csv" else "json"

    async def _body() -> AsyncIterator[str]:
        # only the done doc's attempt_id chunks are canonical — a fenced loser's are orphans
        async for data in stream_chunks(client, report_id, doc["attempt_id"]):
            yield data

    return StreamingResponse(
        _body(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.{ext}"'},
    )
