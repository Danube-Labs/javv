"""Saved dashboards (issue 440, slice S4): the `system-dashboards` store and its routes, against
real OpenSearch.

Contract pins: a session for every read, `can_edit_dashboards` for every write; a new dashboard is
private; the owner shares it with everyone or with roles (D2); a user who cannot see a dashboard
gets 404, as if it did not exist (Q3); only the owner or a holder of `can_manage_settings` changes
or removes it (D3); a write with an old `revision` gets 409 (D4); each write is journaled first;
the panel model refuses an unknown field or panel, a height the catalog does not give, a scanner
setting on a panel without scanner data, a place outside the two columns, two panels on one cell,
and more than 24 panels (Q2, Q5 to Q7)."""

import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.dashboards.catalog import PANELS, CatalogPanel
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "dashboards-route-password"
EDIT = ["can_edit_dashboards"]
ADMIN = ["can_edit_dashboards", "can_manage_settings"]

pytestmark = requires_opensearch


class _User(httpx.AsyncClient):
    """A signed-in client that knows its username."""

    username = ""


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)
    opened: list[_User] = []

    async def user(capabilities: list[str], *, role: str = "custom") -> _User:
        app = create_app()
        app.state.opensearch = client
        http = _User(transport=httpx.ASGITransport(app=app), base_url="https://t")
        opened.append(http)
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": role,
                "capabilities": capabilities,
                "must_change": False,
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": "2026-10-25T00:00:00+00:00",
            },
            params={"refresh": "true"},
        )
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        http.username = username
        return http

    yield user, client
    for http in opened:
        await http.aclose()
    await client.close()


def _panel(panel: str = "findings-summary", **over: Any) -> dict[str, Any]:
    return {"panel": panel, "x": 0, "y": 0, "w": 2, "h": "short", **over}


