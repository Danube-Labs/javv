"""Health tests. `/healthz` must answer without OpenSearch (pure liveness), so it runs in CI with
no OpenSearch service. `/readyz` answers 503 when OpenSearch does not answer, and 200 otherwise,
with `checks.store` when the store is read-only (its disk past the flood-stage watermark) or red:
reads still work then, and a 503 would take the only backend pod out of service (issue 832)."""

import uuid
from typing import Any

import httpx
import pytest
import structlog
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import TransportError
from prometheus_client import REGISTRY

from backend.main import create_app
from os_env import OS_URL, requires_opensearch


async def test_healthz_ok_without_opensearch() -> None:
    app = create_app()
    # plain ASGITransport does not run lifespan, so no OpenSearch client is created — proving
    # liveness has no OpenSearch dependency.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_unknown_route_uses_problem_envelope() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["status"] == 404
    assert set(body) >= {"type", "title", "status"}


# --- /readyz: a read-only or red store stays in service (issue 832) ------------------------

FLOOD_BLOCK = {"12": {"description": "disk usage exceeded flood-stage watermark", "levels": []}}


class _Cluster:
    def __init__(self, status: str, blocks: dict[str, Any], fails: bool) -> None:
        self.status, self.blocks, self.fails = status, blocks, fails
        self.state_args: dict[str, Any] = {}

    async def health(self, **kwargs: Any) -> dict[str, Any]:
        if self.fails:
            raise TransportError(403, "security_exception", None)
        return {"status": self.status}

    async def state(self, **kwargs: Any) -> dict[str, Any]:
        self.state_args = kwargs
        return {"blocks": {"indices": self.blocks}} if self.blocks else {}


class _Store:
    def __init__(
        self,
        *,
        reachable: bool = True,
        status: str = "green",
        blocks: dict[str, Any] | None = None,
        fails: bool = False,
    ) -> None:
        self.reachable = reachable
        self.cluster = _Cluster(status, blocks or {}, fails)

    async def ping(self) -> bool:
        return self.reachable


def _app(store: Any) -> Any:
    app = create_app()  # before any capture_logs: building the app reconfigures logging
    app.state.opensearch = store
    return app


async def _readyz(store: Any, app: Any = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app or _app(store))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get("/readyz")


@pytest.mark.parametrize("status", ["green", "yellow"])
async def test_a_healthy_store_is_ready(status: str) -> None:
    r = await _readyz(_Store(status=status))
    assert (r.status_code, r.json()) == (200, {"status": "ready"})


async def test_a_store_past_its_flood_stage_is_ready_and_read_only() -> None:
    store = _Store(blocks={"javv-occurrences-c1-000001": FLOOD_BLOCK})
    r = await _readyz(store)
    assert (r.status_code, r.json()) == (200, {"status": "ready", "checks": {"store": "read-only"}})
    assert store.cluster.state_args["index"] == "findings,javv-*,system-*"


async def test_another_block_is_not_a_full_disk() -> None:
    r = await _readyz(_Store(blocks={"system-users": {"5": {"description": "index read-only"}}}))
    assert r.json() == {"status": "ready"}


@pytest.mark.parametrize("blocks", [{}, {"system-users": FLOOD_BLOCK}], ids=["red", "red-and-full"])
async def test_a_red_store_is_ready_and_red(blocks: dict[str, Any]) -> None:
    r = await _readyz(_Store(status="red", blocks=blocks))
    assert (r.status_code, r.json()) == (200, {"status": "ready", "checks": {"store": "red"}})


async def test_a_check_that_fails_leaves_the_store_ready_and_is_counted(monkeypatch) -> None:
    from backend.core import errors as core_errors
    from backend.routers import health

    monkeypatch.setattr(core_errors, "log", structlog.get_logger())  # StoreWarnings logs there
    fresh = health.StoreWarnings(health._check_warned.event, health._check_warned.counter)
    monkeypatch.setattr(health, "_check_warned", fresh)
    before = REGISTRY.get_sample_value("javv_opensearch_request_errors_total", {"kind": "other"})
    store = _Store(fails=True)
    app = _app(store)
    with structlog.testing.capture_logs() as logs:
        r = await _readyz(store, app)
    assert (r.status_code, r.json()) == (200, {"status": "ready"})
    after = REGISTRY.get_sample_value("javv_opensearch_request_errors_total", {"kind": "other"})
    assert after == (before or 0.0) + 1
    (line,) = [e for e in logs if e["event"] == "store check failed"]
    assert line["log_level"] == "warning"


async def test_an_unreachable_store_is_still_a_503() -> None:
    r = await _readyz(_Store(reachable=False))
    assert (r.status_code, r.json()) == (503, {"status": "degraded", "opensearch": "unreachable"})


@requires_opensearch
@pytest.mark.serial  # a shard nobody can host turns the whole store red while it runs
async def test_a_real_red_store_reads_red() -> None:
    client = AsyncOpenSearch(hosts=[OS_URL])
    index = f"t-red-{uuid.uuid4().hex[:8]}"
    try:
        await client.indices.create(
            index=index,
            body={
                "settings": {
                    "number_of_replicas": 0,
                    "index.routing.allocation.require._name": "no-such-node",
                }
            },
            params={"wait_for_active_shards": "0"},
        )
        r = await _readyz(client)
        assert (r.status_code, r.json()) == (200, {"status": "ready", "checks": {"store": "red"}})
    finally:
        await client.indices.delete(index=index, params={"ignore_unavailable": "true"})
        await client.close()


@requires_opensearch
async def test_a_real_store_accepts_both_checks() -> None:
    # the blocks read with its index filter and options goes to a real store here
    failed = {"kind": "other"}
    before = REGISTRY.get_sample_value("javv_opensearch_request_errors_total", failed) or 0.0
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        r = await _readyz(client)
    finally:
        await client.close()
    assert (r.status_code, r.json()) == (200, {"status": "ready"})
    # a refused check would also answer ready; the counter tells the two apart
    assert REGISTRY.get_sample_value("javv_opensearch_request_errors_total", failed) == before
