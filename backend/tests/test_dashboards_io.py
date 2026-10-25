"""Dashboard files (issue 440, slice S6): export and import as NDJSON, against real OpenSearch.

Contract pins: the export gives only what the caller can see, needs no `can_export` (D7), names
no owner or author, and ends with a summary line (D5). The import needs `can_edit_dashboards`,
makes the caller the owner and ignores the authors of the file (D6, risk 3), checks each line
with the model of a create, gives 409 for an id that exists and a new id with `copy`, never
sends a value of the file back (issue 842), and refuses a file over the limit before it writes."""

import json
import uuid
from typing import Any

import httpx
import pytest

import test_dashboards_route
from backend.core.settings import Settings
from backend.routers import dashboards_io
from test_dashboards_route import ADMIN, EDIT, _audit_rows, _create, _panel

env = test_dashboards_route.env  # the signed-in users of the route tests

NDJSON = {"content-type": "application/x-ndjson"}


def _lines(r: httpx.Response) -> list[dict[str, Any]]:
    return [json.loads(line) for line in r.text.splitlines()]


def _file(*objs: dict[str, Any]) -> str:
    return "\n".join(json.dumps(o) for o in objs) + "\n"


def _line(**over: Any) -> dict[str, Any]:
    return {
        "dashboard_id": uuid.uuid4().hex,
        "schema_version": 1,
        "name": f"d-{uuid.uuid4().hex[:8]}",
        "panels": [_panel()],
        **over,
    }


async def _import(http: httpx.AsyncClient, body: str, **params: Any) -> httpx.Response:
    return await http.post("/api/v1/dashboards/import", content=body, headers=NDJSON, params=params)


# --- export -------------------------------------------------------------------------------


async def test_the_export_gives_what_the_user_sees_and_a_summary(env) -> None:
    user, _ = env
    owner = await user(EDIT)
    shared = await _create(owner, sharing="everyone")
    private = await _create(owner)

    viewer = await user([], role="viewer")  # no can_export, no can_edit_dashboards (D7)
    nobody = uuid.uuid4().hex
    r = await viewer.get(
        "/api/v1/dashboards/export.ndjson",
        params={"dashboard_id": [shared["dashboard_id"], private["dashboard_id"], nobody]},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    *dashboards, summary = _lines(r)
    assert [d["dashboard_id"] for d in dashboards] == [shared["dashboard_id"]]
    # a dashboard the viewer cannot see reads the same as one that does not exist (Q3)
    assert summary == {
        "exported_count": 1,
        "missing_ids": [private["dashboard_id"], nobody],
    }


async def test_an_exported_line_names_nobody(env) -> None:
    user, _ = env
    owner = await user(EDIT)
    made = await _create(owner)
    r = await owner.get(
        "/api/v1/dashboards/export.ndjson", params={"dashboard_id": made["dashboard_id"]}
    )
    line = _lines(r)[0]
    assert set(line) == {
        "dashboard_id",
        "schema_version",
        "name",
        "description",
        "scanner",
        "panels",
        "sharing",
        "roles",
    }
    assert owner.username not in r.text


async def test_the_export_without_ids_gives_each_visible_dashboard(env) -> None:
    user, _ = env
    owner = await user(EDIT)
    mine = {(await _create(owner))["dashboard_id"] for _ in range(2)}
    r = await owner.get("/api/v1/dashboards/export.ndjson")
    *dashboards, summary = _lines(r)
    assert mine <= {d["dashboard_id"] for d in dashboards}
    assert summary["exported_count"] == len(dashboards) and summary["missing_ids"] == []


# --- import -------------------------------------------------------------------------------


async def test_an_export_imports_again_with_the_importer_as_owner(env) -> None:
    user, client = env
    author = await user(EDIT)
    made = await _create(author, sharing="everyone", description="the team view")
    exported = (
        await author.get(
            "/api/v1/dashboards/export.ndjson", params={"dashboard_id": made["dashboard_id"]}
        )
    ).text
    importer = await user(EDIT)
    r = await _import(importer, exported, copy="true")
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["created"], out["conflicts"], out["invalid"]) == (1, 0, 0)
    new_id = out["results"][0]["dashboard_id"]
    assert new_id != made["dashboard_id"] and out["results"][0]["status"] == 201

    copy = (await importer.get(f"/api/v1/dashboards/{new_id}")).json()
    assert copy["owner"] == importer.username and copy["created_by"] == importer.username
    assert copy["revision"] == 1
    for key in ("name", "description", "scanner", "panels", "sharing", "roles"):
        assert copy[key] == made[key], key
    rows = await _audit_rows(client, new_id)
    assert [row["action"] for row in rows] == ["dashboard_create"]
    assert rows[0]["actor"] == importer.username


