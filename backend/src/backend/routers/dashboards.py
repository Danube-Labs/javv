"""Saved dashboards (issue 440, slice S4) — `/api/v1/dashboards`, in the `system-dashboards` index.

A dashboard is a layout of panels from the closed catalog (`dashboards/catalog.py`), never data:
each panel reads its own numbers with the permissions of the user who opens it. Who sees one is
the owner's choice (D2): only the owner, everyone, or the roles in a list. A user who cannot see
a dashboard gets 404, as if it did not exist (Q3), on every route. Holders of
`can_manage_settings` (admin's `*` covers it) see each dashboard, because D3 lets them change and
remove each one.

Writes need `can_edit_dashboards`, and a change or a removal of another user's dashboard also
needs `can_manage_settings` (D3, the saved-views rule). The client sends the `revision` it read; a
different stored revision is 409 (D4), and the seq_no CAS still catches two writes at once. Every
write is journaled first (D17/A-M5), the frozen doc riding the row: the audit log is the history,
there is no history index (D4)."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from opensearchpy.exceptions import ConflictError, NotFoundError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from backend.audit.writer import append_field_change
from backend.auth.capabilities import ROLES_INDEX, holds, require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.dashboards.catalog import PANELS, PanelHeight, PanelId

router = APIRouter(prefix="/api/v1/dashboards", tags=["dashboards"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]
CanEdit = Annotated[Principal, Depends(require_capability("can_edit_dashboards"))]

DASHBOARDS_INDEX = "system-dashboards"
DASHBOARD_SCHEMA_VERSION = 1
MAX_PANELS = 24  # ruling Q2: a full dashboard measured 590 ms for its 24 panel reads
MAX_DASHBOARDS = 1_000  # ruling D9: the list ceiling, as for the saved views
_MAX_Y = 1_000  # 24 panels of at most 26 rows each fit with room to spare

_RoleName = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class DashboardPanel(BaseModel):
    """One panel: a catalog ID, its cell, its width in columns and the NAME of its height."""

    model_config = ConfigDict(extra="forbid")

    panel: PanelId
    x: int = Field(ge=0, le=1)
    y: int = Field(ge=0, le=_MAX_Y)
    w: Literal[1, 2]
    h: PanelHeight
    # only on a panel with scanner data; `dashboard` follows the dashboard's switch (ruling Q7)
    scanner: Literal["dashboard", "trivy", "grype"] | None = None

    @model_validator(mode="after")
    def _fits_the_catalog(self) -> "DashboardPanel":
        entry = PANELS[self.panel]
        if self.h not in entry.heights:
            raise ValueError(f"the panel {self.panel} has no {self.h} height")
        if self.x + self.w > 2:
            raise ValueError("a panel must fit in the two columns")
        if not entry.uses_scanner and self.scanner is not None:
            raise ValueError(f"the panel {self.panel} has no scanner data")
        if entry.uses_scanner and self.scanner is None:
            self.scanner = "dashboard"
        return self

    def start_cells(self) -> set[tuple[int, int]]:
        # only the first row: in edit mode a panel is as tall as its content, so the catalog rows
        # are not the rows it fills, and a short panel lets the one under it move up (issue 1045)
        return {(x, self.y) for x in range(self.x, self.x + self.w)}


class DashboardFields(BaseModel):
    """Everything an owner sets. A create is this model; a change is merged onto the stored
    dashboard and checked again by this model, so a change can never store what a create can't.
    The one exception: a change that sends no panels keeps the stored ones unchecked."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1024)
    scanner: Literal["all", "trivy", "grype"] = "all"  # the switch the dashboard opens with
    panels: list[DashboardPanel] = Field(default_factory=list, max_length=MAX_PANELS)
    sharing: Literal["private", "everyone", "roles"] = "private"
    roles: list[_RoleName] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def _consistent(self) -> "DashboardFields":
        if (self.sharing == "roles") != bool(self.roles):
            raise ValueError("roles go with sharing 'roles', and sharing 'roles' needs a role")
        taken: set[tuple[int, int]] = set()
        for panel in self.panels:
            cells = panel.start_cells()
            if taken & cells:
                raise ValueError(f"the panel {panel.panel} at ({panel.x}, {panel.y}) overlaps")
            taken |= cells
        return self

    def stored(self) -> dict[str, Any]:
        return {
            **self.model_dump(exclude={"panels"}),
            "panels": [p.model_dump(exclude_none=True) for p in self.panels],
        }


