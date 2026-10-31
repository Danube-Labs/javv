"""M6 slice 1 — GET /api/v1/findings against real OpenSearch.

Pins: tenant isolation through the tenant read path (a page NEVER carries another cluster's rows);
deep paging via the opaque cursor with ZERO PITs left behind after the walk (D38); facet
filters; the default present=true grid vs the opt-in tombstone view; overdue decoration via the
M5d group clock (D21 — the group's EARLIEST first_seen_at drives every sibling, even when the
page filter hides the earliest row); `as_of` in the past is 501 until M8b's seam lands.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from backend.models.envelope import canonical_severity
from backend.query.search import FILTER_PAIRS, MAX_FILTER_VALUES
from os_env import OS_URL, clear_pits, requires_opensearch

PASSWORD = "findings-route-password"


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
            "first_seen_at": now,
            **row,
        }
        # D46/#274 hygiene: derive the canonical query key exactly like the server does — a
        # vocabulary drift can never again be self-consistent with hand-seeded docs
        doc.setdefault("severity_canonical", canonical_severity(doc["severity"]))
        await client.index(index="findings", id=doc["finding_key"], body=doc)
    await client.indices.refresh(index="findings")


def _rows(n: int, *, cve: str = "CVE-2024-9000", **over: Any) -> list[dict[str, Any]]:
    return [
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": cve,
            "image_digest": f"sha256:aa{i:02d}",
            **over,
        }
        for i in range(n)
    ]


async def _pit_count(client: AsyncOpenSearch) -> int:
    resp = await client.transport.perform_request("GET", "/_search/point_in_time/_all")
    return len(resp.get("pits") or [])


async def test_tenant_isolation_and_default_grid(env) -> None:
    login, client = env
    cid_a, cid_b = f"c-srch-{uuid.uuid4().hex[:8]}", f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid_a, _rows(3))
    await _seed(client, cid_b, _rows(2))
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid_a})
    assert r.status_code == 200
    out = r.json()
    assert out["total"]["value"] == 3
    assert {d["cluster_id"] for d in out["data"]} == {cid_a}  # never another tenant's rows
    assert out["next_cursor"] is None

    r = await http.get("/api/v1/findings")  # cluster_id is REQUIRED, never all-tenant
    assert r.status_code == 422


# serial: clears and counts every open PIT in the store, so it cannot share it with a live walk
@pytest.mark.serial
async def test_deep_paging_leaves_zero_pits_behind(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(5))
    http = await login()

    await clear_pits(client)
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params: dict[str, Any] = {"cluster_id": cid, "size": 2}
        if cursor:
            params["cursor"] = cursor
        r = await http.get("/api/v1/findings", params=params)
        assert r.status_code == 200
        out = r.json()
        seen += [d["finding_key"] for d in out["data"]]
        cursor = out["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 5 and len(set(seen)) == 5  # complete, no dup/skip across pages
    assert await _pit_count(client) == 0  # the walk cleaned its PITs (D38)

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "cursor": "garbage!"})
    assert r.status_code == 422  # an unreadable cursor is a client error, not a 500


async def test_pit_cap_429s_per_principal_and_release_frees_a_slot(env, monkeypatch) -> None:
    """A-m12 (audit #189): a principal that piles up open cursors past the cap gets a 429; a
    different principal is unaffected; finishing a walk (its final page) frees a slot."""
    import backend.query.pit_guard as pit_guard

    login, client = env
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "2")
    get_settings.cache_clear()
    pit_guard._slots.clear()
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(3))
    http, other = await login(), await login()

    # each cursor-less size=1 page over 3 docs returns a next_cursor → the PIT + its slot persist
    cursors: list[str] = []
    for _ in range(2):
        r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
        assert r.status_code == 200 and r.json()["next_cursor"] is not None
        cursors.append(r.json()["next_cursor"])

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 429 and r.headers.get("retry-after") == "5"

    r = await other.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200  # a different principal has its own budget

    cursor: str | None = cursors[0]  # drive one walk to its final page → releases that slot
    while cursor:
        r = await http.get(
            "/api/v1/findings", params={"cluster_id": cid, "size": 1, "cursor": cursor}
        )
        assert r.status_code == 200
        cursor = r.json()["next_cursor"]

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200  # a slot freed up — the open fits again


async def test_tampered_but_decodable_cursor_is_422_not_500(env) -> None:
    """A-m1 (audit #191): a base64/JSON-valid cursor with a bad shape is a 422 at the door, never
    a 500 from inside client.search — on both the grid and the groups routes."""
    import base64
    import json

    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(2))
    http = await login()

    bad = base64.urlsafe_b64encode(
        json.dumps({"p": "x", "a": "notalist", "s": "severity_rank", "o": "asc"}).encode()
    ).decode()
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "cursor": bad})
    assert r.status_code == 422

    bad_after = base64.urlsafe_b64encode(json.dumps({"key": {"nested": 1}}).encode()).decode()
    r = await http.get(
        "/api/v1/findings/groups",
        params={"cluster_id": cid, "by": "image_repo", "cursor": bad_after},
    )
    assert r.status_code == 422


# serial: deletes every PIT in the store, which would kill another worker's walk mid-page
@pytest.mark.serial
async def test_expired_pit_cursor_is_410_and_a_fresh_walk_is_unaffected(env) -> None:
    """A-m1 (audit #191): a client that idled past keep_alive gets a clear 410 "restart", not a
    500 — and a brand-new walk (its own fresh PIT) still works."""
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(3))
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200
    cursor = r.json()["next_cursor"]
    assert cursor  # a live multi-page walk

    # kill the PIT out-of-band → the client's next page references a context that's gone
    await client.transport.perform_request("DELETE", "/_search/point_in_time/_all")

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1, "cursor": cursor})
    assert r.status_code == 410
    assert "restart" in r.json()["title"].lower()

    # a fresh walk opens its own PIT — unaffected by the expiry above
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 1})
    assert r.status_code == 200


async def test_read_route_forces_no_refresh(env, monkeypatch) -> None:
    """A-m2 (audit #191): the read path must not force a Lucene refresh (the #117 storm relocated
    to reads). Seeding refreshes explicitly; the route itself calls refresh zero times."""
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(1))  # _seed already refreshes findings
    http = await login()

    calls: list[Any] = []
    orig = client.indices.refresh

    async def _spy(*a: Any, **k: Any) -> Any:
        calls.append((a, k))
        return await orig(*a, **k)

    monkeypatch.setattr(client.indices, "refresh", _spy)
    r = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.status_code == 200
    assert calls == []  # the read forced no refresh


async def test_facets_filter_the_grid(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(2, severity="CRITICAL", severity_rank=5, state="open"))
    await _seed(client, cid, _rows(3, cve="CVE-2024-9001", state="acknowledged"))
    http = await login()

    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "severity": ["critical"], "state": ["open"]},
    )
    assert r.status_code == 200
    assert r.json()["total"]["value"] == 2
    assert all(d["severity"] == "CRITICAL" for d in r.json()["data"])


async def test_tombstone_view_is_opt_in(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _rows(2))
    await _seed(client, cid, _rows(1, cve="CVE-2024-9002", present=False))
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.json()["total"]["value"] == 2  # the grid is the "now" view (D39)
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "present": "false"})
    assert r.json()["total"]["value"] == 1
    assert r.json()["data"][0]["present"] is False


async def test_overdue_decoration_uses_the_group_clock(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    digest = "sha256:groupclock01"
    # grype saw the vuln 30 days ago; trivy's row is fresh — SAME (cve, digest) group (D21)
    await _seed(
        client,
        cid,
        [
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-7777",
                "image_digest": digest,
                "scanner": "grype",
                "first_seen_at": old,
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-7777",
                "image_digest": digest,
                "scanner": "trivy",
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
            # a handled row is never overdue, however old (M5d)
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-7778",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": old,
                "state": "risk_accepted",
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
        ],
    )
    http = await login()

    # page filtered to trivy only — the fresh row must STILL be overdue off grype's clock
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "scanner": "trivy"})
    assert r.status_code == 200
    by_cve = {d["cve_id"]: d for d in r.json()["data"]}
    assert by_cve["CVE-2024-7777"]["overdue"] is True
    assert by_cve["CVE-2024-7777"]["due_at"] is not None
    assert by_cve["CVE-2024-7778"]["overdue"] is False
    assert by_cve["CVE-2024-7778"]["due_at"] is None


async def test_group_clock_is_exact_across_a_paged_composite(env, monkeypatch) -> None:
    """A-M4 (audit #187, both passes): the group clock must be the EXACT earliest first_seen_at per
    (cve, digest), fetched via a composite agg that PAGES to exhaustion — never the old truncatable
    cve×digest cross-product doc fetch that could drop the earliest holder and under-report overdue.
    Force the composite page to 1 so the target pair's bucket lands on a later page; its off-page
    (grype) clock must still make the trivy row overdue."""
    monkeypatch.setattr("backend.routers.findings._GROUP_CLOCK_PAGE", 1)
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    rows: list[dict[str, Any]] = [
        # noise pairs (present, on-page under a trivy filter) so the composite spans several pages
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": f"CVE-N-{i}",
            "image_digest": f"sha256:noise{i}",
            "scanner": "trivy",
        }
        for i in range(3)
    ]
    # the target group: grype saw it 30d ago (hidden by the trivy page filter), trivy fresh
    rows += [
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": "CVE-TGT",
            "image_digest": "sha256:tgt",
            "scanner": "grype",
            "first_seen_at": old,
            "severity": "CRITICAL",
            "severity_rank": 5,
        },
        {
            "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
            "cve_id": "CVE-TGT",
            "image_digest": "sha256:tgt",
            "scanner": "trivy",
            "severity": "CRITICAL",
            "severity_rank": 5,
        },
    ]
    await _seed(client, cid, rows)
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "scanner": "trivy"})
    assert r.status_code == 200
    by_cve = {d["cve_id"]: d for d in r.json()["data"]}
    assert by_cve["CVE-TGT"]["overdue"] is True  # exact clock survived the paged composite


async def test_group_clock_is_tenant_scoped(env) -> None:
    """The group-clock fetch carries cluster_id (tenant read path): an identical (cve, digest) in
    ANOTHER cluster, however ancient, must never anchor this cluster's clock (audit #187)."""
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    other = f"c-other-{uuid.uuid4().hex[:8]}"
    ancient = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    fresh = datetime.now(UTC).isoformat()
    digest = "sha256:tenantclock"
    await _seed(
        client,
        other,
        [
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-TEN",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": ancient,
                "severity": "CRITICAL",
                "severity_rank": 5,
            }
        ],
    )
    await _seed(
        client,
        cid,
        [
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-TEN",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": fresh,
                "severity": "CRITICAL",
                "severity_rank": 5,
            }
        ],
    )
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.status_code == 200
    by_cve = {d["cve_id"]: d for d in r.json()["data"]}
    # crit SLA is 2 days; the same-cluster clock is fresh (not overdue). If the other tenant's
    # 90-day-old sibling leaked in, this would be overdue — it must not.
    assert by_cve["CVE-TEN"]["overdue"] is False


async def test_reads_require_auth_and_as_of_past_is_501(env) -> None:
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    http = await login()

    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http._transport.app),  # type: ignore[attr-defined]
        base_url="https://t",
    )
    r = await bare.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.status_code == 401
    await bare.aclose()

    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "as_of": "2026-01-01T00:00:00+00:00"},
    )
    assert r.status_code == 501  # T<now reconstruction lands with M8b (D28 seam)


