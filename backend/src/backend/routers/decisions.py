"""Decision routes (M5c, FR-8) — the HTTP face of `decisions/lifecycle.py` + the projector.

Capability regime mirrors triage (SEC-2/D33): every route needs `can_triage`. A
**`risk_accepted`** or **`ignore_rule`** decision (both project `state=risk_accepted`) additionally
requires `can_accept_audit_final` to create, to edit (from or to that type) and to revoke: a
triager can neither make nor undo one (issue 892 rulings 1 and 5). All three mutating routes are
registered in the standing RBAC/IDOR suite. This layer only translates auth + errors — the
service owns CAS, journaling, the revoke+create pair, and re-projection.

List is a tenant read: `cluster_id` is a REQUIRED filter (the tenant-read-path rule — never an
unscoped cross-cluster read), with task-E pagination (`size`/`offset` + `total`).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from opensearchpy import NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.auth.capabilities import accept_final_refusal, holds_accept_final, require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.core.metrics import EXPORT_BYTES, EXPORT_ROWS, LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.decisions.lifecycle import (
    DECISIONS_INDEX,
    DecisionPayload,
    create_decision,
    edit_decision,
    revoke_decision,
)
from backend.export.approvals_csv import count_approvals_lens, stream_approvals_csv
from backend.query import pit_guard
from backend.query.approvals import (
    SCANNER_VALUES,
    STATUS_VALUES,
    ApprovalFilters,
    build_approvals_body,
    shape_facets,
)

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])
log = structlog.get_logger()

CanTriage = Annotated[Principal, Depends(require_capability("can_triage"))]
Authenticated = Annotated[Principal, Depends(get_current_principal)]


# the types whose projection is state=risk_accepted (decisions/projection.py)
ACCEPT_TYPES = frozenset({"risk_accepted", "ignore_rule"})


def _require_accept_final(principal: Principal, reason: str) -> None:
    if not holds_accept_final(principal):
        raise accept_final_refusal(f"{reason} requires can_accept_audit_final")


class DecisionEditRequest(BaseModel):
    """The editable payload fields — anything set becomes the revoke+create pair's change set."""

    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    cve_id: str | None = None
    scope: dict[str, Any] | None = None
    apply_both_scanners: bool | None = None
    scanner: str | None = None
    vex_justification: str | None = None
    justification: str | None = Field(default=None, min_length=1, max_length=10_000)
    expiry: str | None = None


@router.post("", status_code=201)
async def create(
    request: Request, payload: DecisionPayload, principal: CanTriage
) -> dict[str, Any]:
    if payload.type in ACCEPT_TYPES:
        _require_accept_final(principal, f"a {payload.type} decision")  # SEC-2
    client = cast(Any, request.app.state.opensearch)
    doc = await create_decision(client, actor=principal.user_id, payload=payload)
    return {"decision": doc}


