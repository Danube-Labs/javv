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

from backend.jobs.staleness import StalenessTimers
from backend.main import create_app
from backend.mcp.read_tools import READ_TOOLS
from backend.mcp.tools import Tool, _plan, build
from backend.query import as_of_t
from backend.query.aggs import FACET_FIELDS, GROUP_FIELDS
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
    ("top_cves", {"cluster_id": "{cluster}", "by": "cve_id"}),
    ("top_cves", {"cluster_id": "{cluster}", "by": "cve_id", "scanner": "grype", "fixable": True}),
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


def _shares_the_store(name: str, args: dict[str, Any]) -> bool:
    """A read of the audit log with no as_of also gives the rows with no cluster, such as the
    sign-ins of every test (issue 1137)."""
    if name in ("audit_log", "count_audit_log") and "as_of" not in args:
        return True
    return not args.get("cluster_id") or name == "list_accounts"


def _params() -> list[Any]:
    """A read of data that the whole store shares (users, tokens, dashboards, settings, the audit
    log) runs serial: a test in another worker could change it between the two reads."""
    return [
        pytest.param(
            name,
            args,
            id=f"{name}-{i}",
            marks=pytest.mark.serial if _shares_the_store(name, args) else (),
        )
        for i, (name, args) in enumerate(CASES)
    ]


def test_the_audit_reads_with_no_as_of_run_serial():
    serial = {
        (p.values[0], "as_of" in p.values[1]): any(m.name == "serial" for m in p.marks)
        for p in _params()
        if p.values[0] in ("audit_log", "count_audit_log")
    }
    assert serial == {
        ("audit_log", False): True,
        ("audit_log", True): False,
        ("count_audit_log", False): True,
    }


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


async def test_search_findings_sends_the_count_of_paths_and_never_the_paths(mcp_on):
    """Issue 1077, D5: the tool reads as the Findings grid does. A page of 25 rows with 64 paths
    each could pass the size that a client takes, so the agent gets `locations_total` only."""
    async with _endpoint() as (http, client):
        cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
        await _seed(client, cluster, _findings(2, locations=["/usr/bin/curl"], locations_total=1))
        _, raw = await _token(client)
        schema = (await _tools(http, raw))["search_findings"]["inputSchema"]
        assert "locations" not in schema["properties"]
        text = _text(
            await http.post(PATH, **_call("search_findings", {"cluster_id": cluster}, raw))
        )
        r = await http.post(
            PATH, **_call("search_findings", {"cluster_id": cluster, "locations": True}, raw)
        )
        refused = r.json()["result"]
    rows = json.loads(text)["data"]
    assert len(rows) == 2
    assert all(r["locations_total"] == 1 and "locations" not in r for r in rows)
    assert "/usr/bin/curl" not in text
    assert refused["isError"] and "locations" in refused["content"][0]["text"]


async def test_top_cves_ranks_the_cve_with_no_by_from_the_agent(mcp_on):
    """Issue 1176 (D7 A): the route ranks only `cve_id` (D5), so the tool takes it by default
    and a call with no `by` answers what the route answers for `by=cve_id`."""
    async with _endpoint() as (http, client):
        cluster = f"c-mcp-{uuid.uuid4().hex[:8]}"
        await _seed(client, cluster, _findings(3) + _findings(2, cve="CVE-2024-9001"))
        await _session(http, client, admin=True)
        _, raw = await _token(client)
        schema = (await _tools(http, raw))["top_cves"]["inputSchema"]
        assert schema["properties"]["by"]["default"] == "cve_id"
        assert "by" not in schema.get("required", [])
        text = _text(await http.post(PATH, **_call("top_cves", {"cluster_id": cluster}, raw)))
        route = await http.get(
            "/api/v1/findings/top-values", params={"cluster_id": cluster, "by": "cve_id"}
        )
    assert json.loads(text) == route.json()
    assert [v["value"] for v in route.json()["values"]] == ["CVE-2024-9000", "CVE-2024-9001"]


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


class _ThreeRowsInThePast(AsOfTQuery):
    async def findings_snapshot(self, client: Any, **kw: Any) -> list[dict[str, Any]]:
        return [{"finding_key": f"k{i}"} for i in range(3)]