# ── slice 2: /facets + /groups ─────────────────────────────────────────────────────────────────


async def test_facets_count_per_scanner_and_stay_in_tenant(env) -> None:
    login, client = env
    cid_a, cid_b = f"c-aggs-{uuid.uuid4().hex[:8]}", f"c-aggs-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid_a, _rows(2, severity="CRITICAL", severity_rank=5))
    await _seed(client, cid_a, _rows(1, cve="CVE-2024-9100", scanner="grype"))
    await _seed(client, cid_b, _rows(4, severity="CRITICAL", severity_rank=5))  # other tenant
    http = await login()

    r = await http.get("/api/v1/findings/facets", params={"cluster_id": cid_a})
    assert r.status_code == 200
    facets = r.json()["facets"]
    sev = {b["key"]: b for b in facets["severity"]}
    assert sev["critical"]["count"] == 2  # tenant B's 4 crits are invisible (SEC-4)
    assert sev["critical"]["by_scanner"] == {"trivy": 2}  # per-scanner is sacred
    assert sev["high"]["by_scanner"] == {"grype": 1}
    assert {b["key"] for b in facets["scanner"]} == {"trivy", "grype"}
    # bool facets keep readable keys, not 0/1
    assert {b["key"] for b in facets["present"]} == {"true"}

    r = await http.get(
        "/api/v1/findings/facets", params={"cluster_id": cid_a, "fields": ["package_name"]}
    )
    assert r.status_code == 422  # not facetable — whitelist enforced at the edge


