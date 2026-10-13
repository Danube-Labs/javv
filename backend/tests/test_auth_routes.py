"""Login/logout/password routes + lockout + bootstrap admin (M5a slice 3, FR-18/SEC-6).

Failure discipline: wrong password, unknown user, and disabled user are the SAME generic 401 (no
existence oracle; the dummy-hash keeps timing flat). Lockout answers 429 regardless of credential
correctness. The session cookie is httpOnly+SameSite=Lax, plus Secure unless
JAVV_SESSION_COOKIE_SECURE is false — tests speak https to the ASGI app so the cookie jar replays it
either way. Real OpenSearch (real indices, unique per-test usernames — same
convention as the ingest route tests)."""

import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.bootstrap_admin import seed_bootstrap_admin
from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.core.settings import Settings, get_settings
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"


pytestmark = requires_opensearch


@pytest.fixture
async def auth_client():
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)  # v4 indices must exist (fresh CI)
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
        yield http, client
    await client.close()


async def _seed_user(
    client,
    username: str,
    *,
    password: str = PASSWORD,
    role: str = "triager",
    must_change: bool = False,
    disabled: bool = False,
) -> None:
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "capabilities": ["can_triage"],
            "must_change": must_change,
            "disabled": disabled,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-04T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )


def _u() -> str:
    return f"u-{uuid.uuid4().hex[:12]}"


def _attributes(set_cookie: str) -> set[str]:
    """The attribute names of one Set-Cookie header, lowercased. Read as names, not substrings,
    since a random session value could contain the letters "secure"."""
    _pair, *attrs = set_cookie.split(";")
    return {a.strip().split("=", 1)[0].lower() for a in attrs}


@pytest.fixture
def cookie_secure(request, monkeypatch):
    monkeypatch.setenv("JAVV_SESSION_COOKIE_SECURE", "true" if request.param else "false")
    get_settings.cache_clear()
    yield request.param
    get_settings.cache_clear()


async def _login(
    http, username: str, password: str = PASSWORD, *, request_id: str | None = None
) -> httpx.Response:
    headers = {"X-Request-ID": request_id} if request_id else {}
    return await http.post(
        "/auth/login", json={"username": username, "password": password}, headers=headers
    )


# --- login ------------------------------------------------------------------------


@pytest.mark.parametrize("cookie_secure", [True, False], indirect=True)
async def test_login_happy_path_sets_cookie_and_returns_the_public_user(
    auth_client, cookie_secure: bool
) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)

    r = await _login(http, user)

    assert r.status_code == 200
    body: dict[str, Any] = r.json()["user"]
    assert body["username"] == user and body["role"] == "triager"
    assert body["must_change"] is False
    assert "password_hash" not in str(r.json())  # the hash never leaves the server
    cookie = r.headers["set-cookie"]
    assert "javv_session=" in cookie
    for flag in ("HttpOnly", "SameSite=lax", "Path=/"):
        assert flag.lower() in cookie.lower(), flag
    assert ("secure" in _attributes(cookie)) is cookie_secure  # JAVV_SESSION_COOKIE_SECURE


async def test_wrong_password_and_unknown_user_are_the_same_generic_401(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)

    # one request id for both: the body carries it (issue 644), and it's the only per-request part
    wrong = await _login(http, user, "not the password xx", request_id="oracle-check")
    unknown = await _login(http, _u(), request_id="oracle-check")  # never seeded

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.content == unknown.content  # byte-identical — no existence oracle


async def test_disabled_user_gets_the_same_generic_401(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user, disabled=True)

    r = await _login(http, user)  # correct password, disabled account

    assert r.status_code == 401


async def test_lockout_answers_429_even_for_the_correct_password(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)

    for _ in range(5):  # burn the JAVV_LOGIN_MAX_ATTEMPTS budget
        assert (await _login(http, user, "wrong password xx")).status_code == 401

    r = await _login(http, user)  # correct password — still refused while locked

    assert r.status_code == 429


# --- session round-trip -------------------------------------------------------------


