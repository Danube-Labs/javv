"""Capability RBAC (M5a slice 4, D33/SEC-2/SEC-9): `require_capability` is the single enforcement
point every protected route declares. 401 = who are you (no/dead session); 403 = you may not
(missing capability, or a `must_change` session, which the principal it depends on refuses). Admin
holds all via the "*" marker. Real OpenSearch, real routes, unique per-test usernames."""

import uuid
from typing import Annotated

import httpx
import pytest
from fastapi import Depends
from opensearchpy import AsyncOpenSearch

from backend.auth.capabilities import ROLE_BUNDLES, require_capability, seed_default_roles
from backend.auth.passwords import hash_password
from backend.auth.principal import Principal
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"


pytestmark = requires_opensearch


@pytest.fixture
async def auth_client():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client

    @app.get("/test-triage")  # a stand-in protected route — the enforcement point under test
    async def protected(
        principal: Annotated[Principal, Depends(require_capability("can_triage"))],
    ) -> dict:
        return {"as": principal.username}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
        yield http, client
    await client.close()


async def _seed_and_login(
    http,
    client,
    *,
    role: str = "triager",
    capabilities: list[str] | None = None,
    must_change: bool = False,
) -> str:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": role,
            "capabilities": capabilities,
            "must_change": must_change,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-07-04T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


async def test_no_session_is_401(auth_client) -> None:
    http, _ = auth_client
    assert (await http.get("/test-triage")).status_code == 401


async def test_capability_holder_passes_and_gets_the_principal(auth_client) -> None:
    http, client = auth_client
    username = await _seed_and_login(http, client, capabilities=["can_triage"])

    r = await http.get("/test-triage")

    assert r.status_code == 200 and r.json()["as"] == username


async def test_missing_capability_is_403_not_401(auth_client) -> None:
    http, client = auth_client
    await _seed_and_login(http, client, role="viewer", capabilities=[])

    assert (await http.get("/test-triage")).status_code == 403  # authenticated, not authorized


async def test_admin_star_holds_every_capability(auth_client) -> None:
    http, client = auth_client
    await _seed_and_login(http, client, role="admin", capabilities=["*"])

    assert (await http.get("/test-triage")).status_code == 200


async def test_must_change_session_is_403_even_with_the_capability(auth_client) -> None:
    # SEC-6: until the forced password change happens, the session can ONLY touch /auth/*
    http, client = auth_client
    await _seed_and_login(http, client, capabilities=["can_triage"], must_change=True)

    assert (await http.get("/test-triage")).status_code == 403
    assert (await http.get("/auth/me")).status_code == 200  # the escape hatch stays open


async def test_capabilities_fall_back_to_the_role_bundle(auth_client) -> None:
    # user doc without denormalized capabilities → resolve the role's bundle from system-roles
    http, client = auth_client
    await _seed_and_login(http, client, role="triager", capabilities=None)

    assert (await http.get("/test-triage")).status_code == 200


async def test_default_role_bundles_seed_once_and_match_d33(auth_client) -> None:
    _, client = auth_client
    first = await seed_default_roles(client)
    second = await seed_default_roles(client)  # idempotent — customized bundles never overwritten

    assert second == 0 and first in (0, len(ROLE_BUNDLES))  # 0 when another test seeded already
    doc = (await client.get(index="system-roles", id="security_lead"))["_source"]
    assert "can_accept_audit_final" in doc["capabilities"]  # SEC-2: gates risk-accept
    admin = (await client.get(index="system-roles", id="admin"))["_source"]
    assert admin["capabilities"] == ["*"]


async def test_a_new_store_gives_can_export_to_every_role_but_viewer(real_os) -> None:
    # issue 243 ruling 1: the viewer reads, the other default roles also export
    client, prefix = real_os
    assert await seed_default_roles(client, prefix=prefix) == len(ROLE_BUNDLES)

    bundles = {
        role: (await client.get(index=f"{prefix}system-roles", id=role))["_source"]["capabilities"]
        for role in ROLE_BUNDLES
    }
    assert bundles == {
        "viewer": [],
        "triager": ["can_triage", "can_export"],
        "security_lead": ["can_triage", "can_accept_audit_final", "can_export"],
        "admin": ["*"],
    }