async def test_new_excludes_are_pure_must_not_with_a_missing_field(env) -> None:
    """Issue 492: the `cve_id`/`package_name` exclude twins, proven against a real index
    rather than by clause shape alone.

    `package_name` is the field that makes the pure-must_not rule load-bearing: an OS-level
    finding can carry no package at all, and an exists-guarded exclusion would silently drop
    those rows — the operator would exclude one package and lose findings that never had one.
    Seeded here as a row with the field ABSENT, and asserted to survive.
    """
    login, client = env
    cid = f"c-x492-{uuid.uuid4().hex[:8]}"
    await _seed(
        client,
        cid,
        [
            *_rows(2, cve="CVE-2024-1000", package_name="zlib"),
            *_rows(3, cve="CVE-2024-2000", package_name="openssl"),
            *_rows(1, cve="CVE-2024-3000"),  # no package_name key at all — the carve-out
        ],
    )
    http = await login()

    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "size": 50, "exclude_package_name": "zlib"},
    )
    assert r.status_code == 200
    rows = r.json()["data"]
    assert {d["cve_id"] for d in rows} == {"CVE-2024-2000", "CVE-2024-3000"}
    assert len(rows) == 4  # 3 openssl + the package-less row, which the exclusion must KEEP

    # the include side is an exact term, and its exclude twin is the exact complement
    r = await http.get(
        "/api/v1/findings", params={"cluster_id": cid, "size": 50, "package_name": "zlib"}
    )
    assert {d["cve_id"] for d in r.json()["data"]} == {"CVE-2024-1000"}

    r = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "size": 50, "exclude_cve_id": "CVE-2024-1000"},
    )
    assert {d["cve_id"] for d in r.json()["data"]} == {"CVE-2024-2000", "CVE-2024-3000"}

    # facets ride the SAME builder as the grid, so a count that disagrees with the rows is a
    # bug the rail would show (the #488 shape) — pinned here under the new must_not
    r = await http.get(
        "/api/v1/findings/facets",
        params={"cluster_id": cid, "fields": ["severity"], "exclude_package_name": "zlib"},
    )
    assert r.status_code == 200
    facet_total = sum(b["count"] for b in r.json()["facets"]["severity"])
    assert facet_total == 4

    # a field is include OR exclude, never both — 422 before the builder's ValueError
    for pair in (
        {"package_name": "zlib", "exclude_package_name": "openssl"},
        {"cve_id": "CVE-2024-1000", "exclude_cve_id": "CVE-2024-2000"},
    ):
        r = await http.get("/api/v1/findings", params={"cluster_id": cid, **pair})
        assert r.status_code == 422


