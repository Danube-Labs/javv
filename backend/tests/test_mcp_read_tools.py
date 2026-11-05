"""The read tools of the MCP endpoint (issue 1096 step 2, D6): each tool answers what its route
answers for the same arguments, as JSON text.

Each case calls the route with an admin session, then the tool with a read token, in the same
app and on the same seeded cluster. A read token holds no permission, so the equal answers also
show that the tool widens it for the read (`auth.reader`): the audit log shows the account rows
and the dashboard list shows every dashboard. No answer holds a hash. Real OpenSearch."""

import json
import uuid
from collections.abc import Callable, Iterator
from typing import Annotated, Any

import httpx
import pytest
from fastapi import FastAPI, Query

from backend.main import create_app
from backend.mcp.read_tools import READ_TOOLS
from backend.mcp.tools import ReadTool, build
from backend.query.as_of import register_as_of_t
from backend.query.as_of_t import AsOfTQuery
from backend.query.search import cursor_pit_id
from os_env import requires_opensearch
from test_findings_route import _rows as _findings
from test_findings_route import _seed
from test_mcp_endpoint import PATH, _call, _endpoint, _modern, _session, _token
from test_mcp_endpoint import _fresh_limits as _fresh_limits  # an autouse fixture
from test_mcp_endpoint import mcp_on as mcp_on  # the fixture

pytestmark = requires_opensearch

PAST = "2026-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _past_reader():
    register_as_of_t(AsOfTQuery())  # the app's lifespan does it, which these tests do not run
    yield
    register_as_of_t(None)


def get_routes(app: FastAPI) -> Iterator[tuple[str, Callable[..., Any]]]:
    """(path, route function) of each GET route, through the routers that `include_router` adds."""

    def walk(routes: list[Any]) -> Iterator[tuple[str, Callable[..., Any]]]:
        for route in routes:
            if hasattr(route, "original_router"):
                yield from walk(route.original_router.routes)
            elif "GET" in (getattr(route, "methods", None) or ()):
                yield route.path, route.endpoint

    return walk(app.routes)


# (tool, arguments); "{cluster}" is the seeded cluster of the case
CASES: list[tuple[str, dict[str, Any]]] = [
    ("list_clusters", {"include_retired": True}),
    ("search_findings", {"cluster_id": "{cluster}", "severity": ["high"], "size": 20}),
    ("search_findings", {"cluster_id": "{cluster}", "as_of": PAST}),
    ("count_findings", {"cluster_id": "{cluster}", "fields": ["severity", "scanner"]}),
    ("count_findings", {"cluster_id": "{cluster}", "as_of": PAST}),
    ("group_findings", {"cluster_id": "{cluster}", "by": "cve_id"}),
    ("top_images", {"cluster_id": "{cluster}"}),
    ("top_components", {"cluster_id": "{cluster}"}),
    ("list_images", {"cluster_id": "{cluster}"}),
    ("image_timeline", {"cluster_id": "{cluster}", "image_repo": "bench/app", "tag": "1"}),
    ("trends", {"kind": "findings", "cluster_id": "{cluster}", "days": 7}),
    ("trends", {"kind": "scans", "cluster_id": "{cluster}"}),
    ("trends", {"kind": "ingest_failures", "cluster_id": "{cluster}", "as_of": PAST}),
    ("scanner_status", {"kind": "freshness", "cluster_id": "{cluster}"}),
    ("scanner_status", {"kind": "provenance", "cluster_id": "{cluster}"}),
    ("scanner_ingest_failures", {"cluster_id": "{cluster}", "scanner": "trivy"}),
    ("audit_log", {"cluster_id": "{cluster}"}),
    ("audit_log", {"cluster_id": "{cluster}", "as_of": PAST}),
    ("count_audit_log", {"cluster_id": "{cluster}"}),
    ("contributors", {"cluster_id": "{cluster}", "days": 30}),
    ("list_decisions", {"cluster_id": "{cluster}"}),
    ("list_approvals", {"cluster_id": "{cluster}"}),
    ("list_dashboards", {}),
    ("get_dashboard", {"dashboard_id": "{dashboard}"}),
    ("read_settings", {"kind": "about"}),
    ("read_settings", {"kind": "scan_scope", "cluster_id": "{cluster}"}),
    ("read_settings", {"kind": "sla"}),
    ("read_settings", {"kind": "staleness", "cluster_id": "{cluster}"}),
    ("read_settings", {"kind": "retirement"}),
    ("read_settings", {"kind": "data"}),
    ("read_settings", {"kind": "snapshots"}),
    ("read_settings", {"kind": "opensearch"}),
    ("read_settings", {"kind": "jobs"}),
    ("list_accounts", {"kind": "users", "size": 5}),
    ("list_accounts", {"kind": "roles"}),
    ("list_accounts", {"kind": "scanner_tokens", "cluster_id": "{cluster}"}),
    ("list_accounts", {"kind": "mcp_tokens", "size": 1000}),
]


