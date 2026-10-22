"""Admin user/role management (audit task D, #141 — closes the M5a FR-18 gap): a
`can_manage_users`-gated router over `system-users`. Rulings (recorded on the issue): bootstrap
stays secret-only (no default credential); new users get an admin-set temp password and start
`must_change: true` (the same server-enforced first-login change the bootstrap admin gets);
role change updates role + denormalized capabilities together and REVOKES the user's sessions
(D33 — `revoke_all_for_user` finally has a caller); the LAST enabled admin can be neither demoted
nor disabled (no self-bricking). Real OpenSearch."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"
TEMP_PASSWORD = "a temporary horse to replace"


pytestmark = requires_opensearch


@pytest.fixture
async def admin_env():
    """(make_http, os_client) — make_http() mints an isolated cookie jar (one per 'browser')."""
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    def make_http() -> httpx.AsyncClient:
        http = httpx.AsyncClient(transport=transport, base_url="https://t")
        jars.append(http)
        return http

    yield make_http, client
    for http in jars:
        await http.aclose()
    await client.close()


async def _seed_and_login(
    http: httpx.AsyncClient,
    client: AsyncOpenSearch,
    *,
    capabilities: list[str],
    role: str = "custom",
) -> str:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": role,
            "capabilities": capabilities,
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-05T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


def _name() -> str:
    return f"nu-{uuid.uuid4().hex[:12]}"


async def _doc(client: AsyncOpenSearch, username: str) -> dict[str, Any]:
    return (await client.get(index="system-users", id=username))["_source"]


async def _audit_actions(client: AsyncOpenSearch, entity_id: str) -> list[str]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={"size": 20, "query": {"term": {"entity_id": entity_id}}},
    )
    return [h["_source"]["action"] for h in hits["hits"]["hits"]]


# --- create ----------------------------------------------------------------------------


async def test_create_user_starts_must_change_and_can_log_in(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = _name()

    r = await admin.post(
        "/api/v1/admin/users",
        json={"username": username, "temp_password": TEMP_PASSWORD, "role": "triager"},
    )

    assert r.status_code == 201
    assert "password_hash" not in str(r.json())  # the hash never leaves the server
    doc = await _doc(client, username)
    assert doc["must_change"] is True  # SEC-6 discipline applies to admin-created users too
    assert doc["role"] == "triager"
    assert doc["capabilities"] == ["can_triage"]  # denormalized from the D33 bundle
    # the temp password works — and the session is the restricted must_change one
    fresh = make_http()
    login = await fresh.post("/auth/login", json={"username": username, "password": TEMP_PASSWORD})
    assert login.status_code == 200
    assert login.json()["user"]["must_change"] is True
    assert "user_create" in await _audit_actions(client, username)


async def test_create_duplicate_is_409_and_never_overwrites(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = _name()
    body = {"username": username, "temp_password": TEMP_PASSWORD, "role": "viewer"}
    assert (await admin.post("/api/v1/admin/users", json=body)).status_code == 201
    before = await _doc(client, username)

    assert (await admin.post("/api/v1/admin/users", json=body)).status_code == 409
    assert await _doc(client, username) == before  # untouched


async def test_create_with_unknown_role_or_weak_password_is_422(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])

    r = await admin.post(
        "/api/v1/admin/users",
        json={"username": _name(), "temp_password": TEMP_PASSWORD, "role": "warlord"},
    )
    assert r.status_code == 422
    r = await admin.post(
        "/api/v1/admin/users",
        json={"username": _name(), "temp_password": "short", "role": "viewer"},
    )
    assert r.status_code == 422


async def test_reserved_usernames_are_rejected(admin_env) -> None:
    """A-m6 (audit #192): `system`/`fleet` are machine actor literals (audit log + fleet-wide
    config) — a human can't claim one, case-insensitively, or it would blur machine-vs-human
    forensics and do triage that never charts."""
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    for reserved in ("system", "fleet", "SYSTEM", "Fleet"):
        r = await admin.post(
            "/api/v1/admin/users",
            json={"username": reserved, "temp_password": TEMP_PASSWORD, "role": "viewer"},
        )
        assert r.status_code == 422, reserved


async def test_a_name_with_a_capital_letter_is_refused_and_nothing_is_written(admin_env) -> None:
    """Issue 965: the user id is the name, so a lower-case-only name makes the create-only write
    refuse `alice` when `alice` exists, with no second check that two creates could race."""
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    name = _name()

    for typed in (name.capitalize(), name.upper()):
        r = await admin.post(
            "/api/v1/admin/users",
            json={"username": typed, "temp_password": TEMP_PASSWORD, "role": "viewer"},
        )
        assert r.status_code == 422, typed
        assert "a username must be in lower case" in r.text
        assert typed not in r.text  # the 422 does not send the name back (issue 842)
        assert not await client.exists(index="system-users", id=typed)
        assert "user_create" not in await _audit_actions(client, typed)

    r = await admin.post(
        "/api/v1/admin/users",
        json={"username": name, "temp_password": TEMP_PASSWORD, "role": "viewer"},
    )
    assert r.status_code == 201


# --- list ------------------------------------------------------------------------------


async def test_list_returns_public_fields_only(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    # Flake fix (#223): the shared dev store accumulates thousands of `u-…`/`nu-…` test users
    # across runs, so a fresh name may not land on page 1 of the asc-sorted list. Use a
    # digit-prefixed name (sorts before every letter) and sweep THIS test's own leftovers
    # first, so page 1 deterministically contains it — forever, not until the next 100 runs.
    await client.delete_by_query(
        index="system-users",
        body={"query": {"prefix": {"username": "0-list-"}}},
        params={"refresh": "true", "conflicts": "proceed"},
    )
    username = f"0-list-{uuid.uuid4().hex[:12]}"
    await admin.post(
        "/api/v1/admin/users",
        json={"username": username, "temp_password": TEMP_PASSWORD, "role": "viewer"},
    )

    r = await admin.get("/api/v1/admin/users")

    assert r.status_code == 200
    payload = r.json()
    assert "password_hash" not in str(payload)
    assert any(u["username"] == username for u in payload["users"])


# --- role change (D33: revokes sessions) ------------------------------------------------


async def test_role_change_updates_caps_and_revokes_sessions(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=["can_triage"], role="triager")
    assert (await target_http.get("/auth/me")).status_code == 200  # live session

    r = await admin.patch(f"/api/v1/admin/users/{target}/role", json={"role": "viewer"})

    assert r.status_code == 200
    doc = await _doc(client, target)
    assert doc["role"] == "viewer" and doc["capabilities"] == []  # role + caps move together
    assert (await target_http.get("/auth/me")).status_code == 401  # D33: sessions revoked
    assert "role_change" in await _audit_actions(client, target)


async def test_role_change_to_the_same_role_is_a_noop(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=["can_triage"], role="triager")

    r = await admin.patch(f"/api/v1/admin/users/{target}/role", json={"role": "triager"})

    assert r.status_code == 200
    assert (await target_http.get("/auth/me")).status_code == 200  # no-op: sessions survive


async def test_unknown_user_is_404_and_unknown_role_is_422(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    r = await admin.patch("/api/v1/admin/users/nobody-here/role", json={"role": "viewer"})
    assert r.status_code == 404
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=[])
    r = await admin.patch(f"/api/v1/admin/users/{target}/role", json={"role": "warlord"})
    assert r.status_code == 422


# --- disable / enable --------------------------------------------------------------------


async def test_disable_revokes_sessions_and_blocks_login(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=[])

    r = await admin.patch(f"/api/v1/admin/users/{target}/disabled", json={"disabled": True})

    assert r.status_code == 200
    assert (await target_http.get("/auth/me")).status_code == 401  # session dead
    fresh = make_http()
    login = await fresh.post("/auth/login", json={"username": target, "password": PASSWORD})
    assert login.status_code == 401  # generic — disabled is indistinguishable
    assert "user_disable" in await _audit_actions(client, target)

    # re-enable: login works again
    r = await admin.patch(f"/api/v1/admin/users/{target}/disabled", json={"disabled": False})
    assert r.status_code == 200
    login = await fresh.post("/auth/login", json={"username": target, "password": PASSWORD})
    assert login.status_code == 200
    assert "user_enable" in await _audit_actions(client, target)


# --- the last-admin guard ----------------------------------------------------------------


@pytest.mark.serial  # disables every OTHER enabled admin for its window — a concurrent xdist
# worker's admin session then trips the last-admin guard (200 vs 409). CI runs `-m serial` alone.
async def test_the_last_enabled_admin_cannot_be_demoted_or_disabled(admin_env) -> None:
    make_http, client = admin_env
    admin_http = make_http()
    # the acting admin IS a real admin (role=admin) — and the only one in this scenario
    acting = await _seed_and_login(admin_http, client, capabilities=["*"], role="admin")
    # make them provably the only enabled admin: disable every OTHER admin user — and RESTORE
    # them after (this runs against the shared dev OpenSearch; leaving the real bootstrap
    # `admin` disabled bricked the e2e smoke, #158)
    other_admins = {
        "bool": {
            "filter": [{"term": {"role": "admin"}}, {"term": {"disabled": False}}],
            "must_not": [{"term": {"username": acting}}],
        }
    }
    hits = await client.search(index="system-users", body={"query": other_admins, "size": 1000})
    disabled_ids = [h["_id"] for h in hits["hits"]["hits"]]
    flip = "ctx._source.disabled = {};"

    async def _set_disabled(ids: list[str], value: bool) -> None:
        if not ids:
            return
        await client.update_by_query(
            index="system-users",
            body={
                "query": {"ids": {"values": ids}},
                "script": {"lang": "painless", "source": flip.format("true" if value else "false")},
            },
            params={"conflicts": "proceed", "refresh": "true"},
        )

    await _set_disabled(disabled_ids, True)
    try:
        r = await admin_http.patch(f"/api/v1/admin/users/{acting}/role", json={"role": "viewer"})
        assert r.status_code == 409
        r = await admin_http.patch(
            f"/api/v1/admin/users/{acting}/disabled", json={"disabled": True}
        )
        assert r.status_code == 409
        assert (await _doc(client, acting))["role"] == "admin"  # untouched

        # with a second enabled admin present, the same demotion is allowed (+ revokes sessions)
        second_http = make_http()
        await _seed_and_login(second_http, client, capabilities=["*"], role="admin")
        r = await admin_http.patch(f"/api/v1/admin/users/{acting}/role", json={"role": "viewer"})
        assert r.status_code == 200
        assert (await admin_http.get("/auth/me")).status_code == 401  # self-demotion: logged out
    finally:
        await _set_disabled(disabled_ids, False)  # leave the shared index as we found it


# --- password reset ----------------------------------------------------------------------


async def test_password_reset_forces_change_and_kills_sessions(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target_http = make_http()
    target = await _seed_and_login(target_http, client, capabilities=[])

    r = await admin.post(
        f"/api/v1/admin/users/{target}/password-reset", json={"temp_password": TEMP_PASSWORD}
    )

    assert r.status_code == 200
    assert (await target_http.get("/auth/me")).status_code == 401  # stolen sessions die too
    doc = await _doc(client, target)
    assert doc["must_change"] is True
    fresh = make_http()
    old = await fresh.post("/auth/login", json={"username": target, "password": PASSWORD})
    assert old.status_code == 401  # the old password is gone
    new = await fresh.post("/auth/login", json={"username": target, "password": TEMP_PASSWORD})
    assert new.status_code == 200
    assert "pwd_reset" in await _audit_actions(client, target)


async def test_password_reset_refuses_externally_managed_users(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = f"ext-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": None,
            "role": "viewer",
            "capabilities": [],
            "must_change": False,
            "disabled": False,
            "auth_source": "oidc",
            "external_id": "sub-123",
            "created_at": "2026-07-05T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )

    r = await admin.post(
        f"/api/v1/admin/users/{username}/password-reset", json={"temp_password": TEMP_PASSWORD}
    )
    assert r.status_code == 403


async def test_create_and_reset_refuse_a_lone_surrogate_with_422(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target = await _seed_and_login(make_http(), client, capabilities=[])
    temp = "a temporary \\ud800 horse"  # JSON source text: the escape stays unpaired
    json_ = {"content-type": "application/json"}

    created = await admin.post(
        "/api/v1/admin/users",
        content=f'{{"username": "{_name()}", "temp_password": "{temp}", "role": "viewer"}}',
        headers=json_,
    )
    reset = await admin.post(
        f"/api/v1/admin/users/{target}/password-reset",
        content=f'{{"temp_password": "{temp}"}}',
        headers=json_,
    )

    assert created.status_code == reset.status_code == 422
    assert (await _doc(client, target))["must_change"] is False  # the reset changed nothing


async def test_create_and_reset_do_not_send_a_too_long_password_back(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    target = await _seed_and_login(make_http(), client, capabilities=[])
    too_long = "a temporary password past the cap " + "x" * 256

    created = await admin.post(
        "/api/v1/admin/users",
        json={"username": _name(), "temp_password": too_long, "role": "viewer"},
    )
    reset = await admin.post(
        f"/api/v1/admin/users/{target}/password-reset", json={"temp_password": too_long}
    )

    for r in (created, reset):
        body = r.json()
        assert (r.status_code, body["title"]) == (422, "Validation error")
        assert "'temp_password'" in body["detail"]
        assert too_long not in r.text
        assert "'input'" not in body["detail"]


async def test_user_list_paginates(admin_env) -> None:
    # task E (#142): the same pagination the token list gained
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])

    r = await admin.get("/api/v1/admin/users", params={"size": 1, "offset": 0})

    assert r.status_code == 200
    assert len(r.json()["users"]) == 1
    assert r.json()["total"] >= 1


# --- roles listing (M9e §13.6 / A-4) -----------------------------------------------------


async def test_roles_list_serves_the_seeded_bundles_and_is_gated(admin_env) -> None:
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])

    r = await admin.get("/api/v1/admin/roles")

    assert r.status_code == 200
    bundles = {row["role"]: row["capabilities"] for row in r.json()["roles"]}
    # the D33 defaults are present (a customized/extra role may also exist — content-driven UI)
    assert bundles["viewer"] == []
    assert bundles["triager"] == ["can_triage"]
    assert set(bundles["security_lead"]) == {"can_triage", "can_accept_audit_final"}
    assert bundles["admin"] == ["*"]

    viewer = make_http()
    await _seed_and_login(viewer, client, capabilities=[])
    assert (await viewer.get("/api/v1/admin/roles")).status_code == 403


# --- audit-log completeness (D17) + last-admin race (audit #188) ------------------------


def _fail_audit_once(monkeypatch) -> dict:
    """Make the NEXT audit append raise (a transient audit-index hiccup), then heal."""
    from backend.audit import writer

    real = writer._append
    state = {"fired": False}

    async def flaky(*args, **kwargs):
        if not state["fired"]:
            state["fired"] = True
            raise RuntimeError("audit index hiccup")
        return await real(*args, **kwargs)

    monkeypatch.setattr(writer, "_append", flaky)
    return state


async def test_create_user_not_left_unjournaled_on_audit_failure(admin_env, monkeypatch) -> None:
    """A-M5: journal-first + strict — a failed audit append must not leave a live-but-unjournaled
    user (the old fire-and-forget swallowed it silently). No user on failure; a retry creates it
    with exactly one create row."""
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = _name()
    body = {"username": username, "temp_password": TEMP_PASSWORD, "role": "viewer"}
    _fail_audit_once(monkeypatch)

    with pytest.raises(Exception):  # noqa: B017 — a strict audit failure fails the request (500)
        await admin.post("/api/v1/admin/users", json=body)
    assert not await client.exists(index="system-users", id=username)  # never created

    assert (await admin.post("/api/v1/admin/users", json=body)).status_code == 201
    assert (await _audit_actions(client, username)).count("user_create") == 1


async def test_role_change_not_left_unjournaled_on_audit_failure(admin_env, monkeypatch) -> None:
    """A-M5: the role mutation must not land without its audit row — journal-first means a failed
    append leaves the role unchanged, and a retry re-drives it (the no-op guard can't swallow)."""
    make_http, client = admin_env
    admin = make_http()
    await _seed_and_login(admin, client, capabilities=["can_manage_users"])
    username = _name()
    assert (
        await admin.post(
            "/api/v1/admin/users",
            json={"username": username, "temp_password": TEMP_PASSWORD, "role": "viewer"},
        )
    ).status_code == 201
    _fail_audit_once(monkeypatch)

    with pytest.raises(Exception):  # noqa: B017 — strict audit failure fails the request (500)
        await admin.patch(f"/api/v1/admin/users/{username}/role", json={"role": "triager"})
    assert (await _doc(client, username))["role"] == "viewer"  # journal-first: unchanged

    r = await admin.patch(f"/api/v1/admin/users/{username}/role", json={"role": "triager"})
    assert r.status_code == 200
    assert (await _doc(client, username))["role"] == "triager"
    assert (await _audit_actions(client, username)).count("role_change") == 1


@pytest.mark.serial  # disables EVERY enabled admin for its window — kills concurrent tests'
# admin sessions under -n N (this broke CI on main 2026-07-07). CI runs `-m serial` separately.
async def test_concurrent_admin_demotes_never_zero_admins(admin_env) -> None:
    """A-m3: two racing demotes of the last two admins must not self-brick. Pre-check is TOCTOU;
    the post-mutation re-check + rollback guarantees at least one enabled admin survives and at
    most one demote succeeds."""
    make_http, client = admin_env
    # isolate: disable every pre-existing enabled admin (restore in finally), then seed exactly two
    hits = await client.search(
        index="system-users",
        body={
            "size": 1000,
            "query": {
                "bool": {"filter": [{"term": {"role": "admin"}}, {"term": {"disabled": False}}]}
            },
        },
    )
    pre_existing = [h["_id"] for h in hits["hits"]["hits"]]

    async def _disable(ids: list[str], value: bool) -> None:
        if not ids:
            return
        await client.update_by_query(
            index="system-users",
            body={
                "query": {"ids": {"values": ids}},
                "script": {
                    "lang": "painless",
                    "source": f"ctx._source.disabled = {'true' if value else 'false'};",
                },
            },
            params={"conflicts": "proceed", "refresh": "true"},
        )

    await _disable(pre_existing, True)
    a_http = make_http()
    admin_a = await _seed_and_login(a_http, client, capabilities=["*"], role="admin")
    admin_b = await _seed_and_login(make_http(), client, capabilities=["*"], role="admin")
    try:
        results = await asyncio.gather(
            a_http.patch(f"/api/v1/admin/users/{admin_a}/role", json={"role": "viewer"}),
            a_http.patch(f"/api/v1/admin/users/{admin_b}/role", json={"role": "viewer"}),
            return_exceptions=True,
        )
        codes = [r.status_code for r in results if isinstance(r, httpx.Response)]

        await client.indices.refresh(index="system-users")
        # the "at most one wins" invariant only holds while a and b are the ONLY enabled admins.
        # Under -n 2 a concurrently-running test can seed another enabled admin mid-race — then
        # two wins are LEGITIMATE (the API's guarantee is global, not pairwise). Detect that and
        # call the run inconclusive rather than false-alarm on correct behavior.
        interlopers = await client.count(
            index="system-users",
            body={
                "query": {
                    "bool": {
                        "filter": [{"term": {"role": "admin"}}, {"term": {"disabled": False}}],
                        "must_not": [{"ids": {"values": [admin_a, admin_b]}}],
                    }
                }
            },
        )
        if interlopers["count"] > 0:
            pytest.skip("a concurrent test seeded another enabled admin — isolation broken")
        assert sum(c == 200 for c in codes) <= 1  # at most one demote won
        survivors = await client.count(
            index="system-users",
            body={
                "query": {
                    "bool": {
                        "filter": [{"term": {"role": "admin"}}, {"term": {"disabled": False}}],
                        "must": [{"ids": {"values": [admin_a, admin_b]}}],
                    }
                }
            },
        )
        assert survivors["count"] >= 1  # never zero — no self-brick
    finally:
        await _disable(pre_existing, False)  # leave the shared index as we found it