# one query value for each side of every pair (issue 969)
_PAIR_PARAM = {
    "severity": "high",
    "state": "open",
    "scanner": "trivy",
    "assignee": "ana",
    "image_repo": "registry.local/api",
    "namespace": "payments",
    "ptype": "os",
    "cve_id": "CVE-2024-1000",
    "package_name": "zlib",
    "unassigned": "true",
}


async def test_the_route_refuses_each_pair_of_the_shared_list(env) -> None:
    """Saved views and export settings refuse the pairs of FILTER_PAIRS; the route reads the same
    list, so a view or a queued export can never hold a pair the screen answers with 422. The
    CSV export is the read where only this check stands between a pair and a 500: /findings
    also turns the builder's own ValueError into a 422."""
    login, _ = env
    http = await login()
    cid = f"c-pairs-{uuid.uuid4().hex[:8]}"
    for first, second in FILTER_PAIRS:
        params = {
            "cluster_id": cid,
            first: _PAIR_PARAM[first],
            second: _PAIR_PARAM[second.removeprefix("exclude_")],
        }
        for path in ("/api/v1/findings", "/api/v1/findings/export.csv"):
            r = await http.get(path, params=params)
            assert r.status_code == 422, (path, first, second)
            assert r.json()["title"] == f"{first} and {second} are mutually exclusive"


async def test_several_values_in_one_filter_against_a_real_index(env) -> None:
    """Issue 949: a repeated parameter is a list. The values are ORed inside the field, an
    exclude list drops every listed value, and one value keeps the meaning it always had.
    `namespaces` is a keyword array, so a row in two namespaces matches either one."""
    login, client = env
    cid = f"c-x949-{uuid.uuid4().hex[:8]}"
    await _seed(
        client,
        cid,
        [
            *_rows(1, cve="CVE-2024-0001", namespaces=["a"], assignee="alice"),
            *_rows(1, cve="CVE-2024-0002", namespaces=["b"], assignee="bob"),
            *_rows(1, cve="CVE-2024-0003", namespaces=["c"]),
            *_rows(1, cve="CVE-2024-0004", namespaces=["a", "c"], assignee="carol"),
        ],
    )
    http = await login()

    async def cves(**params: Any) -> set[str]:
        r = await http.get("/api/v1/findings", params={"cluster_id": cid, "size": 50, **params})
        assert r.status_code == 200, r.text
        return {d["cve_id"] for d in r.json()["data"]}

    assert await cves(namespace=["a", "b"]) == {"CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0004"}
    assert await cves(namespace="c") == {"CVE-2024-0003", "CVE-2024-0004"}
    # "is not a, b" drops a row in EITHER, including the row that is also in c
    assert await cves(exclude_namespace=["a", "b"]) == {"CVE-2024-0003"}
    assert await cves(assignee=["alice", "bob"]) == {"CVE-2024-0001", "CVE-2024-0002"}
    # the pure must_not rule holds for a list: the row with no assignee stays
    assert await cves(exclude_assignee=["alice", "bob"]) == {"CVE-2024-0003", "CVE-2024-0004"}
    assert await cves(cve_id=["CVE-2024-0001", "CVE-2024-0003"]) == {
        "CVE-2024-0001",
        "CVE-2024-0003",
    }

    # the groups route and the facets route read the same filter dependency
    r = await http.get(
        "/api/v1/findings/groups",
        params={"cluster_id": cid, "by": "cve_id", "namespace": ["a", "b"]},
    )
    assert {g["key"] for g in r.json()["data"]} == {
        "CVE-2024-0001",
        "CVE-2024-0002",
        "CVE-2024-0004",
    }

    refused = (
        {"namespace": [f"n{i}" for i in range(MAX_FILTER_VALUES + 1)]},  # one value too many
        {"namespace": "x" * 257},  # each value keeps its own length cap
        {"namespace": ["a"], "exclude_namespace": ["b"]},  # include OR exclude, never both
        {"assignee": ["alice", "bob"], "unassigned": "true"},
    )
    for params in refused:
        r = await http.get("/api/v1/findings", params={"cluster_id": cid, **params})
        assert r.status_code == 422, params
    ok = await http.get(
        "/api/v1/findings",
        params={"cluster_id": cid, "namespace": [f"n{i}" for i in range(MAX_FILTER_VALUES)]},
    )
    assert ok.status_code == 200


