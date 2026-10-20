"""Server-side saved views (M8e/C-6, #242) — `GET/POST /api/v1/views` (slice 1).

Durable, shareable filter views in the new `system-views` index: a view is a tiny serialized
**preset** (the `SearchFilters` mirror — same field set as the grid and queued exports, drift
fails the mirror test) plus display metadata. Views are visible to **all** authenticated users
(the C-6 ruling; per-view ACLs are post-MVP); card counts stay server aggregations
(`/findings/facets` at render time — a view never stores a number).

Presets are validated at the edge against the CLOSED vocabularies (`extra="forbid"`): lowercase
canonical severities incl. `negligible`, the 6 triage states, the two scanners, the M8d ptype
shape. Garbage is 422 and never stored — a preset outlives UI versions, so only vocabulary the
server owns goes in. `q` (DATA_MODEL sketch) is deliberately absent: there is no server text
query (the tenant read path refuses `q=`, SEC-4) and the §6 deep-link contract is query-params-only.

Every mutation is journaled **journal-first** (D17/A-M5): the audit row lands before the doc
write, so a journal failure leaves no applied-but-unjournaled change. `owner` = the creating
principal, immutable (`extra="forbid"` on the patch body makes an owner write unrepresentable).
PATCH/DELETE are **owner-or-admin** (slice 2): the owner, or a principal holding
`can_manage_settings` (admin's `*` covers it) — anyone else is the 403 IDOR case. The PATCH is a
seq_no-CAS whole-doc update (409 on a concurrent edit — reload and retry, never a silent
overwrite)."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from opensearchpy.exceptions import ConflictError, NotFoundError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.audit.writer import append_field_change
from backend.auth.principal import Principal, get_current_principal
from backend.models.envelope import SEVERITY_RANK
from backend.query.search import (
    MAX_FILTER_VALUES,
    FilterValue128,
    FilterValue256,
    FilterValue512,
)
from backend.triage.state_machine import STATES

router = APIRouter(prefix="/api/v1/views", tags=["views"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

VIEWS_INDEX = "system-views"
VIEW_SCHEMA_VERSION = 2  # v2 (M9f slice 4): + `workbench` (columns/density/sort/window capture)
_MAX_VIEWS = 1_000  # list ceiling; a fleet has dozens of views, not thousands


# a package type as a stored preset holds it: lowercase, the same check the field had as one string
_PtypeValue = Annotated[str, StringConstraints(max_length=64, pattern=r"^[a-z0-9][a-z0-9+._-]*$")]


class ViewPreset(BaseModel):
    """The stored filter lens — MIRRORS `SearchFilters` one-to-one (drift fails the mirror
    test). Closed vocabularies validated here; free-string fields keep the route caps."""

    model_config = ConfigDict(extra="forbid")

    severity: list[str] | None = Field(default=None, max_length=16)
    state: list[str] | None = Field(default=None, max_length=16)
    scanner: Literal["trivy", "grype"] | None = None
    assignee: list[FilterValue128] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    kev: bool | None = None
    fixable: bool | None = None
    disagree: bool | None = None
    cve_id: list[FilterValue128] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    image_digest: str | None = Field(default=None, max_length=128)
    image_repo: list[FilterValue512] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    namespace: list[FilterValue256] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    ptype: list[_PtypeValue] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    package_name: list[FilterValue512] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    q: str | None = Field(default=None, min_length=2, max_length=128)
    present: bool = True
    new_within_days: int | None = Field(default=None, ge=1, le=365)
    unassigned: bool | None = None
    overdue: bool | None = None
    exclude_severity: list[str] | None = Field(default=None, max_length=16)
    exclude_state: list[str] | None = Field(default=None, max_length=16)
    exclude_scanner: Literal["trivy", "grype"] | None = None
    exclude_assignee: list[FilterValue128] | None = Field(
        default=None, max_length=MAX_FILTER_VALUES
    )
    exclude_image_repo: list[FilterValue512] | None = Field(
        default=None, max_length=MAX_FILTER_VALUES
    )
    exclude_namespace: list[FilterValue256] | None = Field(
        default=None, max_length=MAX_FILTER_VALUES
    )
    exclude_ptype: list[_PtypeValue] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    exclude_cve_id: list[FilterValue128] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    exclude_package_name: list[FilterValue512] | None = Field(
        default=None, max_length=MAX_FILTER_VALUES
    )

    @field_validator("severity", "exclude_severity")
    @classmethod
    def _severities_canonical(cls, v: list[str] | None) -> list[str] | None:
        # LOWERCASE canonical buckets incl. negligible (A-1) — presets outlive UI versions,
        # so only the server-owned vocabulary is storable
        if v is not None and (bad := [s for s in v if s not in SEVERITY_RANK]):
            raise ValueError(f"severity must be canonical {sorted(SEVERITY_RANK)}: {bad}")
        return v

    @field_validator("state", "exclude_state")
    @classmethod
    def _states_closed(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and (bad := [s for s in v if s not in STATES]):
            raise ValueError(f"state must be one of {sorted(STATES)}: {bad}")
        return v

    @model_validator(mode="after")
    def _no_mixing(self) -> "ViewPreset":
        # a stored preset must satisfy the same rule the live route enforces (issue 349)
        names = ("severity", "state", "scanner", "assignee", "image_repo", "namespace", "ptype")
        for name in names:
            if getattr(self, name) is not None and getattr(self, f"exclude_{name}") is not None:
                raise ValueError(f"{name} and exclude_{name} are mutually exclusive")
        return self


class ViewWorkbench(BaseModel):
    """The findings-workbench capture (schema v2): everything beyond the lens needed to
    reproduce the operator's table. Cluster-agnostic BY SHAPE — no cluster_id, no absolute
    `t` (a deep link carries `?cluster=` separately); the time range is the relative window."""

    model_config = ConfigDict(extra="forbid")

    columns: list[str] | None = Field(default=None, max_length=32)  # visible keys, in order
    dense: bool | None = None
    sort: Literal["severity_rank", "first_seen_at", "last_scan_at", "cvss", "epss"] | None = None
    order: Literal["asc", "desc"] | None = None
    window_days: float | None = Field(default=None, gt=0, le=365)


class CreateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1024)
    preset: ViewPreset = ViewPreset()
    workbench: ViewWorkbench = ViewWorkbench()


class UpdateView(BaseModel):
    """Partial update — unset fields keep their stored value. `owner`/`view_id` are not fields
    here, so a rename-the-owner write is UNREPRESENTABLE (extra=forbid), not just forbidden."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    preset: ViewPreset | None = None
    workbench: ViewWorkbench | None = None


