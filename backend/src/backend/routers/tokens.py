"""Token admin API (M5a slice 6, D38/M14) — the capability-gated (`can_manage_tokens`) surface
over the EXISTING ingest-token machinery (`core/security.py` crypto, SEC-3 binding at ingest);
one token path only, the CLI (`core/tokens.py`) stays for bootstrap use. The raw token appears
exactly once — in the mint/rotate response — and is never recoverable. Revoke = `disabled:true`
(the ingest 401s on its next push); rotate = mint-new + disable-old in that order (a rotation
never leaves the scanner with zero valid tokens; the staleness sweep already dedupes rotated
tokens per audit M-2). Every mutation is journaled (D17). Registered in the standing RBAC/IDOR
suite (`tests/security/test_rbac_idor_contract.py`)."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from opensearchpy import NotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.admin.cluster_delete import clear_for_onboarding, deletes_started
from backend.audit.writer import append_auth_event
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.core.errors import delete_unfinished
from backend.core.identifiers import ClusterId
from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings

router = APIRouter(prefix="/api/v1/admin/tokens", tags=["token-admin"])

TOKENS_INDEX = "system-tokens"
_PUBLIC_FIELDS = (  # never token_hash — the hash never leaves the server either
    "cluster_id",
    "scanner",
    "scope",
    "created_by",
    "created_at",
    "expiry",
    "disabled",
    "last_ingest_at",
)

ManageTokens = Annotated[Principal, Depends(require_capability("can_manage_tokens"))]


class MintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: ClusterId  # the ONE shared shape (task E / audit M2)
    scanner: str = Field(pattern="^(trivy|grype)$")  # per-scanner is sacred — no other value
    # optional expiry (task E m-7): enforced at ingest since the M3 audit — now settable too
    expiry: datetime | None = None

    @field_validator("expiry")
    @classmethod
    def _expiry_in_the_future(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        aware = v if v.tzinfo is not None else v.replace(tzinfo=UTC)
        if aware <= datetime.now(UTC):
            raise ValueError("expiry must be in the future")
        return aware


def _os(request: Request) -> Any:
    return cast(Any, request.app.state.opensearch)


def _public(token_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    return {"id": token_id, **{k: doc.get(k) for k in _PUBLIC_FIELDS}}


async def _write_token(
    client: Any,
    *,
    token_id: str,
    cluster_id: str,
    scanner: str,
    created_by: str,
    expiry: str | None = None,
) -> str:
    """Write a token doc under a caller-supplied id (so the id can be journaled BEFORE the write,
    audit #188); returns the RAW token — the raw value's only server-side moment."""
    raw = mint_token()
    doc = {
        "token_hash": hash_token(raw, pepper=get_settings().secret_key),
        "cluster_id": cluster_id,
        "scanner": scanner,
        "scope": "push:findings",
        "created_by": created_by,
        "created_at": datetime.now(UTC).isoformat(),
        "expiry": expiry,
        "disabled": False,
    }
    await client.index(
        index=TOKENS_INDEX, id=token_id, body=doc, params={"op_type": "create", "refresh": "true"}
    )
    return raw


@router.get("")
async def list_tokens(
    request: Request,
    principal: ManageTokens,
    cluster_id: str | None = None,
    size: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0, le=9000)] = 0,
) -> dict[str, Any]:
    # explicit from/size pagination (task E / audit L1) — fine under 10k (day-one rule);
    # an admin token inventory beyond that is not a realistic MVP shape
    filters: list[dict[str, Any]] = []
    if cluster_id:
        filters.append({"term": {"cluster_id": cluster_id}})
    hits = await _os(request).search(
        index=TOKENS_INDEX,
        body={
            "size": size,
            "from": offset,
            "track_total_hits": True,
            "sort": [{"created_at": "desc"}],
            "query": {"bool": {"filter": filters}},
        },
    )
    return {
        "tokens": [_public(h["_id"], h["_source"]) for h in hits["hits"]["hits"]],
        "total": hits["hits"]["total"]["value"],
    }


@router.post("", status_code=201)
async def mint(request: Request, body: MintRequest, principal: ManageTokens) -> dict[str, Any]:
    client = _os(request)
    if body.cluster_id in await deletes_started(client):
        raise delete_unfinished()
    token_id = uuid4().hex
    # journal-first (D17, audit #188): strict append before the token exists — an audit failure
    # 500s without a live-but-unjournaled token; a retry mints a fresh id and re-drives both.
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="token_mint",
        entity_type="token",
        entity_id=token_id,
        cluster_id=body.cluster_id,
        strict=True,
    )
    if not await clear_for_onboarding(client, body.cluster_id):  # a delete started since the check
        raise delete_unfinished()
    raw = await _write_token(
        client,
        token_id=token_id,
        cluster_id=body.cluster_id,
        scanner=body.scanner,
        created_by=principal.user_id,
        expiry=body.expiry.isoformat() if body.expiry else None,
    )
    return {"id": token_id, "token": raw}  # shown once — not recoverable


@router.post("/{token_id}/revoke")
async def revoke(request: Request, token_id: str, principal: ManageTokens) -> dict[str, Any]:
    client = _os(request)
    doc = await _load(client, token_id)
    # journal-first (D17, audit #188)
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="token_revoke",
        entity_type="token",
        entity_id=token_id,
        cluster_id=doc.get("cluster_id"),
        strict=True,
    )
    await client.update(
        index=TOKENS_INDEX,
        id=token_id,
        body={"doc": {"disabled": True}},
        params={"refresh": "true"},
    )
    return {"id": token_id, "disabled": True}


@router.post("/{token_id}/rotate", status_code=201)
async def rotate(request: Request, token_id: str, principal: ManageTokens) -> dict[str, Any]:
    """Mint the sibling FIRST, then disable the old — the scanner is never token-less.
    The sibling inherits the old token's expiry (rotation is not extension, task E m-7)."""
    client = _os(request)
    old = await _load(client, token_id)
    new_id = uuid4().hex
    # journal-first (D17, audit #188): both events land before any mutation, strict — an audit
    # failure leaves neither the new token nor the disable, and a retry re-drives cleanly.
    for action, entity in (("token_mint", new_id), ("token_revoke", token_id)):
        await append_auth_event(
            client,
            actor=principal.user_id,
            action=action,
            entity_type="token",
            entity_id=entity,
            cluster_id=old["cluster_id"],
            strict=True,
        )
    raw = await _write_token(
        client,
        token_id=new_id,
        cluster_id=old["cluster_id"],
        scanner=old["scanner"],
        created_by=principal.user_id,
        expiry=old.get("expiry"),
    )
    await client.update(
        index=TOKENS_INDEX,
        id=token_id,
        body={"doc": {"disabled": True}},
        params={"refresh": "true"},
    )
    return {"id": new_id, "token": raw}


async def _load(client: Any, token_id: str) -> dict[str, Any]:
    try:
        return (await client.get(index=TOKENS_INDEX, id=token_id))["_source"]
    except NotFoundError:
        raise HTTPException(404, "token not found") from None