async def test_list_facets_leave_out_their_own_filter_against_a_real_index(env) -> None:
    """Issue 949, ruling 2. After a pick of namespace a, the Namespace facet still lists b and c
    with their counts, so a second pick is possible. Every other facet still counts under the
    pick: the saved-view card count is the severity sum under the view's filters, and it must
    stay equal to the grid total."""
    login, client = env
    cid = f"c-f949-{uuid.uuid4().hex[:8]}"
    await _seed(
        client,
        cid,
        [
            *_rows(2, cve="CVE-2024-0001", namespaces=["a"], severity="critical", ptype="deb"),
            *_rows(3, cve="CVE-2024-0002", namespaces=["b"], severity="low", ptype="npm"),
            *_rows(1, cve="CVE-2024-0003", namespaces=["c"], severity="low", ptype="deb"),
        ],
    )
    http = await login()

    async def facets(**params: Any) -> dict[str, dict[str, int]]:
        r = await http.get(
            "/api/v1/findings/facets",
            params={"cluster_id": cid, "fields": ["namespaces", "severity", "ptype"], **params},
        )
        assert r.status_code == 200, r.text
        return {k: {b["key"]: b["count"] for b in v} for k, v in r.json()["facets"].items()}

    picked = await facets(namespace="a")
    assert picked["namespaces"] == {"a": 2, "b": 3, "c": 1}  # the others stay listed
    assert picked["severity"] == {"critical": 2}  # severity still counts under the pick
    assert picked["ptype"] == {"deb": 2}

    two = await facets(namespace=["a", "b"], ptype="deb")
    assert two["namespaces"] == {"a": 2, "c": 1}  # counts under the ptype pick, not its own
    assert two["ptype"] == {"deb": 2, "npm": 3}  # counts under the namespace pick only
    assert two["severity"] == {"critical": 2}

    # an excluded value stays listed with its count, so the rail can show it struck out
    excluded = await facets(exclude_namespace="a")
    assert excluded["namespaces"] == {"a": 2, "b": 3, "c": 1}
    assert excluded["severity"] == {"low": 4}

    # the saved-view count rule: the severity sum equals the grid total under the same filters
    grid = await http.get(
        "/api/v1/findings", params={"cluster_id": cid, "namespace": ["a", "b"], "ptype": "deb"}
    )
    assert sum(two["severity"].values()) == grid.json()["total"]["value"] == 2