async def test_me_roundtrip_and_logout_kills_the_session_server_side(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    assert (await _login(http, user)).status_code == 200  # cookie now in the jar

    me = await http.get("/auth/me")
    assert me.status_code == 200 and me.json()["user"]["username"] == user

    assert (await http.post("/auth/logout")).status_code == 204
    assert (await http.get("/auth/me")).status_code == 401  # revoked, not just cookie-cleared


@pytest.mark.parametrize("cookie_secure", [True, False], indirect=True)
async def test_logout_clears_the_cookie_with_the_same_flags_as_login(
    auth_client, cookie_secure: bool
) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    login = await _login(http, user)

    out = await http.post("/auth/logout")

    cleared = out.headers["set-cookie"]
    assert cleared.startswith("javv_session=")
    assert "max-age=0" in cleared.lower()  # an expired cookie: the browser drops it
    # logout follows JAVV_SESSION_COOKIE_SECURE exactly as login does
    assert _attributes(cleared) >= {"httponly", "samesite", "path"}
    assert ("secure" in _attributes(cleared)) is cookie_secure
    assert ("secure" in _attributes(login.headers["set-cookie"])) is cookie_secure


async def test_me_without_or_with_garbage_cookie_is_401(auth_client) -> None:
    http, _ = auth_client
    assert (await http.get("/auth/me")).status_code == 401
    http.cookies.set("javv_session", "garbage-value", domain="t")
    assert (await http.get("/auth/me")).status_code == 401


# --- password change (SEC-6) ---------------------------------------------------------


async def test_password_change_clears_must_change_and_rotates_credentials(auth_client) -> None:
    http, client = auth_client
    user = _u()
    new_password = "an entirely new passphrase"
    await _seed_user(client, user, must_change=True)
    login = await _login(http, user)
    assert login.json()["user"]["must_change"] is True

    r = await http.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": new_password}
    )

    assert r.status_code == 200
    assert r.json()["user"]["must_change"] is False
    assert (await http.get("/auth/me")).status_code == 200  # fresh session works
    # the old password is dead, the new one lives
    fresh = httpx.AsyncClient(transport=http._transport, base_url="https://t")
    async with fresh:
        assert (await _login(fresh, user, PASSWORD)).status_code == 401
        assert (await _login(fresh, user, new_password)).status_code == 200


async def test_password_change_rejects_a_wrong_current_password(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    await _login(http, user)

    r = await http.post(
        "/auth/password",
        json={"current_password": "guessed wrong xx", "new_password": "another passphrase ok"},
    )

    assert r.status_code == 401


async def test_password_change_enforces_the_policy(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    await _login(http, user)

    r = await http.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
    )

    assert r.status_code == 422


# JSON source text, so the escape stays unpaired. Request validation refuses it before the
# password policy or the hash sees it; FastAPI's default 422 handler would then fail to encode
# the echoed input and answer 500, so these pin the app's own handler too.
LONE_SURROGATE = "correct horse \\ud800 staple"


async def test_password_change_refuses_a_lone_surrogate_with_422(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    await _login(http, user)
    before = (await client.get(index="system-users", id=user))["_source"]["password_hash"]

    r = await http.post(
        "/auth/password",
        content=f'{{"current_password": "{PASSWORD}", "new_password": "{LONE_SURROGATE}"}}',
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 422
    after = (await client.get(index="system-users", id=user))["_source"]["password_hash"]
    assert after == before


async def test_login_with_a_lone_surrogate_is_422(auth_client) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user)

    r = await http.post(
        "/auth/login",
        content=f'{{"username": "{user}", "password": "{LONE_SURROGATE}"}}',
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 422


async def test_password_change_without_a_session_is_401(auth_client) -> None:
    http, _ = auth_client
    r = await http.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": "whatever works ok"}
    )
    assert r.status_code == 401


async def _audit_actions(client, entity_id: str) -> list[str]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={"size": 20, "query": {"term": {"entity_id": entity_id}}},
    )
    return [h["_source"]["action"] for h in hits["hits"]["hits"]]


@pytest.mark.parametrize("must_change", [True, False], ids=["forced", "later"])
async def test_every_password_change_writes_its_audit_row(auth_client, must_change) -> None:
    http, client = auth_client
    user = _u()
    await _seed_user(client, user, must_change=must_change)
    await _login(http, user)

    r = await http.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "an entirely new passphrase"},
    )

    assert r.status_code == 200
    assert (await _audit_actions(client, user)).count("pwd_change") == 1


async def test_a_password_change_the_audit_log_cannot_record_does_not_happen(
    auth_client, monkeypatch
) -> None:
    """Strict and written first (issue 833, amending the #188 split): a failed audit append leaves
    the password and the sessions as they were, and a retry changes it with one row."""
    from backend.audit import writer

    http, client = auth_client
    user = _u()
    new_password = "an entirely new passphrase"
    await _seed_user(client, user)
    await _login(http, user)
    real = writer._append

    async def failing(*args, **kwargs):
        raise RuntimeError("audit index hiccup")

    monkeypatch.setattr(writer, "_append", failing)
    body = {"current_password": PASSWORD, "new_password": new_password}
    with pytest.raises(RuntimeError):  # a strict audit failure fails the request (500)
        await http.post("/auth/password", json=body)
    monkeypatch.setattr(writer, "_append", real)

    assert (await http.get("/auth/me")).status_code == 200  # the session was not revoked
    fresh = httpx.AsyncClient(transport=http._transport, base_url="https://t")
    async with fresh:
        assert (await _login(fresh, user, PASSWORD)).status_code == 200  # nor the password
    assert "pwd_change" not in await _audit_actions(client, user)

    assert (await http.post("/auth/password", json=body)).status_code == 200
    assert (await _audit_actions(client, user)).count("pwd_change") == 1


