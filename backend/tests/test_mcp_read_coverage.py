"""Each read route of the API has an MCP read tool, or a reason on the list of reads with no tool
(issue 1096, D6). A new GET route fails this test until it gets one or the other, so the agent
never silently misses a read that the screens have. The write tools use only the write routes
of D5: an agent never changes users, roles, settings, tokens, retention or jobs."""

from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI

from backend.main import create_app
from backend.mcp.read_tools import NO_TOOL, READ_TOOLS
from backend.mcp.write_tools import WRITE_TOOLS
from test_mcp_read_tools import get_routes

# D5: the state, the assignee and the note of a finding, also in bulk, and the decisions
D5_WRITES = {
    ("PATCH", "/api/v1/findings/{finding_key}/triage"),
    ("POST", "/api/v1/findings/bulk-triage"),
    ("POST", "/api/v1/decisions"),
    ("PATCH", "/api/v1/decisions/{decision_id}"),
    ("POST", "/api/v1/decisions/{decision_id}/revoke"),
}


def _get_paths() -> set[str]:
    paths = create_app().openapi()["paths"]
    return {path for path, methods in paths.items() if "get" in methods}


def test_each_read_route_has_a_tool_or_a_reason():
    routes = dict(get_routes(create_app()))
    tool_fns = {fn for tool in READ_TOOLS for fn in tool.routes.values()}
    with_tool = {path for path, fn in routes.items() if fn in tool_fns}
    assert _get_paths() - with_tool - set(NO_TOOL) == set()


def test_the_list_of_reads_with_no_tool_names_only_reads_with_no_tool():
    routes = dict(get_routes(create_app()))
    tool_fns = {fn for tool in READ_TOOLS for fn in tool.routes.values()}
    assert set(NO_TOOL) - _get_paths() == set()  # a removed or renamed route leaves the list
    assert {path for path in NO_TOOL if routes[path] in tool_fns} == set()
    assert all(reason.strip() for reason in NO_TOOL.values())


def test_each_tool_reads_through_a_get_route():
    routes = {fn for _, fn in get_routes(create_app())}
    for tool in READ_TOOLS:
        for kind, fn in tool.routes.items():
            assert fn in routes, f"{tool.name} {kind or '-'}: {fn.__name__} is not a GET route"


def _write_routes(app: FastAPI) -> Iterator[tuple[tuple[str, str], Any]]:
    """((method, path), route function) of each route that is not a GET."""
    for route in app.routes:
        if hasattr(route, "original_router"):
            yield from _write_routes(route.original_router)  # pyright: ignore[reportAttributeAccessIssue]
            continue
        for method in getattr(route, "methods", None) or ():
            if method not in {"GET", "HEAD"}:
                yield (method, route.path), route.endpoint  # pyright: ignore[reportAttributeAccessIssue]


def test_the_write_tools_use_only_the_write_routes_of_d5():
    by_fn = {fn: key for key, fn in _write_routes(create_app())}
    used = {by_fn.get(fn) for tool in WRITE_TOOLS for fn in tool.routes.values()}
    assert used == D5_WRITES  # each D5 route has a tool, and no tool uses another route