async def test_all_filters_counts_the_list_facets_under_their_own_filter_against_a_real_index(
    env,
) -> None:
    """Issue 999, decision 4. A dashboard panel asks with `all_filters=true`: "Namespace is not
    a" leaves a out of the Namespace facet, and "Namespace is one of a, b" lists only a and b.
    Without the parameter, the Findings filter list keeps every value (issue 949)."""
    login, client = env
    cid = f"c-f999-{uuid.uuid4().hex[:8]}"
    await _seed(
        client,
        cid,
        [
            *_rows(2, cve="CVE-2024-0001", namespaces=["a"], severity="critical", ptype="deb"),
            *_rows(3, cve="CVE-2024-0002", namespaces=["b"], severity="low", ptype="npm"),
            *_rows(1, cve="CVE-2024-0003", namespaces=["c"], severity="low", ptype="deb"),
        ],
    )
    http = await login()

    async def facets(**params: Any) -> dict[str, dict[str, int]]:
        r = await http.get(
            "/api/v1/findings/facets",
            params={"cluster_id": cid, "fields": ["namespaces", "ptype"], **params},
        )
        assert r.status_code == 200, r.text
        return {k: {b["key"]: b["count"] for b in v} for k, v in r.json()["facets"].items()}

    not_a = await facets(exclude_namespace="a", all_filters="true")
    assert not_a["namespaces"] == {"b": 3, "c": 1}
    assert not_a["ptype"] == {"npm": 3, "deb": 1}
    two = await facets(namespace=["a", "b"], ptype="deb", all_filters="true")
    assert two["namespaces"] == {"a": 2}
    assert two["ptype"] == {"deb": 2}
    # the default stays the Findings rule
    assert (await facets(exclude_namespace="a"))["namespaces"] == {"a": 2, "b": 3, "c": 1}


async def test_the_unassigned_count_is_the_rows_its_click_shows_against_a_real_index(env) -> None:
    """Issue 979. With Assignee "is lead", a click on Unassigned clears Assignee (issue 975), so
    the Unassigned count must equal the grid total of `unassigned=true` under the other
    filters. With Assignee "is not" (the click keeps it), the count also equals the click."""
    login, client = env
    cid = f"c-f979-{uuid.uuid4().hex[:8]}"
    await _seed(
        client,
        cid,
        [
            *_rows(2, cve="CVE-2024-0011", assignee="lead", severity="critical"),
            *_rows(3, cve="CVE-2024-0012", severity="critical"),
            *_rows(1, cve="CVE-2024-0013", assignee="", severity="critical"),
            *_rows(4, cve="CVE-2024-0014", severity="low"),
            *_rows(1, cve="CVE-2024-0015", assignee="bob", severity="critical"),
        ],
    )
    http = await login()

    async def facets(**params: Any) -> dict[str, dict[str, int]]:
        r = await http.get(
            "/api/v1/findings/facets",
            params={"cluster_id": cid, "fields": ["unassigned", "severity"], **params},
        )
        assert r.status_code == 200, r.text
        return {k: {b["key"]: b["count"] for b in v} for k, v in r.json()["facets"].items()}

    async def total(**params: Any) -> int:
        r = await http.get("/api/v1/findings", params={"cluster_id": cid, **params})
        assert r.status_code == 200, r.text
        return r.json()["total"]["value"]

    picked = await facets(assignee="lead", severity="critical")
    clicked = await total(unassigned="true", severity="critical")
    assert picked["unassigned"] == {"true": clicked} == {"true": 4}  # None and "" are no owner
    assert picked["severity"] == {"critical": 2}  # the other facets keep Assignee "is"

    kept = await facets(exclude_assignee="bob", severity="critical")
    assert kept["unassigned"] == {"true": await total(unassigned="true", severity="critical")}
    assert kept["severity"] == {"critical": 6}  # 2 lead + 3 none + 1 empty, bob left out


async def test_groups_paginate_via_after_key_to_exhaustion(env) -> None:
    login, client = env
    cid = f"c-aggs-{uuid.uuid4().hex[:8]}"
    for i in range(5):
        await _seed(client, cid, _rows(2, cve=f"CVE-2024-92{i:02d}", image_repo=f"registry/app{i}"))
    http = await login()

    keys: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params: dict[str, Any] = {"cluster_id": cid, "by": "image_repo", "size": 2}
        if cursor:
            params["cursor"] = cursor
        r = await http.get("/api/v1/findings/groups", params=params)
        assert r.status_code == 200
        out = r.json()
        keys += [g["key"] for g in out["data"]]
        cursor = out["next_cursor"]
        if cursor is None:
            break
    # every bucket reachable — nothing silently capped (DoD)
    assert keys == sorted(f"registry/app{i}" for i in range(5))
    assert len(keys) == 5

    r = await http.get("/api/v1/findings/groups", params={"cluster_id": cid, "by": "severity"})
    assert r.status_code == 422  # facet field, not a group dim
    r = await http.get(
        "/api/v1/findings/groups",
        params={"cluster_id": cid, "by": "image_repo", "as_of": "2026-01-01T00:00:00Z"},
    )
    assert r.status_code == 501  # same as_of seam on every read (D28)


