"""M7 slice 5 (#32) — the bulk_triage report kind, against real OpenSearch.

Pins (audit A-Mc): enqueue is capability-gated like the inline bulk (can_triage; +accept_final
for risk-accepts) while the export kind stays session-only; the selector FREEZES at enqueue —
findings appearing after enqueue are untouched at drain; the drain applies the frozen set,
journals ONE row (frozen ids + result_hash), finalizes done, rings the bell; the inline 5000
ceiling is LIFTED for scheduled runs (only the 10k freeze cap applies); patch/selector garbage
422s at the door.
"""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.jobs.report_drain import run_job
from backend.main import create_app
from backend.reports.claim import claim_next
from backend.reports.models import DONE, FAILED, REPORTS_INDEX, EnqueueReport, new_report_doc
from os_env import OS_URL, requires_opensearch

PASSWORD = "bulk-kind-password"


pytestmark = requires_opensearch


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login(capabilities: list[str]) -> httpx.AsyncClient:
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


def _finding(cluster_id: str, i: int, cve: str = "CVE-2026-7777") -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "finding_key": f"fk-{cluster_id}-{i}",
        "cluster_id": cluster_id,
        "scanner": "trivy",
        "cve_id": cve,
        "severity": "high",
        "severity_rank": 3,
        "state": "open",
        "vex_justification": None,
        "package_name": "libx",
        "installed_version": "1.0.0",
        "fixed_version": None,
        "fixable": False,
        "kev": False,
        "epss": None,
        "cvss": 7.0,
        "image_repo": "nginx",
        "tag": "1",
        "image_digest": f"sha256:{i:064x}",
        "namespaces": ["default"],
        "assignee": None,
        "first_seen_at": now,
        "last_seen_at": now,
        "last_scan_at": now,
        "present": True,
        "state_decision_id": None,
        "schema_version": 2,
    }


async def _seed_findings(client, cluster_id: str, n: int, **kw) -> None:
    for i in range(n):
        doc = _finding(cluster_id, i, **kw)
        await client.index(index="findings", id=doc["finding_key"], body=doc)
    await client.indices.refresh(index="findings")


def _body(cluster_id: str, **patch) -> dict:
    return {
        "kind": "bulk_triage",
        "cluster_id": cluster_id,
        "bulk_params": {
            "selector": {"cve_id": "CVE-2026-7777"},
            "patch": patch or {"state": "acknowledged"},
        },
    }


async def test_capability_gate_mirrors_inline_bulk(env) -> None:
    login, _ = env
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"

    viewer = await login([])
    assert (await viewer.post("/api/v1/reports", json=_body(cluster_id))).status_code == 403
    # ...but the export kind stays session-only for the same viewer (regression)
    r = await viewer.post("/api/v1/reports", json={"cluster_id": cluster_id})
    assert r.status_code == 201

    triager = await login(["can_triage"])
    assert (await triager.post("/api/v1/reports", json=_body(cluster_id))).status_code == 201
    # risk-accept needs accept_final on top
    r = await triager.post(
        "/api/v1/reports",
        json=_body(cluster_id, state="risk_accepted"),
    )
    assert r.status_code == 403
    lead = await login(["can_triage", "can_accept_audit_final"])
    r = await lead.post("/api/v1/reports", json=_body(cluster_id, state="risk_accepted"))
    assert r.status_code == 201


async def test_garbage_is_422_at_the_door(env) -> None:
    login, _ = env
    http = await login(["can_triage"])
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"

    # unknown state (A-M1 closed vocabulary)
    assert (
        await http.post("/api/v1/reports", json=_body(cluster_id, state="obliterated"))
    ).status_code == 422
    # stale is system-only
    assert (
        await http.post("/api/v1/reports", json=_body(cluster_id, state="stale"))
    ).status_code == 422
    # empty selector refused (whole-cluster guard, A-m8)
    body = _body(cluster_id)
    body["bulk_params"]["selector"] = {}
    assert (await http.post("/api/v1/reports", json=body)).status_code == 422
    # bulk_params required for the kind; forbidden for export
    assert (
        await http.post("/api/v1/reports", json={"kind": "bulk_triage", "cluster_id": cluster_id})
    ).status_code == 422
    # as_of_t is meaningless for a bulk write
    body = _body(cluster_id)
    body["as_of_t"] = "2026-01-01T00:00:00+00:00"
    assert (await http.post("/api/v1/reports", json=body)).status_code == 422


