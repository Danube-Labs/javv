"""M8d slice 2 (#241) — ptype through every read surface, against real OpenSearch.

Contract pins: `/findings?ptype=` filters; the facet buckets are **per-scanner** (sacred — never
merged, DoD) and pre-M8d null rows land in an explicit `"unknown"` bucket (the B-1 reingest
caveat) instead of silently vanishing; `/findings/groups?by=ptype` pages; the as-of-T reader
reconstructs ptype (filter + facet at a past T, unknown-bucket mirrored); pure-builder units."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.bootstrap import bootstrap
from backend.main import create_app
from backend.models.envelope import IngestEnvelope
from backend.query.aggs import build_composite_body, build_facets_body
from backend.query.search import SearchFilters, build_search_body
from backend.services.ingest import ingest_envelope
from os_env import OS_URL, requires_opensearch

FIXTURES = Path(__file__).parent / "fixtures"
PASSWORD = "ptype-read-password"


pytestmark = requires_opensearch


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client)  # additive v13 put_mapping — ptype must be indexed, not just stored
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
            "role": "viewer",
            "capabilities": [],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-08T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client
    await http.aclose()
    await client.close()


def _envelope(name: str, cluster_id: str, **over) -> IngestEnvelope:
    raw = json.loads((FIXTURES / name).read_text())
    raw["cluster_id"] = cluster_id
    raw.update(over)
    return IngestEnvelope.model_validate(raw)


async def _seed_v4_and_v3(client: AsyncOpenSearch, cid: str) -> None:
    """One v4 trivy image (29 ptype=os rows) + one v3 grype-labelled image (29 null rows) —
    the mid-rollout fleet: swapped and un-swapped scanners side by side."""
    await ingest_envelope(client, _envelope("envelope-trivy-golden.json", cid))
    v3 = json.loads((FIXTURES / "envelope-trivy-v3-golden.json").read_text())
    v3.update(
        cluster_id=cid,
        scanner="grype",
        image_digest="sha256:" + "b" * 64,
        scan_run_id=f"run-{uuid.uuid4().hex[:8]}",
    )
    # the tuning shape must match the relabelled scanner (the D44 validator)
    v3["effective_config"]["tuning"] = {"only_fixed": False, "scope": None, "scan_timeout": 300}
    await ingest_envelope(client, IngestEnvelope.model_validate(v3))
    await client.indices.refresh(index="findings")


async def test_ptype_filter_narrows_the_grid(env) -> None:
    http, client = env
    cid = f"c-ptr-{uuid.uuid4().hex[:8]}"
    await _seed_v4_and_v3(client, cid)

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "ptype": "os", "size": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["total"]["value"] == 29  # only the v4 image's rows; null rows don't match
    assert all(row["ptype"] == "os" for row in body["data"])


async def test_facet_buckets_are_per_scanner_with_an_unknown_bucket_for_nulls(env) -> None:
    http, client = env
    cid = f"c-ptr-{uuid.uuid4().hex[:8]}"
    await _seed_v4_and_v3(client, cid)

    r = await http.get("/api/v1/findings/facets", params={"cluster_id": cid, "fields": "ptype"})
    assert r.status_code == 200
    buckets = {b["key"]: b for b in r.json()["facets"]["ptype"]}
    assert buckets["os"]["count"] == 29
    assert buckets["os"]["by_scanner"] == {"trivy": 29}  # per-scanner split, never merged (DoD)
    assert buckets["unknown"]["count"] == 29  # the v3-era nulls surface, not vanish (B-1 caveat)
    assert buckets["unknown"]["by_scanner"] == {"grype": 29}


async def test_groups_by_ptype_pages(env) -> None:
    http, client = env
    cid = f"c-ptr-{uuid.uuid4().hex[:8]}"
    await _seed_v4_and_v3(client, cid)

    r = await http.get("/api/v1/findings/groups", params={"cluster_id": cid, "by": "ptype"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert [g["key"] for g in data] == ["os"]  # groups skip nulls (drill-down semantics)
    assert data[0]["count"] == 29 and data[0]["by_scanner"] == {"trivy": 29}


@pytest.fixture
def reader():
    """The ASGI fixture never runs lifespan — register the reader like lifespan would,
    and unregister after (the #266 leak rule: reader lifetime = app lifetime)."""
    from backend.query.as_of import register_as_of_t
    from backend.query.as_of_t import AsOfTQuery

    register_as_of_t(AsOfTQuery())
    yield
    register_as_of_t(None)


async def test_as_of_t_reconstruction_carries_filters_and_facets_ptype(env, reader) -> None:
    http, client = env
    cid = f"c-ptr-{uuid.uuid4().hex[:8]}"
    await _seed_v4_and_v3(client, cid)
    for pattern in (f"javv-scan-events-{cid}-*", f"javv-finding-occurrences-{cid}-*"):
        await client.indices.refresh(index=pattern, params={"ignore_unavailable": "true"})
    t = datetime.now(UTC).isoformat()

    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "as_of": t, "ptype": "os", "size": 100},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"]["value"] == 29  # as-scanned: v3-era rows correctly drop out
    assert all(row["ptype"] == "os" for row in body["data"])

    r = await http.get(
        "/api/v1/findings/facets", params={"cluster_id": cid, "as_of": t, "fields": "ptype"}
    )
    buckets = {b["key"]: b["count"] for b in r.json()["facets"]["ptype"]}
    assert buckets == {"os": 29, "unknown": 29}  # unknown-bucket mirrored at a past T

    r = await http.get(
        "/api/v1/findings/groups", params={"cluster_id": cid, "as_of": t, "by": "ptype"}
    )
    assert [g["key"] for g in r.json()["data"]] == ["os"]


def test_builders_carry_the_ptype_clauses() -> None:
    body = build_search_body(SearchFilters(ptype=["os"]), size=10)
    assert {"terms": {"ptype": ["os"]}} in body["query"]["bool"]["filter"]

    facets = build_facets_body(SearchFilters(), fields=["ptype"])
    assert facets["aggs"]["ptype"]["terms"]["missing"] == "unknown"
    severity = build_facets_body(SearchFilters(), fields=["severity"])
    assert "missing" not in severity["aggs"]["severity"]["terms"]  # only ptype has the caveat

    groups = build_composite_body(SearchFilters(), by="ptype", size=10)
    assert groups["aggs"]["groups"]["composite"]["sources"] == [
        {"key": {"terms": {"field": "ptype"}}}
    ]
