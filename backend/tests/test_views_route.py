"""Saved views (M8e/C-6, #242) — slice 1: the store + create/list, against real OpenSearch.

Contract pins: session required; a created view is visible to EVERY authenticated user (the C-6
all-visible ruling) with `owner` = the creator; creation is journaled (D17 journal-first — the
`view_create` row lands); garbage presets (unknown severity/state/scanner, uppercase severity,
extra field, bad ptype shape) → 422 and NEVER stored; the preset mirrors `SearchFilters`
one-to-one (drift here silently breaks the §6 deep-link contract)."""

import uuid
from typing import Any, get_args, get_origin, get_type_hints

import httpx
import pytest
from opensearchpy import AsyncOpenSearch
from pydantic import ValidationError

from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.main import create_app
from backend.query.search import FILTER_PAIRS, SearchFilters
from backend.routers.views import ViewPreset
from os_env import OS_URL, requires_opensearch

PASSWORD = "views-route-password"


pytestmark = requires_opensearch


async def _login(
    http: httpx.AsyncClient,
    client: AsyncOpenSearch,
    *,
    capabilities: list[str] | None = None,
    must_change: bool = False,
) -> str:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom" if capabilities else "viewer",
            "capabilities": capabilities or [],
            "must_change": must_change,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-08T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)  # v14 — the system-views index must exist
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    username = await _login(http, client)
    yield http, client, username
    await http.aclose()
    await client.close()


async def test_requires_a_session(env) -> None:
    _, client, _ = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        assert (await c.get("/api/v1/views")).status_code == 401
        assert (await c.post("/api/v1/views", json={"name": "x"})).status_code == 401


async def test_created_view_is_visible_to_everyone_and_journaled(env) -> None:
    http, client, username = env
    name = f"KEV criticals {uuid.uuid4().hex[:8]}"
    r = await http.post(
        "/api/v1/views",
        json={
            "name": name,
            "description": "critical + kev, trivy lens",
            "preset": {"severity": ["critical"], "kev": True, "scanner": "trivy"},
        },
    )
    assert r.status_code == 201
    view = r.json()
    assert view["owner"] == username  # owner = the creating principal
    assert view["preset"]["severity"] == ["critical"] and view["preset"]["present"] is True

    # a DIFFERENT authenticated user sees it (C-6: all views visible to all users)
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        await _login(c, client)
        listed = (await c.get("/api/v1/views")).json()["views"]
    mine = [v for v in listed if v["view_id"] == view["view_id"]]
    assert mine and mine[0]["name"] == name and mine[0]["owner"] == username

    # D17: the journal row landed (journal-first), carrying the frozen doc
    await client.indices.refresh(index="system-audit-log-*")
    rows = await client.search(
        index="system-audit-log-*",
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": "view_create"}},
                        {"term": {"entity_id": view["view_id"]}},
                    ]
                }
            }
        },
    )
    assert rows["hits"]["total"]["value"] == 1
    assert rows["hits"]["hits"][0]["_source"]["actor"] == username
    # views are fleet-global: no cluster_id, so the Audit screen shows the row (issue 559)
    assert rows["hits"]["hits"][0]["_source"].get("cluster_id") is None


async def test_a_must_change_session_cannot_save_a_view(env) -> None:
    # SEC-6: capability-EXEMPT, so the refusal comes from the session principal (issue 803)
    _, client, _ = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        await _login(c, client, must_change=True)
        r = await c.post("/api/v1/views", json={"name": "locked"})
    assert r.status_code == 403


async def test_garbage_presets_are_422_and_never_stored(env) -> None:
    http, client, _ = env
    marker = f"garbage-{uuid.uuid4().hex[:8]}"
    for preset in (
        {"severity": ["CRITICAL"]},  # uppercase — presets store the lowercase canonical only
        {"severity": ["urgent"]},  # not a canonical bucket
        {"state": ["closed"]},  # not one of the 6 states
        {"scanner": "snyk"},  # per-scanner is sacred — only the two exist
        {"ptype": ["OS Pkgs"]},  # ptype shape (M8d), checked on each value of the list
        {"ptype": "OS Pkgs"},  # the same check when the value comes as one string
        {"bogus_field": 1},  # extra=forbid
    ):
        r = await http.post("/api/v1/views", json={"name": marker, "preset": preset})
        assert r.status_code == 422, f"stored a garbage preset: {preset}"
    listed = (await http.get("/api/v1/views")).json()["views"]
    assert all(v["name"] != marker for v in listed)  # nothing landed


