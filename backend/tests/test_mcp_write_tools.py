"""The write tools of the MCP endpoint (issue 1096 step 3, D5).

A write tool runs the permission check of its route on the token's principal as it is, never on
the principal that the read tools widen. A token lists only the tools that its level allows, and
a call to another tool is a tool error with 403 that still writes its audit row. Real OpenSearch."""

from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI

from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.mcp import server as mcp_server
from backend.mcp.auth import LEVEL_CAPABILITIES
from backend.mcp.tools import READ_ONLY, WRITES, RouteError, Tool, build, current_principal
from os_env import requires_opensearch
from test_mcp_endpoint import PATH, _call, _endpoint, _modern, _rows, _token
from test_mcp_endpoint import _bearer as _bearer
from test_mcp_endpoint import _fresh_limits as _fresh_limits  # an autouse fixture
from test_mcp_endpoint import mcp_on as mcp_on  # the fixture

pytestmark = requires_opensearch


def _principal(level: str) -> Principal:
    return Principal(
        user_id="mcp:t", username="mcp:t", role=None, capabilities=LEVEL_CAPABILITIES[level]
    )


async def _triage_route(
    principal: Annotated[Principal, Depends(require_capability("can_triage"))],
) -> dict[str, Any]:
    """A write route as the triage routes declare it: the answer shows what the route saw."""
    return {"capabilities": sorted(principal.capabilities)}


async def _session_route(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, Any]:
    return {}


async def _run(tool: Tool, principal: Principal, **args: Any) -> str:
    reset = current_principal.set(principal)
    try:
        return await build(tool, FastAPI())(**args)
    finally:
        current_principal.reset(reset)


WRITE = Tool("w", "d", {"": _triage_route}, needs="can_triage")


async def test_a_write_route_sees_the_permissions_of_the_level_and_no_more():
    answer = await _run(WRITE, _principal("write"))
    # the read tools add can_manage_users and can_manage_settings; a write never gets them
    assert answer == '{"capabilities":["can_triage"]}'


async def test_a_write_route_runs_its_own_permission_check():
    with pytest.raises(RouteError) as refused:
        await _run(WRITE, _principal("read"))
    assert refused.value.status == 403


def test_a_write_tool_needs_a_route_with_a_permission_check():
    with pytest.raises(TypeError, match="no permission check"):
        build(Tool("w", "d", {"": _session_route}, needs="can_triage"), FastAPI())


def test_a_write_tool_asks_the_client_before_it_runs():
    assert WRITE.annotations == WRITES
    assert WRITES.destructive_hint is True and WRITES.read_only_hint is False
    assert Tool("r", "d", {"": _triage_route}).annotations == READ_ONLY


async def test_a_token_lists_and_calls_only_the_tools_of_its_level(mcp_on, monkeypatch):
    # list_clusters stands in for a write tool: the frame checks the name, not the route
    monkeypatch.setitem(mcp_server._NEEDS, "list_clusters", "can_triage")
    async with _endpoint() as (http, client):
        name, read = await _token(client, level="read")
        _, write = await _token(client, level="write")

        listed = await http.post(PATH, **_modern("tools/list", **_bearer(read)))
        assert "list_clusters" not in {t["name"] for t in listed.json()["result"]["tools"]}
        listed = await http.post(PATH, **_modern("tools/list", **_bearer(write)))
        assert "list_clusters" in {t["name"] for t in listed.json()["result"]["tools"]}

        r = await http.post(PATH, **_call("list_clusters", {}, read))
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        assert result["isError"] is True
        assert result["content"][0]["text"].startswith("403:")
        [row] = await _rows(client, f"mcp:{name}")
        assert row["entity_id"].startswith("list_clusters sha256:")
        assert row["new_value"] == "error 403"
