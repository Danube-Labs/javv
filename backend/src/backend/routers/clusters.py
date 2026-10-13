"""Cluster registry (M8c slice 2, #240 — the D-5 ruling): `GET /api/v1/clusters` + the rename.

One *document* in the existing `system-config` (`_id = "cluster-registry"`), not a new index:
`{cluster_id → cluster_name}`. `cluster_name` is DISPLAY-ONLY — never a query key, never in an
index name, never a filter (hard constraint; `cluster_id` is the immutable tenant key). The
listing is cross-cluster BY DESIGN (MVP tenant model D38/H9: all clusters visible to any
authenticated user): known clusters = the distinct `cluster_id`s that ever minted a token (the
onboarding requirement — a cluster cannot push without one) ∪ registry entries ∪ retirement
records (a cluster whose delete stopped halfway has only that left); unnamed clusters default
`cluster_name = cluster_id`.

Rename = `can_manage_settings` (admin), journal-FIRST per D17/#188 (the audit row lands before
the registry write — a journal failure leaves no applied-but-unjournaled rename), mirroring the
SLA settings write.

Retire and un-retire (issue 765, `admin/cluster_retirement.py`) are `can_manage_settings` too: a
retired cluster leaves the default listing and keeps its data. Deleting a retired cluster
(`admin/cluster_delete.py`) is `can_manage_retention`, the capability of every other setting
that deletes data."""

from datetime import datetime
from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import TransportError
from pydantic import BaseModel, ConfigDict, Field

