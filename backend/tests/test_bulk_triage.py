"""M5d bulk triage (FR-7/D38-H8/SND-8) — frozen ids, ONE audit row, retry_on_conflict.

Pins: a bulk action over N findings appends EXACTLY ONE `system-audit-log` row carrying the
frozen `target_ids` (+`result_hash`/`result_count`) — never a selector, never a per-finding
fan-out; the apply is bounded-synchronous (audit A-Mc/#189): a set over `JAVV_BULK_INLINE_LIMIT`
→ 413 (narrow / M7), a selector matching over `JAVV_BULK_MAX_TARGETS` → 413 ("selector too broad",
bailed during freeze paging), NO async 202; risk-accept patch is SEC-2-gated; a bulk write racing
a single-triage on an overlapping finding loses no update (SND-8)."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest
import structlog
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.metrics import LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.main import create_app
from backend.triage import bulk_routes
from os_env import OS_URL, requires_opensearch

CID = "c-bulk-triage"
PASSWORD = "bulk-route-password"


pytestmark = requires_opensearch


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login_with(capabilities: list[str]) -> httpx.AsyncClient:
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

    yield login_with, client, app
    for http in jars:
        await http.aclose()
    await client.close()


async def _seed(client, cve: str, n: int) -> list[str]:
    keys = []
    for i in range(n):
        fk = f"fk-{uuid.uuid4().hex[:10]}"
        await client.index(
            index="findings",
            id=fk,
            body={
                "finding_key": fk,
                "cluster_id": CID,
                "scanner": "trivy",
                "cve_id": cve,
                "image_digest": f"sha256:bulk-{i}",
                "namespaces": ["default"],
                "state": "open",
                "vex_justification": None,
                "state_decision_id": None,
                "present": True,
                "severity": "high",
            },
        )
        keys.append(fk)
    await client.indices.refresh(index="findings")
    return keys


def _body(cve: str, **patch) -> dict[str, Any]:
    return {
        "cluster_id": CID,
        "selector": {"cve_id": cve},
        "patch": patch or {"state": "acknowledged"},
    }


async def test_bulk_applies_and_journals_exactly_one_row_with_frozen_ids(env) -> None:
    login_with, client, _ = env
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    keys = await _seed(client, cve, 3)

    r = await http.post("/api/v1/findings/bulk-triage", json=_body(cve))
    assert r.status_code == 200
    assert r.json()["count"] == 3 and r.json()["applied"] is True

    for fk in keys:
        doc = (await client.get(index="findings", id=fk))["_source"]
        assert doc["state"] == "acknowledged"

    await client.indices.refresh(index="system-audit-log")
    rows = await client.search(
        index="system-audit-log*",
        body={
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": "bulk_triage"}},
                        {"term": {"cluster_id": CID}},
                    ]
                }
            },
        },
    )
    ours = [
        h["_source"]
        for h in rows["hits"]["hits"]
        if set(h["_source"]["new_value_json"]["target_ids"]) == set(keys)
    ]
    assert len(ours) == 1  # EXACTLY one row — never a per-finding fan-out (D38/H8)
    row = ours[0]["new_value_json"]
    assert row["result_count"] == 3
    assert sorted(row["target_ids"]) == sorted(keys)  # frozen IDS, not a selector
    assert row["result_hash"]


@pytest.fixture
def captured(monkeypatch):
    """The route's logger, wired straight to a capture. `capture_logs` swaps the GLOBAL config,
    which `create_app()` → `configure_logging()` swaps back, so it only worked while `env` happened
    to build the app first; a logger that owns its processor chain doesn't depend on that order."""
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(bulk_routes, "log", structlog.wrap_logger(None, processors=[capture]))
    return capture.entries


async def test_set_over_inline_limit_is_413_not_async(env, monkeypatch, captured) -> None:
    """A-Mc (audit #189): a frozen set larger than the inline limit but within the freeze cap →
    413 (narrow, or M7's scheduled bulk). NO 202/async path exists any more, and NOTHING is
    applied — a rejected bulk leaves the findings untouched."""
    login_with, client, _ = env
    monkeypatch.setenv("JAVV_BULK_INLINE_LIMIT", "2")  # 3 docs > inline limit, < max_targets
    monkeypatch.setenv("JAVV_BULK_MAX_TARGETS", "100")
    get_settings.cache_clear()
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    keys = await _seed(client, cve, 3)

    before = LIMIT_REJECTIONS.labels("bulk_inline")._value.get()
    r = await http.post("/api/v1/findings/bulk-triage", json=_body(cve))
    assert r.status_code == 413
    assert "inline bulk limit" in r.json()["title"]
    # ops parity (logging.md, issue 523): a cap logs a warning AND bumps its metric
    assert LIMIT_REJECTIONS.labels("bulk_inline")._value.get() == before + 1
    [line] = [e for e in captured if e["event"] == "bulk triage rejected: over the inline limit"]
    assert line["log_level"] == "warning"
    assert (line["targets"], line["limit"]) == (3, 2)
    assert line["cluster_id"] == CID
    for fk in keys:  # nothing applied — no volatile background write
        assert (await client.get(index="findings", id=fk))["_source"]["state"] == "open"