async def test_a_selector_that_fails_its_check_names_the_field_not_the_value(env) -> None:
    login, _ = env
    http = await login(["can_triage"])
    body = _body(f"c-bk-{uuid.uuid4().hex[:8]}")
    sent = "echo-842 " + "y" * 200  # pydantic shortens a long value to its two ends
    body["bulk_params"]["selector"] = {"cve_id": sent, "namespace": sent}

    r = await http.post("/api/v1/reports", json=body)

    detail = r.json()["detail"]
    assert (r.status_code, r.json()["title"]) == (422, "Validation error")
    assert "('body', 'bulk_params', 'selector', 'cve_id')" in detail  # string_too_long
    assert "('body', 'bulk_params', 'selector', 'namespace')" in detail  # extra_forbidden
    assert "echo-842" not in r.text
    assert "'input'" not in detail


async def _queued(client, cluster_id: str) -> list[dict]:
    await client.indices.refresh(index=REPORTS_INDEX)
    rows = await client.search(
        index=REPORTS_INDEX, body={"query": {"term": {"cluster_id": cluster_id}}}
    )
    return [h["_source"] for h in rows["hits"]["hits"]]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("present", False),
        ("cluster_id", "7e57c1a5-0000-4000-8000-000000000002"),
        ("severity", "LOW"),
        ("severity_canonical", "low"),
        ("severity_rank", 2),
        ("not_a_finding_field", "x"),
    ],
)
async def test_a_patch_field_the_inline_route_refuses_queues_nothing(env, field, value) -> None:
    """Issue 854: the drain copies the patch onto each finding, so a field outside BulkPatch would
    hide a finding, lower its severity or move it to another cluster."""
    login, client = env
    http = await login(["can_triage"])
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 1)

    body = _body(cluster_id)
    body["bulk_params"]["patch"][field] = value

    r = await http.post("/api/v1/reports", json=body)

    assert r.status_code == 422
    assert r.json()["title"] == "Validation error"
    assert f"('body', 'bulk_params', 'patch', '{field}')" in r.json()["detail"]
    assert await _queued(client, cluster_id) == []


async def test_a_note_over_the_cap_is_refused_without_the_note(env) -> None:
    login, client = env
    http = await login(["can_triage"])
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 1)
    too_long = "echo-854 " + "n" * 9_992  # 10,001 characters

    r = await http.post("/api/v1/reports", json=_body(cluster_id, notes=too_long))

    assert r.status_code == 422
    assert "('body', 'bulk_params', 'patch', 'notes')" in r.json()["detail"]
    assert "string_too_long" in r.json()["detail"]
    assert "echo-854" not in r.text
    assert await _queued(client, cluster_id) == []

    r = await http.post("/api/v1/reports", json=_body(cluster_id, notes="n" * 10_000))
    assert r.status_code == 201
    [doc] = await _queued(client, cluster_id)
    assert len(doc["params"]["patch"]["notes"]) == 10_000


async def test_a_null_patch_field_is_still_dropped(env) -> None:
    """A scheduled patch has always dropped a `null` field (the inline route keeps one, as an
    unassign); the BulkPatch check keeps that rule, so a stored patch holds only set fields."""
    login, client = env
    http = await login(["can_triage"])
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 1)

    r = await http.post(
        "/api/v1/reports", json=_body(cluster_id, state="acknowledged", assignee=None)
    )

    assert r.status_code == 201
    [doc] = await _queued(client, cluster_id)
    assert doc["params"]["patch"] == {"state": "acknowledged"}


@pytest.mark.parametrize(
    ("patch", "named"),
    [
        ({"state": "acknowledged", "cluster_id": "echo-854-move"}, "cluster_id extra_forbidden"),
        ({"notes": "echo-854 " + "n" * 9_992}, "notes string_too_long"),
        ({"state": "stale"}, "stale is system-only"),
    ],
)
async def test_the_drain_refuses_a_queued_patch_the_route_now_refuses(env, patch, named) -> None:
    """A job queued before the route checked the patch (issue 854) ends failed, writes nothing,
    and its error, which GET /api/v1/reports/{id} shows, names the field but not the value."""
    _, client = env
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 1)
    report_id, doc = new_report_doc(
        EnqueueReport.model_validate(_body(cluster_id)), requested_by="u-drain-854"
    )
    doc["params"] = {
        "selector": {"cve_id": "CVE-2026-7777"},
        "patch": patch,
        "target_ids": [f"fk-{cluster_id}-0"],
    }
    await client.index(index=REPORTS_INDEX, id=report_id, body=doc, params={"refresh": "true"})

    job = await claim_next(client, worker="w-bulk", report_id=report_id)
    assert job is not None and await run_job(client, job) is False

    final = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    assert final["status"] == FAILED
    assert named in final["error"]
    assert "echo-854" not in final["error"]
    finding = (await client.get(index="findings", id=f"fk-{cluster_id}-0"))["_source"]
    assert (finding["cluster_id"], finding["state"], finding.get("notes")) == (
        cluster_id,
        "open",
        None,
    )
    await client.indices.refresh(index="system-audit-log-*")
    rows = await client.count(
        index="system-audit-log-*", body={"query": {"term": {"cluster_id": cluster_id}}}
    )
    assert rows["count"] == 0