def _fill(args: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
    return {k: v.format(**values) if isinstance(v, str) else v for k, v in args.items()}


def _text(r: httpx.Response) -> str:
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError"), result["content"][0]["text"]
    return result["content"][0]["text"]


def test_each_tool_has_a_case():
    assert {name for name, _ in CASES} == {t.name for t in READ_TOOLS}
    kinds = {(name, args.get("kind", "")) for name, args in CASES}
    assert kinds == {(t.name, kind) for t in READ_TOOLS for kind in t.routes}


def _params() -> list[Any]:
    """A read of data that the whole store shares (users, tokens, dashboards, settings) runs
    serial: a test in another worker could change it between the two reads."""
    return [
        pytest.param(
            name,
            args,
            id=f"{name}-{i}",
            marks=() if args.get("cluster_id") and name != "list_accounts" else pytest.mark.serial,
        )
        for i, (name, args) in enumerate(CASES)
    ]


@pytest.mark.parametrize(("name", "args"), _params())
async def test_the_tool_answers_what_its_route_answers(mcp_on, name, args):
    async with _endpoint() as (http, client):
        cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
        await _seed(client, cluster, _findings(3) + _findings(2, cve="CVE-2024-9001"))
        await _session(http, client, admin=True)
        made = await http.post("/api/v1/dashboards", json={"name": f"mcp {cluster}"})
        assert made.status_code == 201, made.text
        dashboard = made.json()["dashboard_id"]
        try:
            _, raw = await _token(client)
            # the first call notes the token's last use, so the token list does not change after
            assert _text(await http.post(PATH, **_call("list_clusters", {}, raw)))
            filled = _fill(args, {"cluster": cluster, "dashboard": dashboard})
            tool = next(t for t in READ_TOOLS if t.name == name)
            fn = tool.routes[filled.get("kind", "")]
            path = next(p for p, f in get_routes(create_app()) if f is fn)
            query = {k: v for k, v in filled.items() if k != "kind"}
            if "{dashboard_id}" in path:
                path = path.format(dashboard_id=query.pop("dashboard_id"))
            route = await http.get(path, params=query)
            assert route.status_code == 200, route.text
            text = _text(await http.post(PATH, **_call(name, filled, raw)))
            answers = json.loads(text), route.json()
            # a cursor names the open search of its own read, so the two cursors differ
            cursors = [a.pop("next_cursor", None) if isinstance(a, dict) else None for a in answers]
            for cursor in filter(None, cursors):
                await client.delete_pit(body={"pit_id": [cursor_pit_id(cursor)]})
        finally:
            await http.delete(f"/api/v1/dashboards/{dashboard}")
    assert answers[0] == answers[1]
    assert (cursors[0] is None) == (cursors[1] is None)
    assert "token_hash" not in text and "password_hash" not in text


async def _tools(http: httpx.AsyncClient, raw: str) -> dict[str, dict[str, Any]]:
    r = await http.post(PATH, **_modern("tools/list", authorization=f"Bearer {raw}"))
    assert r.status_code == 200, r.text
    return {t["name"]: t for t in r.json()["result"]["tools"]}


async def test_the_findings_page_is_25_at_most_and_the_ui_switch_is_not_offered(mcp_on):
    """Q5 of the step 0 report: a client refused one answer of 92,789 characters. The route
    takes pages of 500; the tool takes 25 at most. `keep_open` is for the screen's Prev button."""
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        schema = (await _tools(http, raw))["search_findings"]["inputSchema"]
        assert "keep_open" not in schema["properties"]
        assert schema["properties"]["size"]["maximum"] == 25
        assert schema["properties"]["size"]["default"] == 20
        cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
        r = await http.post(
            PATH, **_call("search_findings", {"cluster_id": cluster, "size": 26}, raw)
        )
        result = r.json()["result"]
        assert result["isError"] and "size" in result["content"][0]["text"]
        assert "26" not in result["content"][0]["text"]  # a refused value is not sent back


async def test_a_grouped_tool_takes_a_kind_and_only_the_parameters_of_that_kind(mcp_on):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        tools = await _tools(http, raw)
        size = tools["list_accounts"]["inputSchema"]["properties"]["size"]
        assert {"type": "integer", "minimum": 1, "maximum": 1000} in size["anyOf"]  # route limits
        schema = tools["read_settings"]["inputSchema"]
        assert schema["required"] == ["kind"]
        assert set(schema["properties"]["kind"]["enum"]) == set(
            next(t for t in READ_TOOLS if t.name == "read_settings").routes
        )
        for args, refusal in (
            ({"kind": "about", "cluster_id": "c-mcp-x"}, "this kind does not take cluster_id"),
            ({"kind": "scan_scope"}, "this kind needs cluster_id"),
        ):
            result = (await http.post(PATH, **_call("read_settings", args, raw))).json()["result"]
            assert result["isError"] and refusal in result["content"][0]["text"]


async def test_a_read_token_reads_the_account_rows_of_the_audit_log(mcp_on):
    """A read token holds no permission, and the audit log shows account rows only with
    `can_manage_users`: the tool adds it for the read, so the agent sees its own calls."""
    async with _endpoint() as (http, client):
        name, raw = await _token(client)
        cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
        assert _text(await http.post(PATH, **_call("count_findings", {"cluster_id": cluster}, raw)))
        await client.indices.refresh(index="system-audit-log-*")
        text = _text(await http.post(PATH, **_call("audit_log", {"cluster_id": cluster}, raw)))
    rows = [r for r in json.loads(text)["data"] if r["actor"] == f"mcp:{name}"]
    assert [(r["entity_type"], r["action"]) for r in rows] == [("mcp_tool", "mcp_tool_call")]


async def _small(size: Annotated[int, Query(ge=1, le=10)] = 5) -> dict[str, Any]:
    return {"size": size}


async def _large(size: Annotated[int, Query(ge=1, le=500)] = 5) -> dict[str, Any]:
    return {"size": size}


async def _maybe(size: Annotated[int | None, Query(ge=1, le=10)] = None) -> dict[str, Any]:
    return {"size": size}


async def _text_size(size: Annotated[str, Query()] = "5") -> dict[str, Any]:
    return {"size": size}


@pytest.mark.parametrize(("other", "same"), [(_maybe, True), (_large, False), (_text_size, False)])
def test_routes_of_one_tool_give_a_parameter_one_type_and_one_set_of_limits(other, same):
    """Each route keeps its own `Query()`, so the limits are compared, not the objects. A route
    that takes None does not change the type: the tool takes None for every parameter."""
    tool = ReadTool("t", "d", {"a": _small, "b": other})
    if same:
        assert build(tool, create_app())
    else:
        with pytest.raises(TypeError, match=r"t\.size: .* differ"):
            build(tool, create_app())