async def test_the_import_ignores_a_forged_owner_and_authors(env) -> None:
    user, _ = env
    importer = await user(EDIT)
    line = _line(
        owner="admin",
        created_by="admin",
        updated_by="admin",
        created_at="2020-01-01T00:00:00+00:00",
        updated_at="2020-01-01T00:00:00+00:00",
        revision=99,
    )
    r = await _import(importer, _file(line))
    assert r.json()["results"][0]["status"] == 201
    stored = (await importer.get(f"/api/v1/dashboards/{line['dashboard_id']}")).json()
    assert stored["owner"] == importer.username
    assert stored["created_by"] == stored["updated_by"] == importer.username
    assert stored["revision"] == 1 and not stored["created_at"].startswith("2020")


async def test_a_bad_line_gets_its_own_error_and_the_others_continue(env) -> None:
    user, _ = env
    importer = await user(EDIT)
    good = _line()
    secret = "do-not-echo-this-value"
    body = (
        _file(
            good,
            _line(color=secret),  # an unknown field
            _line(panels=[_panel(secret)]),  # an unknown panel
            _line(panels=[_panel(), _panel("package-type", w=1, y=6)]),  # two on one cell
        )
        + "{not json\n"
        + "\n"  # an empty line is skipped
        + json.dumps({"exported_count": 4, "missing_ids": []})  # the summary of an export
    )
    r = await _import(importer, body)
    assert r.status_code == 200
    out = r.json()
    assert [(x["line"], x["status"]) for x in out["results"]] == [
        (1, 201),
        (2, 422),
        (3, 422),
        (4, 422),
        (5, 422),
    ]
    assert (out["created"], out["conflicts"], out["invalid"]) == (1, 0, 4)
    assert secret not in r.text  # the errors name the place, not the value (issue 842)
    assert (await importer.get(f"/api/v1/dashboards/{good['dashboard_id']}")).status_code == 200


async def test_a_second_import_gives_409_for_each_line_and_copy_makes_new_ones(env) -> None:
    user, client = env
    importer = await user(EDIT)
    first = _line()
    body = _file(first, _line())
    assert (await _import(importer, body)).json()["created"] == 2

    again = (await _import(importer, body)).json()
    assert [x["status"] for x in again["results"]] == [409, 409]
    assert again["created"] == 0 and again["conflicts"] == 2
    # a line that gets 409 writes no audit row
    assert len(await _audit_rows(client, first["dashboard_id"])) == 1

    copies = (await _import(importer, body, copy="true")).json()
    assert [x["status"] for x in copies["results"]] == [201, 201]
    assert not {x["dashboard_id"] for x in copies["results"]} & {
        json.loads(line)["dashboard_id"] for line in body.splitlines()
    }


async def test_an_id_must_have_the_shape_that_create_gives(env) -> None:
    user, _ = env
    importer = await user(EDIT)
    r = await _import(importer, _file(_line(dashboard_id="../../system-users")))
    assert r.json()["results"][0]["status"] == 422


async def test_the_import_needs_the_permission(env) -> None:
    user, _ = env
    viewer = await user([], role="viewer")
    assert (await _import(viewer, _file(_line()))).status_code == 403


async def test_a_file_over_the_byte_limit_gets_413_and_writes_nothing(env, monkeypatch) -> None:
    user, _ = env
    importer = await user(EDIT)
    line = _line()
    body = _file(line)
    small = Settings(dashboard_import_max_bytes=len(body.encode()) - 1)
    monkeypatch.setattr(dashboards_io, "get_settings", lambda: small)
    r = await _import(importer, body)
    assert r.status_code == 413
    assert (await importer.get(f"/api/v1/dashboards/{line['dashboard_id']}")).status_code == 404


async def test_a_file_over_the_line_limit_gets_413_and_writes_nothing(env, monkeypatch) -> None:
    user, _ = env
    importer = await user(EDIT)
    monkeypatch.setattr(dashboards_io, "MAX_DASHBOARDS", 2)
    lines = [_line() for _ in range(3)]
    r = await _import(importer, _file(*lines))
    assert r.status_code == 413
    for line in lines:
        assert (await importer.get(f"/api/v1/dashboards/{line['dashboard_id']}")).status_code == 404


@pytest.mark.parametrize("over", [{"sharing": "roles"}, {"panels": [_panel(h="tall")]}])
async def test_the_import_uses_the_checks_of_a_create(env, over: dict[str, Any]) -> None:
    user, _ = env
    importer = await user(ADMIN)
    r = await _import(importer, _file(_line(**over)))
    assert r.json()["results"][0]["status"] == 422
