"""The MCP token store and its admin routes (issue 1096 step 1): `/api/v1/admin/mcp-tokens`.

A token document has the token name as its id, so the create-only write refuses a name in use,
and a name stays taken after a revoke: the token is the principal `mcp:<name>` (D3). Rotate
changes the hash and the expiry of the same document. An expiry is required, at most 90 days out
(D10). No answer holds the hash, and only make and rotate hold the token, one time. Real
OpenSearch."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.security import hash_token
from backend.core.settings import get_settings
from backend.main import create_app
from backend.routers import mcp_tokens as mcp_tokens_router
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"
INDEX = "system-mcp-tokens"
ROUTE = "/api/v1/admin/mcp-tokens"

pytestmark = requires_opensearch


@pytest.fixture
async def admin_client():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": "admin",
                "capabilities": ["*"],
                "must_change": False,
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": "2026-07-04T00:00:00+00:00",
            },
            params={"refresh": "true"},
        )
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        yield http, client, username
    await client.close()


def _name() -> str:
    return f"t-{uuid.uuid4().hex[:12]}"


def _in_days(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


async def _make(http: httpx.AsyncClient, name: str, **extra: Any) -> httpx.Response:
    return await http.post(ROUTE, json={"name": name, "expiry": _in_days(30), **extra})


async def _doc(client: AsyncOpenSearch, name: str) -> dict[str, Any]:
    return (await client.get(index=INDEX, id=name))["_source"]


async def _audit_rows(client: AsyncOpenSearch, *, entity_id: str) -> list[dict[str, Any]]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={
            "size": 10,
            "sort": [{"@timestamp": "asc"}, {"event_id": "asc"}],
            "query": {"term": {"entity_id": entity_id}},
        },
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


async def _expire(client: AsyncOpenSearch, name: str) -> None:
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    await client.update(
        index=INDEX, id=name, body={"doc": {"expiry": past}}, params={"refresh": "true"}
    )


# --- make ------------------------------------------------------------------------------------


async def test_make_returns_the_token_once_and_stores_only_its_hash(admin_client) -> None:
    http, client, username = admin_client
    name = _name()

    r = await _make(http, name)

    assert r.status_code == 201
    raw = r.json()["token"]
    assert r.json()["name"] == name
    doc = await _doc(client, name)
    assert raw not in str(doc)
    assert doc["token_hash"] == hash_token(raw, pepper=get_settings().secret_key)
    assert (doc["name"], doc["level"], doc["created_by"]) == (name, "read", username)
    assert doc["disabled"] is False and doc["last_used_at"] is None


async def test_make_journals_a_token_row_before_it_writes(admin_client) -> None:
    http, client, username = admin_client
    name = _name()

    await _make(http, name, level="write")

    rows = await _audit_rows(client, entity_id=name)
    assert [(r["action"], r["entity_type"], r["actor"]) for r in rows] == [
        ("token_mint", "token", username)
    ]
    assert (await _doc(client, name))["level"] == "write"


async def test_each_level_can_be_made(admin_client) -> None:
    http, client, _ = admin_client
    for level in ("read", "write", "write_risk_accept"):
        name = _name()
        assert (await _make(http, name, level=level)).status_code == 201
        assert (await _doc(client, name))["level"] == level


async def test_a_name_in_use_is_409_and_the_first_token_stays(admin_client) -> None:
    http, client, _ = admin_client
    name = _name()
    first = await _make(http, name)
    before = await _doc(client, name)

    r = await _make(http, name, level="write")

    assert r.status_code == 409 and "token" not in r.json()
    assert await _doc(client, name) == before
    assert first.json()["token"]


async def test_a_revoked_name_stays_taken(admin_client) -> None:
    http, _, _ = admin_client
    name = _name()
    await _make(http, name)
    await http.post(f"{ROUTE}/{name}/revoke")

    assert (await _make(http, name)).status_code == 409


@pytest.mark.parametrize(
    "bad",
    [
        {"expiry": None},
        {"expiry": "2020-01-01T00:00:00+00:00"},
        {"expiry": "in-91-days"},
        {"expiry": "no-time-zone"},
        {"level": "admin"},
        {"name": "Has-Capital"},
        {"name": "ab"},
        {"name": "x" * 65},
        {"name": "a/b/c"},
        {"name": "mcp:alias"},
    ],
)
async def test_make_refuses_a_bad_field_with_422(admin_client, bad: dict[str, Any]) -> None:
    http, client, _ = admin_client
    name = _name()
    body = {"name": name, "level": "read", "expiry": _in_days(30), **bad}
    if body["expiry"] == "in-91-days":
        body["expiry"] = _in_days(91)
    if body["expiry"] == "no-time-zone":  # in 30 days, but with no time zone
        body["expiry"] = (datetime.now(UTC) + timedelta(days=30)).replace(tzinfo=None).isoformat()
    if body["expiry"] is None:
        del body["expiry"]

    r = await http.post(ROUTE, json=body)

    assert r.status_code == 422
    for value in bad.values():  # issue 842: a refusal never sends the value back
        if isinstance(value, str) and len(value) > 3:
            assert value not in r.text
    assert not await client.exists(index=INDEX, id=body["name"])


async def test_an_expiry_of_89_days_is_accepted(admin_client) -> None:
    http, _, _ = admin_client
    r = await http.post(ROUTE, json={"name": _name(), "expiry": _in_days(89)})
    assert r.status_code == 201


async def test_make_not_left_unjournaled_on_audit_failure(admin_client, monkeypatch) -> None:
    """Journal-first (D17): a failed audit append fails the make before the token exists."""
    http, client, _ = admin_client
    from backend.audit import writer

    real = writer._append
    state = {"fired": False}

    async def flaky(*args: Any, **kwargs: Any) -> None:
        if not state["fired"]:
            state["fired"] = True
            raise RuntimeError("audit index hiccup")
        await real(*args, **kwargs)

    monkeypatch.setattr(writer, "_append", flaky)
    name = _name()

    with pytest.raises(Exception):  # noqa: B017 — the strict audit failure fails the request (500)
        await _make(http, name)
    assert not await client.exists(index=INDEX, id=name)

    assert (await _make(http, name)).status_code == 201


# --- list ------------------------------------------------------------------------------------


async def test_list_shows_the_tokens_and_never_a_hash(admin_client) -> None:
    http, _, username = admin_client
    name = _name()
    await _make(http, name, level="write_risk_accept")

    r = await http.get(ROUTE, params={"size": 1000})

    assert r.status_code == 200
    assert "token_hash" not in r.text
    mine = [t for t in r.json()["tokens"] if t["name"] == name]
    assert len(mine) == 1
    assert set(mine[0]) == {
        "name",
        "level",
        "created_by",
        "created_at",
        "expiry",
        "disabled",
        "last_used_at",
    }
    assert (mine[0]["level"], mine[0]["created_by"]) == ("write_risk_accept", username)


async def test_list_is_newest_first_and_pages(admin_client) -> None:
    """Other xdist workers make tokens at the same time, so the test reads the order of its own
    tokens inside one page, never their place on the page."""
    http, _, _ = admin_client
    names = [_name() for _ in range(3)]
    for name in names:
        await _make(http, name)

    listed = [t["name"] for t in (await http.get(ROUTE, params={"size": 1000})).json()["tokens"]]
    page = (await http.get(ROUTE, params={"size": 2, "offset": 1})).json()

    assert [n for n in listed if n in names] == [names[2], names[1], names[0]]
    assert len(page["tokens"]) == 2 and page["total"] >= 3


async def test_list_needs_can_manage_tokens(admin_client) -> None:
    _, client, _ = admin_client
    app = create_app()
    app.state.opensearch = client
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "viewer",
            "capabilities": [],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-04T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://t"
    ) as viewer:
        r = await viewer.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200

        assert (await viewer.get(ROUTE)).status_code == 403


# --- revoke ----------------------------------------------------------------------------------


async def test_revoke_disables_the_token_and_journals_it(admin_client) -> None:
    http, client, username = admin_client
    name = _name()
    await _make(http, name)

    r = await http.post(f"{ROUTE}/{name}/revoke")

    assert r.status_code == 200 and r.json() == {"name": name, "disabled": True}
    assert (await _doc(client, name))["disabled"] is True
    rows = await _audit_rows(client, entity_id=name)
    assert [(r["action"], r["actor"]) for r in rows] == [
        ("token_mint", username),
        ("token_revoke", username),
    ]


async def test_a_second_revoke_is_409_and_writes_no_row(admin_client) -> None:
    http, client, _ = admin_client
    name = _name()
    await _make(http, name)
    await http.post(f"{ROUTE}/{name}/revoke")

    r = await http.post(f"{ROUTE}/{name}/revoke")

    assert r.status_code == 409
    assert [row["action"] for row in await _audit_rows(client, entity_id=name)] == [
        "token_mint",
        "token_revoke",
    ]


async def test_a_revoke_that_read_the_token_before_a_rotate_still_revokes(
    admin_client, monkeypatch
) -> None:
    """A revoke wins against a rotate in either order: the new secret of the rotate stops too,
    and the last audit row says what is true."""
    http, client, _ = admin_client
    name = _name()
    await _make(http, name)
    stale = await mcp_tokens_router._load(client, name)
    rotated = await http.post(f"{ROUTE}/{name}/rotate", json={"expiry": _in_days(30)})
    assert rotated.status_code == 201

    async def load_before_the_rotate(*_args: Any) -> Any:
        return stale

    monkeypatch.setattr(mcp_tokens_router, "_load", load_before_the_rotate)
    r = await http.post(f"{ROUTE}/{name}/revoke")

    assert r.status_code == 200
    assert (await _doc(client, name))["disabled"] is True
    assert (await _audit_rows(client, entity_id=name))[-1]["action"] == "token_revoke"


async def test_an_expired_token_can_be_revoked(admin_client) -> None:
    http, client, _ = admin_client
    name = _name()
    await _make(http, name)
    await _expire(client, name)

    r = await http.post(f"{ROUTE}/{name}/revoke")

    assert r.status_code == 200
    assert (await _doc(client, name))["disabled"] is True


# --- rotate ----------------------------------------------------------------------------------


async def test_rotate_changes_the_secret_and_keeps_the_name_and_level(admin_client) -> None:
    http, client, username = admin_client
    name = _name()
    old_raw = (await _make(http, name, level="write")).json()["token"]
    before = await _doc(client, name)
    expiry = _in_days(60)

    r = await http.post(f"{ROUTE}/{name}/rotate", json={"expiry": expiry})

    assert r.status_code == 201
    new_raw = r.json()["token"]
    assert r.json()["name"] == name and new_raw != old_raw
    after = await _doc(client, name)
    pepper = get_settings().secret_key
    assert after["token_hash"] == hash_token(new_raw, pepper=pepper) != before["token_hash"]
    assert (after["name"], after["level"], after["disabled"]) == (name, "write", False)
    assert after["expiry"] == expiry
    assert (after["created_by"], after["created_at"]) == (username, before["created_at"])
    rows = await _audit_rows(client, entity_id=name)
    assert [row["action"] for row in rows] == ["token_mint", "token_revoke", "token_mint"]


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"expiry": "in-91-days"},
        {"expiry": "2020-01-01T00:00:00+00:00"},
        {"expiry": "no-time-zone"},
    ],
)
async def test_rotate_needs_a_new_expiry_of_at_most_90_days(admin_client, body) -> None:
    http, client, _ = admin_client
    name = _name()
    await _make(http, name)
    before = await _doc(client, name)
    if body and body.get("expiry") == "in-91-days":
        body = {"expiry": _in_days(91)}
    if body and body.get("expiry") == "no-time-zone":  # in 30 days, but with no time zone
        body = {"expiry": (datetime.now(UTC) + timedelta(days=30)).replace(tzinfo=None).isoformat()}

    r = await http.post(f"{ROUTE}/{name}/rotate", json=body)

    assert r.status_code == 422
    assert await _doc(client, name) == before


async def test_rotate_of_a_revoked_token_is_409_and_changes_nothing(admin_client) -> None:
    http, client, _ = admin_client
    name = _name()
    await _make(http, name)
    await http.post(f"{ROUTE}/{name}/revoke")
    before = await _doc(client, name)

    r = await http.post(f"{ROUTE}/{name}/rotate", json={"expiry": _in_days(30)})

    assert r.status_code == 409 and "token" not in r.json()
    assert await _doc(client, name) == before


async def test_rotate_of_an_expired_token_is_409_and_changes_nothing(admin_client) -> None:
    http, client, _ = admin_client
    name = _name()
    await _make(http, name)
    await _expire(client, name)
    before = await _doc(client, name)

    r = await http.post(f"{ROUTE}/{name}/rotate", json={"expiry": _in_days(30)})

    assert r.status_code == 409
    assert await _doc(client, name) == before
    assert [row["action"] for row in await _audit_rows(client, entity_id=name)] == ["token_mint"]


async def test_a_rotate_that_races_a_revoke_is_409(admin_client, monkeypatch) -> None:
    """The rotate read the token before a revoke came: its write must not hand out a secret for
    the revoked token."""
    http, client, _ = admin_client
    name = _name()
    await _make(http, name)
    stale = await mcp_tokens_router._load(client, name)
    await http.post(f"{ROUTE}/{name}/revoke")
    revoked = await _doc(client, name)

    async def load_before_the_revoke(*_args: Any) -> Any:
        return stale

    monkeypatch.setattr(mcp_tokens_router, "_load", load_before_the_revoke)
    r = await http.post(f"{ROUTE}/{name}/rotate", json={"expiry": _in_days(30)})

    assert r.status_code == 409 and "token" not in r.json()
    assert await _doc(client, name) == revoked


async def test_an_unknown_name_is_404(admin_client) -> None:
    http, _, _ = admin_client
    assert (await http.post(f"{ROUTE}/nope-{_name()}/revoke")).status_code == 404
    rotate = await http.post(f"{ROUTE}/nope-{_name()}/rotate", json={"expiry": _in_days(30)})
    assert rotate.status_code == 404