async def test_selector_freezes_at_enqueue_and_drain_applies_only_that_set(env) -> None:
    login, client = env
    http = await login(["can_triage"])
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 3)

    r = await http.post("/api/v1/reports", json=_body(cluster_id))
    assert r.status_code == 201 and r.json()["target_count"] == 3
    report_id = r.json()["report_id"]

    # the frozen set is in the job doc — and a LATE-ARRIVING match is not in it
    doc = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    assert len(doc["params"]["target_ids"]) == 3
    late = _finding(cluster_id, 99)
    await client.index(
        index="findings", id=late["finding_key"], body=late, params={"refresh": "true"}
    )

    job = await claim_next(client, worker="w-bulk", report_id=report_id)
    assert job is not None and await run_job(client, job) is True

    final = (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]
    assert final["status"] == DONE and final["chunk_count"] == 3  # count IS the result

    await client.indices.refresh(index="findings")
    for i in range(3):
        state = (await client.get(index="findings", id=f"fk-{cluster_id}-{i}"))["_source"]["state"]
        assert state == "acknowledged"
    late_state = (await client.get(index="findings", id=late["finding_key"]))["_source"]["state"]
    assert late_state == "open"  # frozen semantics: enqueue-time set, not drain-time selector

    # ONE audit row, carrying the frozen ids (D38/H8)
    await client.indices.refresh(index="system-audit-log-*")
    rows = await client.search(
        index="system-audit-log-*",
        body={
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": "bulk_triage"}},
                        {"term": {"cluster_id": cluster_id}},
                    ]
                }
            },
        },
    )
    assert rows["hits"]["total"]["value"] == 1

    # the bell rang for the requester
    bell = await client.search(
        index="system-notifications", body={"query": {"term": {"ref": report_id}}}
    )
    assert bell["hits"]["total"]["value"] == 1


async def test_inline_ceiling_is_lifted_for_scheduled_runs(env, monkeypatch) -> None:
    """The A-Mc lift: a set over JAVV_BULK_INLINE_LIMIT 413s inline but schedules + applies fine."""
    from backend.core.settings import get_settings

    login, client = env
    http = await login(["can_triage"])
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 3)
    monkeypatch.setattr(get_settings(), "bulk_inline_limit", 2)  # 3 targets > inline 2

    inline = await http.post(
        "/api/v1/findings/bulk-triage",
        json={
            "cluster_id": cluster_id,
            "selector": {"cve_id": "CVE-2026-7777"},
            "patch": {"state": "acknowledged"},
        },
    )
    assert inline.status_code == 413  # the inline path still refuses

    r = await http.post("/api/v1/reports", json=_body(cluster_id))
    assert r.status_code == 201 and r.json()["target_count"] == 3  # the queue takes it

    report_id = r.json()["report_id"]
    job = await claim_next(client, worker="w-bulk", report_id=report_id)
    assert job is not None and await run_job(client, job) is True
    await client.indices.refresh(index="findings")
    state = (await client.get(index="findings", id=f"fk-{cluster_id}-0"))["_source"]["state"]
    assert state == "acknowledged"


async def test_freeze_cap_still_applies_to_scheduled_runs(env, monkeypatch) -> None:
    from backend.core.settings import get_settings

    login, client = env
    http = await login(["can_triage"])
    cluster_id = f"c-bk-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 3)
    monkeypatch.setattr(get_settings(), "bulk_max_targets", 2)  # 3 matches > freeze cap 2

    r = await http.post("/api/v1/reports", json=_body(cluster_id))
    assert r.status_code == 413  # selector too broad — bounded memory even for scheduled runs
