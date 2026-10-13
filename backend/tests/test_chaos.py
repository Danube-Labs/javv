"""Chaos / fault-injection against a REAL OpenSearch (#223, major-audit 06 §3).

The unit suite maps exceptions; these tests make the failure happen at the TIMING unit mocks
can't reproduce — a PIT killed under a live cursor, the store dying between requests, a client
walking away mid-stream. Deterministic only (06 ruling: no toxiproxy, no random-fault monkey —
flaky chaos tests get skipped and rot). Every scenario also asserts the guard bookkeeping:
the PIT slot is RELEASED on the failure path, so one fault can't leak a principal's budget."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from backend.query.search import decode_cursor
from os_env import OS_URL, requires_opensearch

PASSWORD = "chaos-route-password"


pytestmark = requires_opensearch


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FlakyStore:
    """Delegates to the real client; `search` (and `ping`) fail while `broken` — the store
    'dies' mid-session and 'recovers' without an app restart."""

    def __init__(self, real: AsyncOpenSearch):
        self._real = real
        self.broken = False

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    async def search(self, *a, **k):
        if self.broken:
            from opensearchpy.exceptions import ConnectionError as OSConnectionError

            raise OSConnectionError("N/A", "store is down (chaos)", None)
        return await self._real.search(*a, **k)

    async def ping(self):
        if self.broken:
            from opensearchpy.exceptions import ConnectionError as OSConnectionError

            raise OSConnectionError("N/A", "store is down (chaos)", None)
        return await self._real.ping()


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    store = FlakyStore(client)
    app = create_app()
    app.state.opensearch = store
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "viewer",
            "capabilities": [],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-07T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client, store
    await http.aclose()
    await client.close()


async def _seed(client: AsyncOpenSearch, cid: str, n: int) -> None:
    for i in range(n):
        fk = f"fk-chaos-{uuid.uuid4().hex[:10]}"
        await client.index(
            index="findings",
            id=fk,
            body={
                "finding_key": fk,
                "cluster_id": cid,
                "scanner": "trivy",
                "cve_id": f"CVE-CHAOS-{i}",
                "image_digest": f"sha256:chaos-{i}",
                "namespaces": ["default"],
                "state": "open",
                "present": True,
                "severity": "high",
                "severity_rank": 4,
                # relative stamps — nothing here may rot with the calendar (chaos asserts
                # status codes, not overdue; relative anyway so the question never arises)
                "first_seen_at": (datetime.now(UTC) - timedelta(days=6)).isoformat(),
                "last_seen_at": datetime.now(UTC).isoformat(),
                "kev": False,
            },
        )
    await client.indices.refresh(index="findings")


async def test_pit_killed_under_a_live_cursor_is_410_and_releases_the_slot(
    env, monkeypatch
) -> None:
    """The REAL A-m1 scenario: the PIT dies server-side while a client holds the cursor. The
    follow-up must be a clean 410 problem-envelope (no stack trace), and the guard slot must be
    freed — proven by running at cap=1 and succeeding on a fresh search afterwards."""
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "1")
    get_settings.cache_clear()
    http, client, _ = env
    cid = f"c-chaos-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, 5)

    page = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 2})
    assert page.status_code == 200
    cursor = page.json()["next_cursor"]
    assert cursor, "corpus must be big enough to leave an open cursor"

    pit_id, *_ = decode_cursor(cursor)  # kill OUR pit only (xdist-safe: never delete_all_pits)
    await client.delete_pit(body={"pit_id": [pit_id]})

    gone = await http.get("/api/v1/findings", params={"cluster_id": cid, "cursor": cursor})
    assert gone.status_code == 410
    body = gone.json()
    assert body["status"] == 410 and "Traceback" not in gone.text
    assert gone.headers.get("x-request-id")

    # A walk's slot records its PIT, so the 410 frees exactly the dead walk's slot and never
    # another live walk's (issue 832): at cap=1 the follow-up search fits.
    fresh = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 2})
    assert fresh.status_code == 200


async def test_store_down_mid_session_degrades_and_recovers_without_restart(env) -> None:
    """The store dies between requests: reads answer 503 (problem envelope, no internals),
    /readyz flips degraded, and when the store comes back the SAME app serves 200s — no
    poisoned client state, no restart."""
    http, client, store = env
    cid = f"c-chaos-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, 2)

    ok = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert ok.status_code == 200

    store.broken = True
    down = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert down.status_code == 503
    assert "chaos" not in down.text  # the raw exception detail never reaches the client
    ready = await http.get("/readyz")
    assert ready.status_code == 503 and ready.json()["status"] == "degraded"

    store.broken = False
    back = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert back.status_code == 200, "app did not recover without a restart"
    assert (await http.get("/readyz")).status_code == 200


async def test_csv_stream_abandoned_midway_releases_the_pit_slot(env, monkeypatch) -> None:
    """A client that disconnects mid-export must not eat the principal's PIT budget: the
    streaming generator's finally releases the slot. Proven at cap=1 — the follow-up export
    only succeeds if the abandoned stream cleaned up."""
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "1")
    get_settings.cache_clear()
    http, client, _ = env
    cid = f"c-chaos-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, 8)

    async with http.stream(
        "GET", "/api/v1/findings/export.csv", params={"cluster_id": cid, "scanner": "trivy"}
    ) as r:
        assert r.status_code == 200
        async for _ in r.aiter_text():
            break  # walk away after the first chunk — the 'closed laptop' case

    again = await http.get(
        "/api/v1/findings/export.csv", params={"cluster_id": cid, "scanner": "trivy"}
    )
    assert again.status_code == 200, "abandoned stream leaked its PIT slot"