async def test_images_affected_decoration_counts_distinct_digests_per_cve(env) -> None:
    """M9b slice 4 / B-4: each page row carries `images_affected` = distinct image_digest count
    for its CVE (cluster + present=true scoped) — server-computed, tenant-isolated, and blind to
    tombstoned rows."""
    login, client = env
    cid, other = f"c-imgs-{uuid.uuid4().hex[:8]}", f"c-imgs-{uuid.uuid4().hex[:8]}"
    # CVE-A on 3 digests (one digest twice via both scanners — still ONE image), CVE-B on 1
    await _seed(
        client,
        cid,
        [
            {"finding_key": "ia-1", "cve_id": "CVE-A", "image_digest": "sha256:d1"},
            {"finding_key": "ia-2", "cve_id": "CVE-A", "image_digest": "sha256:d2"},
            {"finding_key": "ia-3", "cve_id": "CVE-A", "image_digest": "sha256:d3"},
            {
                "finding_key": "ia-4",
                "cve_id": "CVE-A",
                "image_digest": "sha256:d3",
                "scanner": "grype",
            },
            {"finding_key": "ia-5", "cve_id": "CVE-B", "image_digest": "sha256:d1"},
            # a tombstoned CVE-B sibling on another digest must NOT count toward "now"
            {
                "finding_key": "ia-6",
                "cve_id": "CVE-B",
                "image_digest": "sha256:d9",
                "present": False,
            },
        ],
    )
    # same CVE in another tenant: must never leak into this cluster's count
    await _seed(
        client, other, [{"finding_key": "ia-7", "cve_id": "CVE-A", "image_digest": "sha256:zz"}]
    )
    http = await login()

    r = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert r.status_code == 200
    counts = {d["cve_id"]: d["images_affected"] for d in r.json()["data"]}
    assert counts == {"CVE-A": 3, "CVE-B": 1}


async def test_overdue_filter_agrees_with_the_chip_on_a_coverage_lag_group(env) -> None:
    """Issue 363, the keystone: ?overdue=true returns EXACTLY the rows whose chip says overdue —
    including the coverage-lag row (fresh own sighting, old materialized group clock) that a
    per-doc first_seen_at filter would have missed. The negation is the exact complement."""
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    fresh = datetime.now(UTC).isoformat()
    digest = "sha256:clockfilter01"
    await _seed(
        client,
        cid,
        [
            # grype saw it 30d ago; trivy's row is FRESH but wears the materialized group clock
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-8801",
                "image_digest": digest,
                "scanner": "grype",
                "first_seen_at": old,
                "sla_clock_at": old,
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-8801",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": fresh,
                "sla_clock_at": old,  # the coverage-lag row — the whole point of the field
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
            # handled: never overdue, however old (shared HANDLED_STATES — chip ≡ filter)
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-8802",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": old,
                "sla_clock_at": old,
                "state": "risk_accepted",
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
            # fresh clock, inside its window — not breached
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-8803",
                "image_digest": digest,
                "scanner": "trivy",
                "first_seen_at": fresh,
                "sla_clock_at": fresh,
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
        ],
    )
    http = await login()

    unfiltered = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert unfiltered.status_code == 200
    chip_overdue = {d["finding_key"] for d in unfiltered.json()["data"] if d["overdue"]}

    breached = await http.get("/api/v1/findings", params={"cluster_id": cid, "overdue": "true"})
    assert breached.status_code == 200
    assert {d["finding_key"] for d in breached.json()["data"]} == chip_overdue
    assert {d["cve_id"] for d in breached.json()["data"]} == {
        "CVE-2024-8801"
    }  # BOTH scanners' rows

    ok = await http.get("/api/v1/findings", params={"cluster_id": cid, "overdue": "false"})
    assert ok.status_code == 200
    ok_keys = {d["finding_key"] for d in ok.json()["data"]}
    all_keys = {d["finding_key"] for d in unfiltered.json()["data"]}
    assert ok_keys == all_keys - chip_overdue  # exact complement

    # facets carry the lens like any other filter (the rail count describes the filtered grid)
    fac = await http.get(
        "/api/v1/findings/facets",
        params={"cluster_id": cid, "overdue": "true", "fields": "severity"},
    )
    assert fac.status_code == 200
    assert {b["key"]: b["count"] for b in fac.json()["facets"]["severity"]} == {"critical": 2}

    # the rail chip's own count: the overdue FACET (filter off) ≡ the filtered row count,
    # shaped as a true-bucket with the per-scanner split (per-scanner is sacred)
    count = await http.get(
        "/api/v1/findings/facets", params={"cluster_id": cid, "fields": "overdue"}
    )
    assert count.status_code == 200
    (bucket,) = count.json()["facets"]["overdue"]
    assert bucket["key"] == "true" and bucket["count"] == len(chip_overdue) == 2
    assert bucket["by_scanner"] == {"grype": 1, "trivy": 1}


