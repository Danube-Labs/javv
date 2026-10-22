"""Admin user/role management (audit task D, #141) — the `can_manage_users`-gated surface that
closes the M5a FR-18 gap. Rulings (recorded on #141): bootstrap stays secret-only (no default
credential); a created/reset user gets an admin-set temp password and starts `must_change: true`
(the same SEC-6 server-enforced first-login change the bootstrap admin gets); a role change
updates `role` + the denormalized `capabilities` together and REVOKES every session of the user
(D33 — role/permission changes must not ride an old session); disable also revokes. The LAST
enabled admin can be neither demoted nor disabled (409 — no self-bricking). An admin who forgets
their password is reset from a shell instead, by `python -m backend.auth.reset_password` (issue
761). Role-bundle EDITING is out of scope (assignment of `system-roles` bundles
only); external (`oidc`/`ldap`) users' passwords are their IdP's business (403 on reset).

Every route registers in the standing RBAC/IDOR suite (`tests/security/test_rbac_idor_contract.py`)
and every mutation is journaled (D17)."""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from opensearchpy import NotFoundError
from opensearchpy.exceptions import ConflictError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.audit.writer import append_auth_event
from backend.auth.capabilities import ROLES_INDEX, require_capability
from backend.auth.passwords import check_policy, hash_password
from backend.auth.principal import Principal
from backend.auth.sessions import revoke_all_for_user
from backend.auth.usernames import (
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    USERNAME_PATTERN,
    check_username,
)

router = APIRouter(prefix="/api/v1/admin/users", tags=["user-admin"])
roles_router = APIRouter(prefix="/api/v1/admin/roles", tags=["user-admin"])

USERS_INDEX = "system-users"
_PUBLIC_FIELDS = (  # never password_hash — the hash never leaves the server
    "username",
    "role",
    "capabilities",
    "must_change",
    "disabled",
    "auth_source",
    "created_at",
)

ManageUsers = Annotated[Principal, Depends(require_capability("can_manage_users"))]


class CreateUser(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    username: str = Field(
        min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN
    )
    temp_password: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=64)

    # before the pattern, so a capital letter gets the plain "lower case" message, not a regex
    @field_validator("username", mode="before")
    @classmethod
    def _username_rule(cls, v: object) -> object:
        return check_username(v) if isinstance(v, str) else v


class RolePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1, max_length=64)


class DisabledPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disabled: bool


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temp_password: str = Field(min_length=1, max_length=256)


def _os(request: Request) -> Any:
    return cast(Any, request.app.state.opensearch)


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: doc.get(k) for k in _PUBLIC_FIELDS}


def _check_policy_or_422(password: str) -> None:
    try:
        check_policy(password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


async def _role_capabilities_or_422(client: Any, role: str) -> list[str]:
    """The role's bundle — an unknown role is a caller error (422), never fail-open."""
    try:
        doc = (await client.get(index=ROLES_INDEX, id=role))["_source"]
    except NotFoundError:
        raise HTTPException(422, f"unknown role {role!r}") from None
    return list(doc.get("capabilities", []))


async def _load_user(client: Any, username: str) -> dict[str, Any]:
    try:
        return (await client.get(index=USERS_INDEX, id=username))["_source"]
    except NotFoundError:
        raise HTTPException(404, "user not found") from None


async def _count_enabled_admins(client: Any, *, excluding: str | None = None) -> int:
    must_not: list[dict[str, Any]] = [{"term": {"disabled": True}}]
    if excluding is not None:
        must_not.append({"term": {"username": excluding}})
    hits = await client.search(
        index=USERS_INDEX,
        body={
            "size": 0,
            "query": {"bool": {"filter": [{"term": {"role": "admin"}}], "must_not": must_not}},
        },
    )
    return int(hits["hits"]["total"]["value"])


async def _assert_not_last_admin(client: Any, username: str) -> None:
    """Cheap pre-check: refuse to remove the final enabled admin — another one must exist first.
    A concurrent pair can both pass this (each sees the other), so the caller ALSO re-checks after
    the mutation and rolls back on zero admins (A-m3 — the pre-check alone is TOCTOU)."""
    if await _count_enabled_admins(client, excluding=username) == 0:
        raise HTTPException(409, "cannot demote or disable the last enabled admin")


@router.get("")
async def list_users(
    request: Request,
    principal: ManageUsers,
    size: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0, le=9000)] = 0,
) -> dict[str, Any]:
    # explicit from/size pagination (task E / audit L1) — same shape as the token list
    hits = await _os(request).search(
        index=USERS_INDEX,
        body={
            "size": size,
            "from": offset,
            "track_total_hits": True,
            "sort": [{"username": "asc"}],
            "query": {"match_all": {}},
        },
    )
    return {
        "users": [_public(h["_source"]) for h in hits["hits"]["hits"]],
        "total": hits["hits"]["total"]["value"],
    }


@roles_router.get("")
async def list_roles(request: Request, principal: ManageUsers) -> dict[str, Any]:
    """The seeded `system-roles` bundles (A-4/§13.6) — the UI renders whatever is seeded, so a
    later 5th role appears without a client change. Read-only; bundle EDITING stays out of scope."""
    hits = await _os(request).search(
        index=ROLES_INDEX,
        body={"size": 100, "sort": [{"_id": "asc"}], "query": {"match_all": {}}},
    )
    return {
        "roles": [
            {"role": h["_id"], "capabilities": list(h["_source"].get("capabilities", []))}
            for h in hits["hits"]["hits"]
        ]
    }


