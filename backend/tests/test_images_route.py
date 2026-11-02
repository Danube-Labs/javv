"""GET /api/v1/images (M8c slice 2, #240) — the running-images inventory read.

Contract pins (bolt DoD): only the latest COMMITTED inventory run answers — a newer partial run
never leaks (its image docs are invisible until its manifest commits); clean images (zero
findings) appear as ordinary rows; no inventory yet → `inventory: null` (unknown ≠ empty);
tenant isolation; session auth; and the share-the-query-layer pin — the route's rows are
byte-identical to M8b's `running_images_at` at `t=now` (the two can never disagree)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.query.pit import running_images_at
from os_env import OS_URL, requires_opensearch

PASSWORD = "images-route-password"


pytestmark = requires_opensearch


@pytest.fixture
async def env():
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


async def _manifest(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    inventory_run_id: str,
    inventory_order: int,
    status: str = "committed",
    ts: str | None = None,
) -> None:
    now = ts or datetime.now(UTC).isoformat()
    await client.index(
        index=f"javv-inventory-runs-{cluster_id}-000001",
        id=inventory_run_id,
        body={
            "@timestamp": now,
            "inventory_run_id": inventory_run_id,
            "inventory_order": inventory_order,
            "cluster_id": cluster_id,
            "started_at": now,
            "completed_at": now,
            "expected_count": 2,
            "written_count": 2,
            "status": status,
            "schema_version": 1,
        },
    )


async def _image(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    inventory_run_id: str,
    digest: str,
    total: int,
) -> None:
    await client.index(
        index=f"javv-images-{cluster_id}-000001",
        id=uuid.uuid4().hex,
        body={
            "@timestamp": datetime.now(UTC).isoformat(),
            "scan_run_id": inventory_run_id,
            "inventory_run_id": inventory_run_id,
            "cluster_id": cluster_id,
            "image_digest": digest,
            "image_repo": "nginx",
            "tag": "1.21",
            "namespaces": ["default"],
            "scanners": ["trivy"],
            "total": total,
            "replicas": 2,
            "schema_version": 3,
        },
    )


async def _refresh(client: AsyncOpenSearch, cluster_id: str) -> None:
    for pattern in (f"javv-inventory-runs-{cluster_id}-*", f"javv-images-{cluster_id}-*"):
        await client.indices.refresh(index=pattern, params={"ignore_unavailable": "true"})


async def test_requires_a_session(env) -> None:
    _, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        r = await c.get("/api/v1/images", params={"cluster_id": "c-img-anon1"})
    assert r.status_code == 401


async def test_committed_only_partial_never_leaks_and_clean_images_appear(env) -> None:
    http, client = env
    cid = f"c-img-{uuid.uuid4().hex[:8]}"
    # run A: committed, 2 images — one CLEAN (zero findings; DoD: it MUST appear)
    await _manifest(client, cluster_id=cid, inventory_run_id="inv-a", inventory_order=1)
    await _image(client, cluster_id=cid, inventory_run_id="inv-a", digest="sha256:aa", total=5)
    await _image(client, cluster_id=cid, inventory_run_id="inv-a", digest="sha256:bb", total=0)
    # run B: NEWER order but partial — its rows must be invisible until it commits
    await _manifest(
        client, cluster_id=cid, inventory_run_id="inv-b", inventory_order=2, status="partial"
    )
    await _image(client, cluster_id=cid, inventory_run_id="inv-b", digest="sha256:cc", total=9)
    await _refresh(client, cid)

    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    assert r.status_code == 200
    body = r.json()
    assert body["inventory"]["inventory_run_id"] == "inv-a"  # partial inv-b never the answer
    assert [i["image_digest"] for i in body["images"]] == ["sha256:aa", "sha256:bb"]
    clean = body["images"][1]
    assert clean["total"] == 0 and clean["replicas"] == 2  # the zero-findings image is a real row

    # ... and the moment inv-b COMMITS, it takes over
    await _manifest(client, cluster_id=cid, inventory_run_id="inv-b", inventory_order=2)
    await _refresh(client, cid)
    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    assert r.json()["inventory"]["inventory_run_id"] == "inv-b"
    assert [i["image_digest"] for i in r.json()["images"]] == ["sha256:cc"]


async def test_route_rows_equal_the_time_travel_reader_at_now(env) -> None:
    """The share-the-query-layer pin: this route IS running_images_at(t=now) — same primitives,
    so the M9c screen and a T=just-now time-travel read can never disagree."""
    http, client = env
    cid = f"c-img-{uuid.uuid4().hex[:8]}"
    await _manifest(client, cluster_id=cid, inventory_run_id="inv-p", inventory_order=1)
    await _image(client, cluster_id=cid, inventory_run_id="inv-p", digest="sha256:dd", total=1)
    await _refresh(client, cid)

    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    reader_rows = await running_images_at(client, cid, datetime.now(UTC))
    # the wire adds the per-scanner severity decoration ON TOP of the reader's rows
    stripped = [
        {k: v for k, v in row.items() if k != "severity_by_scanner"} for row in r.json()["images"]
    ]
    assert stripped == reader_rows


async def test_as_of_rewinds_to_the_inventory_committed_at_t(env) -> None:
    """M9c slice 3 (D28/FR-23): `as_of` dispatches through the SAME primitives at T — the
    inventory committed ≤ T answers, a later run doesn't leak backwards, pre-history is
    unknown (`inventory: null`), and a malformed T is a 422."""
    http, client = env
    cid = f"c-img-{uuid.uuid4().hex[:8]}"
    # explicit, well-separated stamps — date fields are millis-precision, `lte` includes equal
    await _manifest(
        client,
        cluster_id=cid,
        inventory_run_id="inv-old",
        inventory_order=1,
        ts="2026-07-01T00:00:00+00:00",
    )
    await _image(client, cluster_id=cid, inventory_run_id="inv-old", digest="sha256:old", total=1)
    await _refresh(client, cid)
    t_between = "2026-07-02T00:00:00+00:00"

    await _manifest(client, cluster_id=cid, inventory_run_id="inv-new", inventory_order=2)
    await _image(client, cluster_id=cid, inventory_run_id="inv-new", digest="sha256:new", total=2)
    await _refresh(client, cid)

    # now = the new run; at T between = the old run; before history = unknown
    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    assert r.json()["inventory"]["inventory_run_id"] == "inv-new"
    r = await http.get("/api/v1/images", params={"cluster_id": cid, "as_of": t_between})
    assert r.json()["inventory"]["inventory_run_id"] == "inv-old"
    assert [i["image_digest"] for i in r.json()["images"]] == ["sha256:old"]
    r = await http.get(
        "/api/v1/images", params={"cluster_id": cid, "as_of": "2020-01-01T00:00:00+00:00"}
    )
    assert r.json()["inventory"] is None and r.json()["images"] == []
    r = await http.get("/api/v1/images", params={"cluster_id": cid, "as_of": "not-a-time"})
    assert r.status_code == 422


async def _scan_event(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    scanner: str,
    digest: str,
    scan_order: int,
    total: int,
    ts: str,
    crit: int = 0,
) -> None:
    await client.index(
        index=f"javv-scan-events-{cluster_id}-000001",
        id=uuid.uuid4().hex,
        body={
            "@timestamp": ts,
            "scan_run_id": f"run-{scan_order}",
            "scan_order": scan_order,
            "cluster_id": cluster_id,
            "scanner": scanner,
            "image_digest": digest,
            "image_repo": "nginx",
            "tag": "1.21",
            "crit": crit,
            "total": total,
            "schema_version": 4,
        },
    )


async def test_rows_carry_per_scanner_severity_buckets_from_the_catalog(env) -> None:
    """M9c slice 3: each image row is decorated with `severity_by_scanner` — every scanner's
    latest committed counts for that digest (R-CATALOG, max scan_order) — so the UI can show
    BOTH mixes without merging. The image doc's own buckets stay the committing scanner's."""
    http, client = env
    cid = f"c-img-{uuid.uuid4().hex[:8]}"
    await _manifest(client, cluster_id=cid, inventory_run_id="inv-s", inventory_order=1)
    await _image(client, cluster_id=cid, inventory_run_id="inv-s", digest="sha256:sv", total=5)
    # trivy scanned twice (order 2 supersedes 1); grype once — counts land per scanner
    await _scan_event(
        client,
        cluster_id=cid,
        scanner="trivy",
        digest="sha256:sv",
        scan_order=1,
        total=9,
        ts="2026-07-01T00:00:00+00:00",
        crit=9,
    )
    await _scan_event(
        client,
        cluster_id=cid,
        scanner="trivy",
        digest="sha256:sv",
        scan_order=2,
        total=5,
        ts="2026-07-02T00:00:00+00:00",
        crit=2,
    )
    await _scan_event(
        client,
        cluster_id=cid,
        scanner="grype",
        digest="sha256:sv",
        scan_order=1,
        total=7,
        ts="2026-07-01T00:01:00+00:00",
        crit=4,
    )
    await client.indices.refresh(index=f"javv-scan-events-{cid}-*")
    await _refresh(client, cid)

    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    row = r.json()["images"][0]
    by = row["severity_by_scanner"]
    assert by["trivy"]["crit"] == 2 and by["trivy"]["total"] == 5  # max scan_order wins
    assert by["grype"]["crit"] == 4 and by["grype"]["total"] == 7  # never merged with trivy's


async def test_timeline_is_the_per_image_scan_event_history_in_scan_order(env) -> None:
    """M9c slice 3 (DigestSubTimeline): the committed scan-events for one repo:tag, ordered by
    (scan_order, scanner) — digest changes and order gaps are the client's build-change/gap
    markers. Tenant-scoped; unknown repo:tag = empty, not an error."""
    http, client = env
    cid = f"c-img-{uuid.uuid4().hex[:8]}"
    await _scan_event(
        client,
        cluster_id=cid,
        scanner="trivy",
        digest="sha256:v1",
        scan_order=1,
        total=5,
        ts="2026-07-01T00:00:00+00:00",
    )
    await _scan_event(
        client,
        cluster_id=cid,
        scanner="grype",
        digest="sha256:v1",
        scan_order=1,
        total=7,
        ts="2026-07-01T00:01:00+00:00",
    )
    # order 2 skipped for trivy (a gap), build changed to v2 by order 3
    await _scan_event(
        client,
        cluster_id=cid,
        scanner="trivy",
        digest="sha256:v2",
        scan_order=3,
        total=0,
        ts="2026-07-03T00:00:00+00:00",
    )
    await client.indices.refresh(index=f"javv-scan-events-{cid}-*")

    r = await http.get(
        "/api/v1/images/timeline",
        params={"cluster_id": cid, "image_repo": "nginx", "tag": "1.21"},
    )
    assert r.status_code == 200
    events = r.json()["events"]
    assert [(e["scan_order"], e["scanner"], e["image_digest"]) for e in events] == [
        (1, "grype", "sha256:v1"),
        (1, "trivy", "sha256:v1"),
        (3, "trivy", "sha256:v2"),
    ]
    assert events[0]["total"] == 7  # counts ride along verbatim

    r = await http.get(
        "/api/v1/images/timeline",
        params={"cluster_id": cid, "image_repo": "nginx", "tag": "other"},
    )
    assert r.json()["events"] == []


async def test_no_inventory_is_unknown_not_empty_and_tenant_scoped(env) -> None:
    http, client = env
    cid, other = (f"c-img-{uuid.uuid4().hex[:8]}" for _ in range(2))
    await _manifest(client, cluster_id=other, inventory_run_id="inv-x", inventory_order=1)
    await _image(client, cluster_id=other, inventory_run_id="inv-x", digest="sha256:ee", total=1)
    await _refresh(client, other)

    r = await http.get("/api/v1/images", params={"cluster_id": cid})
    assert r.status_code == 200
    body: dict[str, Any] = r.json()
    assert body["inventory"] is None and body["images"] == []  # unknown — the other tenant's
    # committed run never bleeds across cluster_id


_SEVERITY_KEYS = ("crit", "high", "med", "low", "negligible", "unknown")


async def test_images_and_top_images_give_the_same_counts_after_a_real_ingest(env) -> None:
    """Issue 1063 step 3: with no filter, the Riskiest images card shows the same numbers from
    either read. GET /api/v1/images takes them from the scan events, GET
    /api/v1/findings/top-images from the findings. They agree because ingest counts findings,
    not the entries of the report (issue 1076): the seed repeats one finding in a second file,
    and the scanners send their own severity words."""
    import json
    from pathlib import Path

    from backend.models.envelope import IngestEnvelope, canonical_severity
    from backend.services.ingest import ingest_envelope

    http, client = env
    cid = f"c-cmp-{uuid.uuid4().hex[:8]}"
    golden = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
    digest = golden["image_digest"]
    repeated = {**golden["findings"][1], "severity": golden["findings"][1]["severity"].lower()}
    trivy = {**golden, "cluster_id": cid, "findings": [*golden["findings"], repeated]}
    grype = {
        **golden,
        "cluster_id": cid,
        "scanner": "grype",
        "scan_run_id": "grypecmp0001",
        "effective_config": {
            **golden["effective_config"],
            "tuning": {"only_fixed": False, "scope": None, "scan_timeout": 300},
        },
        "findings": [{**f, "severity": f["severity"].title()} for f in golden["findings"][:12]],
    }
    for raw in (trivy, grype):
        # the scanner's counts are the entries of its report, as it sends them
        counts: dict[str, int] = dict.fromkeys(_SEVERITY_KEYS, 0)
        for f in raw["findings"]:
            bucket = canonical_severity(f["severity"])
            counts[{"critical": "crit", "medium": "med"}.get(bucket, bucket)] += 1
        raw["counts"] = {
            **counts,
            "total": len(raw["findings"]),
            "fixable": sum(1 for f in raw["findings"] if f.get("fixable")),
        }
        await ingest_envelope(client, IngestEnvelope.model_validate(raw))
    await _manifest(client, cluster_id=cid, inventory_run_id="inv-cmp", inventory_order=1)
    await _image(client, cluster_id=cid, inventory_run_id="inv-cmp", digest=digest, total=0)
    await client.indices.refresh(index="findings")
    await client.indices.refresh(index=f"javv-scan-events-{cid}-*")
    await _refresh(client, cid)

    images = (await http.get("/api/v1/images", params={"cluster_id": cid})).json()["images"]
    top = (await http.get("/api/v1/findings/top-images", params={"cluster_id": cid})).json()[
        "images"
    ]
    [row] = [i for i in images if i["image_digest"] == digest]
    [ranked] = top
    assert ranked["image_digest"] == digest
    assert (
        set(row["severity_by_scanner"])
        == set(ranked["severity_by_scanner"])
        == {
            "trivy",
            "grype",
        }
    )
    for scanner, counts in ranked["severity_by_scanner"].items():
        from_events = {k: row["severity_by_scanner"][scanner][k] for k in _SEVERITY_KEYS}
        assert counts == from_events, scanner
    # the repeated entry is one finding: 29 findings, not the 30 entries of the report
    assert sum(ranked["severity_by_scanner"]["trivy"].values()) == len(golden["findings"])
