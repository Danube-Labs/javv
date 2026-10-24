"""M7 slice 1 (#32) — POST /api/v1/reports enqueue + GET status, against real OpenSearch.

Pins: enqueue writes a `pending` `system-reports` doc (auth required — a scheduled export is a read,
same regime as the M6 inline export); bad request shapes 422 at the door; the status view never
leaks the params blob; an unknown id is 404; tenant `cluster_id` is stored for the drain/download.
"""

import uuid

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.reports.models import REPORTS_INDEX
from os_env import OS_URL, requires_opensearch

PASSWORD = "reports-route-password"


pytestmark = requires_opensearch


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login() -> httpx.AsyncClient:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": "custom",
                "capabilities": ["can_export"],  # the export routes need it (issue 243)
                "must_change": False,
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": "2026-07-05T00:00:00+00:00",
            },
            params={"refresh": "true"},
        )
        http = httpx.AsyncClient(transport=transport, base_url="https://t")
        jars.append(http)
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        return http

    yield login, client
    for http in jars:
        await http.aclose()
    await client.close()


def _body(**over) -> dict:
    return {"cluster_id": f"c-rep-{uuid.uuid4().hex[:8]}", **over}


async def test_enqueue_writes_a_pending_doc_and_status_reads_it_back(env) -> None:
    login, client = env
    http = await login()
    body = _body(run_mode="offpeak", params={"format": "csv", "severity": ["critical"]})

    r = await http.post("/api/v1/reports", json=body)
    assert r.status_code == 201
    report_id = r.json()["report_id"]
    assert r.json()["status"] == "pending"

    # the doc is durable with the right shape
    doc = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    assert doc["status"] == "pending" and doc["kind"] == "export"
    assert doc["cluster_id"] == body["cluster_id"] and doc["run_mode"] == "offpeak"
    assert doc["params"] == {
        "format": "csv",
        "severity": ["critical"],
        "state": None,
        "scanner": None,
        "assignee": None,
        "kev": None,
        "fixable": None,
        "disagree": None,
        "cve_id": None,
        "image_digest": None,
        "image_repo": None,
        "namespace": None,
        "ptype": None,  # M8d/#241 — mirrors SearchFilters
        "package_name": None,  # issue 492 — the package lens, an exact term
        "q": None,  # M9b slice 4 — the contains-search lens
        "present": True,
        "new_within_days": None,  # the new-in-range event lens
        "overdue": None,  # issue 363 — the SLA-breached lens
        "unassigned": None,  # issue 349 §1 — the untriaged-backlog lens
        "exclude_severity": None,  # issue 349 — the negation mirror family
        "exclude_state": None,
        "exclude_scanner": None,
        "exclude_assignee": None,
        "exclude_image_repo": None,
        "exclude_namespace": None,
        "exclude_ptype": None,
        "exclude_cve_id": None,  # issue 492 — the last two facets to grow an exclude side
        "exclude_package_name": None,
    }

    # the status view returns the public shape, never the params blob or claim internals
    s = await http.get(f"/api/v1/reports/{report_id}")
    assert s.status_code == 200
    got = s.json()
    assert got["report_id"] == report_id and got["status"] == "pending"
    assert "params" not in got and "attempt_id" not in got


async def test_a_filter_sent_as_one_string_is_stored_as_a_list(env) -> None:
    """issue 949: Schedule export on a screen that sends one string per filter still enqueues,
    and the drain gets the list shape the query reads."""
    login, client = env
    http = await login()
    sent = {
        "assignee": "ana",
        "cve_id": "CVE-2021-3711",
        "image_repo": "registry.local/api",
        "namespace": "payments",
        "ptype": "os",
        "package_name": "openssl",
    }
    r = await http.post("/api/v1/reports", json=_body(params={"format": "csv", **sent}))
    assert r.status_code == 201
    doc = (await client.get(index=REPORTS_INDEX, id=r.json()["report_id"]))["_source"]
    assert {k: doc["params"][k] for k in sent} == {k: [v] for k, v in sent.items()}


async def test_bad_request_shapes_are_422(env) -> None:
    login, _ = env
    http = await login()
    # missing cluster_id
    assert (await http.post("/api/v1/reports", json={})).status_code == 422
    # extra field (extra=forbid)
    assert (await http.post("/api/v1/reports", json=_body(nope=1))).status_code == 422
    # unknown format
    assert (
        await http.post("/api/v1/reports", json=_body(params={"format": "pdf"}))
    ).status_code == 422
    # VEX without a scanner (per-scanner is sacred)
    assert (
        await http.post("/api/v1/reports", json=_body(params={"format": "openvex"}))
    ).status_code == 422
    # a scanner-scoped VEX is fine
    assert (
        await http.post(
            "/api/v1/reports", json=_body(params={"format": "openvex", "scanner": "trivy"})
        )
    ).status_code == 201


@pytest.mark.parametrize(
    "pair",
    [
        {"package_name": ["openssl"], "exclude_package_name": ["zlib"]},
        {"assignee": ["ana"], "unassigned": True},
    ],
)
async def test_a_filter_pair_findings_refuses_is_422_and_queues_nothing(env, pair) -> None:
    """issue 962: Findings answers 422 for these pairs and the search raises on them, so a job
    that held one would fail only when it ran."""
    login, client = env
    http = await login()
    body = _body(params={"format": "csv", **pair})
    r = await http.post("/api/v1/reports", json=body)
    assert r.status_code == 422
    await client.indices.refresh(index=REPORTS_INDEX)
    queued = await client.count(
        index=REPORTS_INDEX, body={"query": {"term": {"cluster_id": body["cluster_id"]}}}
    )
    assert queued["count"] == 0


async def test_unknown_report_is_404_and_auth_is_required(env) -> None:
    login, _ = env
    http = await login()
    assert (await http.get("/api/v1/reports/nope")).status_code == 404

    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http._transport.app),  # type: ignore[attr-defined]
        base_url="https://t",
    )
    assert (await bare.post("/api/v1/reports", json=_body())).status_code == 401
    await bare.aclose()
