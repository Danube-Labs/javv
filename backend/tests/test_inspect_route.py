"""Data inspector route (#406): the allowlist is the security boundary — accept/reject matrix,
credential-index denial, body-key denial, caps (hit ceiling 422, byte cap 413), journal-first,
and the store's own 4xx surfacing verbatim. Real OpenSearch."""

import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"

pytestmark = requires_opensearch


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    http = httpx.AsyncClient(transport=transport, base_url="https://t")
    yield http, client
    await http.aclose()
    await client.close()


async def _login(http: httpx.AsyncClient, client: AsyncOpenSearch, capabilities: list[str]) -> str:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
            "capabilities": capabilities,
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-18T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


async def _inspect(http: httpx.AsyncClient, **body: Any) -> httpx.Response:
    return await http.post("/api/v1/admin/opensearch/inspect", json=body)


async def test_search_runs_and_is_journaled(env):
    http, client = env
    actor = await _login(http, client, ["can_inspect_store"])
    r = await _inspect(
        http, method="POST", path="findings/_search", body={"size": 1, "query": {"match_all": {}}}
    )
    assert r.status_code == 200
    out = r.json()
    assert set(out) == {"took_ms", "bytes", "cap_bytes", "body"}
    assert "hits" in out["body"]
    assert out["bytes"] <= out["cap_bytes"]
    # journal-first (D17): the read left a store_inspect trail naming the actor and the path
    await client.indices.refresh(index="system-audit-log")
    hits = await client.search(
        index="system-audit-log",
        body={
            "size": 1,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": "store_inspect"}},
                        {"term": {"actor": actor}},
                    ]
                }
            },
        },
    )
    assert hits["hits"]["total"]["value"] == 1
    entity = hits["hits"]["hits"][0]["_source"]["entity_id"]
    assert entity.startswith("POST findings/_search sha256:")


@pytest.mark.parametrize("path", ["_cat/indices", "_cat/shards"])
async def test_global_cat_read_lists_only_javv_indices(env, path):
    """Issue 729: an unscoped _cat takes in every index, OpenSearch's security index too, which
    JAVV's role cannot read; the inspector lists JAVV's own indices and nothing else."""
    http, client = env
    other = f"other-{uuid.uuid4().hex[:8]}"
    await client.indices.create(index=other)
    try:
        await _login(http, client, ["can_inspect_store"])
        r = await _inspect(http, method="GET", path=path)
        assert r.status_code == 200
        rows = r.json()["body"]
        assert isinstance(rows, list) and rows and "index" in rows[0]  # format=json, not plaintext
        names = {row["index"] for row in rows}
        assert "findings" in names
        assert other not in names
        assert all(
            name == "findings" or name.startswith(("javv-", "system-", "restored-"))
            for name in names
        )
    finally:
        await client.indices.delete(index=other)


@pytest.mark.parametrize(
    ("method", "path", "body", "fragment"),
    [
        ("POST", "findings/_bulk", None, '"_bulk" is not permitted'),
        ("POST", "findings/_delete_by_query", None, "not permitted"),
        ("POST", "findings/_mapping", None, "GET only"),
        ("GET", "_snapshot/repo", None, "not permitted"),
        ("GET", "a/b/c", None, "global read endpoints"),
        ("POST", "_cluster/health", None, "GET only"),
        ("GET", "_cat/indices", {"q": 1}, "takes no body"),
        ("POST", "system-users/_search", {"query": {"match_all": {}}}, "credential indices"),
        ("POST", "system-*/_search", {"query": {"match_all": {}}}, "credential indices"),
        ("POST", "sys*/_search", {"query": {"match_all": {}}}, "credential indices"),
        # a restore writes `restored-<name>` copies, password hashes included (issue 892)
        ("POST", "restored-system-users/_search", None, "credential indices"),
        ("GET", "restored-system-sessions/_count", None, "credential indices"),
        ("GET", "restored-system-tokens/_mapping", None, "credential indices"),
        ("POST", "restored-*/_search", None, "credential indices"),
        ("POST", "res*/_search", None, "credential indices"),
        ("POST", "findings,restored-system-*/_search", None, "credential indices"),
        (
            "POST",
            "findings/_search",
            {"query": {"bool": {"filter": [{"script": {"script": "1"}}]}}},
            '"script" is not permitted',
        ),
        ("POST", "findings/_search", {"size": 100000}, "hit ceiling"),
        ("GET", "findings/_mapping", {"a": 1}, "_mapping takes no body"),
    ],
)
async def test_allowlist_rejections_carry_verbatim_reasons(env, method, path, body, fragment):
    http, client = env
    await _login(http, client, ["can_inspect_store"])
    r = await _inspect(http, method=method, path=path, body=body)
    assert r.status_code == 422
    assert fragment in r.json()["title"]  # problem+json: the reason rides `title`


@pytest.mark.parametrize("path", ["restored-findings/_search", "restored-javv-images-*/_count"])
async def test_restored_copies_of_other_indices_stay_inspectable(env, path):
    http, client = env
    await _login(http, client, ["can_inspect_store"])
    r = await _inspect(http, method="POST", path=path)
    assert r.status_code != 422  # past the allowlist: the store answers (no such index here)


async def test_capability_gate(env):
    http, client = env
    await _login(http, client, [])  # viewer-shaped: no capability
    r = await _inspect(http, method="GET", path="_cluster/health")
    assert r.status_code == 403


async def test_store_errors_surface_verbatim(env):
    http, client = env
    await _login(http, client, ["can_inspect_store"])
    r = await _inspect(
        http, method="POST", path="findings/_search", body={"query": {"no_such_query": {}}}
    )
    assert r.status_code == 400  # the store's own rejection, not a masked 500


async def test_response_byte_cap_413(env, monkeypatch):
    http, client = env
    await _login(http, client, ["can_inspect_store"])
    monkeypatch.setenv("JAVV_INSPECT_MAX_RESPONSE_BYTES", "10")
    get_settings.cache_clear()
    try:
        r = await _inspect(http, method="GET", path="_cluster/health")
        assert r.status_code == 413
        assert "narrow the query" in r.json()["title"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
