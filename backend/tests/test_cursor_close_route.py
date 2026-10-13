"""POST /api/v1/cursors/close (issue 832) against real OpenSearch.

Pins: a caller closes its own findings or audit walk early, which deletes the PIT and frees the
slot; another user's cursor, an ended walk and an expired one answer 204 and close nothing; a bad
cursor is 422; the route needs a session (401) and a changed password (403). A continuation that
finds its PIT gone frees the walk's slot too. The cap is 1 here, so "the slot is free" is read off
the next first page: 200 when it fits, 429 when the slot is still held.
"""

import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError
from prometheus_client import REGISTRY

from backend.audit.writer import append_field_change
from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from backend.query import pit_guard
from backend.query.search import cursor_pit_id
from os_env import OS_URL, requires_opensearch
from test_findings_route import _rows, _seed

PASSWORD = "cursor-close-password"

pytestmark = requires_opensearch


@pytest.fixture(autouse=True)
def _one_slot_each(monkeypatch):
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "1")
    get_settings.cache_clear()
    pit_guard._slots.clear()
    yield
    pit_guard._slots.clear()
    get_settings.cache_clear()


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login(*, must_change: bool = False) -> httpx.AsyncClient:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": "viewer",
                "capabilities": [],
                "must_change": must_change,
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": "2026-10-13T00:00:00+00:00",
            },
            params={"refresh": "true"},
        )
        http = httpx.AsyncClient(transport=transport, base_url="https://t")
        jars.append(http)
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        return http

    yield login, client, transport
    for http in jars:
        await http.aclose()
    await client.close()


async def _findings_walk(http: httpx.AsyncClient, cid: str) -> str:
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200 and r.json()["next_cursor"]
    return r.json()["next_cursor"]


async def _first_page(http: httpx.AsyncClient, cid: str) -> int:
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    return r.status_code


async def _pit_alive(client: AsyncOpenSearch, pit_id: str) -> bool:
    try:
        await client.search(body={"pit": {"id": pit_id}, "size": 0})
    except NotFoundError:
        return False
    return True


async def _close(http: httpx.AsyncClient, cursor: Any) -> httpx.Response:
    return await http.post("/api/v1/cursors/close", json={"cursor": cursor})


def _pits_open() -> float:
    return REGISTRY.get_sample_value("javv_pits_open") or 0.0


async def test_your_own_findings_walk_closes_and_frees_its_slot(env) -> None:
    login, client, _ = env
    cid = f"c-close-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(3))
    http = await login()

    cursor = await _findings_walk(http, cid)
    pit_id = cursor_pit_id(cursor)
    assert await _first_page(http, cid) == 429  # the walk holds the only slot
    held = _pits_open()

    r = await _close(http, cursor)
    assert r.status_code == 204 and r.content == b""
    assert not await _pit_alive(client, pit_id)
    assert _pits_open() == held - 1
    assert await _first_page(http, cid) == 200  # the slot is free again


async def _journal(client: AsyncOpenSearch, cid: str) -> None:
    for i in range(3):
        await append_field_change(
            client,
            actor="u-close-actor",
            action="assign",
            entity_type="finding",
            entity_id=f"fk-{cid}-{i}",
            field="assignee",
            old_value=None,
            new_value="u-close-actor",
            revision=1,
            cluster_id=cid,
            finding_key=f"fk-{cid}-{i}",
        )
    await client.indices.refresh(index="system-audit-log-*")


async def _audit_walk(http: httpx.AsyncClient, cid: str) -> str:
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200 and r.json()["next_cursor"]
    return r.json()["next_cursor"]


async def test_your_own_audit_walk_closes_too(env) -> None:
    login, client, _ = env
    cid = f"c-close-{uuid.uuid4().hex[:8]}"
    await _journal(client, cid)
    http = await login()

    cursor = await _audit_walk(http, cid)
    assert (await _close(http, cursor)).status_code == 204
    assert not await _pit_alive(client, cursor_pit_id(cursor))
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200  # the slot is free again


async def test_another_users_cursor_closes_nothing(env) -> None:
    login, client, _ = env
    cid = f"c-close-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(3))
    alice, bob = await login(), await login()

    cursor = await _findings_walk(alice, cid)
    r = await _close(bob, cursor)
    assert r.status_code == 204  # the same answer as a real close: no oracle for other walks

    assert await _pit_alive(client, cursor_pit_id(cursor))
    assert await _first_page(alice, cid) == 429  # alice still holds her slot
    r = await alice.get("/api/v1/findings", params={"cluster_id": cid, "size": 1, "cursor": cursor})
    assert r.status_code == 200  # and her walk goes on
    assert await _first_page(bob, cid) == 200  # bob's budget was never touched


async def test_an_ended_walk_and_an_expired_one_are_closed_already(env) -> None:
    login, client, _ = env
    cid = f"c-close-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(2))
    http = await login()

    first = await _findings_walk(http, cid)
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1, "cursor": first})
    assert r.status_code == 200
    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "size": 1, "cursor": r.json()["next_cursor"]},
    )
    assert r.status_code == 200 and r.json()["next_cursor"] is None  # the walk ended
    assert (await _close(http, first)).status_code == 204
    assert await _first_page(http, cid) == 200

    # a walk whose PIT went away under its slot: the close still frees the slot
    pit_guard._slots.clear()
    cursor = await _findings_walk(http, cid)
    await client.delete_pit(body={"pit_id": [cursor_pit_id(cursor)]})
    assert await _first_page(http, cid) == 429
    assert (await _close(http, cursor)).status_code == 204
    assert await _first_page(http, cid) == 200


async def test_a_continuation_that_finds_its_pit_gone_frees_the_walk_slot(env) -> None:
    login, client, _ = env
    cid = f"c-close-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(3))
    http = await login()

    cursor = await _findings_walk(http, cid)
    await client.delete_pit(body={"pit_id": [cursor_pit_id(cursor)]})
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1, "cursor": cursor})
    assert r.status_code == 410
    assert await _first_page(http, cid) == 200  # the dead walk's slot went with it


async def test_an_audit_continuation_that_finds_its_pit_gone_frees_the_walk_slot(env) -> None:
    login, client, _ = env
    cid = f"c-close-{uuid.uuid4().hex[:8]}"
    await _journal(client, cid)
    http = await login()

    cursor = await _audit_walk(http, cid)
    await client.delete_pit(body={"pit_id": [cursor_pit_id(cursor)]})
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "size": 1, "cursor": cursor})
    assert r.status_code == 410
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200  # the dead walk's slot went with it


async def test_a_bad_cursor_or_body_is_422(env) -> None:
    login, _, _ = env
    http = await login()
    assert (await _close(http, "garbage!")).status_code == 422
    assert (await _close(http, "")).status_code == 422
    assert (await _close(http, "x" * 4097)).status_code == 422
    r = await http.post("/api/v1/cursors/close", json={"cursor": "e30=", "extra": 1})
    assert r.status_code == 422
    assert (await http.post("/api/v1/cursors/close", json={})).status_code == 422


async def test_it_needs_a_session_and_a_changed_password(env) -> None:
    login, _, transport = env
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as anonymous:
        assert (await _close(anonymous, "garbage!")).status_code == 401
    must_change = await login(must_change=True)
    assert (await _close(must_change, "garbage!")).status_code == 403
