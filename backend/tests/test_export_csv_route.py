"""M6 slice 5 — GET /api/v1/findings/export.csv against real OpenSearch.

Pins: the export is the SAME lens as the grid (filters apply); every row is
injection-sanitized on the wire; the sweep walks multiple PIT pages and leaves ZERO PITs
behind (D38 — the sweep case); tenant isolation via the tenant read path (a bait row in another
cluster never leaks into the file); auth required; `as_of` in the past is 501 (D28 seam).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

import backend.export.sweep as sweep_mod
from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from os_env import OS_URL, clear_pits, requires_opensearch

PASSWORD = "export-route-password"


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


async def _seed(client: AsyncOpenSearch, cluster_id: str, rows: list[dict[str, Any]]) -> None:
    now = datetime.now(UTC).isoformat()
    for row in rows:
        doc = {
            "cluster_id": cluster_id,
            "scanner": "trivy",
            "namespaces": ["default"],
            "state": "open",
            "vex_justification": None,
            "state_decision_id": None,
            "present": True,
            "severity": "high",
            "severity_rank": 4,
            "kev": False,
            "fixable": False,
            "disagree": False,
            "assignee": None,
            "image_repo": "bench/app",
            "package_name": "libfoo",
            "installed_version": "1.0.0",
            "first_seen_at": now,
            **row,
        }
        await client.index(index="findings", id=doc["finding_key"], body=doc)
    await client.indices.refresh(index="findings")


def _rows(n: int, *, cve: str = "CVE-2024-9500", **over: Any) -> list[dict[str, Any]]:
    return [
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": cve,
            "image_digest": f"sha256:ex{i:02d}",
            **over,
        }
        for i in range(n)
    ]


async def _pit_count(client: AsyncOpenSearch) -> int:
    resp = await client.transport.perform_request("GET", "/_search/point_in_time/_all")
    return len(resp.get("pits") or [])


# serial: clears and counts every open PIT in the store, so it cannot share it with a live walk
@pytest.mark.serial
async def test_export_streams_sanitized_lens_and_cleans_pits(env, monkeypatch) -> None:
    login, client = env
    monkeypatch.setattr(sweep_mod, "_PAGE_SIZE", 2)  # force a real multi-page sweep
    cid, other = f"c-exp-{uuid.uuid4().hex[:8]}", f"c-exp-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(5, package_name="=cmd()|bait"))
    await _seed(client, cid, _rows(1, cve="CVE-2024-9501", state="acknowledged"))
    await _seed(client, other, _rows(1, cve="CVE-2024-9666"))  # must never leak
    http = await login()

    await clear_pits(client)
    r = await http.get("/api/v1/findings/export.csv", params={"cluster_id": cid, "state": ["open"]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]

    lines = r.text.splitlines()
    assert lines[0].startswith("finding_key,cluster_id,scanner,cve_id")
    assert len(lines) == 1 + 5  # the lens: open only — the acknowledged row filtered out
    assert all("CVE-2024-9666" not in ln for ln in lines)  # tenant isolation (SEC-4)
    assert all("'=cmd()|bait" in ln for ln in lines[1:])  # every bait cell left neutralized
    assert "\n=cmd" not in r.text and not any(ln.startswith("=") for ln in lines)

    assert await _pit_count(client) == 0  # the sweep cleaned its PIT (D38)


async def test_export_over_row_cap_is_413_before_streaming(env, monkeypatch) -> None:
    """A-M6 (audit #189): a lens exceeding JAVV_EXPORT_MAX_ROWS is a clean 413 from a cheap
    pre-count — never a streamed-open giant body / OOM. Under the cap → 200."""
    login, client = env
    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "3")
    get_settings.cache_clear()
    cid = f"c-exp-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(5))  # 5 > cap 3
    http = await login()

    r = await http.get("/api/v1/findings/export.csv", params={"cluster_id": cid})
    assert r.status_code == 413
    assert "inline export limit" in r.json()["title"]

    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "50")  # now comfortably above the lens
    get_settings.cache_clear()
    r = await http.get("/api/v1/findings/export.csv", params={"cluster_id": cid})
    assert r.status_code == 200
    assert len(r.text.splitlines()) == 1 + 5


async def test_export_requires_auth_and_as_of_past_is_501(env) -> None:
    login, client = env
    cid = f"c-exp-{uuid.uuid4().hex[:8]}"
    http = await login()

    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http._transport.app),  # type: ignore[attr-defined]
        base_url="https://t",
    )
    r = await bare.get("/api/v1/findings/export.csv", params={"cluster_id": cid})
    assert r.status_code == 401
    await bare.aclose()

    r = await http.get(
        "/api/v1/findings/export.csv",
        params={"cluster_id": cid, "as_of": "2026-01-01T00:00:00+00:00"},
    )
    assert r.status_code == 501  # export-at-T lands with M8b (D28)