class UpdateDashboard(BaseModel):
    """A change: the revision the user read, and the fields to change. `owner` and the audit
    fields are not fields here, so a write of them is unrepresentable (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    scanner: Literal["all", "trivy", "grype"] | None = None
    panels: list[DashboardPanel] | None = Field(default=None, max_length=MAX_PANELS)
    sharing: Literal["private", "everyone", "roles"] | None = None
    roles: list[_RoleName] | None = Field(default=None, max_length=32)


async def unknown_role_errors(
    client: Any, roles: list[str], loc: tuple[str, ...]
) -> list[dict[str, Any]]:
    """A field error for each name in `roles` that no `system-roles` bundle has: sharing with it
    would share with nobody (ruling of 2026-10-26, issue 440). The place and the reason, never the
    name (issue 842)."""
    if not roles:
        return []
    resp = await client.mget(index=ROLES_INDEX, body={"ids": sorted(set(roles))})
    known = {d["_id"] for d in resp["docs"] if d.get("found")}
    return [
        {"loc": (*loc, i), "msg": "no role has this name", "type": "unknown_role"}
        for i, role in enumerate(roles)
        if role not in known
    ]


def _sees_all(principal: Principal) -> bool:
    return holds(principal, "can_manage_settings")


def _may_see(principal: Principal, doc: dict[str, Any]) -> bool:
    return (
        _sees_all(principal)
        or doc["owner"] == principal.user_id
        or doc["sharing"] == "everyone"
        or (doc["sharing"] == "roles" and principal.role in doc["roles"])
    )


async def _visible_or_404(
    client: Any, principal: Principal, dashboard_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(doc, CAS params). Not found and not visible are the same 404 (ruling Q3)."""
    try:
        got = await client.get(index=DASHBOARDS_INDEX, id=dashboard_id)
    except NotFoundError as exc:
        raise HTTPException(404, "dashboard not found") from exc
    doc = got["_source"]
    if not _may_see(principal, doc):
        raise HTTPException(404, "dashboard not found")
    return doc, {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}


def _check_write(principal: Principal, doc: dict[str, Any], revision: int) -> None:
    if doc["owner"] != principal.user_id and not _sees_all(principal):
        raise HTTPException(403, "only the owner or an admin may change a dashboard")
    if doc["revision"] != revision:
        raise HTTPException(409, "the dashboard changed since you read it — reload and retry")


def visibility_query(principal: Principal) -> dict[str, Any]:
    if _sees_all(principal):
        return {"match_all": {}}
    should: list[dict[str, Any]] = [
        {"term": {"owner": principal.user_id}},
        {"term": {"sharing": "everyone"}},
    ]
    if principal.role:
        should.append(
            {
                "bool": {
                    "filter": [{"term": {"sharing": "roles"}}, {"term": {"roles": principal.role}}]
                }
            }
        )
    return {"bool": {"should": should, "minimum_should_match": 1}}


@router.get("")
async def list_dashboards(request: Request, principal: Authenticated) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    resp = await client.search(
        index=DASHBOARDS_INDEX,
        body={
            "query": visibility_query(principal),
            "size": MAX_DASHBOARDS,
            "sort": [{"name": "asc"}, {"dashboard_id": "asc"}],
        },
        params={"ignore_unavailable": "true"},
    )
    return {"dashboards": [h["_source"] for h in resp["hits"]["hits"]]}


@router.get("/roles")
async def list_sharing_roles(request: Request, principal: CanEdit) -> dict[str, list[str]]:
    """The roles an owner can share a dashboard with (D2): the names of the `system-roles` bundles,
    so a later 5th role appears without a client change. The capabilities of each bundle stay
    behind `can_manage_users` (`/api/v1/admin/roles`); an owner who is not an admin needs only the
    names (ruling of 2026-10-26, issue 440). Declared before `/{dashboard_id}`, which would take
    `roles` as an id."""
    client = cast(Any, request.app.state.opensearch)
    hits = await client.search(
        index=ROLES_INDEX,
        body={"size": 100, "sort": [{"_id": "asc"}], "_source": False, "query": {"match_all": {}}},
    )
    return {"roles": [h["_id"] for h in hits["hits"]["hits"]]}