async def test_a_past_time_findings_page_with_a_next_page_pages_on(mcp_on):
    """A past-time cursor holds the key of the last row, not an open search, so the tool keeps no
    search for it, and the next page goes on where the first one stopped."""
    register_as_of_t(_ThreeRowsInThePast())
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        args = {"cluster_id": f"c-mcp-{uuid.uuid4().hex[:8]}", "as_of": PAST, "size": 2}
        first = json.loads(_text(await http.post(PATH, **_call("search_findings", args, raw))))
        assert [r["finding_key"] for r in first["data"]] == ["k0", "k1"]
        args["cursor"] = first["next_cursor"]
        last = json.loads(_text(await http.post(PATH, **_call("search_findings", args, raw))))
    assert [r["finding_key"] for r in last["data"]] == ["k2"]
    assert last["next_cursor"] is None


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
    tool = Tool("t", "d", {"a": _small, "b": other})
    if same:
        assert build(tool, create_app())
    else:
        with pytest.raises(TypeError, match=r"t\.size: .* differ"):
            build(tool, create_app())


# --- what each tool takes and gives (issue 1112) --------------------------------------------


def _description(name: str) -> str:
    return next(t for t in READ_TOOLS if t.name == name).description


def _and(names: list[str]) -> str:
    return ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]


def test_group_findings_names_the_fields_that_it_groups_by_also_at_a_past_time():
    text = _description("group_findings")
    assert f"by: {', '.join(GROUP_FIELDS)}" in text
    past = [f for f in GROUP_FIELDS if f not in as_of_t._GROUP_FIELDS]
    assert past and f"With as_of, not {' or '.join(past)}" in text


def test_count_findings_names_the_fields_that_it_counts_also_at_a_past_time():
    text = _description("count_findings")
    assert f"fields: {', '.join(FACET_FIELDS)}" in text
    past = [f for f in FACET_FIELDS if f not in as_of_t._FACET_FIELDS]
    assert past and f"With as_of, not {' or '.join(past)}" in text


def test_search_findings_names_the_fields_that_a_past_time_does_not_record():
    """A past-time row from values for each field of the history: what stays null is what the
    history does not record. `pre_stale_status` is not a field that an agent filters on."""
    occurrence = {
        "finding_key": "fk-1",
        "cluster_id": "c-past-1",
        "scanner": "trivy",
        "image_digest": "sha256:aa",
        "namespaces": ["default"],
        "vuln_id": "CVE-2024-1",
        "package_name": "openssl",
        "package_version": "1.0",
        "severity": "HIGH",
        "cvss": 7.5,
        "fixable": True,
        "fixed_version": "1.1",
        "ptype": "os",
        "locations": ["/usr/lib/libssl.so.1.0"],
        "locations_total": 1,
        "@timestamp": "2026-01-01T00:00:00Z",
        "scan_run_id": "r-1",
        "scan_order": 1,
        "schema_version": 5,
    }
    raw = {
        "occurrence": occurrence,
        "first_seen_at": "2026-01-01T00:00:00Z",
        "present": True,
        "resolved_at": "2026-01-02T00:00:00Z",
    }
    human = {
        "state": "open",
        "vex_justification": "none",
        "assignee": "bob",
        "notes": "n",
        "state_decision_id": "d-1",
    }
    row = as_of_t._finding_row(raw, human)
    nulls = [k for k, v in row.items() if v is None and k != "pre_stale_status"]
    assert f"With as_of, {_and(nulls)} are null" in _description("search_findings")


def test_scanner_status_tells_when_a_scanner_is_late():
    text = _description("scanner_status")
    assert "silent_for_seconds" in text
    assert "freshness_days of read_settings kind staleness" in text
    assert "freshness_days" in StalenessTimers.model_fields


def test_read_settings_names_the_kinds_that_take_a_cluster():
    [tool] = [t for t in READ_TOOLS if t.name == "read_settings"]
    takes = {kind: set(_plan(fn).tool_params()) for kind, fn in tool.routes.items()}
    with_cluster = [kind for kind, params in takes.items() if params == {"cluster_id"}]
    assert {kind for kind, params in takes.items() if params} == set(with_cluster)
    assert f"Kinds {_and(with_cluster)} take a cluster_id" in tool.description
    assert "the other kinds take no parameter" in tool.description


async def test_the_error_of_a_kind_names_the_parameters_that_the_kind_takes(mcp_on):
    async with _endpoint() as (http, client):
        _, raw = await _token(client)
        for name, args, refusal in (
            (
                "read_settings",
                {"kind": "about", "cluster_id": "c-mcp-x"},
                "this kind does not take cluster_id. It takes no parameter",
            ),
            (
                "list_accounts",
                {"kind": "users", "cluster_id": "c-mcp-x"},
                "this kind does not take cluster_id. It takes offset, size",
            ),
        ):
            result = (await http.post(PATH, **_call(name, args, raw))).json()["result"]
            assert result["isError"] and refusal in result["content"][0]["text"], name
