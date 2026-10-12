"""M8a slice 2 (#33): the inventory commit manifest. Endpoint tests (fake OpenSearch) pin the
token regime + SEC-3 binding (the manifest is always the TOKEN's cluster; written_count is counted
server-side, never client-reported). Semantics run against a real OpenSearch: committed iff every
discovered image landed, manifests are immutable + idempotent on retry (original `inventory_order`
kept), and the per-cluster order allocation is strictly increasing with a committed-floor
self-heal — the D45 contract."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings
from backend.main import create_app
from backend.services.aliases import ensure_write_alias
from backend.snapshots.inventory_runs import (
    COMMITTED,
    PARTIAL,
    allocate_inventory_order,
    commit_inventory_run,
)
from os_env import requires_opensearch

PEPPER = get_settings().secret_key
STARTED = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)


# --- endpoint (fake OpenSearch) ------------------------------------------------


class _Indices:
    async def refresh(self, **_: Any) -> dict[str, Any]:
        return {}

    async def exists_alias(self, **_: Any) -> bool:
        return True  # alias already ensured — the fake never creates indices


class FakeOS:
    """Token lookup + enough surface for one manifest commit (count is canned)."""

    def __init__(self, token_doc: dict[str, Any] | None, written: int = 0):
        self.token_doc = token_doc
        self.written = written
        self.indexed: list[dict[str, Any]] = []
        self.indices = _Indices()

    async def search(self, **kw: Any) -> dict[str, Any]:
        if "javv-inventory-runs" in str(kw.get("index", "")):  # committed-floor query
            return {"aggregations": {"m": {"value": None}}}
        hits = [{"_id": "t1", "_source": self.token_doc}] if self.token_doc else []
        return {"hits": {"hits": hits}}

    async def count(self, **_: Any) -> dict[str, Any]:
        return {"count": self.written}

    async def get(self, **_: Any) -> dict[str, Any]:
        raise NotFoundError(404, "not_found", {})  # counter doc: first allocation path

    async def index(self, **kw: Any) -> dict[str, Any]:
        self.indexed.append(kw)
        return {"result": "created"}


def _client(fake: FakeOS) -> httpx.AsyncClient:
    app = create_app()
    app.state.opensearch = fake
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _token_doc(token: str, cluster: str = "cluster-aaaa") -> dict[str, Any]:
    return {
        "token_hash": hash_token(token, pepper=PEPPER),
        "cluster_id": cluster,
        "scanner": "trivy",
        "disabled": False,
    }


def _body(expected: int = 2) -> dict[str, Any]:
    return {
        "scan_run_id": "run-0001",
        "expected_count": expected,
        "started_at": "2026-07-07T12:00:00Z",
    }


async def test_post_requires_a_valid_token() -> None:
    fake = FakeOS(None)
    async with _client(fake) as c:
        missing = await c.post("/api/v1/inventory-runs", json=_body())
        bad = await c.post(
            "/api/v1/inventory-runs", json=_body(), headers={"Authorization": "Bearer nope"}
        )
    assert missing.status_code == 401 and bad.status_code == 401


async def test_post_rejects_malformed_bodies() -> None:
    token = mint_token()
    fake = FakeOS(_token_doc(token))
    headers = {"Authorization": f"Bearer {token}"}
    async with _client(fake) as c:
        negative = await c.post(
            "/api/v1/inventory-runs", json={**_body(), "expected_count": -1}, headers=headers
        )
        extra = await c.post(
            "/api/v1/inventory-runs", json={**_body(), "cluster_id": "evil"}, headers=headers
        )
        no_zone = await c.post(
            "/api/v1/inventory-runs",
            json={**_body(), "started_at": "2026-07-07T12:00:00"},
            headers=headers,
        )
    assert negative.status_code == 422
    assert no_zone.status_code == 422  # every time on the ingest contract carries a zone
    assert extra.status_code == 422  # extra=forbid: no payload cluster_id, ever (SEC-3)


async def test_post_binds_to_the_tokens_cluster_and_counts_server_side() -> None:
    token = mint_token()
    fake = FakeOS(_token_doc(token), written=2)
    async with _client(fake) as c:
        r = await c.post(
            "/api/v1/inventory-runs", json=_body(2), headers={"Authorization": f"Bearer {token}"}
        )
    assert r.status_code == 200
    got = r.json()
    assert got["status"] == COMMITTED and got["written_count"] == 2
    assert got["cluster_id"] == "cluster-aaaa"  # the TOKEN's cluster — no payload value exists
    manifest = fake.indexed[-1]  # counter first, manifest last
    assert manifest["id"] == "run-0001"  # _id = inventory_run_id
    assert "javv-inventory-runs-cluster-aaaa" in manifest["index"]
    assert manifest["params"]["op_type"] == "create"  # immutable — never overwritten


# --- semantics (real OpenSearch) ------------------------------------------------


CLUSTER = "cluster-semantics"


async def _seed_images(client: AsyncOpenSearch, prefix: str, run_id: str, n: int) -> None:
    alias = f"{prefix}javv-images-{CLUSTER}"
    await ensure_write_alias(client, alias)
    for i in range(n):
        await client.index(
            index=alias,
            id=f"{run_id}:{i}",
            body={"scan_run_id": run_id, "inventory_run_id": run_id, "cluster_id": CLUSTER},
            params={"refresh": "true"},
        )


@requires_opensearch
async def test_committed_iff_every_discovered_image_landed(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    await _seed_images(client, prefix, "run-a", 2)
    complete = await commit_inventory_run(
        client, CLUSTER, "run-a", expected_count=2, started_at=STARTED, prefix=prefix
    )
    assert complete["status"] == COMMITTED and complete["inventory_order"] == 1

    # run-b discovered 3 images but only 1 landed (scan failure / dead letter) → partial, and it
    # must never be read as the live inventory — the latest COMMITTED run is still run-a
    await _seed_images(client, prefix, "run-b", 1)
    short = await commit_inventory_run(
        client, CLUSTER, "run-b", expected_count=3, started_at=STARTED, prefix=prefix
    )
    assert short["status"] == PARTIAL
    assert short["inventory_order"] == 2  # ordered after — but not readable
    resp = await client.search(
        index=f"{prefix}javv-inventory-runs-{CLUSTER}-*",
        body={
            "query": {"term": {"status": COMMITTED}},
            "sort": [{"inventory_order": "desc"}],
            "size": 1,
        },
    )
    assert resp["hits"]["hits"][0]["_source"]["inventory_run_id"] == "run-a"


@requires_opensearch
async def test_manifest_is_immutable_and_retry_idempotent(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    await _seed_images(client, prefix, "run-r", 1)
    first = await commit_inventory_run(
        client, CLUSTER, "run-r", expected_count=2, started_at=STARTED, prefix=prefix
    )
    assert first["status"] == PARTIAL

    # a late image lands, then the scanner retries the commit — the manifest must NOT upgrade:
    # runs are certified exactly once (immutable), the retry returns the original verdict
    await _seed_images(client, prefix, "run-r", 2)
    retry = await commit_inventory_run(
        client, CLUSTER, "run-r", expected_count=2, started_at=STARTED, prefix=prefix
    )
    assert retry["status"] == PARTIAL
    assert retry["inventory_order"] == first["inventory_order"]  # no ordering churn
    resp = await client.search(
        index=f"{prefix}javv-inventory-runs-{CLUSTER}-*",
        body={"query": {"term": {"inventory_run_id": "run-r"}}, "size": 5},
    )
    assert len(resp["hits"]["hits"]) == 1  # one manifest per run, ever


@requires_opensearch
async def test_order_allocation_is_racing_safe_and_self_heals(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    # keystone-lite: 8 concurrent allocators, no order issued twice (the D45 CAS contract)
    orders = await asyncio.gather(
        *(allocate_inventory_order(client, CLUSTER, prefix=prefix) for _ in range(8))
    )
    assert len(set(orders)) == 8

    # forward self-heal: a lost/restored counter must never re-issue an order at or below a
    # COMMITTED manifest's — the floor comes from the manifests, not the counter doc
    await _seed_images(client, prefix, "run-h", 1)
    committed = await commit_inventory_run(
        client, CLUSTER, "run-h", expected_count=1, started_at=STARTED, prefix=prefix
    )
    await client.delete(index=f"{prefix}javv-scan-orders", id=f"{CLUSTER}:__inventory__")
    healed = await allocate_inventory_order(client, CLUSTER, prefix=prefix)
    assert healed > committed["inventory_order"]