async def _create(http: httpx.AsyncClient, **over: Any) -> dict[str, Any]:
    body = {"name": f"d-{uuid.uuid4().hex[:8]}", "panels": [_panel()], **over}
    r = await http.post("/api/v1/dashboards", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _audit_rows(client: AsyncOpenSearch, dashboard_id: str) -> list[dict[str, Any]]:
    await client.indices.refresh(index="system-audit-log-*")
    resp = await client.search(
        index="system-audit-log-*",
        body={"query": {"term": {"entity_id": dashboard_id}}, "sort": [{"@timestamp": "asc"}]},
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


# --- access -------------------------------------------------------------------------------


async def test_reads_need_a_session_and_writes_need_the_permission(env) -> None:
    user, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        assert (await c.get("/api/v1/dashboards")).status_code == 401
        assert (await c.get("/api/v1/dashboards/x")).status_code == 401

    viewer = await user([], role="viewer")
    assert (await viewer.get("/api/v1/dashboards")).status_code == 200
    r = await viewer.post("/api/v1/dashboards", json={"name": "x", "panels": []})
    assert r.status_code == 403


async def test_a_new_dashboard_is_private_with_its_owner_and_revision(env) -> None:
    user, client = env
    owner = await user(EDIT)
    made = await _create(owner)
    me = owner.username

    assert made["sharing"] == "private" and made["roles"] == []
    assert made["owner"] == me and made["created_by"] == me and made["updated_by"] == me
    assert made["revision"] == 1 and made["scanner"] == "all"
    # a panel with scanner data follows the dashboard switch unless its owner pins one (Q7)
    assert made["panels"][0]["scanner"] == "dashboard"
    assert (await owner.get(f"/api/v1/dashboards/{made['dashboard_id']}")).status_code == 200
    listed = (await owner.get("/api/v1/dashboards")).json()["dashboards"]
    assert made["dashboard_id"] in {d["dashboard_id"] for d in listed}

    rows = await _audit_rows(client, made["dashboard_id"])
    assert [r["action"] for r in rows] == ["dashboard_create"]
    assert rows[0]["entity_type"] == "dashboard" and rows[0]["actor"] == me


async def test_a_private_dashboard_is_404_for_another_user_and_seen_by_an_admin(env) -> None:
    user, _ = env
    owner = await user(EDIT)
    made = await _create(owner)
    path = f"/api/v1/dashboards/{made['dashboard_id']}"

    other = await user(EDIT, role="triager")
    assert (await other.get(path)).status_code == 404
    assert made["dashboard_id"] not in {
        d["dashboard_id"] for d in (await other.get("/api/v1/dashboards")).json()["dashboards"]
    }
    assert (await other.patch(path, json={"revision": 1, "name": "x"})).status_code == 404
    assert (await other.delete(path, params={"revision": 1})).status_code == 404

    admin = await user(ADMIN)
    assert (await admin.get(path)).status_code == 200
    listed = (await admin.get("/api/v1/dashboards")).json()["dashboards"]
    assert made["dashboard_id"] in {d["dashboard_id"] for d in listed}


async def test_the_owner_shares_with_everyone_or_with_roles(env) -> None:
    user, _ = env
    owner = await user(EDIT)
    for_all = await _create(owner, sharing="everyone")
    for_leads = await _create(owner, sharing="roles", roles=["security_lead"])

    viewer = await user([], role="viewer")
    lead = await user([], role="security_lead")

    def ids(r: httpx.Response) -> set[str]:
        return {d["dashboard_id"] for d in r.json()["dashboards"]}

    assert for_all["dashboard_id"] in ids(await viewer.get("/api/v1/dashboards"))
    assert for_leads["dashboard_id"] not in ids(await viewer.get("/api/v1/dashboards"))
    assert (await viewer.get(f"/api/v1/dashboards/{for_leads['dashboard_id']}")).status_code == 404
    assert for_leads["dashboard_id"] in ids(await lead.get("/api/v1/dashboards"))
    assert (await lead.get(f"/api/v1/dashboards/{for_leads['dashboard_id']}")).status_code == 200


# --- change and remove --------------------------------------------------------------------


async def test_the_owner_changes_it_and_an_old_revision_gets_409(env) -> None:
    user, client = env
    owner = await user(EDIT)
    made = await _create(owner)
    path = f"/api/v1/dashboards/{made['dashboard_id']}"

    r = await owner.patch(path, json={"revision": 1, "name": "renamed", "scanner": "trivy"})
    assert r.status_code == 200, r.text
    changed = r.json()
    assert changed["name"] == "renamed" and changed["scanner"] == "trivy"
    assert changed["revision"] == 2 and changed["created_at"] == made["created_at"]
    assert changed["panels"] == made["panels"]  # a field the change leaves out keeps its value

    stale = await owner.patch(path, json={"revision": 1, "name": "lost update"})
    assert stale.status_code == 409
    assert (await owner.get(path)).json()["name"] == "renamed"
    assert (await owner.delete(path, params={"revision": 1})).status_code == 409

    rows = await _audit_rows(client, made["dashboard_id"])
    assert [r["action"] for r in rows] == ["dashboard_create", "dashboard_update"]


async def test_only_the_owner_or_an_admin_changes_or_removes_it(env) -> None:
    user, client = env
    owner = await user(EDIT)
    made = await _create(owner, sharing="everyone")
    path = f"/api/v1/dashboards/{made['dashboard_id']}"

    other = await user(EDIT)  # sees it, may make dashboards, but is not the owner
    assert (await other.patch(path, json={"revision": 1, "name": "x"})).status_code == 403
    assert (await other.delete(path, params={"revision": 1})).status_code == 403

    admin = await user(ADMIN)
    r = await admin.patch(path, json={"revision": 1, "name": "by the admin"})
    assert r.status_code == 200
    assert r.json()["owner"] == owner.username  # the owner stays
    assert r.json()["updated_by"] == admin.username

    assert (await admin.delete(path, params={"revision": 2})).status_code == 204
    assert (await owner.get(path)).status_code == 404
    rows = await _audit_rows(client, made["dashboard_id"])
    assert [r["action"] for r in rows][-1] == "dashboard_delete"


async def test_a_change_cannot_name_another_owner(env) -> None:
    user, _ = env
    owner = await user(EDIT)
    made = await _create(owner)
    r = await owner.patch(
        f"/api/v1/dashboards/{made['dashboard_id']}", json={"revision": 1, "owner": "someone"}
    )
    assert r.status_code == 422


# --- the panel model ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"panels": [_panel(color="red")]}, id="unknown field on a panel"),
        pytest.param({"panels": [_panel("not-a-panel")]}, id="unknown panel"),
        pytest.param({"panels": [_panel(h="tall")]}, id="a height the catalog does not give"),
        pytest.param({"panels": [_panel(h="medium")]}, id="an unknown height"),
        pytest.param(
            {"panels": [_panel("scan-ingest", scanner="trivy")]},
            id="a scanner setting on a panel without scanner data",
        ),
        pytest.param({"panels": [_panel(x=1, w=2)]}, id="outside the two columns"),
        pytest.param({"panels": [_panel(x=2, w=1)]}, id="a third column"),
        pytest.param({"panels": [_panel(y=-1)]}, id="above the top"),
        pytest.param(
            {"panels": [_panel(), _panel("package-type", w=1, y=6)]},
            id="two panels on one cell",
        ),
        pytest.param(
            {"panels": [_panel("scan-ingest", y=5 * i) for i in range(25)]},
            id="25 panels",
        ),
        pytest.param({"sharing": "roles", "roles": []}, id="shared with no role"),
        pytest.param(
            {"sharing": "everyone", "roles": ["triager"]}, id="roles without role sharing"
        ),
        pytest.param({"scanner": "dashboard"}, id="an unknown dashboard scanner"),
        pytest.param({"name": ""}, id="an empty name"),
        pytest.param({"owner": "someone"}, id="an owner in the body"),
    ],
)
async def test_the_model_refuses(env, body: dict[str, Any]) -> None:
    user, _ = env
    owner = await user(EDIT)
    r = await owner.post("/api/v1/dashboards", json={"name": "d", "panels": [], **body})
    assert r.status_code == 422, r.text


