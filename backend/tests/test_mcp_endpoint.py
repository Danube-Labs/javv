"""The MCP endpoint `/api/v1/mcp` (issue 1096 step 2): the gate, the sign-in and both protocol eras.

The gate refuses an `Origin` header (403), a method other than POST (405), a token that is not a
live MCP token (401) and a token past its rate (429), before the SDK sees the request. Behind it,
the SDK answers a 2026-07-28 request and an `initialize` of each older version, with no session
id. The endpoint is not there when `JAVV_MCP_ENABLED` is off. Real OpenSearch."""

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import structlog
from fastapi import FastAPI
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools.base import Tool as SdkTool
from mcp_types import CLIENT_CAPABILITIES_META_KEY, CLIENT_INFO_META_KEY, PROTOCOL_VERSION_META_KEY
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings
from backend.main import create_app
from backend.mcp import auth as mcp_auth
from backend.mcp import server as mcp_server
from backend.mcp import tools
from backend.mcp.tools import RouteError, Tool, build, current_principal, cut_to_fit
from backend.query import pit_guard
from backend.query.search import cursor_pit_id
from backend.routers import dashboards, findings
from os_env import OS_URL, requires_opensearch
from test_findings_route import _rows as _findings
from test_findings_route import _seed

pytestmark = requires_opensearch

PATH = "/api/v1/mcp"
MODERN = "2026-07-28"
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
ACCEPT = "application/json, text/event-stream"
INDEX = "system-mcp-tokens"
PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def _fresh_limits():
    mcp_server._limiter.reset()
    mcp_auth._last_use.clear()
    yield
    mcp_server._limiter.reset()
    mcp_auth._last_use.clear()
    get_settings.cache_clear()


@pytest.fixture
def mcp_on(monkeypatch):
    monkeypatch.setenv("JAVV_MCP_ENABLED", "true")
    get_settings.cache_clear()


async def _token(client: AsyncOpenSearch, *, level: str = "read", **extra: Any) -> tuple[str, str]:
    """A token document as the admin route writes it; returns (name, raw token)."""
    name = f"t-{uuid.uuid4().hex[:12]}"
    raw = mint_token()
    doc = {
        "token_hash": hash_token(raw, pepper=get_settings().secret_key),
        "name": name,
        "level": level,
        "created_by": f"u-mcp-{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now(UTC).isoformat(),
        "expiry": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        "disabled": False,
        "last_used_at": None,
        **extra,
    }
    await client.index(index=INDEX, id=name, body=doc, params={"refresh": "true"})
    return name, raw


@asynccontextmanager
async def _endpoint() -> AsyncIterator[tuple[httpx.AsyncClient, AsyncOpenSearch]]:
    """The app with the endpoint on. The SDK's request manager runs in a task group, which must
    end in the task that started it, so each test enters this itself (an async fixture's
    teardown runs in a different task)."""
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    try:
        async with (
            app.state.mcp.session_manager.run(),
            httpx.AsyncClient(transport=transport, base_url="https://t") as http,
        ):
            yield http, client
    finally:
        await client.close()


def _modern(method: str, params: dict[str, Any] | None = None, /, **headers: str) -> dict[str, Any]:
    p = dict(params or {})
    p["_meta"] = {
        PROTOCOL_VERSION_META_KEY: MODERN,
        CLIENT_INFO_META_KEY: {"name": "test", "version": "0"},
        CLIENT_CAPABILITIES_META_KEY: {},
    }
    h = {
        "accept": ACCEPT,
        "content-type": "application/json",
        "mcp-protocol-version": MODERN,
        "mcp-method": method,
        **headers,
    }
    if method == "tools/call":
        h["mcp-name"] = p["name"]
    return {"json": {"jsonrpc": "2.0", "id": 1, "method": method, "params": p}, "headers": h}


def _bearer(raw: str) -> dict[str, str]:
    return {"authorization": f"Bearer {raw}"}


async def test_the_endpoint_is_not_there_when_the_setting_is_off():
    assert get_settings().mcp_enabled is False  # the default
    app = create_app()
    assert not hasattr(app.state, "mcp")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as h:
        r = await h.post(PATH, **_modern("tools/list"))
    assert r.status_code == 404


