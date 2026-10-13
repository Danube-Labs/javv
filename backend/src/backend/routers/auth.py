"""Human auth routes (M5a slice 3, FR-18/SEC-6) — login/logout/me/password over the
provider-agnostic session layer. Failure discipline: unknown user, wrong password, disabled
account, and a dead session are all the SAME generic 401 (no oracle of any kind); lockout is 429
before credentials are even looked at. The session cookie is `HttpOnly; SameSite=Lax`, plus
`Secure` unless `JAVV_SESSION_COOKIE_SECURE` is false (a plain-http install; localhost counts as a
secure context in browsers, so dev works either way); its `Max-Age` mirrors the TTL but the
server-side `expires_at` is what actually decides.

`must_change` (SEC-6): a fresh bootstrap admin can log in, read `/auth/me`, change its password,
and log out — nothing else. `get_current_principal` (principal.py), which every other session
route depends on, refuses a `must_change` user. None of the routes here use it: `/me` and
`/password` resolve the session through `require_session`, and `/login` and `/logout` take none.
"""

from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.audit.writer import append_auth_event
from backend.auth import lockout
from backend.auth.passwords import check_policy, hash_password, verify_password
from backend.auth.providers import USERS_INDEX, LocalPasswordProvider, LoginCredentials
from backend.auth.sessions import (
    COOKIE_NAME,
    lookup_session,
    mint_session,
    revoke_all_for_user,
    revoke_session,
)
from backend.core.metrics import AUTH_FAILURES
from backend.core.settings import get_settings

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

_provider = LocalPasswordProvider()  # the IdentityProvider seam — OIDC/LDAP swap in post-MVP

_GENERIC_401 = HTTPException(401, "invalid credentials")  # one answer for every failure mode


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def _os(request: Request) -> Any:
    return cast(Any, request.app.state.opensearch)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    """The response shape — UI hints only (the server re-checks every call); never the hash."""
    return {
        "username": user["username"],
        "role": user.get("role"),
        "capabilities": user.get("capabilities", []),
        "must_change": bool(user.get("must_change")),
    }


def _set_session_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw,
        httponly=True,
        secure=get_settings().session_cookie_secure,
        samesite="lax",
        path="/",
        max_age=int(get_settings().session_ttl_hours * 3600),  # advisory; expires_at decides
    )


async def require_session(request: Request) -> dict[str, Any]:
    """Cookie → live session doc, else the generic 401. Slice 4's principal resolution builds on
    this; auth routes only need the session's `user_id`."""
    session = await lookup_session(_os(request), request.cookies.get(COOKIE_NAME, ""))
    if session is None:
        raise _GENERIC_401
    return session


@router.post("/login")
async def login(request: Request, creds: LoginCredentials, response: Response) -> dict[str, Any]:
    # task C m-8 (#140): login CSRF. A cross-site HTML form can only POST as urlencoded /
    # multipart / text/plain — never application/json — and a cross-origin fetch with a JSON
    # content type dies in the CORS preflight (no CORS middleware is configured, by design).
    # Enforcing the content type here closes the text/plain JSON-smuggling arm.
    if "application/json" not in request.headers.get("content-type", ""):
        raise HTTPException(415, "login requires application/json")
    if lockout.locked(creds.username):
        # the client sees only 429 — this warning is the operator's ONLY trace (#156)
        log.warning("login locked out", username=creds.username)
        AUTH_FAILURES.labels("locked_out").inc()  # M-5 (#220): reason only, never a username
        raise HTTPException(429, "too many attempts")  # budget spent — credentials unseen
    client = _os(request)
    result = await _provider.authenticate(client, creds)
    if result is None:
        lockout.record_failure(creds.username)
        AUTH_FAILURES.labels("bad_credentials").inc()  # M-5 (#220)
        raise _GENERIC_401
    lockout.clear(creds.username)
    # task C m-10 (#140): a login that arrives with a still-valid session cookie is this
    # browser replacing its session (account switch without logout) — revoke the old one so
    # no live orphan outlasts the cookie that held it. Idempotent; unknown cookie is a no-op.
    prior = request.cookies.get(COOKIE_NAME, "")
    if prior:
        await revoke_session(client, prior)
    _set_session_cookie(response, await mint_session(client, result.user_id))
    await append_auth_event(
        _os(request),
        actor=result.user_id,
        action="login",
        entity_type="user",
        entity_id=result.user_id,
    )
    return {"user": _public_user(result.user)}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    raw = request.cookies.get(COOKIE_NAME, "")
    if raw:
        client = _os(request)
        session = await lookup_session(client, raw)
        await revoke_session(client, raw)  # server-side kill — the cookie is now inert
        if session is not None:
            await append_auth_event(
                client,
                actor=session["user_id"],
                action="logout",
                entity_type="user",
                entity_id=session["user_id"],
            )
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=get_settings().session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.get("/me")
async def me(
    request: Request, session: Annotated[dict[str, Any], Depends(require_session)]
) -> dict[str, Any]:
    user = await _load_user(request, session["user_id"])
    return {"user": _public_user(user)}


@router.post("/password")
async def change_password(
    request: Request,
    body: PasswordChange,
    response: Response,
    session: Annotated[dict[str, Any], Depends(require_session)],
) -> dict[str, Any]:
    """First-login `must_change` exit + regular self-service change. Verifies the CURRENT password
    (a hijacked cookie alone can't rotate credentials), then revokes every session of the user and
    mints a fresh one — a concurrently-stolen session dies with the old password.

    The audit row is strict and written first (D17; issue 833 moved password changes out of the
    #188 fire-and-forget split), so a change the log cannot record does not happen. A new session
    that cannot be made after the update is still a 200, with no cookie: the password has changed
    and every old session is gone, so the user signs in again with the new one."""
    client = _os(request)
    user_id = session["user_id"]
    user = await _load_user(request, user_id)
    if user.get("auth_source", "local") != "local":
        raise HTTPException(403, "password is managed by the identity provider")
    if not verify_password(body.current_password, user.get("password_hash") or ""):
        raise _GENERIC_401
    try:
        check_policy(body.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await append_auth_event(
        client,
        actor=user_id,
        action="pwd_change",
        entity_type="user",
        entity_id=user_id,
        strict=True,
    )
    await client.update(
        index=USERS_INDEX,
        id=user_id,
        body={"doc": {"password_hash": hash_password(body.new_password), "must_change": False}},
        params={"refresh": "true"},
    )
    await revoke_all_for_user(client, user_id)
    try:
        raw = await mint_session(client, user_id)
    except Exception as exc:  # noqa: BLE001 — whatever failed, the change itself has landed
        log.warning("password changed, no new session", username=user_id, error=type(exc).__name__)
        AUTH_FAILURES.labels("session_not_minted").inc()
    else:
        _set_session_cookie(response, raw)
    return {"user": _public_user({**user, "must_change": False})}


async def _load_user(request: Request, user_id: str) -> dict[str, Any]:
    from opensearchpy import NotFoundError  # local import keeps the router surface tidy

    try:
        user = (await _os(request).get(index=USERS_INDEX, id=user_id))["_source"]
    except NotFoundError:  # user deleted while the session lived
        raise _GENERIC_401 from None
    if user.get("disabled"):
        raise _GENERIC_401
    return user