async def test_unbackfilled_rows_keep_their_chip_but_escape_the_filter_loudly(env) -> None:
    """The pre-backfill degradation contract: a row missing sla_clock_at still gets a correct
    CHIP (agg fallback — never a silent under-report) but cannot match the FILTER (no field to
    range on). rebuild-state closes the gap; the decorator logs + bumps a metric meanwhile."""
    login, client = env
    cid = f"c-srch-{uuid.uuid4().hex[:8]}"
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    await _seed(
        client,
        cid,
        [
            {
                "finding_key": f"fk-{uuid.uuid4().hex[:10]}",
                "cve_id": "CVE-2024-8810",
                "image_digest": "sha256:nobackfill01",
                "first_seen_at": old,  # NO sla_clock_at — a pre-363 store
                "severity": "CRITICAL",
                "severity_rank": 5,
            },
        ],
    )
    http = await login()

    page = await http.get("/api/v1/findings", params={"cluster_id": cid})
    assert page.json()["data"][0]["overdue"] is True  # the chip is right (fallback agg)

    breached = await http.get("/api/v1/findings", params={"cluster_id": cid, "overdue": "true"})
    assert breached.json()["data"] == []  # an expected gap until rebuild-state backfills


async def test_a_value_search_finds_values_past_the_top_32_against_a_real_index(env) -> None:
    """Issue 1064. The text matches in any case, from all values of the field, with the counts
    of the list. A finding with a second namespace does not bring that namespace into the
    result, and another tenant's values stay out."""
    login, client = env
    cid, other = f"c-f1064-{uuid.uuid4().hex[:8]}", f"c-f1064-{uuid.uuid4().hex[:8]}"
    # 40 top values that do not match, so every "pay" value is past the top 32
    await _seed(client, cid, [r for i in range(40) for r in _rows(3, namespaces=[f"ns-{i:02d}"])])
    await _seed(client, cid, [r for i in range(33) for r in _rows(1, namespaces=[f"pay-{i:02d}"])])
    await _seed(client, cid, _rows(2, namespaces=["Payroll-EU", "kube-system"], scanner="grype"))
    await _seed(client, other, _rows(5, namespaces=["payments-other"]))
    http = await login()

    async def search(text: str, **params: Any) -> httpx.Response:
        return await http.get(
            "/api/v1/findings/facets",
            params={"cluster_id": cid, "fields": ["namespaces"], "contains": text, **params},
        )

    top = await http.get(
        "/api/v1/findings/facets", params={"cluster_id": cid, "fields": ["namespaces"]}
    )
    assert not any("pay" in b["key"].lower() for b in top.json()["facets"]["namespaces"])

    r = await search("PAY")
    assert r.status_code == 200, r.text
    keys = [b["key"] for b in r.json()["facets"]["namespaces"]]
    assert len(keys) == 32 and r.json()["more"] is True  # 34 values match, 32 are sent
    assert all("pay" in k.lower() for k in keys)
    assert "Payroll-EU" in keys  # the stored case, found with the text in another case

    r = await search("roll-eu")
    assert r.json() == {
        "facets": {"namespaces": [{"key": "Payroll-EU", "count": 2, "by_scanner": {"grype": 2}}]},
        "more": False,
    }  # kube-system shares the findings but does not contain the text

    # the text is a text, never a pattern: no value contains ".*" or "pay.*"
    for text in (".*", "pay.*", "p[a]y"):
        r = await search(text)
        assert r.status_code == 200 and r.json()["facets"]["namespaces"] == [], text
    assert (await search("payments")).json()["facets"]["namespaces"] == []  # other tenant

    # the counts use the filters of the list: a picked namespace leaves its own field out
    r = await search("roll", namespace="ns-01")
    assert [b["key"] for b in r.json()["facets"]["namespaces"]] == ["Payroll-EU"]


async def test_a_value_search_takes_one_list_field_and_a_short_text(env) -> None:
    login, _client = env
    http = await login()
    cid = f"c-f1064-{uuid.uuid4().hex[:8]}"
    for params in (
        {"contains": "pay"},  # no field: all facets
        {"contains": "pay", "fields": ["namespaces", "assignee"]},
        {"contains": "pay", "fields": ["severity"]},  # a fixed list needs no search
        {"contains": "p", "fields": ["namespaces"]},  # the menu asks from 2 letters
        {"contains": "p" * 129, "fields": ["namespaces"]},
    ):
        r = await http.get("/api/v1/findings/facets", params={"cluster_id": cid, **params})
        assert r.status_code == 422, params
    ok = await http.get(
        "/api/v1/findings/facets",
        params={"cluster_id": cid, "fields": ["assignee"], "contains": "p" * 128},
    )
    assert ok.status_code == 200 and ok.json() == {"facets": {"assignee": []}, "more": False}