# one valid value for each side of every pair Findings refuses (issue 969)
_PAIR_VALUE: dict[str, Any] = {
    "severity": ["high"],
    "state": ["open"],
    "scanner": "trivy",
    "assignee": ["ana"],
    "image_repo": ["registry.local/api"],
    "namespace": ["payments"],
    "ptype": ["os"],
    "cve_id": ["CVE-2021-3711"],
    "package_name": ["openssl"],
    "unassigned": True,
}


def _pair_preset(first: str, second: str) -> dict[str, Any]:
    return {first: _PAIR_VALUE[first], second: _PAIR_VALUE[second.removeprefix("exclude_")]}


def test_every_pair_findings_refuses_has_a_value_here() -> None:
    assert {n for pair in FILTER_PAIRS for n in pair if not n.startswith("exclude_")} == set(
        _PAIR_VALUE
    )


@pytest.mark.parametrize(("first", "second"), FILTER_PAIRS)
def test_a_preset_refuses_every_pair_findings_refuses(first: str, second: str) -> None:
    with pytest.raises(ValidationError, match=f"{first} and {second} are mutually exclusive"):
        ViewPreset.model_validate(_pair_preset(first, second))
    ViewPreset.model_validate({first: _pair_preset(first, second)[first]})
    ViewPreset.model_validate({second: _pair_preset(first, second)[second]})


async def test_a_pair_findings_refuses_is_422_and_stores_nothing(env) -> None:
    """issue 969: a view that Findings answers with 422 is not stored, on create or on edit.
    The first pair is the body Save view sends for Assignee with the Unassigned flag."""
    http, _, _ = env
    view = await _create(http, f"pairs-{uuid.uuid4().hex[:8]}", severity=["critical"])
    marker = f"pair-{uuid.uuid4().hex[:8]}"
    for preset in (
        {"assignee": ["ana"], "unassigned": True},
        {"cve_id": ["CVE-2021-3711"], "exclude_cve_id": ["CVE-2024-0001"]},
        {"package_name": ["openssl"], "exclude_package_name": ["zlib"]},
    ):
        r = await http.post("/api/v1/views", json={"name": marker, "preset": preset})
        assert r.status_code == 422, preset
        r = await http.patch(f"/api/v1/views/{view['view_id']}", json={"preset": preset})
        assert r.status_code == 422, preset
    listed = (await http.get("/api/v1/views")).json()["views"]
    assert all(v["name"] != marker for v in listed)
    stored = next(v for v in listed if v["view_id"] == view["view_id"])
    assert stored["preset"] == view["preset"]


async def test_a_preset_sent_with_one_string_saves_as_a_list(env) -> None:
    """issue 949: Save view on a screen that sends one string per filter still saves, and the
    stored preset has the list shape the findings query reads."""
    http, _, _ = env
    sent = {
        "assignee": "ana",
        "cve_id": "CVE-2021-3711",
        "image_repo": "registry.local/api",
        "namespace": "payments",
        "ptype": "os",
        "exclude_package_name": "openssl",
    }
    view = await _create(http, f"one-{uuid.uuid4().hex[:8]}", **sent)
    assert {k: view["preset"][k] for k in sent} == {k: [v] for k, v in sent.items()}
    listed = (await http.get("/api/v1/views")).json()["views"]
    stored = next(v for v in listed if v["view_id"] == view["view_id"])
    assert {k: stored["preset"][k] for k in sent} == {k: [v] for k, v in sent.items()}


def test_one_string_still_meets_the_value_checks() -> None:
    # the string is read as a list first, so it fails the value check, not the list check
    for preset, kind in (
        ({"ptype": "OS Pkgs"}, "string_pattern_mismatch"),
        ({"namespace": "x" * 257}, "string_too_long"),
    ):
        with pytest.raises(ValidationError) as err:
            ViewPreset.model_validate(preset)
        assert err.value.errors()[0]["type"] == kind, preset


def test_preset_mirrors_search_filters_one_to_one() -> None:
    """Drift here silently breaks the deep-link contract (SCREENS §6): a preset must map
    onto the findings query params exactly — same rule as the ExportParams mirror."""
    assert set(ViewPreset.model_fields) == set(SearchFilters.__dataclass_fields__)
    # and the same SHAPE (issue 949): a field that holds one string here but a list in
    # SearchFilters would save a view the findings query cannot read
    filter_types = get_type_hints(SearchFilters)
    for name, field in ViewPreset.model_fields.items():
        assert _takes_a_list(field.annotation) == _takes_a_list(filter_types[name]), name