from backend.admin.cluster_delete import (
    DeleteIncomplete,
    NotRetired,
    delete_cluster,
    deletes_started,
)
from backend.admin.cluster_registry import read_registry, set_registry_name
from backend.admin.cluster_retirement import (
    DeleteUnderway,
    Retirement,
    read_retirements,
    retire_cluster,
    unretire_cluster,
)
from backend.audit.writer import append_field_change
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.core.errors import delete_unfinished
from backend.core.identifiers import CLUSTER_ID_RE
from backend.core.metrics import CLUSTER_DELETE_INCOMPLETE
from backend.jobs.cluster_retirement import (
    TokenActivity,
    is_retired,
    read_schedules,
    returned_at,
    token_activity,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/clusters", tags=["clusters"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]
ManageSettings = Annotated[Principal, Depends(require_capability("can_manage_settings"))]
ManageRetention = Annotated[Principal, Depends(require_capability("can_manage_retention"))]
ClusterIdPath = Annotated[str, Path(pattern=CLUSTER_ID_RE.pattern)]


class RenameCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_name: str = Field(min_length=1, max_length=128)


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at is not None else None


async def _fleet(
    client: AsyncOpenSearch,
) -> tuple[dict[str, str], dict[str, TokenActivity], dict[str, Retirement], set[str], set[str]]:
    """(names, token activity, retirement records, every known cluster, the retired ones). A
    retirement that a newer scan has outlived already reads as not retired; the sweep journals the
    return."""
    names = await read_registry(client)
    activity = await token_activity(client)
    retirements = await read_retirements(client)
    # a retirement record alone still names a cluster: a delete that stopped halfway removed its
    # tokens and its name, and a retry must still find it
    known = set(activity) | set(names) | set(retirements)
    retired = {
        cid
        for cid, r in retirements.items()
        if is_retired(r, activity[cid].last_scan_at if cid in activity else None)
    }
    return names, activity, retirements, known, retired


@router.get("")
async def list_clusters(
    request: Request,
    principal: Authenticated,
    include_retired: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """Retired clusters (issue 765) are left out unless asked for: the switcher and All clusters
    both read this list, so leaving one out here is what takes it off them. Each row carries the
    newest accepted scan (`last_scan_at`) and its retirement schedule for the warning banner:
    `silent_since` is where the countdown starts (the newest scan, else the first token's mint,
    or the return from retirement if later), then `warns_at` and `retires_at` (null = never)."""
    client = cast(Any, request.app.state.opensearch)
    names, activity, retirements, known, retired = await _fleet(client)
    shown = sorted(cid for cid in known if include_retired or cid not in retired)
    schedules = await read_schedules(client, activity, shown, returned=returned_at(retirements))
    deleting = await deletes_started(client)
    return {
        "clusters": [
            {
                "cluster_id": cid,
                "cluster_name": names.get(cid, cid),
                "retired": cid in retired,
                "last_scan_at": _iso(activity[cid].last_scan_at if cid in activity else None),
                "silent_since": _iso(schedules[cid].silent_since),
                "warns_at": _iso(schedules[cid].warns_at),
                "retires_at": _iso(schedules[cid].retires_at),
                "delete_started": cid in deleting,
                # a manual retire revoked the tokens, so bringing it back needs a new one
                "retirement_mode": retirements[cid].mode if cid in retired else None,
            }
            for cid in shown
        ]
    }


async def _require_known(client: AsyncOpenSearch, cluster_id: str) -> set[str]:
    """404 for a cluster JAVV has never seen; else the retired set."""
    _, _, _, known, retired = await _fleet(client)
    if cluster_id not in known:
        raise HTTPException(404, "cluster not found")
    return retired


@router.post("/{cluster_id}/retire")
async def retire(
    request: Request, cluster_id: ClusterIdPath, principal: ManageSettings
) -> dict[str, Any]:
    """Manual retire: off the list, tokens revoked, data kept (issue 765)."""
    client = cast(Any, request.app.state.opensearch)
    if cluster_id in await _require_known(client, cluster_id):
        raise HTTPException(409, "cluster is already retired")
    retirement = await retire_cluster(client, cluster_id, actor=principal.user_id, mode="manual")
    return {"cluster_id": cluster_id, "retired": True, **retirement.model_dump(mode="json")}


@router.post("/{cluster_id}/unretire")
async def unretire(
    request: Request, cluster_id: ClusterIdPath, principal: ManageSettings
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if cluster_id not in await _require_known(client, cluster_id):
        raise HTTPException(409, "cluster is not retired")
    try:
        brought = await unretire_cluster(client, cluster_id, actor=principal.user_id)
    except DeleteUnderway:
        # its tokens and part of its data are gone: bringing it back would list a broken cluster
        raise delete_unfinished() from None
    if not brought:
        raise HTTPException(409, "cluster is not retired")  # a concurrent write got there first
    return {"cluster_id": cluster_id, "retired": False}


@router.delete("/{cluster_id}")
async def delete_retired_cluster(
    request: Request, cluster_id: ClusterIdPath, principal: ManageRetention
) -> dict[str, Any]:
    """Delete everything JAVV holds for a retired cluster but its audit rows (issue 765,
    `admin/cluster_delete.py`). It must be retired first. A delete that could not finish, a step
    contended or the store away or overloaded, answers 503, and a retry finishes it: every step
    can be re-run, the retirement record goes after the data and the delete's own marker last."""
    client = cast(Any, request.app.state.opensearch)
    if cluster_id not in await _require_known(client, cluster_id):
        raise HTTPException(409, "retire the cluster before deleting it")
    try:
        counts = await delete_cluster(client, cluster_id, actor=principal.user_id)
    except NotRetired:
        raise HTTPException(409, "cluster is not retired") from None  # brought back first
    except (DeleteIncomplete, TransportError) as exc:
        if isinstance(exc, TransportError) and not _retryable(exc):
            raise
        CLUSTER_DELETE_INCOMPLETE.inc()
        log.warning("cluster delete incomplete", cluster_id=cluster_id, error=str(exc))
        raise HTTPException(503, "the delete did not finish, retry it") from exc
    return {"cluster_id": cluster_id, "deleted": counts}


def _retryable(exc: TransportError) -> bool:
    """The store away, timed out or pushing back; a 4xx is a bug and stays a 500."""
    return isinstance(exc, OSConnectionError) or exc.status_code in (429, 500, 502, 503, 504)


@router.put("/{cluster_id}/name")
async def rename_cluster(
    request: Request,
    cluster_id: ClusterIdPath,
    body: RenameCluster,
    principal: ManageSettings,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    # journal-first (D17, audit #188): the row lands before the registry write, so an audit
    # failure leaves NO applied-but-unjournaled rename — a retry re-drives both.
    await append_field_change(
        client,
        actor=principal.user_id,
        action="cluster_rename",
        entity_type="config",
        entity_id=f"cluster:{cluster_id}",
        field="cluster_name",
        old_value=(await read_registry(client)).get(cluster_id),
        new_value=body.cluster_name,
        revision=1,
        cluster_id=cluster_id,
    )
    if await set_registry_name(client, cluster_id, body.cluster_name, actor=principal.user_id):
        return {"cluster_id": cluster_id, "cluster_name": body.cluster_name}
    raise HTTPException(503, "cluster registry contended — retry")  # journaled; retry re-drives
