"""Issue 359 (absorbing #373) — GET /api/v1/decisions/approvals/export.csv against real
OpenSearch.

Pins what this export can get wrong that the queue read cannot: leaking a capability-gated
queue to a session that may not see it, a formula-armed justification cell, a derived status
column that disagrees with the chip it mirrors, and a sweep that drops rows because the review
sort is not unique.
"""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.metrics import EXPORT_BYTES, EXPORT_ROWS, LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.decisions.lifecycle import DECISIONS_INDEX
from backend.export.approvals_csv import APPROVALS_CSV_COLUMNS
from backend.main import create_app
from os_env import OS_URL, clear_pits, requires_opensearch

PASSWORD = "approvals-export-password"
LEAD = ["can_triage", "can_accept_audit_final", "can_export"]

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

    yield login_with, client
    for http in jars:
        await http.aclose()
    await client.close()


async def _accept(
    client: AsyncOpenSearch,
    cid: str,
    *,
    cve: str,
    created_by: str = "lead",
    expiry: datetime | None = None,
    expiry_raw: str | None = None,
    justification: str = "accepted for now",
    scanner: str | None = None,
    both: bool = True,
    revoked: bool = False,
    namespaces: list[str] | None = None,
    images: list[str] | None = None,
) -> str:
    """One standing risk-acceptance, written straight to the index — the queue is a read over
    whatever lives there, and going through the create route would drag in SEC-2 plumbing this
    file is not testing."""
    did = f"d-{uuid.uuid4().hex[:12]}"
    body = {
        "decision_id": did,
        "type": "risk_accepted",
        "cve_id": cve,
        "scope": {"namespaces": namespaces or [], "images": images or []},
        "apply_both_scanners": both,
        "scanner": scanner,
        "vex_justification": "vulnerable_code_not_in_execute_path",
        "justification": justification,
        "created_by": created_by,
        "created_at": datetime.now(UTC).isoformat(),
        "expiry": expiry_raw or (expiry.isoformat() if expiry else None),
        "revoked_at": datetime.now(UTC).isoformat() if revoked else None,
        "cluster_id": cid,
        "schema_version": 1,
    }
    await client.index(
        index=DECISIONS_INDEX,
        id=did,
        body={k: v for k, v in body.items() if v is not None},
        params={"refresh": "true"},
    )
    return did


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


async def _pit_count(client: AsyncOpenSearch) -> int:
    resp = await client.transport.perform_request("GET", "/_search/point_in_time/_all")
    return len(resp.get("pits") or [])


async def test_the_export_inherits_the_queue_s_capability_gate(env) -> None:
    """The queue names who accepted which risk — the file is exactly as sensitive as the
    screen, so a plain session must not be able to download it."""
    login_with, client = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    await _accept(client, cid, cve="CVE-2024-0001")

    viewer = await login_with(["can_triage", "can_export"])  # may export, but NOT accept-final
    r = await viewer.get("/api/v1/decisions/approvals/export.csv", params={"cluster_id": cid})
    assert r.status_code == 403

    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=viewer._transport.app),  # type: ignore[attr-defined]
        base_url="https://t",
    )
    r = await bare.get("/api/v1/decisions/approvals/export.csv", params={"cluster_id": cid})
    assert r.status_code == 401
    await bare.aclose()

    lead = await login_with(LEAD)
    r = await lead.get("/api/v1/decisions/approvals/export.csv", params={"cluster_id": cid})
    assert r.status_code == 200


