"""MCP token admin API (issue 1096 step 1) — `/api/v1/admin/mcp-tokens`, `can_manage_tokens`.

An MCP token signs in an AI agent at the MCP endpoint (step 2). It lives in its own index,
`system-mcp-tokens`, so the scanner token check never reads it and its check never reads a
scanner token. The crypto is the scanner tokens' (`core/security.py`): only a peppered hash is
stored, and the raw token appears once, in the make or rotate answer.

The document id is the token name: the create-only write refuses a name in use, and a name stays
taken after a revoke, because the token is the principal `mcp:<name>` (D3) and a reused name would
merge two tokens in the audit log. Rotate changes the hash and the expiry of the same document, so
the principal survives it. Every mutation is journaled first (D17) as a `token` row with the name
as its id, which keeps it behind `can_manage_users` in the audit log (issue 892)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from opensearchpy import ConflictError, NotFoundError
from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

from backend.audit.writer import append_auth_event
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.auth.usernames import USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH, USERNAME_PATTERN
from backend.core.security import hash_token, mint_token, token_expired
from backend.core.settings import get_settings

router = APIRouter(prefix="/api/v1/admin/mcp-tokens", tags=["mcp-token-admin"])

MCP_TOKENS_INDEX = "system-mcp-tokens"
# the cap of D10 on issue 1096, stated in docs/API.md, not a setting
MAX_EXPIRY_DAYS = 90
_PUBLIC_FIELDS = (  # never token_hash
    "name",
    "level",
    "created_by",
    "created_at",
    "expiry",
    "disabled",
    "last_used_at",
)

ManageTokens = Annotated[Principal, Depends(require_capability("can_manage_tokens"))]


def _check_expiry(value: datetime) -> datetime:
    now = datetime.now(UTC)
    if value <= now:
        raise ValueError("expiry must be in the future")
    if value > now + timedelta(days=MAX_EXPIRY_DAYS):
        raise ValueError(f"expiry must be at most {MAX_EXPIRY_DAYS} days from now")
    return value


Expiry = Annotated[AwareDatetime, AfterValidator(_check_expiry)]


class MakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # the username rule: the principal `mcp:<name>` then reads like a user id in the audit log
    name: str = Field(
        min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN
    )
    level: Literal["read", "write", "write_risk_accept"] = "read"  # D5
    expiry: Expiry


class RotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expiry: Expiry  # a rotate is not an extension of the old expiry: a new one is required


def _os(request: Request) -> Any:
    return cast(Any, request.app.state.opensearch)


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: doc.get(k) for k in _PUBLIC_FIELDS}


async def _load(client: Any, name: str) -> tuple[dict[str, Any], dict[str, int]]:
    """The token doc and the sequence numbers of that read, so a rotate refuses a doc that a
    revoke changed since."""
    try:
        got = await client.get(index=MCP_TOKENS_INDEX, id=name)
    except NotFoundError:
        raise HTTPException(404, "token not found") from None
    return got["_source"], {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}


async def _journal(client: Any, principal: Principal, action: str, name: str) -> None:
    await append_auth_event(
        client,
        actor=principal.user_id,
        action=action,
        entity_type="token",
        entity_id=name,
        strict=True,
    )


@router.get("")
async def list_tokens(
    request: Request,
    principal: ManageTokens,
    size: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0, le=9000)] = 0,
) -> dict[str, Any]:
    hits = await _os(request).search(
        index=MCP_TOKENS_INDEX,
        body={
            "size": size,
            "from": offset,
            "track_total_hits": True,
            "sort": [{"created_at": "desc"}, {"name": "asc"}],
            "query": {"match_all": {}},
        },
    )
    return {
        "tokens": [_public(h["_source"]) for h in hits["hits"]["hits"]],
        "total": hits["hits"]["total"]["value"],
    }


@router.post("", status_code=201)
async def make(request: Request, body: MakeRequest, principal: ManageTokens) -> dict[str, Any]:
    client = _os(request)
    raw = mint_token()
    doc = {
        "token_hash": hash_token(raw, pepper=get_settings().secret_key),
        "name": body.name,
        "level": body.level,
        "created_by": principal.user_id,
        "created_at": datetime.now(UTC).isoformat(),
        "expiry": body.expiry.isoformat(),
        "disabled": False,
        "last_used_at": None,
    }
    # journal-first (D17), as a user create does: a name in use still leaves the row of the try
    await _journal(client, principal, "token_mint", body.name)
    try:
        await client.index(
            index=MCP_TOKENS_INDEX,
            id=body.name,
            body=doc,
            params={"op_type": "create", "refresh": "true"},
        )
    except ConflictError:
        raise HTTPException(409, "a token with this name exists: choose another name") from None
    return {"name": body.name, "token": raw}  # shown once — not recoverable


@router.post("/{name}/revoke")
async def revoke(request: Request, name: str, principal: ManageTokens) -> dict[str, Any]:
    client = _os(request)
    doc, _ = await _load(client, name)
    if doc.get("disabled"):
        raise HTTPException(409, "the token is already revoked")
    # an expired token can still be revoked: a revoke only stops a token and makes no secret
    await _journal(client, principal, "token_revoke", name)
    # no version guard: a revoke wins against a rotate in either order. A rotate that came first
    # gets disabled too, so its row is never the last word on a live token; one that comes after
    # refuses the changed doc itself.
    await client.update(
        index=MCP_TOKENS_INDEX,
        id=name,
        body={"doc": {"disabled": True}},
        params={"refresh": "true"},
    )
    return {"name": name, "disabled": True}


@router.post("/{name}/rotate", status_code=201)
async def rotate(
    request: Request, name: str, body: RotateRequest, principal: ManageTokens
) -> dict[str, Any]:
    """A new secret for the same token: the name, the level and the principal stay. The old secret
    stops at once."""
    client = _os(request)
    doc, seq = await _load(client, name)
    # issue 984: a rotate must not give a working secret back to a revoked token
    if doc.get("disabled"):
        raise HTTPException(409, "the token is revoked: make a new token")
    if token_expired(doc):
        raise HTTPException(409, "the token has expired: make a new token")
    raw = mint_token()
    # journal-first (D17): the old secret is revoked and a new one minted, as a scanner rotate
    # journals both, here for the one name
    for action in ("token_revoke", "token_mint"):
        await _journal(client, principal, action, name)
    try:
        await client.update(
            index=MCP_TOKENS_INDEX,
            id=name,
            body={
                "doc": {
                    "token_hash": hash_token(raw, pepper=get_settings().secret_key),
                    "expiry": body.expiry.isoformat(),
                }
            },
            params={"refresh": "true", **seq},
        )
    except ConflictError:
        raise HTTPException(409, "the token changed: load it again") from None
    return {"name": name, "token": raw}