def _takes_a_list(annotation: Any) -> bool:
    return any(get_origin(a) is list for a in (get_args(annotation) or (annotation,)))


# --- slice 2: owner-or-admin mutations + the deep-link round-trip ------------------------------


async def _create(http: httpx.AsyncClient, name: str, **preset) -> dict:
    r = await http.post("/api/v1/views", json={"name": name, "preset": preset})
    assert r.status_code == 201
    return r.json()


async def test_owner_or_admin_mutation_matrix(env) -> None:
    """The IDOR case (bolt DoD): non-owner PATCH/DELETE → 403; the owner edits; an admin
    overrides; `owner` is unrepresentable in the patch body (immutable after create)."""
    http, client, owner = env
    view = await _create(http, f"matrix-{uuid.uuid4().hex[:8]}", severity=["critical"])
    vid = view["view_id"]

    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        await _login(c, client)  # a different plain user — neither owner nor admin
        assert (await c.patch(f"/api/v1/views/{vid}", json={"name": "hijack"})).status_code == 403
        assert (await c.delete(f"/api/v1/views/{vid}")).status_code == 403

    # the owner edits; owner stays the creator; a patch naming `owner` is unrepresentable (422)
    r = await http.patch(f"/api/v1/views/{vid}", json={"name": "renamed", "preset": {"kev": True}})
    assert r.status_code == 200
    assert r.json()["name"] == "renamed" and r.json()["owner"] == owner
    assert r.json()["preset"]["kev"] is True and r.json()["preset"]["severity"] is None
    assert (await http.patch(f"/api/v1/views/{vid}", json={"owner": "me"})).status_code == 422

    # an admin (can_manage_settings) overrides both mutations; the delete is journaled
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        admin = await _login(c, client, capabilities=["can_manage_settings"])
        r = await c.patch(f"/api/v1/views/{vid}", json={"description": "admin touch"})
        assert r.status_code == 200 and r.json()["owner"] == owner  # override ≠ ownership
        assert (await c.delete(f"/api/v1/views/{vid}")).status_code == 204
    listed = (await http.get("/api/v1/views")).json()["views"]
    assert all(v["view_id"] != vid for v in listed)
    await client.indices.refresh(index="system-audit-log-*")
    rows = await client.search(
        index="system-audit-log-*",
        body={
            "query": {
                "bool": {
                    "filter": [{"term": {"action": "view_delete"}}, {"term": {"entity_id": vid}}]
                }
            }
        },
    )
    assert rows["hits"]["total"]["value"] == 1
    assert rows["hits"]["hits"][0]["_source"]["actor"] == admin  # the frozen doc rides the row

    # unknown id → 404 for both
    assert (await http.patch(f"/api/v1/views/{vid}", json={"name": "x"})).status_code == 404
    assert (await http.delete(f"/api/v1/views/{vid}")).status_code == 404


async def test_concurrent_edit_is_a_409_never_a_silent_overwrite(env) -> None:
    http, client, _ = env
    view = await _create(http, f"cas-{uuid.uuid4().hex[:8]}")
    # someone else moves the doc between our (hypothetical) read and write — simulate by a
    # direct store touch, then PATCH normally: the route re-reads, so to force the CAS window
    # we patch twice from two stale snapshots via raw seq_no writes instead. Simplest reliable
    # probe: the route's own CAS is exercised by racing two PATCHes.
    import asyncio

    r1, r2 = await asyncio.gather(
        http.patch(f"/api/v1/views/{view['view_id']}", json={"name": "racer-one"}),
        http.patch(f"/api/v1/views/{view['view_id']}", json={"name": "racer-two"}),
    )
    codes = sorted((r1.status_code, r2.status_code))
    assert codes in ([200, 200], [200, 409])  # both may serialize cleanly; a loser is 409, never
    # a 500 and never a silent lost update — the winner's name is what the store holds
    final = [
        v
        for v in (await http.get("/api/v1/views")).json()["views"]
        if v["view_id"] == view["view_id"]
    ][0]
    assert final["name"] in ("racer-one", "racer-two")