async def test_rows_statuses_and_scope_match_the_screen_and_defuse_formulas(env) -> None:
    """The justification is free text the approver wrote, so it carries the injection bait.

    The derived `status` column is checked against the SAME four boundaries the chip and the
    `status` filter use, and the scope columns carry the raw lists rather than the screen's
    truncating label — an export that dropped scope entries would be quietly lossy.
    """
    login_with, client = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    bait = "=cmd()|'/c calc'!A1"

    await _accept(client, cid, cve="CVE-2024-EXPIRED", expiry=now - timedelta(days=2))
    await _accept(client, cid, cve="CVE-2024-EXPIRING", expiry=now + timedelta(days=3))
    await _accept(client, cid, cve="CVE-2024-ACTIVE", expiry=now + timedelta(days=90))
    await _accept(
        client,
        cid,
        cve="CVE-2024-OPEN",
        justification=bait,
        namespaces=["team-a", "team-b"],
        images=["nginx"],
        both=False,
        scanner="trivy",
    )
    await _accept(client, cid, cve="CVE-2024-REVOKED", revoked=True)

    lead = await login_with(LEAD)
    r = await lead.get("/api/v1/decisions/approvals/export.csv", params={"cluster_id": cid})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "javv-approvals-" in r.headers["content-disposition"]

    lines = r.text.splitlines()
    assert lines[0].split(",") == list(APPROVALS_CSV_COLUMNS)
    by_cve = {row["cve_id"]: row for row in _rows(r.text)}

    # the revoked guard is the queue's definition — an export must never resurrect one
    assert "CVE-2024-REVOKED" not in by_cve
    assert len(by_cve) == 4

    assert by_cve["CVE-2024-EXPIRED"]["status"] == "expired"
    assert by_cve["CVE-2024-EXPIRING"]["status"] == "expiring"  # inside the default 7d window
    assert by_cve["CVE-2024-ACTIVE"]["status"] == "active"
    assert by_cve["CVE-2024-OPEN"]["status"] == "open-ended"  # no expiry at all

    row = by_cve["CVE-2024-OPEN"]
    assert row["justification"] == f"'{bait}"  # armed cell defused, value still readable
    assert not any(ln.startswith(("=", "+", "@")) for ln in lines[1:])
    assert row["scope_namespaces"] == "team-a;team-b"  # raw list, not the truncating label
    assert row["scope_images"] == "nginx"
    assert row["scanner"] == "trivy"  # the COLUMN's value (D22), not the raw field alone
    assert by_cve["CVE-2024-ACTIVE"]["scanner"] == "both"
    # cluster-wide is the doc's own empty-scope convention, carried through as empty cells
    assert by_cve["CVE-2024-ACTIVE"]["scope_namespaces"] == ""


async def test_warn_days_moves_the_status_column_the_same_way_it_moves_the_filter(env) -> None:
    """chip ≡ filter ≡ export: widening the warn window must reclassify the same row in the
    file that it reclassifies in the queue."""
    login_with, client = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    await _accept(client, cid, cve="CVE-2024-2020", expiry=datetime.now(UTC) + timedelta(days=20))
    lead = await login_with(LEAD)

    r = await lead.get("/api/v1/decisions/approvals/export.csv", params={"cluster_id": cid})
    assert _rows(r.text)[0]["status"] == "active"  # 20d out, default 7d window
    r = await lead.get(
        "/api/v1/decisions/approvals/export.csv", params={"cluster_id": cid, "warn_days": 30}
    )
    assert _rows(r.text)[0]["status"] == "expiring"  # same row, wider window


async def test_the_file_carries_the_lens_and_only_this_tenant(env) -> None:
    login_with, client = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    other = f"c-aexp-{uuid.uuid4().hex[:8]}"
    await _accept(client, cid, cve="CVE-2024-1111", created_by="ana")
    await _accept(client, cid, cve="CVE-2024-2222", created_by="bo")
    await _accept(client, other, cve="CVE-2024-9999", created_by="ana")
    lead = await login_with(LEAD)
    base = {"cluster_id": cid}

    r = await lead.get("/api/v1/decisions/approvals/export.csv", params=base)
    assert {row["cve_id"] for row in _rows(r.text)} == {"CVE-2024-1111", "CVE-2024-2222"}
    assert "CVE-2024-9999" not in r.text  # SEC-4 — the other tenant never leaks

    r = await lead.get(
        "/api/v1/decisions/approvals/export.csv", params={**base, "created_by": "ana"}
    )
    assert {row["cve_id"] for row in _rows(r.text)} == {"CVE-2024-1111"}
    r = await lead.get(
        "/api/v1/decisions/approvals/export.csv", params={**base, "exclude_created_by": "ana"}
    )
    assert {row["cve_id"] for row in _rows(r.text)} == {"CVE-2024-2222"}
    r = await lead.get("/api/v1/decisions/approvals/export.csv", params={**base, "q": "1111"})
    assert {row["cve_id"] for row in _rows(r.text)} == {"CVE-2024-1111"}

    # a field is include OR exclude, never both — the same 422 the queue raises
    r = await lead.get(
        "/api/v1/decisions/approvals/export.csv",
        params={**base, "created_by": "ana", "exclude_created_by": "bo"},
    )
    assert r.status_code == 422
    r = await lead.get(
        "/api/v1/decisions/approvals/export.csv", params={**base, "status": "nonsense"}
    )
    assert r.status_code == 422