async def test_the_model_takes_panels_side_by_side_and_one_under_another(env) -> None:
    user, _ = env
    owner = await user(EDIT)
    made = await _create(
        owner,
        panels=[
            _panel(),  # rows 0 to 6, both columns
            _panel("package-type", x=0, y=7, w=1),  # rows 7 to 18, the left column
            _panel("findings-by-namespace", x=1, y=7, w=1, h="tall", scanner="grype"),
            _panel("scan-ingest", x=0, y=31, w=2),  # under the tall panel (7 + 24 rows)
        ],
    )
    assert [p["panel"] for p in made["panels"]] == [
        "findings-summary",
        "package-type",
        "findings-by-namespace",
        "scan-ingest",
    ]
    assert made["panels"][2]["scanner"] == "grype" and "scanner" not in made["panels"][3]


async def test_a_change_of_panels_goes_through_the_same_checks(env) -> None:
    user, _ = env
    owner = await user(EDIT)
    made = await _create(owner)
    r = await owner.patch(
        f"/api/v1/dashboards/{made['dashboard_id']}",
        json={"revision": 1, "panels": [_panel(), _panel("package-type", w=1, y=3)]},
    )
    assert r.status_code == 422


async def test_a_new_height_does_not_stop_a_change_that_sends_no_panels(env, monkeypatch) -> None:
    """A panel stores its height name, so a new measurement of the rows changes no saved dashboard
    (ruling of 2026-10-25). A change of the name keeps the stored panels; a change of the panels
    is checked with the new rows."""
    user, _ = env
    owner = await user(EDIT)
    panels = [_panel(), _panel("scan-ingest", y=7)]  # flush: findings-summary is 7 rows
    made = await _create(owner, panels=panels)
    path = f"/api/v1/dashboards/{made['dashboard_id']}"
    monkeypatch.setitem(PANELS, "findings-summary", CatalogPanel({"short": 8}, uses_scanner=True))

    r = await owner.patch(path, json={"revision": 1, "name": "renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["panels"] == made["panels"]

    r = await owner.patch(path, json={"revision": 2, "panels": panels})
    assert r.status_code == 422


async def test_only_a_settings_admin_reads_the_audit_rows_of_dashboards(env) -> None:
    """An audit row carries the whole dashboard, a private one too. Only `can_manage_settings`,
    who sees every dashboard, reads those rows: in the list, the facets and the CSV alike
    (ruling of 2026-10-25). Without the rule, a viewer reads a private dashboard here."""
    user, _ = env
    owner = await user([*EDIT, "can_export"], role="triager")
    made = await _create(owner)
    params = {
        "cluster_id": f"c-dash-{uuid.uuid4().hex[:8]}",
        "actor": owner.username,
        "entity_type": "dashboard",
    }

    async def seen(http: httpx.AsyncClient) -> tuple[list[str], set[str], int]:
        responses = [
            await http.get(f"/api/v1/audit{path}", params=params)
            for path in ("", "/facets", "/export.csv")
        ]
        assert [r.status_code for r in responses] == [200, 200, 200]
        rows, facets, csv = responses
        return (
            [r["entity_id"] for r in rows.json()["data"]],
            {b["key"] for b in facets.json()["facets"]["entity_type"]},
            len(csv.text.strip().splitlines()) - 1,  # minus the header
        )

    nobody: tuple[list[str], set[str], int] = ([], set(), 0)
    assert await seen(await user(["can_export"], role="viewer")) == nobody
    assert await seen(owner) == nobody
    # the account rule is a different one: managing users does not open the dashboard rows
    assert await seen(await user(["can_manage_users", "can_export"])) == nobody
    admin = await user([*ADMIN, "can_export"])
    assert await seen(admin) == ([made["dashboard_id"]], {"dashboard"}, 1)