def _may_mutate(principal: Principal, doc: dict[str, Any]) -> bool:
    """Owner-or-admin (C-6): the owner, or `can_manage_settings` (admin's `*` covers it)."""
    caps = principal.capabilities
    return principal.user_id == doc["owner"] or "*" in caps or "can_manage_settings" in caps


async def _get_or_404(client: Any, view_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(doc, CAS params) — the seq_no pair guards the RMW (D40 rule: 409, never last-write-wins)."""
    try:
        got = await client.get(index=VIEWS_INDEX, id=view_id)
    except NotFoundError as exc:
        raise HTTPException(404, "view not found") from exc
    return got["_source"], {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}


@router.get("")
async def list_views(request: Request, principal: Authenticated) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    resp = await client.search(
        index=VIEWS_INDEX,
        body={
            "query": {"match_all": {}},
            "size": _MAX_VIEWS,
            "sort": [{"name": "asc"}, {"view_id": "asc"}],  # deterministic for the UI/tests
        },
        params={"ignore_unavailable": "true"},
    )
    return {"views": [h["_source"] for h in resp["hits"]["hits"]]}


@router.post("", status_code=201)
async def create_view(
    request: Request, body: CreateView, principal: Authenticated
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    view_id = uuid4().hex
    now = datetime.now(UTC).isoformat()
    doc = {
        "view_id": view_id,
        "name": body.name,
        "description": body.description,
        "preset": body.preset.model_dump(),
        "workbench": body.workbench.model_dump(),
        "owner": principal.user_id,  # immutable after create (slice 2 enforces on PATCH)
        "created_at": now,
        "updated_at": now,
        "schema_version": VIEW_SCHEMA_VERSION,
    }
    # journal-first (D17/A-M5): the row lands before the view write — a journal failure leaves
    # no applied-but-unjournaled view; a retry re-drives both. Views are fleet-global (a preset
    # carries no cluster_id — the cluster is chosen at query time), hence the fleet-wide row.
    await append_field_change(
        client,
        actor=principal.user_id,
        action="view_create",
        entity_type="view",
        entity_id=view_id,
        field="view",
        old_value=None,
        new_value=body.name,
        new_value_json=doc,
        revision=1,
        cluster_id=None,  # fleet-wide: no cluster_id, the class the Audit screen shows (issue 559)
    )
    await client.index(
        index=VIEWS_INDEX,
        id=view_id,
        body=doc,
        params={"op_type": "create", "refresh": "true"},  # fresh uuid — a collision is a bug
    )
    return doc


@router.patch("/{view_id}")
async def update_view(
    request: Request,
    view_id: Annotated[str, Path(max_length=64)],
    body: UpdateView,
    principal: Authenticated,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    doc, cas = await _get_or_404(client, view_id)
    if not _may_mutate(principal, doc):
        raise HTTPException(403, "only the owner or an admin may edit a view")  # the IDOR case
    updated = {
        **doc,
        **{k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None},
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if body.preset is not None:
        updated["preset"] = body.preset.model_dump()  # whole-preset replace, re-validated shape
    if body.workbench is not None:
        updated["workbench"] = body.workbench.model_dump()  # same rule — whole-blob replace
    # journal-first (D17/A-M5), with the frozen before/after for causal replay
    await append_field_change(
        client,
        actor=principal.user_id,
        action="view_update",
        entity_type="view",
        entity_id=view_id,
        field="view",
        old_value=doc["name"],
        new_value=updated["name"],
        old_value_json=doc,
        new_value_json=updated,
        revision=1,
        cluster_id=None,  # fleet-wide: no cluster_id, the class the Audit screen shows (issue 559)
    )
    try:
        await client.index(
            index=VIEWS_INDEX,
            id=view_id,
            body=updated,
            params={"refresh": "true", **cas},  # seq_no CAS — concurrent edit = 409, not a
        )  # silent overwrite (the D40 guarded-RMW rule; the client reloads and retries)
    except ConflictError as exc:
        raise HTTPException(409, "view changed concurrently — reload and retry") from exc
    return updated


@router.delete("/{view_id}", status_code=204)
async def delete_view(
    request: Request,
    view_id: Annotated[str, Path(max_length=64)],
    principal: Authenticated,
) -> None:
    client = cast(Any, request.app.state.opensearch)
    doc, cas = await _get_or_404(client, view_id)
    if not _may_mutate(principal, doc):
        raise HTTPException(403, "only the owner or an admin may delete a view")  # the IDOR case
    # journal-first (D17/A-M5) — the frozen doc rides the row, so a deleted view stays auditable
    await append_field_change(
        client,
        actor=principal.user_id,
        action="view_delete",
        entity_type="view",
        entity_id=view_id,
        field="view",
        old_value=doc["name"],
        new_value=None,
        old_value_json=doc,
        revision=1,
        cluster_id=None,  # fleet-wide: no cluster_id, the class the Audit screen shows (issue 559)
    )
    try:
        await client.delete(index=VIEWS_INDEX, id=view_id, params={"refresh": "true", **cas})
    except ConflictError as exc:
        raise HTTPException(409, "view changed concurrently — reload and retry") from exc
    except NotFoundError as exc:  # deleted between our read and now — the outcome stands
        raise HTTPException(404, "view not found") from exc