# serial: counts every open PIT in the store, so another worker's live PIT breaks the equality
@pytest.mark.serial
async def test_over_the_cap_is_413_before_any_pit_and_the_sweep_cleans_up(env, monkeypatch) -> None:
    """The pre-count runs before a PIT opens (audit A-M6), so an oversized lens costs one count
    and no sweep. Ops parity: the 413 logs a warning AND bumps LIMIT_REJECTIONS."""
    login_with, client = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    for i in range(3):
        await _accept(client, cid, cve=f"CVE-2024-30{i}")
    lead = await login_with(LEAD)

    before = LIMIT_REJECTIONS.labels("export_rows")._value.get()
    await clear_pits(client)
    params = {"cluster_id": cid}

    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "2")  # 3 acceptances > cap 2
    get_settings.cache_clear()
    r = await lead.get("/api/v1/decisions/approvals/export.csv", params=params)
    assert r.status_code == 413
    assert "inline export limit" in r.json()["title"]
    assert LIMIT_REJECTIONS.labels("export_rows")._value.get() == before + 1
    assert await _pit_count(client) == 0  # the 413 landed BEFORE any PIT opened

    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "50")
    get_settings.cache_clear()
    rows_before = EXPORT_ROWS.labels("approvals_csv")._value.get()
    bytes_before = EXPORT_BYTES.labels("approvals_csv")._value.get()
    r = await lead.get("/api/v1/decisions/approvals/export.csv", params=params)
    assert r.status_code == 200
    assert len(r.text.splitlines()) == 1 + 3
    assert EXPORT_ROWS.labels("approvals_csv")._value.get() == rows_before + 3  # header excluded
    assert EXPORT_BYTES.labels("approvals_csv")._value.get() == bytes_before + len(r.text)
    assert await _pit_count(client) == 0  # the sweep deleted its PIT (D38)


async def test_the_sweep_pages_past_one_batch_without_losing_rows(env) -> None:
    """The review sort (`expiry asc`) is NOT unique, so a search_after walk needs the
    decision_id tiebreaker. Seeded with rows that all share ONE expiry — the exact tie the
    tiebreaker exists for — and asserted whole across a forced multi-page sweep."""
    login_with, client = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    same = datetime.now(UTC) + timedelta(days=45)
    expected = set()
    for i in range(12):
        await _accept(client, cid, cve=f"CVE-2024-7{i:03d}", expiry=same)
        expected.add(f"CVE-2024-7{i:03d}")
    lead = await login_with(LEAD)

    import backend.export.approvals_csv as mod

    original = mod._PAGE_SIZE
    mod._PAGE_SIZE = 5  # force 3 pages over 12 tied rows
    try:
        r = await lead.get("/api/v1/decisions/approvals/export.csv", params={"cluster_id": cid})
    finally:
        mod._PAGE_SIZE = original
    assert r.status_code == 200
    got = [row["cve_id"] for row in _rows(r.text)]
    assert set(got) == expected  # nothing dropped
    assert len(got) == len(set(got)) == 12  # and nothing repeated across the page boundaries


async def test_a_date_only_expiry_does_not_truncate_the_stream(env) -> None:
    """Caught on the running dev stack, not by the suite: the app stores `expiry` as a bare
    DATE, which parses NAIVE — comparing it to a tz-aware `now` raised inside the generator
    AFTER the header had been yielded, so the client got 200 + a header and no rows.

    Seeded with the shape the app actually writes (`2026-07-15`, not an ISO instant), because
    seeding a tz-aware string is what hid this in the first place.
    """
    login_with, client = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    today = datetime.now(UTC)
    await _accept(
        client,
        cid,
        cve="CVE-2024-DATEONLY",
        expiry_raw=(today - timedelta(days=3)).date().isoformat(),
    )
    await _accept(
        client,
        cid,
        cve="CVE-2024-DATEFAR",
        expiry_raw=(today + timedelta(days=60)).date().isoformat(),
    )
    lead = await login_with(LEAD)

    r = await lead.get("/api/v1/decisions/approvals/export.csv", params={"cluster_id": cid})
    assert r.status_code == 200
    rows = {row["cve_id"]: row["status"] for row in _rows(r.text)}
    assert rows == {"CVE-2024-DATEONLY": "expired", "CVE-2024-DATEFAR": "active"}