@router.post("/{decision_id}/revoke")
async def revoke(request: Request, decision_id: str, principal: CanTriage) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    try:
        old = (await client.get(index=DECISIONS_INDEX, id=decision_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "decision not found") from None
    if old["type"] in ACCEPT_TYPES:
        _require_accept_final(principal, f"revoking a {old['type']} decision")
    try:
        doc = await revoke_decision(client, actor=principal.user_id, decision_id=decision_id)
    except NotFoundError:
        raise HTTPException(404, "decision not found") from None
    except ValueError as exc:  # already revoked
        raise HTTPException(409, str(exc)) from exc
    return {"decision": doc}


@router.patch("/{decision_id}")
async def edit(
    request: Request, decision_id: str, body: DecisionEditRequest, principal: CanTriage
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "empty edit — set at least one field")
    client = cast(Any, request.app.state.opensearch)
    try:
        old = (await client.get(index=DECISIONS_INDEX, id=decision_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "decision not found") from None
    if old["type"] in ACCEPT_TYPES:  # an edit is revoke + create: an undo of the old one
        _require_accept_final(principal, f"editing a {old['type']} decision")
    new_type = changes.get("type", old["type"])
    if new_type in ACCEPT_TYPES:  # an edit can't smuggle one in
        _require_accept_final(principal, f"a {new_type} decision")
    try:
        revoked, new = await edit_decision(
            client, actor=principal.user_id, decision_id=decision_id, changes=changes
        )
    except ValueError as exc:
        # "already revoked" = state conflict; anything else = a bad change set
        status = 409 if "revoked" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    return {"revoked": revoked, "decision": new}


def _approval_lens(
    q: Annotated[str | None, Query(min_length=2, max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=16)] = None,
    created_by: Annotated[str | None, Query(max_length=128)] = None,
    scanner: Annotated[str | None, Query(max_length=8)] = None,
    exclude_status: Annotated[str | None, Query(max_length=16)] = None,
    exclude_created_by: Annotated[str | None, Query(max_length=128)] = None,
    exclude_scanner: Annotated[str | None, Query(max_length=8)] = None,
) -> ApprovalFilters:
    """The 4b lens, validated once at the edge (the `findings._filters` pattern). The queue read
    and its CSV export (issue 359) share it, so an export can never accept a lens the screen
    would have rejected."""
    for name, value, vocabulary in (
        ("status", status, STATUS_VALUES),
        ("exclude_status", exclude_status, STATUS_VALUES),
        ("scanner", scanner, SCANNER_VALUES),
        ("exclude_scanner", exclude_scanner, SCANNER_VALUES),
    ):
        if value is not None and value not in vocabulary:
            raise HTTPException(422, f"{name} must be one of {vocabulary}")
    # a field is included OR excluded, never both (issue 349) — same 422 as the findings edge,
    # instead of silently ANDing a clause with its own must_not into zero rows
    for name, inc, exc in (
        ("status", status, exclude_status),
        ("created_by", created_by, exclude_created_by),
        ("scanner", scanner, exclude_scanner),
    ):
        if inc is not None and exc is not None:
            raise HTTPException(422, f"{name} and exclude_{name} are mutually exclusive")
    return ApprovalFilters(
        q=q,
        status=status,
        created_by=created_by,
        scanner=scanner,
        exclude_status=exclude_status,
        exclude_created_by=exclude_created_by,
        exclude_scanner=exclude_scanner,
    )


ApprovalLens = Annotated[ApprovalFilters, Depends(_approval_lens)]
AcceptFinal = Annotated[Principal, Depends(require_capability("can_accept_audit_final"))]
WarnDays = Annotated[int, Query(ge=1, le=365)]


@router.get("/approvals")
async def approval_list(
    request: Request,
    principal: AcceptFinal,
    cluster_id: ClusterId,
    filters: ApprovalLens,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    warn_days: WarnDays = 7,
) -> dict[str, Any]:
    """M5d/FR-8: the risk-accept review surface for accept_final holders — ACTIVE risk-accept
    decisions, soonest-expiring first (RULING, #30: creation is already SEC-2-gated, so this is
    a review queue over standing acceptances, not a pending-approval workflow). Slice 4b
    (operator re-ruling on the built 4a screen): the prototype rail's dims served server-side —
    `q` (CVE contains) / `status` (derived from `expiry` at query time against `warn_days`,
    mirroring the FE chip's window) / `created_by` / `scanner` (the column value, both|trivy|
    grype) — plus facet counts under the same lens, one round trip."""
    client = cast(Any, request.app.state.opensearch)
    # no read-side refresh (audit A-m2/#191): decision writes use refresh=true, so read-your-writes
    # holds without forcing a Lucene refresh on every read
    body = build_approvals_body(
        filters,
        cluster_id=cluster_id,
        size=size,
        offset=offset,
        now=datetime.now(UTC),
        warn_days=warn_days,
    )
    resp = await client.search(index=DECISIONS_INDEX, body=body)
    return {
        "approvals": [h["_source"] for h in resp["hits"]["hits"]],
        "total": resp["hits"]["total"]["value"],
        "size": size,
        "offset": offset,
        "facets": shape_facets(resp["aggregations"]),
    }


@router.get("/approvals/export.csv")
async def export_approvals_csv(
    request: Request,
    principal: AcceptFinal,
    cluster_id: ClusterId,
    filters: ApprovalLens,
    warn_days: WarnDays = 7,
) -> StreamingResponse:
    """The queue's Export CSV (issue 359, absorbing #373): the CURRENT lens, streamed.

    Capability-gated like the queue it exports — standing risk-acceptances name who accepted
    what, so the file is exactly as sensitive as the screen and inherits its
    `can_accept_audit_final` gate rather than settling for session auth.

    `now` is read ONCE and passed to both the count and the sweep, so the derived `status`
    column and the `status` filter cannot straddle a tick and disagree.
    """
    client = cast(Any, request.app.state.opensearch)
    now = datetime.now(UTC)
    max_rows = get_settings().export_max_rows
    n = await count_approvals_lens(
        client, cluster_id=cluster_id, filters=filters, now=now, warn_days=warn_days
    )
    if n > max_rows:
        log.warning("inline export capped", cluster_id=cluster_id, cap=max_rows, format="approv")
        LIMIT_REJECTIONS.labels("export_rows").inc()  # M-4 (#220)
        raise HTTPException(
            413,
            f"{n} acceptances exceed the inline export limit ({max_rows}) — narrow the filters",
        )
    try:
        slot = pit_guard.acquire(principal.user_id)
    except pit_guard.PitCapExceeded as exc:
        log.warning("PIT cap reached for principal", format="approvals")
        raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc

    async def body() -> AsyncIterator[str]:
        # M-4 (#220): rows/bytes counted in the same finally that frees the PIT slot — a client
        # that disconnects mid-stream reports what was ACTUALLY streamed
        rows, size = 0, 0
        try:
            async for line in stream_approvals_csv(
                client, cluster_id=cluster_id, filters=filters, now=now, warn_days=warn_days
            ):
                rows += 1
                size += len(line)
                yield line
        finally:
            pit_guard.release(principal.user_id, slot)
            EXPORT_ROWS.labels("approvals_csv").inc(max(0, rows - 1))  # minus the header line
            EXPORT_BYTES.labels("approvals_csv").inc(size)

    stamp = now.strftime("%Y-%m-%d")
    return StreamingResponse(
        body(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="javv-approvals-{stamp}.csv"'},
    )


@router.get("")
async def list_decisions(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    cve_id: Annotated[str | None, Query(max_length=128)] = None,  # A-n: bounded query string
    include_revoked: bool = False,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    filters: list[dict[str, Any]] = [{"term": {"cluster_id": cluster_id}}]
    if cve_id:
        filters.append({"term": {"cve_id": cve_id}})
    if not include_revoked:
        filters.append({"bool": {"must_not": [{"exists": {"field": "revoked_at"}}]}})
    # no read-side refresh (audit A-m2/#191): decision writes use refresh=true (read-your-writes)
    resp = await client.search(
        index=DECISIONS_INDEX,
        body={
            "size": size,
            "from": offset,
            "track_total_hits": True,
            "query": {"bool": {"filter": filters}},
            "sort": [{"effective_at": "desc"}],
        },
    )
    return {
        "decisions": [h["_source"] for h in resp["hits"]["hits"]],
        "total": resp["hits"]["total"]["value"],
        "size": size,
        "offset": offset,
    }