async def test_meta_says_if_the_endpoint_is_on(monkeypatch):
    client = AsyncOpenSearch(hosts=[OS_URL])
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
    try:
        for value in (False, True):
            monkeypatch.setenv("JAVV_MCP_ENABLED", str(value).lower())
            get_settings.cache_clear()
            app = create_app()
            app.state.opensearch = client
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
                login = {"username": username, "password": PASSWORD}
                assert (await http.post("/auth/login", json=login)).status_code == 200
                assert (await http.get("/api/v1/meta")).json()["mcp_enabled"] is value
    finally:
        await client.close()


async def test_an_origin_header_gets_403_before_the_token_is_read(mcp_on):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        r = await http.post(
            PATH, **_modern("tools/list", **_bearer(raw), origin="https://evil.example")
        )
        assert r.status_code == 403
        assert r.json()["title"] == "a request with an Origin header is refused"
        assert "https://evil.example" not in r.text


@pytest.mark.parametrize("method", ["GET", "DELETE", "PUT"])
async def test_a_method_other_than_post_gets_405(mcp_on, method):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        r = await http.request(method, PATH, headers={**_bearer(raw), "accept": ACCEPT})
        assert r.status_code == 405
        assert r.headers["allow"] == "POST"


async def test_each_token_that_is_not_live_gets_the_same_401(mcp_on):
    async with _endpoint() as (http, client):
        _, revoked = await _token(client, disabled=True)
        _, expired = await _token(
            client, expiry=(datetime.now(UTC) - timedelta(hours=1)).isoformat()
        )
        scanner = mint_token()  # a scanner token lives in system-tokens, never in system-mcp-tokens
        await client.index(
            index="system-tokens",
            id=f"tok-{uuid.uuid4().hex[:8]}",
            body={
                "token_hash": hash_token(scanner, pepper=get_settings().secret_key),
                "cluster_id": "c-mcp-gate-test",
                "scanner": "trivy",
                "created_at": datetime.now(UTC).isoformat(),
                "disabled": False,
            },
            params={"refresh": "true"},
        )
        cases: list[dict[str, str]] = [
            {},
            {"authorization": "Basic abc"},
            _bearer("not-a-token"),
            _bearer(revoked),
            _bearer(expired),
            _bearer(scanner),
        ]
        for auth in cases:
            r = await http.post(PATH, **_modern("tools/list", **auth))
            assert r.status_code == 401, auth
            assert r.headers["www-authenticate"] == "Bearer"
            assert r.json()["title"] == "invalid token"


async def test_an_mcp_token_does_not_pass_the_scanner_token_check(mcp_on):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        r = await http.get("/api/v1/scan-scope", headers=_bearer(raw))
        assert r.status_code == 401


async def test_a_modern_request_lists_the_tools_with_no_session(mcp_on):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        r = await http.post(PATH, **_modern("tools/list", **_bearer(raw)))
        assert r.status_code == 200, r.text
        assert "mcp-session-id" not in r.headers
        tools = {t["name"]: t for t in r.json()["result"]["tools"]}
        assert "list_clusters" in tools
        assert tools["list_clusters"]["annotations"]["readOnlyHint"] is True