async def test_several_approvers_and_statuses_give_the_same_rows_in_the_queue_and_the_file(
    env,
) -> None:
    """issue 952: `created_by` and `status` take several values. The queue moves the approver
    filter to post_filter so its count keeps the other approvers, so the queue rows, its total
    and the CSV must still be the same set; the status count follows the approver pick."""
    login_with, client = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    await _accept(client, cid, cve="CVE-2024-A1", created_by="ann", expiry=now + timedelta(days=60))
    await _accept(client, cid, cve="CVE-2024-A2", created_by="ann")  # open-ended
    await _accept(client, cid, cve="CVE-2024-B1", created_by="bob", expiry=now - timedelta(days=1))
    await _accept(client, cid, cve="CVE-2024-C1", created_by="cy", expiry=now + timedelta(days=60))
    lead = await login_with(LEAD)

    picked = {"cluster_id": cid, "created_by": ["ann", "bob"]}
    r = await lead.get("/api/v1/decisions/approvals", params=picked)
    assert r.status_code == 200
    queue = r.json()
    assert sorted(a["cve_id"] for a in queue["approvals"]) == [
        "CVE-2024-A1",
        "CVE-2024-A2",
        "CVE-2024-B1",
    ]
    assert queue["total"] == 3
    # the approver count keeps cy, who is not picked; the status count stays ann's and bob's
    assert {f["key"]: f["count"] for f in queue["facets"]["created_by"]} == {
        "ann": 2,
        "bob": 1,
        "cy": 1,
    }
    statuses = {f["key"]: f["count"] for f in queue["facets"]["status"]}
    assert statuses == {"active": 1, "expiring": 0, "expired": 1, "open-ended": 1}
    r = await lead.get("/api/v1/decisions/approvals/export.csv", params=picked)
    assert sorted(row["cve_id"] for row in _rows(r.text)) == [
        a["cve_id"] for a in sorted(queue["approvals"], key=lambda a: a["cve_id"])
    ]

    r = await lead.get(
        "/api/v1/decisions/approvals",
        params={"cluster_id": cid, "status": ["expired", "open-ended"]},
    )
    assert sorted(a["cve_id"] for a in r.json()["approvals"]) == ["CVE-2024-A2", "CVE-2024-B1"]
    r = await lead.get(
        "/api/v1/decisions/approvals",
        params={"cluster_id": cid, "exclude_status": ["expired", "open-ended"]},
    )
    assert sorted(a["cve_id"] for a in r.json()["approvals"]) == ["CVE-2024-A1", "CVE-2024-C1"]
    r = await lead.get(
        "/api/v1/decisions/approvals", params={"cluster_id": cid, "exclude_created_by": ["ann"]}
    )
    assert sorted(a["cve_id"] for a in r.json()["approvals"]) == ["CVE-2024-B1", "CVE-2024-C1"]


async def test_the_approvals_filters_take_at_most_32_values_and_check_each_status(env) -> None:
    login_with, _ = env
    cid = f"c-aexp-{uuid.uuid4().hex[:8]}"
    lead = await login_with(LEAD)
    many = [f"user-{i}" for i in range(33)]
    for path in ("/api/v1/decisions/approvals", "/api/v1/decisions/approvals/export.csv"):
        r = await lead.get(path, params={"cluster_id": cid, "created_by": many})
        assert r.status_code == 422, path
        r = await lead.get(path, params={"cluster_id": cid, "status": ["active", "soon"]})
        assert r.status_code == 422, path  # each value is checked, not only the first
        r = await lead.get(
            path, params={"cluster_id": cid, "status": ["active"], "exclude_status": ["expired"]}
        )
        assert r.status_code == 422, path  # include and exclude of one field
    r = await lead.get(
        "/api/v1/decisions/approvals", params={"cluster_id": cid, "created_by": many[:32]}
    )
    assert r.status_code == 200