async def test_a_password_change_with_no_new_session_answers_200_with_no_cookie(
    auth_client, monkeypatch
) -> None:
    import structlog.testing

    from backend.core.metrics import AUTH_FAILURES
    from backend.routers import auth as auth_module

    http, client = auth_client
    user = _u()
    new_password = "an entirely new passphrase"
    await _seed_user(client, user, must_change=True)
    await _login(http, user)

    async def no_session(*args, **kwargs):
        raise RuntimeError("sessions index hiccup")

    monkeypatch.setattr(auth_module, "mint_session", no_session)
    monkeypatch.setattr(auth_module, "log", structlog.get_logger())  # see the lockout test
    counter = AUTH_FAILURES.labels("session_not_minted")
    before = counter._value.get()  # noqa: SLF001 — prometheus_client test-read idiom

    with structlog.testing.capture_logs() as logs:
        r = await http.post(
            "/auth/password", json={"current_password": PASSWORD, "new_password": new_password}
        )

    assert r.status_code == 200
    assert "set-cookie" not in r.headers
    assert r.json()["user"]["must_change"] is False
    assert (await http.get("/auth/me")).status_code == 401  # the old session ended with it
    monkeypatch.undo()
    fresh = httpx.AsyncClient(transport=http._transport, base_url="https://t")
    async with fresh:
        assert (await _login(fresh, user, new_password)).status_code == 200
    assert counter._value.get() - before == 1  # noqa: SLF001
    warnings = [e for e in logs if e["event"] == "password changed, no new session"]
    assert warnings and warnings[0]["log_level"] == "warning"
    assert warnings[0]["username"] == user


# --- bootstrap admin (seed-once, SEC-6) ----------------------------------------------


async def test_bootstrap_admin_seeds_once_with_must_change(auth_client, monkeypatch) -> None:
    _, client = auth_client
    admin = _u()  # unique "admin" name so the shared real index stays clean
    settings = Settings(bootstrap_admin_username=admin, bootstrap_admin_password=PASSWORD)
    monkeypatch.setattr("backend.auth.bootstrap_admin.get_settings", lambda: settings)

    assert await seed_bootstrap_admin(client) == "created"
    assert await seed_bootstrap_admin(client) == "exists"  # idempotent — never re-seeds

    doc = (await client.get(index="system-users", id=admin))["_source"]
    assert doc["role"] == "admin" and doc["must_change"] is True
    assert doc["password_hash"].startswith("$argon2id$")


async def test_bootstrap_admin_skips_when_no_secret_is_mounted(auth_client, monkeypatch) -> None:
    _, client = auth_client
    settings = Settings(bootstrap_admin_password="")
    monkeypatch.setattr("backend.auth.bootstrap_admin.get_settings", lambda: settings)

    assert await seed_bootstrap_admin(client) == "skipped"


# --- lockout is observable (#156) ---------------------------------------------


async def test_lockout_refusal_emits_a_warning_log(auth_client, monkeypatch) -> None:
    """A tripped lockout is a security signal an operator alerts on — it must leave a WARNING
    (the generic-401 discipline hides it from the client, so the log is the ONLY trace)."""
    import structlog.testing

    from backend.routers import auth as auth_module

    # the module-level proxy may already be BOUND under the cached prod config (an earlier 429
    # test used it), which capture_logs cannot intercept — swap in a fresh unbound proxy
    monkeypatch.setattr(auth_module, "log", structlog.get_logger())

    http, client = auth_client
    user = _u()
    await _seed_user(client, user)
    for _ in range(5):  # burn the budget
        await _login(http, user, "wrong password xx")

    with structlog.testing.capture_logs() as logs:
        r = await _login(http, user)

    assert r.status_code == 429
    warnings = [e for e in logs if e["event"] == "login locked out"]
    assert warnings and warnings[0]["log_level"] == "warning"
    assert warnings[0]["username"] == user  # username is not a secret; the log is server-side
