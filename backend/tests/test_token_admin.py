"""Token admin API + auth-event auditing (M5a slice 6, D38/M14 + D17).

The capability-gated (can_manage_tokens) admin surface over the EXISTING token machinery — one
token path only. Rotate = mint-new + disable-old (the staleness sweep dedupes rotated tokens,
audit M-2); revoke = disabled:true and the ingest 401s immediately. The raw token appears exactly
once, in the mint/rotate response; list never exposes hashes. Every auth/token event appends one
structured row to the system-audit-log write alias (D17; schema owned by M5b, template landed
early so the appender never writes into a dynamic-mapped index). Real OpenSearch."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import structlog
from opensearchpy import AsyncOpenSearch

from backend.admin import cluster_delete
from backend.auth.passwords import hash_password
from backend.core.errors import DELETE_UNFINISHED_TYPE
from backend.main import create_app
from backend.routers import tokens as tokens_router
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"


pytestmark = requires_opensearch


@pytest.fixture
async def admin_client():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": "admin",
                "capabilities": ["*"],
                "must_change": False,
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": "2026-07-04T00:00:00+00:00",
            },
            params={"refresh": "true"},
        )
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        yield http, client, username
    await client.close()


def _cluster() -> str:
    return f"c-{uuid.uuid4().hex[:12]}"


async def _audit_rows(client, *, action: str, entity_id: str) -> list[dict[str, Any]]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"action": action}},
                        {"term": {"entity_id": entity_id}},
                    ]
                }
            },
        },
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


# --- mint / list / revoke / rotate ---------------------------------------------------


async def test_mint_returns_the_raw_token_once_and_stores_only_the_hash(admin_client) -> None:
    http, client, username = admin_client
    cluster = _cluster()

    r = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})

    assert r.status_code == 201
    raw, token_id = r.json()["token"], r.json()["id"]
    doc = (await client.get(index="system-tokens", id=token_id))["_source"]
    assert raw not in str(doc)  # only the peppered hash lands
    assert doc["cluster_id"] == cluster and doc["scanner"] == "trivy"
    assert doc["created_by"] == username and doc["disabled"] is False
    # audited (D17)
    rows = await _audit_rows(client, action="token_mint", entity_id=token_id)
    assert len(rows) == 1
    assert rows[0]["actor"] == username and rows[0]["entity_type"] == "token"


async def test_list_never_exposes_hashes(admin_client) -> None:
    http, _, _ = admin_client
    cluster = _cluster()
    await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})

    r = await http.get("/api/v1/admin/tokens", params={"cluster_id": cluster})

    assert r.status_code == 200
    tokens = r.json()["tokens"]
    assert len(tokens) == 1 and tokens[0]["cluster_id"] == cluster
    assert "token_hash" not in str(r.json())


async def test_revoke_disables_and_audits(admin_client) -> None:
    http, client, username = admin_client
    cluster = _cluster()
    mint = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "grype"})
    token_id = mint.json()["id"]

    r = await http.post(f"/api/v1/admin/tokens/{token_id}/revoke")

    assert r.status_code == 200
    assert (await client.get(index="system-tokens", id=token_id))["_source"]["disabled"] is True
    rows = await _audit_rows(client, action="token_revoke", entity_id=token_id)
    assert len(rows) == 1 and rows[0]["actor"] == username


async def test_rotate_mints_a_sibling_and_disables_the_old(admin_client) -> None:
    http, client, _ = admin_client
    cluster = _cluster()
    mint = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})
    old_id = mint.json()["id"]

    r = await http.post(f"/api/v1/admin/tokens/{old_id}/rotate")

    assert r.status_code == 201
    new_id, new_raw = r.json()["id"], r.json()["token"]
    assert new_id != old_id and new_raw != mint.json()["token"]
    old = (await client.get(index="system-tokens", id=old_id))["_source"]
    new = (await client.get(index="system-tokens", id=new_id))["_source"]
    assert old["disabled"] is True  # rotated out — the staleness sweep dedupes it (M-2)
    assert new["disabled"] is False
    assert (new["cluster_id"], new["scanner"]) == (old["cluster_id"], old["scanner"])


async def test_unknown_token_id_is_404(admin_client) -> None:
    http, _, _ = admin_client
    assert (await http.post("/api/v1/admin/tokens/nope/revoke")).status_code == 404


# --- auth events land in the audit log (D17) -----------------------------------------


async def test_login_logout_and_pwd_change_each_append_one_audit_row(admin_client) -> None:
    http, client, username = admin_client
    # the fixture already logged in once → exactly one login row so far
    rows = await _audit_rows(client, action="login", entity_id=username)
    assert len(rows) == 1
    assert rows[0]["actor"] == username and rows[0]["entity_type"] == "user"
    assert rows[0]["event_id"] and rows[0]["@timestamp"]  # (@timestamp, event_id) ordering keys

    await http.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "a rotated passphrase ok"},
    )
    assert len(await _audit_rows(client, action="pwd_change", entity_id=username)) == 1

    await http.post("/auth/logout")
    assert len(await _audit_rows(client, action="logout", entity_id=username)) == 1


# --- task E (#142): expiry setting, shared cluster_id shape, list pagination -----------------


async def test_mint_with_expiry_stores_it_and_rotate_inherits_it(admin_client) -> None:
    http, client, _ = admin_client
    cluster = _cluster()
    # a year out from now, never a fixed date: the mint rejects an expiry in the past, so a fixed
    # one turns this mint into a 422 once the calendar passes it
    expiry = (datetime.now(UTC) + timedelta(days=365)).isoformat()

    r = await http.post(
        "/api/v1/admin/tokens",
        json={"cluster_id": cluster, "scanner": "trivy", "expiry": expiry},
    )

    assert r.status_code == 201
    doc = (await client.get(index="system-tokens", id=r.json()["id"]))["_source"]
    assert doc["expiry"] == expiry
    # rotation is not extension: the sibling inherits the old token's expiry
    rot = await http.post(f"/api/v1/admin/tokens/{r.json()['id']}/rotate")
    assert rot.status_code == 201
    new = (await client.get(index="system-tokens", id=rot.json()["id"]))["_source"]
    assert new["expiry"] == expiry


async def test_rotate_refuses_an_expired_token(admin_client) -> None:
    """issue 984: the sibling takes the old expiry, so a rotation of an expired token made a new
    secret that ingest refuses, and disabled the old token. Nothing is written now."""
    http, client, _ = admin_client
    cluster = _cluster()
    expiry = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    mint = await http.post(
        "/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy", "expiry": expiry}
    )
    token_id = mint.json()["id"]
    past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    await client.update(
        index="system-tokens",
        id=token_id,
        body={"doc": {"expiry": past}},
        params={"refresh": "true"},
    )

    r = await http.post(f"/api/v1/admin/tokens/{token_id}/rotate")

    assert r.status_code == 409
    assert "token" not in r.json()  # no new secret
    listed = await http.get("/api/v1/admin/tokens", params={"cluster_id": cluster})
    assert [t["id"] for t in listed.json()["tokens"]] == [token_id]  # no sibling
    assert (await client.get(index="system-tokens", id=token_id))["_source"]["disabled"] is False
    assert await _audit_rows(client, action="token_revoke", entity_id=token_id) == []


async def test_rotate_refuses_a_revoked_token(admin_client) -> None:
    """issue 984: a rotation of a revoked token made an active sibling, which went around the
    revoke. The screen offers no Rotate there, and the API now refuses it too."""
    http, client, _ = admin_client
    cluster = _cluster()
    mint = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "grype"})
    token_id = mint.json()["id"]
    await http.post(f"/api/v1/admin/tokens/{token_id}/revoke")

    r = await http.post(f"/api/v1/admin/tokens/{token_id}/rotate")

    assert r.status_code == 409
    listed = await http.get("/api/v1/admin/tokens", params={"cluster_id": cluster})
    assert [t["id"] for t in listed.json()["tokens"]] == [token_id]


async def test_mint_with_a_past_expiry_is_422(admin_client) -> None:
    http, _, _ = admin_client
    r = await http.post(
        "/api/v1/admin/tokens",
        json={
            "cluster_id": _cluster(),
            "scanner": "trivy",
            "expiry": "2020-01-01T00:00:00+00:00",
        },
    )
    assert r.status_code == 422


async def test_mint_rejects_a_malformed_cluster_id(admin_client) -> None:
    # audit M2: one shared cluster_id shape — the envelope's rule, everywhere
    http, _, _ = admin_client
    for bad in ("UPPER-CASE-ID", "short", "has_underscore_x", "-leading-hyphen"):
        r = await http.post("/api/v1/admin/tokens", json={"cluster_id": bad, "scanner": "trivy"})
        assert r.status_code == 422, bad


async def test_token_list_paginates(admin_client) -> None:
    http, _, _ = admin_client
    cluster = _cluster()
    for _ in range(3):
        await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})

    page1 = await http.get(
        "/api/v1/admin/tokens", params={"cluster_id": cluster, "size": 2, "offset": 0}
    )
    page2 = await http.get(
        "/api/v1/admin/tokens", params={"cluster_id": cluster, "size": 2, "offset": 2}
    )

    assert page1.status_code == page2.status_code == 200
    assert page1.json()["total"] == page2.json()["total"] == 3
    assert len(page1.json()["tokens"]) == 2
    assert len(page2.json()["tokens"]) == 1


# --- audit-log completeness (D17) — journal-first (audit #188) ------------------------


def _fail_audit_once(monkeypatch) -> None:
    from backend.audit import writer

    real = writer._append
    state = {"fired": False}

    async def flaky(*args, **kwargs):
        if not state["fired"]:
            state["fired"] = True
            raise RuntimeError("audit index hiccup")
        return await real(*args, **kwargs)

    monkeypatch.setattr(writer, "_append", flaky)


async def test_mint_not_left_unjournaled_on_audit_failure(admin_client, monkeypatch) -> None:
    """A-M5: journal-first + strict — a failed audit append must not leave a live-but-unjournaled
    token (the old fire-and-forget swallowed it, minting a usable token with no trail). No token on
    failure; a retry mints exactly one with exactly one mint row."""
    http, client, _ = admin_client
    cluster = _cluster()
    _fail_audit_once(monkeypatch)

    with pytest.raises(Exception):  # noqa: B017 — the strict audit failure fails the request (500)
        await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})
    await client.indices.refresh(index="system-tokens")
    q = {"query": {"term": {"cluster_id": cluster}}}
    assert (await client.count(index="system-tokens", body=q))["count"] == 0  # no orphan token

    r = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})
    assert r.status_code == 201
    await client.indices.refresh(index="system-tokens")
    assert (await client.count(index="system-tokens", body=q))["count"] == 1
    assert len(await _audit_rows(client, action="token_mint", entity_id=r.json()["id"])) == 1


async def _put_marker(client: AsyncOpenSearch, cluster: str, value: dict[str, Any]) -> str:
    doc_id = f"cluster-delete:{cluster}"
    await client.index(
        index="system-config",
        id=doc_id,
        body={"key": doc_id, "cluster_id": cluster, "value": value},
        params={"refresh": "true"},
    )
    return doc_id


async def test_mint_is_refused_for_a_cluster_whose_delete_did_not_finish(admin_client) -> None:
    http, client, _ = admin_client
    cluster = _cluster()
    marker = await _put_marker(client, cluster, {"started_at": "2026-10-12T00:00:00+00:00"})

    r = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})

    assert (r.status_code, r.json()["title"]) == (409, "its delete did not finish: delete it again")
    assert r.json()["type"] == DELETE_UNFINISHED_TYPE
    count = await client.count(
        index="system-tokens", body={"query": {"term": {"cluster_id": cluster}}}
    )
    assert count["count"] == 0
    assert await client.exists(index="system-config", id=marker)  # the delete still owns it
    await client.delete(index="system-config", id=marker, params={"refresh": "true"})


async def test_a_mint_for_a_deleted_cluster_id_ends_its_tombstone(
    admin_client, monkeypatch
) -> None:
    http, client, _ = admin_client
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(cluster_delete, "log", structlog.wrap_logger(None, processors=[capture]))
    cluster = _cluster()
    marker = await _put_marker(
        client,
        cluster,
        {"started_at": "2026-10-12T00:00:00+00:00", "finished_at": "2026-10-12T00:01:00+00:00"},
    )

    r = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})

    assert r.status_code == 201
    # onboarded again: the next-night pass must leave the new cluster's token and data alone
    assert not await client.exists(index="system-config", id=marker)
    assert await client.exists(index="system-tokens", id=r.json()["id"])
    dropped = [e for e in capture.entries if e["event"] == "cluster delete tombstone dropped"]
    assert [(e["cluster_id"], e["reason"]) for e in dropped] == [(cluster, "onboarded")]


async def test_a_delete_that_starts_during_the_mint_still_refuses_it(
    admin_client, monkeypatch
) -> None:
    http, client, _ = admin_client
    cluster = _cluster()
    marker = await _put_marker(client, cluster, {"started_at": "2026-10-12T00:00:00+00:00"})

    async def not_yet(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()  # the first look ran before the delete wrote its marker

    monkeypatch.setattr(tokens_router, "deletes_started", not_yet)
    r = await http.post("/api/v1/admin/tokens", json={"cluster_id": cluster, "scanner": "trivy"})

    assert (r.status_code, r.json()["type"]) == (409, DELETE_UNFINISHED_TYPE)
    count = await client.count(
        index="system-tokens", body={"query": {"term": {"cluster_id": cluster}}}
    )
    assert count["count"] == 0
    await client.delete(index="system-config", id=marker, params={"refresh": "true"})
