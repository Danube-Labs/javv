"""`can_export` gates every export file (issue 243). The registry in test_rbac_idor_contract.py
covers the gated WRITES only, so the export READS are listed here: each one answers 403 to a user
without the permission and its usual answer to a user with it. The presence check walks
`app.openapi()` (never `app.routes`, issue 540): a new route whose path ends in `export.csv`,
`export.vex` or `/download` fails this file until it is listed below.

Ruling 5 of the issue: the permission stops the files, not the reads. The last test pins that, so
a later change that also closes the reads is a decision, not an accident."""

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.metrics import AUTH_FAILURES
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"
CLUSTER = "c-export-cap"


@dataclass(frozen=True)
class ExportRoute:
    method: str
    path: str
    route_path: str
    allowed: int  # the answer to a user with every other permission the route needs
    also_needs: tuple[str, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] | None = None


EXPORT_ROUTES: tuple[ExportRoute, ...] = (
    ExportRoute(
        "GET",
        "/api/v1/findings/export.csv",
        "/api/v1/findings/export.csv",
        200,
        params={"cluster_id": CLUSTER},
    ),
    ExportRoute(
        "GET",
        "/api/v1/findings/export.vex",
        "/api/v1/findings/export.vex",
        200,
        params={"cluster_id": CLUSTER, "scanner": "trivy"},
    ),
    ExportRoute(
        "GET",
        "/api/v1/audit/export.csv",
        "/api/v1/audit/export.csv",
        200,
        params={"cluster_id": CLUSTER},
    ),
    ExportRoute(
        "GET",
        "/api/v1/contributors/export.csv",
        "/api/v1/contributors/export.csv",
        200,
        params={"cluster_id": CLUSTER},
    ),
    ExportRoute(
        "GET",
        "/api/v1/decisions/approvals/export.csv",
        "/api/v1/decisions/approvals/export.csv",
        200,
        also_needs=("can_accept_audit_final",),
        params={"cluster_id": CLUSTER},
    ),
    ExportRoute(  # past the permission, an unknown report is the usual 404
        "GET",
        "/api/v1/reports/r-unknown/download",
        "/api/v1/reports/{report_id}/download",
        404,
        params={"token": "t"},
    ),
    ExportRoute(
        "POST",
        "/api/v1/reports",
        "/api/v1/reports",
        201,
        body={"kind": "export", "cluster_id": CLUSTER},
    ),
)

_EXPORT_SUFFIXES = ("export.csv", "export.vex", "/download")


def _export_paths_the_app_serves() -> set[tuple[str, str]]:
    spec = create_app().openapi()
    return {
        (method.upper(), path)
        for path, ops in spec["paths"].items()
        for method in ops
        if path.endswith(_EXPORT_SUFFIXES)
    }


def test_the_export_route_walk_is_not_blind() -> None:
    assert len(_export_paths_the_app_serves()) >= 6


def test_each_export_route_the_app_serves_is_listed_here() -> None:
    listed = {(r.method, r.route_path) for r in EXPORT_ROUTES}
    assert not sorted(_export_paths_the_app_serves() - listed)


async def _session(capabilities: list[str]) -> tuple[httpx.AsyncClient, AsyncOpenSearch]:
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
            "capabilities": capabilities,
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-10-24T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return http, client


async def _call(http: httpx.AsyncClient, route: ExportRoute) -> httpx.Response:
    return await http.request(route.method, route.path, params=route.params, json=route.body)


def _ids() -> list[str]:
    return [f"{r.method} {r.route_path}" for r in EXPORT_ROUTES]


@requires_opensearch
@pytest.mark.parametrize("route", EXPORT_ROUTES, ids=_ids())
async def test_without_can_export_the_route_is_403_and_counted(route: ExportRoute) -> None:
    # every other permission, so can_export is the only one missing
    http, client = await _session([*route.also_needs, "can_triage"])
    refusals = AUTH_FAILURES.labels("missing_capability")
    try:
        before = refusals._value.get()
        r = await _call(http, route)
        assert r.status_code == 403
        assert refusals._value.get() == before + 1
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
@pytest.mark.parametrize("route", EXPORT_ROUTES, ids=_ids())
async def test_with_can_export_the_route_gives_its_usual_answer(route: ExportRoute) -> None:
    http, client = await _session([*route.also_needs, "can_export"])
    try:
        assert (await _call(http, route)).status_code == route.allowed
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
async def test_the_approvals_file_also_needs_the_permission_of_its_screen() -> None:
    http, client = await _session(["can_export"])
    try:
        route = next(r for r in EXPORT_ROUTES if r.also_needs)
        assert (await _call(http, route)).status_code == 403
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
async def test_a_user_without_can_export_still_reads_the_findings() -> None:
    http, client = await _session([])
    try:
        r = await http.get("/api/v1/findings", params={"cluster_id": CLUSTER})
        assert r.status_code == 200
    finally:
        await http.aclose()
        await client.close()