@router.get("/{dashboard_id}")
async def get_dashboard(
    request: Request,
    dashboard_id: Annotated[str, Path(max_length=64)],
    principal: Authenticated,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    doc, _ = await _visible_or_404(client, principal, dashboard_id)
    return doc


async def create_doc(
    client: Any, principal: Principal, fields: DashboardFields, dashboard_id: str
) -> dict[str, Any]:
    """A new dashboard of `principal`, journaled first. An existing `dashboard_id` is a
    ConflictError from the store, after its audit row."""
    now = datetime.now(UTC).isoformat()
    doc = {
        "dashboard_id": dashboard_id,
        **fields.stored(),
        "owner": principal.user_id,  # immutable: no change route takes it
        "created_by": principal.username,
        "created_at": now,
        "updated_by": principal.username,
        "updated_at": now,
        "revision": 1,
        "schema_version": DASHBOARD_SCHEMA_VERSION,
    }
    # a dashboard holds no cluster (the cluster picker applies at read time, D8): a fleet-wide row
    await append_field_change(
        client,
        actor=principal.user_id,
        action="dashboard_create",
        entity_type="dashboard",
        entity_id=dashboard_id,
        field="dashboard",
        old_value=None,
        new_value=fields.name,
        new_value_json=doc,
        revision=1,
        cluster_id=None,
    )
    await client.index(
        index=DASHBOARDS_INDEX,
        id=dashboard_id,
        body=doc,
        params={"op_type": "create", "refresh": "true"},
    )
    return doc


@router.post("", status_code=201)
async def create_dashboard(
    request: Request, body: DashboardFields, principal: CanEdit
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if errors := await unknown_role_errors(client, body.roles, ("body", "roles")):
        raise RequestValidationError(errors)
    return await create_doc(client, principal, body, uuid4().hex)


@router.patch("/{dashboard_id}")
async def update_dashboard(
    request: Request,
    dashboard_id: Annotated[str, Path(max_length=64)],
    body: UpdateDashboard,
    principal: CanEdit,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    doc, cas = await _visible_or_404(client, principal, dashboard_id)
    _check_write(principal, doc, body.revision)
    current = {k: doc[k] for k in DashboardFields.model_fields}
    change = body.model_dump(exclude_unset=True, exclude={"revision"}, exclude_none=True)
    # The stored panels are checked only when the change sends panels: a new measurement of the
    # heights must not refuse a change of the name to a dashboard it made overlap (ruling of
    # 2026-10-25).
    keep_panels = "panels" not in change
    try:
        fields = DashboardFields.model_validate(
            {**current, **change, **({"panels": []} if keep_panels else {})}
        )
    except ValidationError as exc:
        # the same 422 as a field check of the body itself, so the value is not sent back
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]
        ) from exc
    # only the roles the change sends: as with the panels, a change of the name keeps what is stored
    if errors := await unknown_role_errors(client, change.get("roles", []), ("body", "roles")):
        raise RequestValidationError(errors)
    stored = fields.stored()
    if keep_panels:
        stored["panels"] = doc["panels"]
    updated = {
        **doc,
        **stored,
        "updated_by": principal.username,
        "updated_at": datetime.now(UTC).isoformat(),
        "revision": doc["revision"] + 1,
    }
    await append_field_change(
        client,
        actor=principal.user_id,
        action="dashboard_update",
        entity_type="dashboard",
        entity_id=dashboard_id,
        field="dashboard",
        old_value=doc["name"],
        new_value=updated["name"],
        old_value_json=doc,
        new_value_json=updated,
        revision=updated["revision"],
        cluster_id=None,
    )
    try:
        await client.index(
            index=DASHBOARDS_INDEX,
            id=dashboard_id,
            body=updated,
            params={"refresh": "true", **cas},
        )
    except ConflictError as exc:
        raise HTTPException(
            409, "the dashboard changed since you read it — reload and retry"
        ) from exc
    return updated


@router.delete("/{dashboard_id}", status_code=204)
async def delete_dashboard(
    request: Request,
    dashboard_id: Annotated[str, Path(max_length=64)],
    revision: Annotated[int, Query(ge=1)],
    principal: CanEdit,
) -> None:
    client = cast(Any, request.app.state.opensearch)
    doc, cas = await _visible_or_404(client, principal, dashboard_id)
    _check_write(principal, doc, revision)
    await append_field_change(
        client,
        actor=principal.user_id,
        action="dashboard_delete",
        entity_type="dashboard",
        entity_id=dashboard_id,
        field="dashboard",
        old_value=doc["name"],
        new_value=None,
        old_value_json=doc,
        revision=doc["revision"],
        cluster_id=None,
    )
    try:
        await client.delete(
            index=DASHBOARDS_INDEX, id=dashboard_id, params={"refresh": "true", **cas}
        )
    except ConflictError as exc:
        raise HTTPException(
            409, "the dashboard changed since you read it — reload and retry"
        ) from exc
    except NotFoundError as exc:  # removed between our read and now: the outcome stands
        raise HTTPException(404, "dashboard not found") from exc