@pytest.mark.parametrize("version", LEGACY)
async def test_a_legacy_initialize_and_its_later_calls_work_with_no_session(mcp_on, version):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        headers = {**_bearer(raw), "accept": ACCEPT, "content-type": "application/json"}
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        r = await http.post(PATH, json=init, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["result"]["protocolVersion"] == version
        assert "mcp-session-id" not in r.headers
        listed = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        r = await http.post(PATH, json=listed, headers={**headers, "mcp-protocol-version": version})
        assert r.status_code == 200, r.text
        assert "list_clusters" in {t["name"] for t in r.json()["result"]["tools"]}


async def test_a_method_header_that_does_not_agree_with_the_body_gets_400(mcp_on):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        r = await http.post(
            PATH, **_modern("tools/list", **_bearer(raw), **{"mcp-method": "tools/call"})
        )
        assert r.status_code == 400


async def test_a_tool_answer_is_one_compact_text_with_no_structured_copy(mcp_on):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        call = {"name": "list_clusters", "arguments": {}}
        r = await http.post(PATH, **_modern("tools/call", call, **_bearer(raw)))
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        assert result.get("isError") is not True
        assert "structuredContent" not in result
        [content] = result["content"]
        assert content["type"] == "text"
        assert "clusters" in json.loads(content["text"])
        text = content["text"]
        assert text == json.dumps(json.loads(text), separators=(",", ":"))  # compact


async def test_a_token_past_its_rate_gets_429(mcp_on, monkeypatch):
    monkeypatch.setenv("JAVV_MCP_RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        statuses = [
            (await http.post(PATH, **_modern("tools/list", **_bearer(raw)))) for _ in range(3)
        ]
        assert [r.status_code for r in statuses] == [200, 200, 429]
        assert statuses[2].headers["retry-after"] == "60"
        _, other = await _token(client)  # each token has its own budget
        assert (await http.post(PATH, **_modern("tools/list", **_bearer(other)))).status_code == 200


async def test_the_last_use_is_written_at_most_one_time_a_minute(mcp_on):
    async with _endpoint() as (http, client):
        name, raw = await _token(client)
        assert (await http.post(PATH, **_modern("tools/list", **_bearer(raw)))).status_code == 200
        first = (await client.get(index=INDEX, id=name))["_source"]["last_used_at"]
        assert first is not None
        await client.update(
            index=INDEX, id=name, body={"doc": {"last_used_at": "2026-01-01T00:00:00Z"}}
        )
        assert (await http.post(PATH, **_modern("tools/list", **_bearer(raw)))).status_code == 200
        second = (await client.get(index=INDEX, id=name))["_source"]["last_used_at"]
        assert second == "2026-01-01T00:00:00Z"  # inside the minute: no second write


@pytest.mark.parametrize(
    ("level", "capabilities"),
    [
        ("read", set()),
        ("write", {"can_triage"}),
        ("write_risk_accept", {"can_triage", "can_accept_audit_final"}),
    ],
)
async def test_the_principal_is_the_token_with_the_permissions_of_its_level(level, capabilities):
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        name, raw = await _token(client, level=level)
        principal = await mcp_auth.resolve(client, f"Bearer {raw}")
        assert principal is not None
        assert principal.user_id == principal.username == f"mcp:{name}"
        assert principal.role is None
        assert set(principal.capabilities) == capabilities
        reader = mcp_auth.reader(principal)
        assert set(reader.capabilities) == capabilities | {
            "can_manage_users",
            "can_manage_settings",
        }
    finally:
        await client.close()


# --- the frame of a tool call: the audit row, errors, the answer cap, open searches --------


def _call(name: str, arguments: dict[str, Any], raw: str) -> dict[str, Any]:
    return _modern("tools/call", {"name": name, "arguments": arguments}, **_bearer(raw))


async def _rows(client: AsyncOpenSearch, actor: str) -> list[dict[str, Any]]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={"query": {"term": {"actor": actor}}, "size": 50, "sort": [{"@timestamp": "asc"}]},
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


async def test_each_call_writes_one_audit_row_with_a_hash_of_its_arguments(mcp_on):
    async with _endpoint() as (http, client):
        name, raw = await _token(client)
        for _ in range(2):
            r = await http.post(PATH, **_call("list_clusters", {"include_retired": True}, raw))
            assert r.status_code == 200, r.text
        rows = await _rows(client, f"mcp:{name}")
    assert len(rows) == 2
    row = rows[0]
    assert row["action"] == "mcp_tool_call"
    assert row["entity_type"] == "mcp_tool"
    assert row["field"] == "result" and row["new_value"] == "ok"
    tool, digest = row["entity_id"].split(" ")
    assert tool == "list_clusters" and digest.startswith("sha256:") and len(digest) == 19
    assert rows[1]["entity_id"] == row["entity_id"]  # the same arguments, the same hash
    assert "cluster_id" not in row  # the call named no cluster


async def test_a_bad_argument_gives_the_field_and_never_the_value(mcp_on):
    async with _endpoint() as (http, client):
        name, raw = await _token(client)
        marker = "SECRET-VALUE-4242"
        r = await http.post(PATH, **_call("list_clusters", {"include_retired": marker}, raw))
        assert r.status_code == 200
        result = r.json()["result"]
        rows = await _rows(client, f"mcp:{name}")
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "invalid arguments" in text and "include_retired" in text
    assert marker not in r.text
    assert [row["new_value"] for row in rows] == ["error 422"]


async def test_an_unknown_tool_is_an_error_with_its_row(mcp_on):
    async with _endpoint() as (http, client):
        name, raw = await _token(client)
        r = await http.post(PATH, **_call("drop_everything", {}, raw))
        rows = await _rows(client, f"mcp:{name}")
    assert r.json()["result"]["isError"] is True
    assert [row["entity_id"].split(" ")[0] for row in rows] == ["unknown_tool"]


async def test_no_data_leaves_when_the_audit_row_cannot_be_written(mcp_on, monkeypatch):
    async def _fails(*_: Any, **__: Any) -> None:
        raise RuntimeError("store refused the row")

    monkeypatch.setattr(mcp_server, "append_tool_call", _fails)
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        r = await http.post(PATH, **_call("list_clusters", {}, raw))
    result = r.json()["result"]
    assert result["isError"] is True
    assert "audit row" in result["content"][0]["text"]
    assert '"clusters"' not in r.text


async def test_each_call_logs_one_line_with_no_argument_value(mcp_on, monkeypatch):
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(mcp_server, "log", structlog.wrap_logger(None, processors=[capture]))
    async with _endpoint() as (http, client):
        name, raw = await _token(client)
        call = _call("list_clusters", {"include_retired": False}, raw)
        assert (await http.post(PATH, **call)).status_code == 200
    [line] = [e for e in capture.entries if e["event"] == "mcp tool call"]
    assert line["tool"] == "list_clusters"
    assert line["principal"] == f"mcp:{name}"
    assert line["result"] == "ok"
    assert len(line["args_hash"]) == 12
    assert "include_retired" not in json.dumps(line)


def test_an_answer_that_fits_is_compact_json_unchanged():
    answer = {"rows": [1, 2, 3], "total": 3}
    assert cut_to_fit(answer, 1000) == '{"rows":[1,2,3],"total":3}'


def test_a_long_answer_loses_rows_from_the_end_of_its_longest_list_and_says_so():
    answer = {"data": [{"i": i, "pad": "x" * 50} for i in range(40)], "tags": ["a"], "total": 40}
    text = cut_to_fit(answer, 1000)
    assert len(text) <= 1000
    cut = json.loads(text)
    kept = cut["cut"]["kept"]
    assert 0 < kept < 40
    assert [row["i"] for row in cut["data"]] == list(range(kept))  # the first rows stay
    assert cut["cut"]["field"] == "data" and cut["cut"]["had"] == 40
    assert cut["tags"] == ["a"] and cut["total"] == 40


def test_a_page_with_a_next_page_is_refused_and_not_cut():
    """The cursor goes on after the last row of the full page: rows cut here would never show."""
    answer = {"data": [{"pad": "x" * 50} for _ in range(40)], "next_cursor": "after-row-39"}
    with pytest.raises(ToolError, match="ask for a smaller size"):
        cut_to_fit(answer, 1000)
    assert json.loads(cut_to_fit({**answer, "data": answer["data"][:5]}, 1000))["next_cursor"]


def test_a_long_list_keeps_the_most_rows_that_fit_in_few_passes(monkeypatch):
    """One pass for each row dropped blocked the event loop for 70 s on 10,000 rows."""
    real = json.dumps
    calls = 0

    def counted(*a: Any, **kw: Any) -> str:
        nonlocal calls
        calls += 1
        return real(*a, **kw)

    monkeypatch.setattr(tools.json, "dumps", counted)
    row = {"pad": "x" * 200}
    text = cut_to_fit({"data": [row] * 10_000}, 50_000)
    assert len(text) <= 50_000
    assert 50_000 - len(text) < len(real(row)) + 1  # one more row would not fit
    assert calls < 30


def test_an_answer_with_no_list_to_cut_is_an_error():
    with pytest.raises(ToolError):
        cut_to_fit({"text": "x" * 2000}, 1000)


async def test_a_route_error_becomes_a_tool_error_with_its_status(mcp_on):
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    tool = build(Tool("get", "d", {"": dashboards.get_dashboard}), app)
    principal = (await _principal(client))[0]
    reset = current_principal.set(principal)
    try:
        with pytest.raises(RouteError) as caught:
            await tool(dashboard_id=f"d-{uuid.uuid4().hex}")
    finally:
        current_principal.reset(reset)
        await client.close()
    assert caught.value.status == 404


async def _principal(client: AsyncOpenSearch) -> tuple[Any, str]:
    name, raw = await _token(client)
    principal = await mcp_auth.resolve(client, f"Bearer {raw}")
    assert principal is not None
    return principal, name


async def test_a_new_first_page_closes_the_open_search_of_the_last_one(mcp_on):
    """Q4: a paged tool keeps one open search for each token. Without the close, an agent that
    starts again on page one holds one more search each time, until the cap refuses it."""
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
    await _seed(client, cluster, _findings(3))
    tool = build(Tool("walk", "d", {"": findings.search_findings}, paged=True), app)
    principal, _ = await _principal(client)
    reset = current_principal.set(principal)
    try:
        first = json.loads(await tool(cluster_id=cluster, size=1))
        assert first["next_cursor"]
        pit = cursor_pit_id(first["next_cursor"])
        assert pit_guard.holds(principal.user_id, pit)
        again = json.loads(await tool(cluster_id=cluster, size=1))
        assert not pit_guard.holds(principal.user_id, pit)  # the last walk is closed
        assert pit_guard.holds(principal.user_id, cursor_pit_id(again["next_cursor"]))
        assert len(pit_guard._slots.get(principal.user_id, [])) == 1
    finally:
        current_principal.reset(reset)
        pit_guard._slots.pop(principal.user_id, None)
        await client.close()


async def _session(http: httpx.AsyncClient, client: AsyncOpenSearch, *, admin: bool) -> None:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "admin" if admin else "viewer",
            "capabilities": ["*"] if admin else [],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-04T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    login = {"username": username, "password": PASSWORD}
    assert (await http.post("/auth/login", json=login)).status_code == 200


async def test_only_can_manage_users_reads_the_rows_of_the_tool_calls(mcp_on):
    """Operator decision B of 2026-11-05: the rows of a token's calls are account rows."""
    cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
    async with _endpoint() as (http, client):
        name, raw = await _token(client)
        call = _call("list_clusters", {}, raw)
        assert (await http.post(PATH, **call)).status_code == 200
        query = {"cluster_id": cluster, "actor": f"mcp:{name}"}
        seen = {}
        for admin in (False, True):
            http.cookies.clear()
            await _session(http, client, admin=admin)
            await client.indices.refresh(index="system-audit-log-*")
            r = await http.get("/api/v1/audit", params=query)
            assert r.status_code == 200, r.text
            seen[admin] = [row["action"] for row in r.json()["data"]]
    assert seen[False] == []
    assert seen[True] == ["mcp_tool_call"]


# --- an argument that a tool does not take (issue 1111) ------------------------------------


def _text(r: httpx.Response) -> tuple[bool, str]:
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    return result.get("isError") is True, result["content"][0]["text"]


async def test_each_tool_refuses_an_argument_that_it_does_not_take(mcp_on):
    """The SDK's argument model drops an argument that it does not know, so the tool answered as
    if the agent had not sent it. Each tool refuses it by its name, never by its value."""
    marker = "SECRET-VALUE-1111"
    async with _endpoint() as (http, client):
        name, raw = await _token(client, level="write_risk_accept")
        refused = {}
        for tool in mcp_server.TOOLS:
            r = await http.post(PATH, **_call(tool.name, {"no_such_argument": marker}, raw))
            error, text = _text(r)
            refused[tool.name] = error and "no_such_argument" in text and "extra_forbidden" in text
            assert marker not in r.text, tool.name
        rows = await _rows(client, f"mcp:{name}")
    assert refused == dict.fromkeys(refused, True)
    assert len(refused) == 24
    assert [row["new_value"] for row in rows] == ["error 422"] * len(refused)


async def test_a_filter_with_a_typo_is_refused_and_not_read_as_no_filter(mcp_on):
    cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
    async with _endpoint() as (http, client):
        await _seed(client, cluster, _findings(2) + _findings(1, severity="CRITICAL"))
        name, raw = await _token(client)
        answers = {}
        for key in ("severity", "severty"):
            args = {"cluster_id": cluster, key: ["critical"]}
            answers[key] = _text(await http.post(PATH, **_call("search_findings", args, raw)))
        rows = await _rows(client, f"mcp:{name}")
    error, text = answers["severity"]
    assert not error, text
    assert len(json.loads(text)["data"]) == 1
    error, text = answers["severty"]
    assert error and "severty" in text
    assert '"data"' not in text
    assert [row["new_value"] for row in rows] == ["ok", "error 422"]


async def test_a_write_tool_with_an_argument_that_it_does_not_take_changes_nothing(mcp_on):
    cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
    [doc] = _findings(1)
    async with _endpoint() as (http, client):
        await _seed(client, cluster, [doc])
        name, raw = await _token(client, level="write")
        args = {"finding_key": doc["finding_key"], "patch": {"assignee": "bob"}, "reason": "x"}
        error, text = _text(await http.post(PATH, **_call("set_triage", args, raw)))
        source = (await client.get(index="findings", id=doc["finding_key"]))["_source"]
        rows = await _rows(client, f"mcp:{name}")
    assert error and "reason" in text
    assert source["assignee"] is None
    assert [(row["action"], row["new_value"]) for row in rows] == [("mcp_tool_call", "error 422")]


async def test_the_input_schema_of_each_tool_refuses_other_arguments(mcp_on):
    async with _endpoint() as (http, client):
        _, raw = await _token(client, level="write_risk_accept")
        r = await http.post(PATH, **_modern("tools/list", **_bearer(raw)))
    schemas = {t["name"]: t["inputSchema"] for t in r.json()["result"]["tools"]}
    assert set(schemas) == {tool.name for tool in mcp_server.TOOLS}
    assert {n: s.get("additionalProperties") for n, s in schemas.items()} == dict.fromkeys(
        schemas, False
    )


def test_the_strict_tool_changes_only_what_it_does_with_other_arguments():
    [search] = [t for t in mcp_server.TOOLS if t.name == "search_findings"]
    loose = SdkTool.from_function(
        build(search, FastAPI()), name=search.name, structured_output=False
    )
    tight = tools.strict(loose)
    assert tight.parameters == {**loose.parameters, "additionalProperties": False}
    assert loose.parameters.get("additionalProperties") is None  # the SDK's own tool is unchanged
    args = {"cluster_id": "c-strict-1", "severity": ["critical"]}
    assert tight.fn_metadata.validate_arguments(args) == loose.fn_metadata.validate_arguments(args)


async def test_the_scheme_name_of_the_header_has_any_case(mcp_on):
    """RFC 7235, section 2.1: the case of a scheme name has no effect (issue 1111)."""
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        for scheme in ("Bearer", "bearer", "BEARER"):
            r = await http.post(PATH, **_modern("tools/list", authorization=f"{scheme} {raw}"))
            assert r.status_code == 200, scheme
        for header in (f"Bearer{raw}", f"Basic {raw}", f"bearer: {raw}", "bearer "):
            r = await http.post(PATH, **_modern("tools/list", authorization=header))
            assert r.status_code == 401, header.split(" ")[0]


class _Store:
    """A store that matches each token, so that only the header check can refuse."""

    def __init__(self) -> None:
        self.searches = 0

    async def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        self.searches += 1
        found = {"token_hash": body["query"]["term"]["token_hash"], "name": "t", "level": "read"}
        return {"hits": {"hits": [{"_source": found}]}}

    async def update(self, **_: Any) -> None:
        return None


@pytest.mark.parametrize(
    "header",
    ["", "Basic abc", "Bearerabc", "Bearer:abc", "Bearer ", "bearer ", f"Bearer {'a' * 506}"],
)
async def test_a_header_that_is_not_a_bearer_token_is_refused_before_the_store(header):
    store = _Store()
    assert await mcp_auth.resolve(store, header) is None
    assert store.searches == 0


async def test_a_bearer_token_of_each_case_reaches_the_store():
    store = _Store()
    for header in ("Bearer abc", "bearer abc", "BeArEr abc", f"Bearer {'a' * 505}"):
        assert await mcp_auth.resolve(store, header) is not None, header[:10]
    assert store.searches == 4
