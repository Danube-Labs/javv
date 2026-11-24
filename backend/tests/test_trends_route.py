"""M6 slice 3 — GET /api/v1/trends/* against real OpenSearch.

THE pin (task B, #139), asserted against the REAL storage duplicate: ingest → rollover → retry
leaves byte-identical sibling scan-event docs in two backing indices, and the scans trend still
reports ONE committed scan (`cardinality(commit_key)`), never two. Plus: the findings new/
resolved burn-down series, per-scanner split, tenant isolation, and the uniform as_of seam.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from backend.models.envelope import IngestEnvelope
from backend.services.ingest import ingest_envelope
from os_env import OS_URL, requires_opensearch

PASSWORD = "trends-route-password"
GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())


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
                "role": "viewer",
                "capabilities": [],
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


def _envelope(cid: str, run: str, order: int) -> IngestEnvelope:
    doc = {
        **GOLDEN,
        "cluster_id": cid,
        "scan_run_id": run,
        "scan_order": order,
        "last_seen_at": datetime.now(UTC).isoformat(),
    }
    return IngestEnvelope.model_validate(doc)


def _today_bucket(series: list[dict[str, Any]], value_key: str) -> int:
    today = datetime.now(UTC).date().isoformat()
    for point in series:
        if point["date"].startswith(today):
            return point[value_key]
    raise AssertionError(f"no bucket for today in {series!r}")


async def test_hourly_interval_is_span_capped(env) -> None:
    """Contract guard (audit 343): hourly buckets over a year is a ~8.8k-bucket cost setting no
    UI uses — the combination 422s; a month of hourly stays legal (744 buckets)."""
    login, _client = env
    cid = f"c-trend-{uuid.uuid4().hex[:8]}"
    http = await login()
    r = await http.get(
        "/api/v1/trends/scans", params={"cluster_id": cid, "days": 365, "interval": "hour"}
    )
    assert r.status_code == 422
    r = await http.get(
        "/api/v1/trends/scans", params={"cluster_id": cid, "days": 31, "interval": "hour"}
    )
    assert r.status_code == 200 and r.json()["interval"] == "hour"


async def test_scans_trend_dedups_the_real_rollover_duplicate(env) -> None:
    login, client = env
    cid = f"c-trend-{uuid.uuid4().hex[:8]}"

    await ingest_envelope(client, _envelope(cid, "run-1", 1))
    await client.indices.rollover(alias=f"javv-scan-events-{cid}")
    await ingest_envelope(client, _envelope(cid, "run-1", 1))  # the post-rollover retry

    pattern = f"javv-scan-events-{cid}-*"
    await client.indices.refresh(index=pattern)
    raw = await client.count(index=pattern)
    assert raw["count"] == 2  # the duplicate is REAL in storage (task B — accepted there)

    http = await login()
    r = await http.get("/api/v1/trends/scans", params={"cluster_id": cid, "days": 7})
    assert r.status_code == 200
    series = r.json()["series"]
    assert _today_bucket(series["trivy"], "scans") == 1  # …and deduped at read (#139)

    await ingest_envelope(client, _envelope(cid, "run-2", 2))  # a genuinely new committed scan
    await client.indices.refresh(index=pattern)
    r = await http.get("/api/v1/trends/scans", params={"cluster_id": cid, "days": 7})
    assert _today_bucket(r.json()["series"]["trivy"], "scans") == 2

    # tenant isolation: a fresh cluster sees an empty series, never this one's scans
    other = f"c-trend-{uuid.uuid4().hex[:8]}"
    r = await http.get("/api/v1/trends/scans", params={"cluster_id": other, "days": 7})
    assert r.status_code == 200
    assert r.json()["series"] == {}


async def test_findings_trend_reports_new_vs_resolved_per_scanner(env) -> None:
    login, client = env
    cid = f"c-trend-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    rows = [
        # new today (trivy), still present
        {"first_seen_at": now.isoformat(), "scanner": "trivy"},
        # new today (trivy) but already tombstoned — STILL counts as new (no present filter)
        {"first_seen_at": now.isoformat(), "scanner": "trivy", "present": False},
        # new last week (grype), resolved today
        {
            "first_seen_at": (now - timedelta(days=6)).isoformat(),
            "resolved_at": now.isoformat(),
            "scanner": "grype",
            "present": False,
        },
        # ancient — outside the window entirely
        {"first_seen_at": (now - timedelta(days=90)).isoformat(), "scanner": "trivy"},
    ]
    for row in rows:
        fk = f"fk-{uuid.uuid4().hex[:10]}"
        await client.index(
            index="findings",
            id=fk,
            body={
                "finding_key": fk,
                "cluster_id": cid,
                "cve_id": "CVE-2024-5000",
                "image_digest": "sha256:trend01",
                "namespaces": ["default"],
                "state": "open",
                "present": True,
                "severity": "high",
                "severity_rank": 4,
                **row,
            },
        )
    await client.indices.refresh(index="findings")

    http = await login()
    r = await http.get("/api/v1/trends/findings", params={"cluster_id": cid, "days": 30})
    assert r.status_code == 200
    out = r.json()
    assert _today_bucket(out["new"]["trivy"], "count") == 2  # tombstoned-new still counts
    assert _today_bucket(out["resolved"]["grype"], "count") == 1
    assert "grype" in out["new"]  # the grype row is new 6 days ago, inside the window
    assert _today_bucket(out["new"]["grype"], "count") == 0

    r = await http.get(
        "/api/v1/trends/findings",
        params={"cluster_id": cid, "days": 30, "as_of": "2026-01-01T00:00:00Z"},
    )
    assert r.status_code == 501  # the uniform D28 seam


# issue 1293: the Scan ingest strip follows the filters of the table that a scan record holds.
def _scan(
    cid: str, run: str, scanner: str, image_ref: str, digest: str, ns: list[str]
) -> IngestEnvelope:
    doc = {
        **GOLDEN,
        "cluster_id": cid,
        "scanner": scanner,
        "scan_run_id": run,
        "image_ref": image_ref,
        "image_digest": "sha256:" + digest * 64,
        "namespaces": ns,
        "last_seen_at": datetime.now(UTC).isoformat(),
    }
    if scanner == "grype":
        doc["effective_config"] = {**GOLDEN["effective_config"], "tuning": GRYPE_TUNING}
    return IngestEnvelope.model_validate(doc)


def _today(series: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """The scans of today for each scanner; a scanner with no scan in the range has no series."""
    return {scanner: _today_bucket(points, "scans") for scanner, points in series.items()}


async def test_scans_trend_follows_the_scan_filters(env) -> None:
    """Issue 1293: the namespace, image, tag, digest and scanner filters of /findings select the
    scans, on the fields of the scan record. A filter on any namespace of a record matches it."""
    login, client = env
    cid = f"c-trend-{uuid.uuid4().hex[:8]}"
    await ingest_envelope(client, _scan(cid, "r1", "trivy", "shop/app:1.4.2", "1", ["shop"]))
    await ingest_envelope(
        client, _scan(cid, "r2", "trivy", "shop/app:1.4.1", "2", ["shop", "team-b"])
    )
    await ingest_envelope(client, _scan(cid, "r3", "trivy", "ops/tool", "3", ["ops"]))  # no tag
    await ingest_envelope(client, _scan(cid, "r4", "grype", "shop/app:1.4.2", "1", ["shop"]))
    # a cluster whose id starts with this one: the index pattern of `cid` matches its indices
    # too, so only the forced cluster_id term keeps its scan out of the counts below
    neighbour = f"{cid}-x"
    await ingest_envelope(client, _scan(neighbour, "rx", "trivy", "shop/app:1.4.2", "1", ["shop"]))
    await client.indices.refresh(index=f"javv-scan-events-{cid}-*")
    http = await login()

    async def scans(**filters: Any) -> dict[str, int]:
        r = await http.get("/api/v1/trends/scans", params={"cluster_id": cid, "days": 7, **filters})
        assert r.status_code == 200, r.text
        return _today(r.json()["series"])

    assert await scans() == {"trivy": 3, "grype": 1}
    assert await scans(namespace="team-b") == {"trivy": 1}
    assert await scans(namespace=["shop", "ops"]) == {"trivy": 3, "grype": 1}
    assert await scans(exclude_namespace="shop") == {"trivy": 1}
    assert await scans(image_repo="shop/app", tag="1.4.2") == {"trivy": 1, "grype": 1}
    assert await scans(exclude_image_repo="shop/app") == {"trivy": 1}
    assert await scans(exclude_tag="1.4.2") == {"trivy": 2}
    assert await scans(untagged="true") == {"trivy": 1}
    assert await scans(untagged="false") == {"trivy": 2, "grype": 1}
    assert await scans(image_digest="sha256:" + "1" * 64) == {"trivy": 1, "grype": 1}
    assert await scans(scanner="grype") == {"grype": 1}
    assert await scans(exclude_scanner="grype") == {"trivy": 3}

    # tenant isolation: the neighbour counts its own scan only, and a cluster with no scans none
    r = await http.get(
        "/api/v1/trends/scans",
        params={"cluster_id": neighbour, "days": 7, "namespace": "shop"},
    )
    assert _today(r.json()["series"]) == {"trivy": 1}
    other = f"c-trend-{uuid.uuid4().hex[:8]}"
    r = await http.get(
        "/api/v1/trends/scans", params={"cluster_id": other, "days": 7, "namespace": "shop"}
    )
    assert r.status_code == 200 and r.json()["series"] == {}


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"tag": "1.4.2", "untagged": "true"}, id="tag with untagged"),
        pytest.param({"namespace": "a", "exclude_namespace": "b"}, id="a filter and its exclude"),
        pytest.param({"scanner": "trivy", "exclude_scanner": "grype"}, id="scanner both sides"),
        pytest.param({"scanner": "clair"}, id="a scanner JAVV does not run"),
        pytest.param({"namespace": [f"n{i}" for i in range(33)]}, id="33 namespaces"),
        pytest.param({"namespace": "n" * 257}, id="a namespace of 257 characters"),
        pytest.param({"image_digest": "d" * 129}, id="a digest of 129 characters"),
    ],
)
async def test_scans_trend_refuses_what_findings_refuses(env, params: dict[str, Any]) -> None:
    """The caps and the pairs of /findings, so the strip cannot send what the table refuses."""
    login, _client = env
    http = await login()
    r = await http.get(
        "/api/v1/trends/scans",
        params={"cluster_id": f"c-trend-{uuid.uuid4().hex[:8]}", "days": 7, **params},
    )
    assert r.status_code == 422, r.text


# issue 1292: the New findings strip. The findings first seen in each bucket, by severity, under
# the filters of the table.
def _raw_words(cid: str, scanner: str, run: str) -> IngestEnvelope:
    """The golden scan with mixed-case severity words, as scanners send them."""
    doc = {
        **GOLDEN,
        "cluster_id": cid,
        "scanner": scanner,
        "scan_run_id": run,
        "last_seen_at": datetime.now(UTC).isoformat(),
        "findings": [dict(f) for f in GOLDEN["findings"]],
    }
    if scanner == "grype":
        doc["effective_config"] = {**GOLDEN["effective_config"], "tuning": GRYPE_TUNING}
    doc["findings"][4]["severity"] = "Critical"  # was CRITICAL
    doc["findings"][8]["severity"] = "High"  # was HIGH
    return IngestEnvelope.model_validate(doc)


def _totals(series: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {sev: sum(p["count"] for p in points) for sev, points in series.items()}


GRYPE_TUNING = {"only_fixed": False, "scope": None, "scan_timeout": 300}
GOLDEN_COUNTS = {"critical": 4, "high": 8, "medium": 8, "low": 5, "unknown": 4}


async def _seed_row(client: AsyncOpenSearch, cid: str, **row: Any) -> None:
    fk = f"fk-{uuid.uuid4().hex[:10]}"
    await client.index(
        index="findings",
        id=fk,
        body={
            "finding_key": fk,
            "cluster_id": cid,
            "scanner": "trivy",
            "cve_id": "CVE-2024-5000",
            "image_digest": "sha256:newfindings01",
            "namespaces": ["default"],
            "state": "open",
            "present": True,
            "severity": "critical",
            "severity_canonical": "critical",
            "severity_rank": 5,
            **row,
        },
    )


async def test_new_findings_trend_counts_raw_scanner_words_in_canonical_buckets(env) -> None:
    login, client = env
    cid = f"c-newf-{uuid.uuid4().hex[:8]}"
    other = f"c-newf-{uuid.uuid4().hex[:8]}"
    await ingest_envelope(client, _raw_words(other, "trivy", "run-o"))  # never counts for cid
    await ingest_envelope(client, _raw_words(cid, "trivy", "run-t"))
    await ingest_envelope(client, _raw_words(cid, "grype", "run-g"))
    await client.indices.refresh(index="findings")

    http = await login()
    params: dict[str, Any] = {"cluster_id": cid, "days": 7}
    r = await http.get("/api/v1/trends/new-findings", params=params)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["days"] == 7
    assert out["interval"] == "day"
    # each scanner's row counts: the two scans give twice the golden counts, never merged
    assert _totals(out["series"]) == {k: 2 * v for k, v in GOLDEN_COUNTS.items()}
    assert _today_bucket(out["series"]["critical"], "count") == 8
    assert len(out["series"]["critical"]) == 8  # a continuous axis: 7 days back to today

    r = await http.get("/api/v1/trends/new-findings", params={**params, "scanner": "trivy"})
    assert _totals(r.json()["series"]) == GOLDEN_COUNTS  # the Scanner filter of the table
    r = await http.get(
        "/api/v1/trends/new-findings", params={**params, "severity": ["critical", "high"]}
    )
    assert _totals(r.json()["series"]) == {"critical": 8, "high": 16}

    r = await http.get("/api/v1/trends/new-findings", params={"cluster_id": other, "days": 7})
    assert _totals(r.json()["series"]) == GOLDEN_COUNTS  # one scan only: cid never leaks in

    r = await http.get("/api/v1/trends/new-findings", params={**params, "interval": "hour"})
    assert r.status_code == 200
    assert r.json()["interval"] == "hour"
    assert _totals(r.json()["series"]) == {k: 2 * v for k, v in GOLDEN_COUNTS.items()}


async def test_new_findings_trend_follows_presence_overdue_and_the_window(env) -> None:
    login, client = env
    cid = f"c-newf-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    await _seed_row(client, cid, first_seen_at=now.isoformat())  # new, present
    await _seed_row(client, cid, first_seen_at=now.isoformat(), present=False)  # gone again
    # a scanner clock ahead of the server: first seen after now, not new yet
    await _seed_row(client, cid, first_seen_at=(now + timedelta(hours=3)).isoformat())
    await _seed_row(client, cid, first_seen_at=(now - timedelta(days=40)).isoformat())  # too old
    # a sibling clock from long ago: past the critical SLA of the default policy
    await _seed_row(
        client,
        cid,
        first_seen_at=(now - timedelta(days=1)).isoformat(),
        sla_clock_at=(now - timedelta(days=400)).isoformat(),
        severity_canonical="high",
    )
    await client.indices.refresh(index="findings")

    http = await login()
    params: dict[str, Any] = {"cluster_id": cid, "days": 30}
    r = await http.get("/api/v1/trends/new-findings", params=params)
    assert _totals(r.json()["series"]) == {"critical": 1, "high": 1}  # D2 A: present now
    r = await http.get("/api/v1/trends/new-findings", params={**params, "present": "false"})
    assert _totals(r.json()["series"]) == {"critical": 1}
    # the overdue filter reads the cutoffs of the live policy, as the grid does (never a 500)
    r = await http.get("/api/v1/trends/new-findings", params={**params, "overdue": "true"})
    assert r.status_code == 200, r.text
    assert _totals(r.json()["series"]) == {"high": 1}

    r = await http.get(
        "/api/v1/trends/new-findings", params={**params, "days": 32, "interval": "hour"}
    )
    assert r.status_code == 422  # the hourly cap of /trends/scans
    r = await http.get(
        "/api/v1/trends/new-findings", params={**params, "tag": "1.4.1", "untagged": "true"}
    )
    assert r.status_code == 422  # the pair that the table refuses
