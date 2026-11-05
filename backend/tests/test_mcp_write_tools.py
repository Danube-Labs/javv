"""The write tools of the MCP endpoint (issue 1096 step 3, D5).

A write tool runs the permission check of its route on the token's principal as it is, never on
the principal that the read tools widen. A token lists only the tools that its level allows, and
a call to another tool is a tool error with 403 that still writes its audit row. Each write makes
the audit rows of its route, with the actor `mcp:<name>`, and keeps the checks of its route: a
write token accepts no risk and leaves a finding with an accepted risk as it is (issue 892).
Real OpenSearch."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI

from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal, get_current_principal
from backend.mcp import server as mcp_server
from backend.mcp.auth import LEVEL_CAPABILITIES
from backend.mcp.tools import READ_ONLY, WRITES, RouteError, Tool, build, current_principal
from backend.mcp.write_tools import WRITE_TOOLS
from backend.triage.service import _STATE_ACTIONS
from os_env import requires_opensearch
from test_findings_route import _rows as _findings
from test_findings_route import _seed
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


WRITE_NAMES = {tool.name for tool in WRITE_TOOLS}


@pytest.mark.parametrize(
    ("level", "seen"),
    [
        ("read", set()),
        ("write", {"set_triage", "bulk_triage", "not_affected_decision"}),
        ("write_risk_accept", WRITE_NAMES),
    ],
)
async def test_each_level_lists_its_write_tools(mcp_on, level, seen):
    async with _endpoint() as (http, client):
        _, raw = await _token(client, level=level)
        r = await http.post(PATH, **_modern("tools/list", **_bearer(raw)))
        listed = {t["name"] for t in r.json()["result"]["tools"]}
        assert listed & WRITE_NAMES == seen
        assert "list_clusters" in listed  # each level reads


async def _finding(client: Any, **row: Any) -> tuple[str, str]:
    """(cluster, finding_key) of one seeded finding with its own CVE."""
    cluster = f"c-mcpw-{uuid.uuid4().hex[:8]}"
    [doc] = _findings(1, cve=f"CVE-2026-{uuid.uuid4().int % 10**6:06d}", **row)
    await _seed(client, cluster, [doc])
    return cluster, doc["finding_key"]


def _answer(r: Any) -> tuple[bool, str]:
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    return bool(result.get("isError")), result["content"][0]["text"]


async def _actions(client: Any, name: str) -> list[str]:
    return [row["action"] for row in await _rows(client, f"mcp:{name}")]


async def test_a_read_token_cannot_call_a_write_tool(mcp_on):
    async with _endpoint() as (http, client):
        _, key = await _finding(client)
        name, raw = await _token(client, level="read")
        args = {"finding_key": key, "patch": {"assignee": "bob"}}
        error, text = _answer(await http.post(PATH, **_call("set_triage", args, raw)))
        assert error and text.startswith("403:")
        assert (await client.get(index="findings", id=key))["_source"]["assignee"] is None
        assert await _actions(client, name) == ["mcp_tool_call"]


async def test_a_write_sets_the_triage_with_the_audit_rows_of_the_route(mcp_on):
    async with _endpoint() as (http, client):
        _, key = await _finding(client)
        name, raw = await _token(client, level="write")
        patch = {"state": "acknowledged", "assignee": "bob", "notes": "checked"}
        args = {"finding_key": key, "patch": patch}
        error, text = _answer(await http.post(PATH, **_call("set_triage", args, raw)))
        assert not error, text
        assert json.loads(text)["finding"]["state"] == "acknowledged"
        rows = await _rows(client, f"mcp:{name}")
        assert sorted(r["action"] for r in rows if r["entity_type"] == "finding") == sorted(
            [_STATE_ACTIONS["acknowledged"], "assign", "note"]
        )
        [call] = [r for r in rows if r["action"] == "mcp_tool_call"]
        assert call["entity_id"].startswith("set_triage sha256:") and call["new_value"] == "ok"


async def test_a_write_token_cannot_accept_a_risk_with_set_triage(mcp_on):
    async with _endpoint() as (http, client):
        _, key = await _finding(client)
        _, raw = await _token(client, level="write")
        args = {"finding_key": key, "patch": {"state": "risk_accepted"}}
        error, text = _answer(await http.post(PATH, **_call("set_triage", args, raw)))
        assert error and "403: risk-accept requires can_accept_audit_final" in text
        assert (await client.get(index="findings", id=key))["_source"]["state"] == "open"


async def test_a_write_token_leaves_a_finding_with_an_accepted_risk_as_it_is(mcp_on):
    async with _endpoint() as (http, client):
        cluster, key = await _finding(client, state="risk_accepted")
        cve = (await client.get(index="findings", id=key))["_source"]["cve_id"]
        _, write = await _token(client, level="write")
        one = {"finding_key": key, "patch": {"state": "acknowledged"}}
        error, text = _answer(await http.post(PATH, **_call("set_triage", one, write)))
        assert error and "403: changing the state of a risk-accepted finding" in text
        bulk = {
            "body": {
                "cluster_id": cluster,
                "selector": {"cve_id": cve},
                "patch": {"state": "acknowledged"},
            }
        }
        error, text = _answer(await http.post(PATH, **_call("bulk_triage", bulk, write)))
        assert error and "403:" in text
        assert (await client.get(index="findings", id=key))["_source"]["state"] == "risk_accepted"
        # the level is the reason: a risk accept token can change it
        _, accept = await _token(client, level="write_risk_accept")
        error, text = _answer(await http.post(PATH, **_call("set_triage", one, accept)))
        assert not error, text


async def test_a_bulk_change_writes_the_bulk_row_of_the_route(mcp_on):
    async with _endpoint() as (http, client):
        cluster = f"c-mcpw-{uuid.uuid4().hex[:8]}"
        cve = f"CVE-2026-{uuid.uuid4().int % 10**6:06d}"
        await _seed(client, cluster, _findings(3, cve=cve))
        name, raw = await _token(client, level="write")
        body = {"cluster_id": cluster, "selector": {"cve_id": cve}, "patch": {"assignee": "bob"}}
        error, text = _answer(await http.post(PATH, **_call("bulk_triage", {"body": body}, raw)))
        assert not error, text
        assert json.loads(text)["count"] == 3
        assert sorted(await _actions(client, name)) == ["bulk_triage", "mcp_tool_call"]


def _payload(cluster: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "cve_id": f"CVE-2026-{uuid.uuid4().int % 10**6:06d}",
        "scope": {},
        "apply_both_scanners": True,
        "justification": "the code is not reachable",
        "cluster_id": cluster,
        **extra,
    }


async def test_a_not_affected_decision_is_made_changed_and_revoked(mcp_on):
    async with _endpoint() as (http, client):
        cluster = f"c-mcpw-{uuid.uuid4().hex[:8]}"
        name, raw = await _token(client, level="write")
        payload = _payload(cluster, "not_affected", vex_justification="component_not_present")
        make = {"kind": "make", "payload": payload}
        error, text = _answer(await http.post(PATH, **_call("not_affected_decision", make, raw)))
        assert not error, text
        made = json.loads(text)["decision"]
        assert made["created_by"] == f"mcp:{name}"
        change = {
            "kind": "change",
            "decision_id": made["decision_id"],
            "body": {"justification": "x"},
        }
        error, text = _answer(await http.post(PATH, **_call("not_affected_decision", change, raw)))
        assert not error, text
        new_id = json.loads(text)["decision"]["decision_id"]
        revoke = {"kind": "revoke", "decision_id": new_id}
        error, text = _answer(await http.post(PATH, **_call("not_affected_decision", revoke, raw)))
        assert not error, text
        actions = [a for a in await _actions(client, name) if a != "mcp_tool_call"]
        assert sorted(actions) == sorted(
            ["decision_create", "decision_revoke", "decision_create", "decision_revoke"]
        )


async def test_the_not_affected_tool_makes_no_risk_accept(mcp_on):
    async with _endpoint() as (http, client):
        cluster = f"c-mcpw-{uuid.uuid4().hex[:8]}"
        _, raw = await _token(client, level="write_risk_accept")
        make = {"kind": "make", "payload": _payload(cluster, "risk_accepted")}
        error, text = _answer(await http.post(PATH, **_call("not_affected_decision", make, raw)))
        assert error and "('payload', 'type')" in text
        change = {"kind": "change", "decision_id": "d", "body": {"type": "ignore_rule"}}
        error, text = _answer(await http.post(PATH, **_call("not_affected_decision", change, raw)))
        assert error and "('body', 'type')" in text


async def test_a_risk_accept_needs_the_risk_accept_level(mcp_on):
    async with _endpoint() as (http, client):
        cluster = f"c-mcpw-{uuid.uuid4().hex[:8]}"
        expiry = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
        make = {"kind": "make", "payload": _payload(cluster, "risk_accepted", expiry=expiry)}
        _, write = await _token(client, level="write")
        error, text = _answer(await http.post(PATH, **_call("risk_accept_decision", make, write)))
        assert error and text.startswith("403:")
        name, accept = await _token(client, level="write_risk_accept")
        error, text = _answer(await http.post(PATH, **_call("risk_accept_decision", make, accept)))
        assert not error, text
        assert json.loads(text)["decision"]["created_by"] == f"mcp:{name}"
        make["payload"]["type"] = "not_affected"
        error, text = _answer(await http.post(PATH, **_call("risk_accept_decision", make, accept)))
        assert error and "('payload', 'type')" in text
