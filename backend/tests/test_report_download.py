"""M7 slice 3 (#32) — download + notifications routes, against real OpenSearch.

Pins: the status view mints a `download_token` only for a done, unexpired report; download
requires session + valid token; expiry → **410** (never stale bytes); a pending report has no
result (404); status + download are OWNER-scoped — another user's report_id is a 404,
indistinguishable from missing; the bell is strictly own-notifications (server-side filter +
IDOR 404 on mark-read), with a server-computed unread count, and each item names its cluster
as the registry does at read time. Token unit contract alongside.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.admin.cluster_registry import set_registry_name
from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.reports import download_token
from backend.reports.models import NOTIFICATIONS_INDEX, REPORT_CHUNKS_INDEX, REPORTS_INDEX
from os_env import OS_URL, requires_opensearch

PASSWORD = "download-route-password"


pytestmark = requires_opensearch


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login() -> tuple[httpx.AsyncClient, str]:
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
        return http, username

    yield login, client
    for http in jars:
        await http.aclose()
    await client.close()


async def _seed_done_report(
    client, *, requested_by: str, expires_in_hours: float = 24.0, chunks: int = 2
) -> str:
    report_id = uuid.uuid4().hex
    attempt_id = uuid.uuid4().hex
    for seq in range(chunks):
        await client.index(
            index=REPORT_CHUNKS_INDEX,
            id=f"{report_id}:{attempt_id}:{seq}",
            body={
                "report_id": report_id,
                "attempt_id": attempt_id,
                "seq": seq,
                "data": f"part-{seq};",
            },
        )
    await client.indices.refresh(index=REPORT_CHUNKS_INDEX)
    await client.index(
        index=REPORTS_INDEX,
        id=report_id,
        body={
            "report_id": report_id,
            "kind": "export",
            "status": "done",
            "cluster_id": f"c-dl-{uuid.uuid4().hex[:8]}",
            "requested_by": requested_by,
            "run_mode": "offpeak",
            "params": {"format": "csv"},
            "created_at": datetime.now(UTC).isoformat(),
            "attempt_id": attempt_id,
            "retry_count": 0,
            "bytes": 12,
            "chunk_count": chunks,
            "expires_at": (datetime.now(UTC) + timedelta(hours=expires_in_hours)).isoformat(),
            "schema_version": 1,
        },
        params={"refresh": "true"},
    )
    return report_id


# --- download ----------------------------------------------------------------


async def test_status_view_mints_a_token_and_download_streams_the_chunks(env) -> None:
    login, client = env
    http, user = await login()
    report_id = await _seed_done_report(client, requested_by=user)

    status = await http.get(f"/api/v1/reports/{report_id}")
    assert status.status_code == 200
    token = status.json().get("download_token")
    assert token  # done + unexpired → token present

    r = await http.get(f"/api/v1/reports/{report_id}/download", params={"token": token})
    assert r.status_code == 200
    assert r.text == "part-0;part-1;"  # reassembled in seq order
    assert "text/csv" in r.headers["content-type"]


async def test_pending_report_has_no_token_and_no_download(env) -> None:
    login, client = env
    http, user = await login()
    report_id = uuid.uuid4().hex
    await client.index(
        index=REPORTS_INDEX,
        id=report_id,
        body={
            "report_id": report_id,
            "kind": "export",
            "status": "pending",
            "cluster_id": "c-dl-pending",
            "requested_by": user,
            "run_mode": "offpeak",
            "params": {"format": "csv"},
            "created_at": datetime.now(UTC).isoformat(),
            "retry_count": 0,
            "schema_version": 1,
        },
        params={"refresh": "true"},
    )
    status = await http.get(f"/api/v1/reports/{report_id}")
    assert "download_token" not in status.json()
    tok = download_token.mint(report_id)  # even a validly-signed token can't fetch a non-result
    r = await http.get(f"/api/v1/reports/{report_id}/download", params={"token": tok})
    assert r.status_code == 404


async def test_expired_report_is_410_and_mints_no_token(env) -> None:
    login, client = env
    http, user = await login()
    # already past expiry
    report_id = await _seed_done_report(client, requested_by=user, expires_in_hours=-1)

    status = await http.get(f"/api/v1/reports/{report_id}")
    assert "download_token" not in status.json()
    tok = download_token.mint(report_id)
    r = await http.get(f"/api/v1/reports/{report_id}/download", params={"token": tok})
    assert r.status_code == 410  # expired → dead link says so, never stale bytes


async def test_bad_token_is_403_and_no_session_is_401(env) -> None:
    login, client = env
    http, user = await login()
    report_id = await _seed_done_report(client, requested_by=user)

    r = await http.get(f"/api/v1/reports/{report_id}/download", params={"token": "9999.fake"})
    assert r.status_code == 403

    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http._transport.app),  # type: ignore[attr-defined]
        base_url="https://t",
    )
    good = download_token.mint(report_id)
    r = await bare.get(f"/api/v1/reports/{report_id}/download", params={"token": good})
    assert r.status_code == 401  # the token never substitutes for the session
    await bare.aclose()


async def test_someone_elses_report_is_404_on_status_and_download(env) -> None:
    """IDOR pin: a foreign report_id must be indistinguishable from a missing one —
    no status view, no token minting, no download even with a validly-signed token."""
    login, client = env
    http_owner, owner = await login()
    http_other, _ = await login()
    report_id = await _seed_done_report(client, requested_by=owner)

    assert (await http_owner.get(f"/api/v1/reports/{report_id}")).status_code == 200
    assert (await http_other.get(f"/api/v1/reports/{report_id}")).status_code == 404

    tok = download_token.mint(report_id)  # even a valid token never crosses owners
    r = await http_other.get(f"/api/v1/reports/{report_id}/download", params={"token": tok})
    assert r.status_code == 404


def test_download_token_contract() -> None:
    """Unit pin: round-trip verifies; expiry, tamper, and cross-report reuse all fail."""
    t = download_token.mint("r-1")
    assert download_token.verify("r-1", t) is True
    assert download_token.verify("r-2", t) is False  # bound to the report id
    assert download_token.verify("r-1", t + "x") is False  # tampered sig
    assert download_token.verify("r-1", "junk") is False
    expired = download_token.mint("r-1", now=0.0)  # minted at the epoch → long expired
    assert download_token.verify("r-1", expired) is False


# --- notifications (D-3, FR-16) ----------------------------------------------


async def _seed_note(client, user_id: str, **over) -> str:
    # one id for _id AND notification_id — the producer invariant _ring_bell pins (audit F-03)
    nid = uuid.uuid4().hex
    body = {
        "notification_id": nid,
        "user_id": user_id,
        "type": "report_ready",
        "ref": uuid.uuid4().hex,
        "cluster_id": "c-bell",
        "created_at": datetime.now(UTC).isoformat(),
        "read": False,
    }
    body.update(over)
    await client.index(index=NOTIFICATIONS_INDEX, id=nid, body=body, params={"refresh": "true"})
    return nid


async def test_bell_lists_only_own_notifications_with_server_computed_unread(env) -> None:
    login, client = env
    http_a, user_a = await login()
    _, user_b = await login()

    n1 = await _seed_note(client, user_a)
    n2 = await _seed_note(client, user_a, read=True)
    await _seed_note(client, user_b)  # someone else's — must never appear

    r = await http_a.get("/api/v1/notifications")
    assert r.status_code == 200
    body = r.json()
    ids = {i["notification_id"] for i in body["items"]}
    assert {n1, n2} <= ids
    assert all("user_id" not in i for i in body["items"])  # public shape only
    assert body["unread"] == 1  # server-computed: n1 unread, n2 read


async def test_each_bell_item_names_its_cluster_as_the_registry_does_now(env) -> None:
    login, client = env
    http, user = await login()
    named, unnamed = f"c-bell-{uuid.uuid4().hex[:8]}", f"c-bell-{uuid.uuid4().hex[:8]}"
    assert await set_registry_name(client, named, "payments-prod", actor="test")
    try:
        n_named = await _seed_note(client, user, type="cluster_retiring", cluster_id=named)
        n_unnamed = await _seed_note(client, user, type="cluster_retiring", cluster_id=unnamed)
        n_none = await _seed_note(client, user, cluster_id=None)

        items = {
            i["notification_id"]: i
            for i in (await http.get("/api/v1/notifications")).json()["items"]
        }

        assert items[n_named]["cluster_name"] == "payments-prod"
        assert items[n_unnamed]["cluster_name"] == unnamed  # never named: its id, as everywhere
        assert items[n_none]["cluster_name"] is None
        # a rename after the notice shows: the name is read now, not stored with the notice
        assert await set_registry_name(client, named, "payments-old", actor="test")
        items = {
            i["notification_id"]: i
            for i in (await http.get("/api/v1/notifications")).json()["items"]
        }
        assert items[n_named]["cluster_name"] == "payments-old"
    finally:
        await set_registry_name(client, named, None, actor="test")


async def test_mark_read_flips_own_and_404s_on_someone_elses(env) -> None:
    login, client = env
    http_a, user_a = await login()
    _, user_b = await login()
    own = await _seed_note(client, user_a)
    theirs = await _seed_note(client, user_b)

    r = await http_a.patch(f"/api/v1/notifications/{own}/read")
    assert r.status_code == 200 and r.json()["read"] is True
    assert (await client.get(index=NOTIFICATIONS_INDEX, id=own))["_source"]["read"] is True

    # IDOR: someone else's id is indistinguishable from missing
    assert (await http_a.patch(f"/api/v1/notifications/{theirs}/read")).status_code == 404
    assert (await http_a.patch(f"/api/v1/notifications/{uuid.uuid4().hex}/read")).status_code == 404


async def test_dismiss_deletes_own_and_404s_on_someone_elses(env) -> None:
    login, client = env
    http_a, user_a = await login()
    _, user_b = await login()
    own = await _seed_note(client, user_a)
    theirs = await _seed_note(client, user_b)

    assert (await http_a.delete(f"/api/v1/notifications/{own}")).status_code == 204
    assert not await client.exists(index=NOTIFICATIONS_INDEX, id=own)

    # IDOR: someone else's id is indistinguishable from missing — and their doc survives
    assert (await http_a.delete(f"/api/v1/notifications/{theirs}")).status_code == 404
    assert await client.exists(index=NOTIFICATIONS_INDEX, id=theirs)
    assert (await http_a.delete(f"/api/v1/notifications/{uuid.uuid4().hex}")).status_code == 404
