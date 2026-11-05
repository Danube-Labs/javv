"""Each read route of the API has an MCP read tool, or a reason on the list of reads with no tool
(issue 1096, D6). A new GET route fails this test until it gets one or the other, so the agent
never silently misses a read that the screens have."""

from backend.main import create_app
from backend.mcp.read_tools import NO_TOOL, READ_TOOLS
from test_mcp_read_tools import get_routes


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