async def test_selector_over_max_targets_is_selector_too_broad_413(
    env, monkeypatch, captured
) -> None:
    """A-Mc (audit #189): a selector matching more than the hard freeze cap → 413 "selector too
    broad", and freeze_targets bails DURING paging (count-don't-collect) — never materializes the
    whole match."""
    login_with, client, _ = env
    monkeypatch.setenv("JAVV_BULK_INLINE_LIMIT", "2")  # keep inline ≤ max_targets (#219 invariant)
    monkeypatch.setenv("JAVV_BULK_MAX_TARGETS", "2")  # 4 docs > the hard freeze cap
    get_settings.cache_clear()
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    keys = await _seed(client, cve, 4)

    before = LIMIT_REJECTIONS.labels("bulk_targets")._value.get()
    r = await http.post("/api/v1/findings/bulk-triage", json=_body(cve))
    assert r.status_code == 413
    assert "selector too broad" in r.json()["title"]
    assert LIMIT_REJECTIONS.labels("bulk_targets")._value.get() == before + 1
    [line] = [e for e in captured if e["event"] == "bulk triage rejected: selector too broad"]
    assert line["log_level"] == "warning"
    assert line["max_targets"] == 2
    assert line["cluster_id"] == CID
    for fk in keys:
        assert (await client.get(index="findings", id=fk))["_source"]["state"] == "open"


async def test_bulk_risk_accept_is_sec2_gated_and_stale_rejected(env) -> None:
    login_with, client, _ = env
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    await _seed(client, cve, 1)

    r = await http.post("/api/v1/findings/bulk-triage", json=_body(cve, state="risk_accepted"))
    assert r.status_code == 403  # SEC-2, same as single triage
    r = await http.post("/api/v1/findings/bulk-triage", json=_body(cve, state="stale"))
    assert r.status_code == 422  # stale is system-only
    r = await http.post("/api/v1/findings/bulk-triage", json={**_body(cve), "patch": {}})
    assert r.status_code == 422  # empty patch


async def test_bulk_unknown_state_is_rejected(env) -> None:
    """A-M1 (audit #185): a bogus target state must 422 at the door — never mass-write junk
    that later 500s the VEX export on an unknown OpenVEX/CycloneDX status."""
    login_with, client, _ = env
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    keys = await _seed(client, cve, 2)

    r = await http.post("/api/v1/findings/bulk-triage", json=_body(cve, state="fixed"))
    assert r.status_code == 422
    for fk in keys:  # nothing was written — the freeze/apply never ran
        assert (await client.get(index="findings", id=fk))["_source"]["state"] == "open"


async def test_bulk_empty_selector_is_rejected(env) -> None:
    """A-m8 (audit #185): an all-null selector must not resolve to the entire cluster."""
    login_with, _, _ = env
    http = await login_with(["can_triage"])
    r = await http.post(
        "/api/v1/findings/bulk-triage",
        json={"cluster_id": CID, "selector": {}, "patch": {"state": "acknowledged"}},
    )
    assert r.status_code == 422


async def test_bulk_overlong_assignee_is_rejected(env) -> None:
    """A-n caps (audit #185): unbounded request strings are rejected (NFR-7)."""
    login_with, _, _ = env
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    r = await http.post("/api/v1/findings/bulk-triage", json=_body(cve, assignee="x" * 5000))
    assert r.status_code == 422


async def test_bulk_racing_single_triage_loses_no_update(env) -> None:
    """SND-8: bulk (assignee) races single-triage (state) on the SAME finding — retry_on_conflict
    resolves both; the final doc carries BOTH writes."""
    login_with, client, _ = env
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    (fk,) = await _seed(client, cve, 1)

    bulk = http.post("/api/v1/findings/bulk-triage", json=_body(cve, assignee="ana"))
    single = http.patch(f"/api/v1/findings/{fk}/triage", json={"state": "acknowledged"})
    r_bulk, r_single = await asyncio.gather(bulk, single)
    assert r_bulk.status_code == 200 and r_single.status_code == 200

    await client.indices.refresh(index="findings")
    doc = (await client.get(index="findings", id=fk))["_source"]
    assert doc["assignee"] == "ana"  # the bulk write survived
    assert doc["state"] == "acknowledged"  # the single write survived


async def test_a_state_change_over_a_risk_accept_needs_the_final_word(env) -> None:
    """issue 892 rulings 6 and 7: a bulk state change whose frozen set holds a risk-accepted
    finding (or a stale one that keeps a risk-accept) is refused whole, with the count; a note
    over the same set is not an undo; a lead may do both."""
    login_with, client, _ = env
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    keys = await _seed(client, cve, 3)
    await client.update(index="findings", id=keys[0], body={"doc": {"state": "risk_accepted"}})
    await client.update(
        index="findings",
        id=keys[1],
        body={"doc": {"state": "stale", "pre_stale_status": "risk_accepted"}},
        params={"refresh": "true"},
    )

    triager = await login_with(["can_triage"])
    r = await triager.post("/api/v1/findings/bulk-triage", json=_body(cve, state="open"))
    assert r.status_code == 403
    assert r.json()["title"].startswith("2 of the 3 selected findings are risk-accepted")

    async def states() -> list[str]:
        return [(await client.get(index="findings", id=k))["_source"]["state"] for k in keys]

    assert await states() == ["risk_accepted", "stale", "open"]  # refused whole: nothing written

    r = await triager.post("/api/v1/findings/bulk-triage", json=_body(cve, notes="seen"))
    assert (r.status_code, r.json()["count"]) == (200, 3)

    lead = await login_with(["can_triage", "can_accept_audit_final"])
    r = await lead.post("/api/v1/findings/bulk-triage", json=_body(cve, state="open"))
    assert (r.status_code, r.json()["count"]) == (200, 3)
    assert await states() == ["open", "open", "open"]