async def test_saved_preset_round_trips_to_findings_query_params(env) -> None:
    """The §6 deep-link contract: a stored preset's non-null fields ARE valid /findings query
    params, and the view's lens returns exactly the rows the same direct query returns."""
    import json as _json
    from pathlib import Path

    from backend.models.envelope import IngestEnvelope
    from backend.services.ingest import ingest_envelope

    http, client, _ = env
    cid = f"c-views-{uuid.uuid4().hex[:8]}"
    golden = _json.loads(
        (Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text()
    )
    golden["cluster_id"] = cid
    await ingest_envelope(client, IngestEnvelope.model_validate(golden))
    await client.indices.refresh(index="findings")

    view = await _create(
        http, f"rt-{uuid.uuid4().hex[:8]}", severity=["low"], scanner="trivy", ptype=["os"]
    )
    params = {k: v for k, v in view["preset"].items() if v is not None}
    assert params.pop("present") is True  # the default rides the preset explicitly
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 200, **params})
    assert r.status_code == 200
    via_view = r.json()

    direct = await http.get(
        "/api/v1/findings",
        params={
            "cluster_id": cid,
            "size": 200,
            "severity": ["low"],
            "scanner": "trivy",
            "ptype": "os",
        },
    )
    assert via_view["total"] == direct.json()["total"] and via_view["total"]["value"] > 0
    assert [d["finding_key"] for d in via_view["data"]] == [
        d["finding_key"] for d in direct.json()["data"]
    ]


def test_golden_preset_serialization_is_pinned() -> None:
    """Presets outlive UI versions — accidental serialization drift (renamed field, changed
    default) breaks every stored view. The golden pins the exact shape."""
    import json as _json
    from pathlib import Path

    golden = _json.loads((Path(__file__).parent / "fixtures/view-preset-golden.json").read_text())
    assert ViewPreset().model_dump() == golden["default"]
    populated = ViewPreset(
        severity=["critical", "high"],
        state=["open"],
        scanner="trivy",
        kev=True,
        ptype=["os"],
        namespace=["team-a"],
        package_name=["zlib"],
    )
    assert populated.model_dump() == golden["populated"]
    negated = ViewPreset(
        exclude_severity=["low", "negligible"],
        exclude_namespace=["kube-system"],
        exclude_cve_id=["CVE-2021-3711"],
        exclude_package_name=["openssl"],
        state=["open"],
    )
    assert negated.model_dump() == golden["negated"]


async def test_v2_workbench_capture_round_trips_and_stamps_schema(env) -> None:
    """Schema v2 (M9f slice 4): the findings-workbench capture rides the view — columns in
    order, density, sort, the RELATIVE window. Cluster-agnostic by shape: no cluster_id and
    no absolute t are representable (extra=forbid)."""
    http, _client, _username = env
    r = await http.post(
        "/api/v1/views",
        json={
            "name": f"wb {uuid.uuid4().hex[:8]}",
            "preset": {"exclude_severity": ["low"]},
            "workbench": {
                "columns": ["vulnerability", "severity", "image"],
                "dense": True,
                "sort": "first_seen_at",
                "order": "desc",
                "window_days": 7,
            },
        },
    )
    assert r.status_code == 201
    view = r.json()
    assert view["schema_version"] == 2
    assert view["workbench"]["columns"] == ["vulnerability", "severity", "image"]
    assert view["workbench"]["window_days"] == 7

    # v1-style create still works — workbench defaults to the all-None blob
    r2 = await http.post("/api/v1/views", json={"name": f"v1 {uuid.uuid4().hex[:8]}"})
    assert r2.status_code == 201
    assert r2.json()["workbench"] == {
        "columns": None,
        "dense": None,
        "sort": None,
        "order": None,
        "window_days": None,
    }

    # the capture is cluster-agnostic BY SHAPE — a cluster_id is unrepresentable
    bad = await http.post(
        "/api/v1/views",
        json={"name": "x", "workbench": {"cluster_id": "c-1"}},
    )
    assert bad.status_code == 422

    # PATCH replaces the whole blob (same rule as preset)
    vid = view["view_id"]
    r3 = await http.patch(f"/api/v1/views/{vid}", json={"workbench": {"dense": False}})
    assert r3.status_code == 200
    assert r3.json()["workbench"]["dense"] is False
    assert r3.json()["workbench"]["columns"] is None  # whole-blob replace, not a merge