@router.post("", status_code=201)
async def create_user(request: Request, body: CreateUser, principal: ManageUsers) -> dict[str, Any]:
    client = _os(request)
    _check_policy_or_422(body.temp_password)
    capabilities = await _role_capabilities_or_422(client, body.role)
    doc = {
        "username": body.username,
        "password_hash": hash_password(body.temp_password),
        "role": body.role,
        "capabilities": capabilities,  # denormalized from the bundle (kept in step on role change)
        "must_change": True,  # SEC-6: the temp password is not a real one
        "disabled": False,
        "auth_source": "local",
        "external_id": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    # journal-first (D17, audit #188): the row lands before the create, strict so an audit failure
    # 500s WITHOUT a silent unjournaled user; a retry re-drives both.
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="user_create",
        entity_type="user",
        entity_id=body.username,
        strict=True,
    )
    try:
        await client.index(
            index=USERS_INDEX,
            id=body.username,
            body=doc,
            params={
                "op_type": "create",
                "refresh": "true",
            },  # an existing user is NEVER overwritten
        )
    except ConflictError:
        raise HTTPException(409, "user already exists") from None
    return {"user": _public(doc)}


@router.patch("/{username}/role")
async def set_role(
    request: Request, username: str, body: RolePatch, principal: ManageUsers
) -> dict[str, Any]:
    client = _os(request)
    user = await _load_user(client, username)
    if user.get("role") == body.role:
        return {"user": _public(user)}  # no-op: nothing changes, sessions survive
    capabilities = await _role_capabilities_or_422(client, body.role)
    demoting_admin = user.get("role") == "admin"
    if demoting_admin:
        await _assert_not_last_admin(client, username)  # cheap pre-check (TOCTOU — see below)
    # journal-first (D17, audit #188): strict append before the write; a retry finds the role still
    # old (not a no-op) and re-drives, so the change is never applied-but-unjournaled.
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="role_change",
        entity_type="user",
        entity_id=username,
        strict=True,
    )
    await client.update(
        index=USERS_INDEX,
        id=username,
        body={"doc": {"role": body.role, "capabilities": capabilities}},
        params={"refresh": "true"},
    )
    if demoting_admin and await _count_enabled_admins(client) == 0:
        # A-m3: a concurrent demote raced past both pre-checks and we jointly zeroed the admins —
        # roll our demotion back and refuse, so at least one admin always survives.
        await client.update(
            index=USERS_INDEX,
            id=username,
            body={"doc": {"role": user["role"], "capabilities": user.get("capabilities", [])}},
            params={"refresh": "true"},
        )
        raise HTTPException(409, "cannot demote or disable the last enabled admin")
    await revoke_all_for_user(client, username)  # D33: a new role never rides an old session
    return {"user": _public({**user, "role": body.role, "capabilities": capabilities})}


@router.patch("/{username}/disabled")
async def set_disabled(
    request: Request, username: str, body: DisabledPatch, principal: ManageUsers
) -> dict[str, Any]:
    client = _os(request)
    user = await _load_user(client, username)
    if bool(user.get("disabled")) == body.disabled:
        return {"user": _public(user)}  # no-op
    disabling_admin = body.disabled and user.get("role") == "admin"
    if disabling_admin:
        await _assert_not_last_admin(client, username)  # cheap pre-check (TOCTOU — see below)
    # journal-first (D17, audit #188)
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="user_disable" if body.disabled else "user_enable",
        entity_type="user",
        entity_id=username,
        strict=True,
    )
    await client.update(
        index=USERS_INDEX,
        id=username,
        body={"doc": {"disabled": body.disabled}},
        params={"refresh": "true"},
    )
    if disabling_admin and await _count_enabled_admins(client) == 0:
        # A-m3: a concurrent disable/demote jointly zeroed the admins — roll back and refuse.
        await client.update(
            index=USERS_INDEX,
            id=username,
            body={"doc": {"disabled": False}},
            params={"refresh": "true"},
        )
        raise HTTPException(409, "cannot demote or disable the last enabled admin")
    if body.disabled:
        await revoke_all_for_user(client, username)  # dead account = dead sessions, immediately
    return {"user": _public({**user, "disabled": body.disabled})}


@router.post("/{username}/password-reset")
async def password_reset(
    request: Request, username: str, body: PasswordReset, principal: ManageUsers
) -> dict[str, Any]:
    client = _os(request)
    user = await _load_user(client, username)
    if user.get("auth_source", "local") != "local":
        raise HTTPException(403, "password is managed by the identity provider")
    _check_policy_or_422(body.temp_password)
    # journal-first (D17, audit #188): strict append before the reset lands
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="pwd_reset",
        entity_type="user",
        entity_id=username,
        strict=True,
    )
    await client.update(
        index=USERS_INDEX,
        id=username,
        body={"doc": {"password_hash": hash_password(body.temp_password), "must_change": True}},
        params={"refresh": "true"},
    )
    await revoke_all_for_user(client, username)  # a possibly-compromised account starts clean
    return {"user": _public({**user, "must_change": True})}
