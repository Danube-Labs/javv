"""M6 slice 6 — GET /api/v1/findings/export.vex against real OpenSearch.

Pins: a triaged finding round-trips into both formats (`state`/`vex_justification` →
OpenVEX statement / CycloneDX analysis); the scanner filter is REQUIRED (per-scanner is
sacred — one VEX document never merges two scanners' verdicts); tenant isolation; auth.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "vex-route-password"


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


async def _seed_finding(client: AsyncOpenSearch, cid: str, **over: Any) -> None:
    doc = {
        "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
        "cluster_id": cid,
        "scanner": "trivy",
        "cve_id": "CVE-2024-0100",
        "namespaces": ["default"],
        "state": "open",
        "vex_justification": None,
        "present": True,
        "severity": "high",
        "severity_rank": 4,
        "kev": False,
        "package_name": "libfoo",
        "installed_version": "1.0.0",
        "image_repo": "registry/app",
        "image_digest": "sha256:vexrt01",
        "first_seen_at": datetime.now(UTC).isoformat(),
        **over,
    }
    await client.index(index="findings", id=doc["finding_key"], body=doc)
    await client.indices.refresh(index="findings")


async def test_vex_over_row_cap_is_413(env, monkeypatch) -> None:
    """A-M6 (audit #189): VEX materializes the whole lens into one JSON document, so a lens over
    JAVV_EXPORT_MAX_ROWS is refused with a 413 pre-count — never an unbounded in-memory build."""
    login, client = env
    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "2")
    get_settings.cache_clear()
    cid = f"c-vex-{uuid.uuid4().hex[:8]}"
    for i in range(4):  # 4 trivy findings > cap 2
        await _seed_finding(client, cid, cve_id=f"CVE-2024-02{i:02d}")
    http = await login()

    r = await http.get(
        "/api/v1/findings/export.vex", params={"cluster_id": cid, "scanner": "trivy"}
    )
    assert r.status_code == 413
    assert "inline export limit" in r.json()["title"]


async def test_vex_round_trips_triage_in_both_formats(env) -> None:
    login, client = env
    cid, other = f"c-vex-{uuid.uuid4().hex[:8]}", f"c-vex-{uuid.uuid4().hex[:8]}"
    await _seed_finding(
        client, cid, state="not_affected", vex_justification="vulnerable_code_not_present"
    )
    await _seed_finding(client, cid, cve_id="CVE-2024-0101", state="risk_accepted")
    await _seed_finding(client, cid, cve_id="CVE-2024-0102", scanner="grype")  # other scanner
    await _seed_finding(client, other, cve_id="CVE-2024-0666")  # other tenant — never leaks
    http = await login()

    r = await http.get(
        "/api/v1/findings/export.vex", params={"cluster_id": cid, "scanner": "trivy"}
    )
    assert r.status_code == 200
    doc = r.json()
    assert doc["@context"].startswith("https://openvex.dev/")
    by_cve = {s["vulnerability"]["name"]: s for s in doc["statements"]}
    assert set(by_cve) == {"CVE-2024-0100", "CVE-2024-0101"}  # one scanner, one tenant
    assert by_cve["CVE-2024-0100"]["status"] == "not_affected"
    assert by_cve["CVE-2024-0100"]["justification"] == "vulnerable_code_not_present"
    assert by_cve["CVE-2024-0101"]["status"] == "affected"
    assert "action_statement" in by_cve["CVE-2024-0101"]

    r = await http.get(
        "/api/v1/findings/export.vex",
        params={"cluster_id": cid, "scanner": "trivy", "format": "cyclonedx"},
    )
    assert r.status_code == 200
    doc = r.json()
    assert doc["bomFormat"] == "CycloneDX"
    by_cve = {v["id"]: v for v in doc["vulnerabilities"]}
    assert by_cve["CVE-2024-0100"]["analysis"]["state"] == "not_affected"
    assert by_cve["CVE-2024-0100"]["analysis"]["justification"] == "code_not_present"
    assert by_cve["CVE-2024-0101"]["analysis"]["response"] == ["will_not_fix"]


async def test_vex_requires_a_scanner_and_auth(env) -> None:
    login, client = env
    cid = f"c-vex-{uuid.uuid4().hex[:8]}"
    http = await login()

    r = await http.get("/api/v1/findings/export.vex", params={"cluster_id": cid})
    assert r.status_code == 422  # per-scanner is sacred — no merged advisory

    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http._transport.app),  # type: ignore[attr-defined]
        base_url="https://t",
    )
    r = await bare.get(
        "/api/v1/findings/export.vex", params={"cluster_id": cid, "scanner": "trivy"}
    )
    assert r.status_code == 401
    await bare.aclose()
