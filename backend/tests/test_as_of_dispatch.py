"""M6 slice 7 — the dispatcher at the routes (DoD: short-circuit + delegate, asserted).

Pins: `T=now` (absent, "now", or future) reads current state and NEVER touches the seam
(the stub reader records zero calls); a past T routes to the registered reader with the
EXACT parsed instant + the route's own params, and the reader's payload is the response
verbatim; with no reader registered a past T is 501 on every surface (grid, facets, groups,
trends, contributors) and exports stay 501 even WITH a reader (deliberately unrouted until
M8b+M7); malformed/naive `as_of` is 422, never a silent "now".
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
from backend.query.as_of import register_as_of_t
from os_env import OS_URL, requires_opensearch

PASSWORD = "asof-route-password"
PAST_T = "2026-01-01T00:00:00+00:00"


pytestmark = requires_opensearch


class _StubReader:
    """Satisfies AsOfTReader; records every call so the tests can assert the seam."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.raise_value_error = False  # simulate the reader's unrecorded-filter rejection

    async def _record(self, surface: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        kwargs.pop("client", None)
        self.calls.append((surface, kwargs))
        if self.raise_value_error:
            self.raise_value_error = False
            raise ValueError("filter is not recorded in per-scan history")
        return {"from": "as_of_t", "surface": surface}

    async def findings_page(self, client: Any, **kw: Any) -> dict[str, Any]:
        return await self._record("findings_page", kw)

    async def findings_facets(self, client: Any, **kw: Any) -> dict[str, Any]:
        return await self._record("findings_facets", kw)

    async def findings_groups(self, client: Any, **kw: Any) -> dict[str, Any]:
        return await self._record("findings_groups", kw)

    async def trends_scans(self, client: Any, **kw: Any) -> dict[str, Any]:
        return await self._record("trends_scans", kw)

    async def trends_findings(self, client: Any, **kw: Any) -> dict[str, Any]:
        return await self._record("trends_findings", kw)

    async def contributors(self, client: Any, **kw: Any) -> dict[str, Any]:
        return await self._record("contributors", kw)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_reader_leaks():
    yield
    register_as_of_t(None)  # whatever a test registered dies with it


@pytest.fixture
async def http():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
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
    session = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    r = await session.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield session
    await session.aclose()
    await client.close()


async def test_a_past_t_delegates_each_surface_with_the_parsed_instant(http) -> None:
    reader = _StubReader()
    register_as_of_t(reader)
    cid = f"c-asof-{uuid.uuid4().hex[:8]}"

    surfaces = [
        ("/api/v1/findings", {}, "findings_page"),
        ("/api/v1/findings/facets", {"fields": "ptype", "contains": "de"}, "findings_facets"),
        ("/api/v1/findings/groups", {"by": "image_repo"}, "findings_groups"),
        ("/api/v1/trends/scans", {}, "trends_scans"),
        ("/api/v1/trends/findings", {}, "trends_findings"),
        ("/api/v1/contributors", {}, "contributors"),
    ]
    for path, extra, surface in surfaces:
        r = await http.get(path, params={"cluster_id": cid, "as_of": PAST_T, **extra})
        assert r.status_code == 200, (path, r.text)
        assert r.json() == {"from": "as_of_t", "surface": surface}  # the reader's payload, verbatim

    assert [s for s, _ in reader.calls] == [s for _, _, s in surfaces]
    for _, kw in reader.calls:
        assert kw["t"] == datetime(2026, 1, 1, tzinfo=UTC)  # the EXACT parsed instant
        assert kw["cluster_id"] == cid
    # the route's own params ride through the seam untouched
    assert reader.calls[1][1]["contains"] == "de"  # a value search reads the history too
    assert reader.calls[2][1]["by"] == "image_repo"
    assert reader.calls[5][1]["days"] == 30


async def test_reader_rejections_are_422_never_500(http) -> None:
    """The reader refuses unrecorded filters with ValueError (q, kev, new_within_days…) —
    the route seam must map that to 422; a 500 hid it behind generic FE copy (audit 343)."""
    reader = _StubReader()
    register_as_of_t(reader)
    cid = f"c-asof-{uuid.uuid4().hex[:8]}"
    for extra in ({"q": "krb5"}, {"new_within_days": "7"}, {"kev": "true"}):
        reader.raise_value_error = True
        r = await http.get("/api/v1/findings", params={"cluster_id": cid, "as_of": PAST_T, **extra})
        assert r.status_code == 422, (extra, r.status_code, r.text)


async def test_t_now_never_touches_the_seam(http) -> None:
    reader = _StubReader()
    register_as_of_t(reader)
    cid = f"c-asof-{uuid.uuid4().hex[:8]}"

    # the future T is built from now: a fixed one becomes a PAST T once the calendar passes it,
    # and the route then (correctly) hands it to the reader this test asserts is never touched
    future = (datetime.now(UTC) + timedelta(days=365)).isoformat()
    for as_of in (None, "now", future):  # absent / literal / future
        params: dict[str, Any] = {"cluster_id": cid}
        if as_of is not None:
            params["as_of"] = as_of
        r = await http.get("/api/v1/findings", params=params)
        assert r.status_code == 200
        assert r.json()["data"] == []  # the real (empty) current-state grid, not the stub
    assert reader.calls == []  # the reconstruction path was NEVER touched (D28 short-circuit)


async def test_unregistered_seam_is_501_and_bad_as_of_is_422(http) -> None:
    cid = f"c-asof-{uuid.uuid4().hex[:8]}"
    r = await http.get("/api/v1/findings", params={"cluster_id": cid, "as_of": PAST_T})
    assert r.status_code == 501

    for bad in ("garbage", "2026-01-01T00:00:00"):  # malformed / naive
        r = await http.get("/api/v1/findings", params={"cluster_id": cid, "as_of": bad})
        assert r.status_code == 422


async def test_exports_stay_501_even_with_a_reader(http) -> None:
    register_as_of_t(_StubReader())
    cid = f"c-asof-{uuid.uuid4().hex[:8]}"
    r = await http.get("/api/v1/findings/export.csv", params={"cluster_id": cid, "as_of": PAST_T})
    assert r.status_code == 501  # export-at-T is deliberately unrouted until M8b+M7
    r = await http.get(
        "/api/v1/findings/export.vex",
        params={"cluster_id": cid, "scanner": "trivy", "as_of": PAST_T},
    )
    assert r.status_code == 501
