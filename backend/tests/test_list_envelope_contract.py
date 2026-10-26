"""THE standing list-response envelope contract (issue 538, out of 530).

`development/standards/api-design.md` § *List response envelopes* documents which key holds the
array on every list route and what `total` looks like. Prose decays: #530 existed because a rig
read `.data` from a route that returns `approvals`, and jq answered `null` — whose `length` is
**0**, a silent, self-consistent wrong answer that passes whenever the real answer is also 0.

Two guarantees here, and the second is the one that keeps the doc accurate:

1. **Shape** — for every registered route, the declared list key exists and is an array, and
   `total` matches its declared form (`wrapped` `{value, relation}` · `bare` int · `absent`).
2. **Presence** — every `GET` route is registered or explicitly exempt *with a reason*, so a new
   list route cannot ship undocumented. Exemptions carry their justification inline; an exemption
   with no reason is indistinguishable from an oversight.

Deliberately data-independent: every probe uses a cluster id that holds nothing. An envelope's
shape does not depend on whether rows matched, so seeding would add residue and prove nothing
extra. That also means an empty array here is a *pass*, not a vacuous one — the assertions are
about keys and types, never counts.

⚠️ Route enumeration goes through `app.openapi()`, NOT `app.routes`. Since FastAPI wraps included
routers in `_IncludedRouter` (no `.path`, no `.methods`, no `.routes`), walking `app.routes` and
filtering on `.methods` silently yields nothing — see issue 540.
"""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"
# A tenant that holds nothing: shapes are identical empty or full, and nothing is written.
EMPTY_CLUSTER = "c-envelope-contract"

CURSOR, OFFSET, UNPAGED = "cursor", "offset", "unpaged"
WRAPPED, BARE, ABSENT = "wrapped", "bare", "absent"


@dataclass(frozen=True)
class ListEndpoint:
    """One list route. `path` is the concrete call target; `route_path` is the OpenAPI template
    it corresponds to, which is what the presence check matches on."""

    path: str
    route_path: str
    family: str
    list_key: str
    total: str
    why: str = ""


# ── THE REGISTRY — every list route, mirroring api-design.md § List response envelopes ─────────
REGISTRY: tuple[ListEndpoint, ...] = (
    # cursor-paged: PIT + search_after / composite after_key
    ListEndpoint(
        path=f"/api/v1/findings?cluster_id={EMPTY_CLUSTER}&size=1",
        route_path="/api/v1/findings",
        family=CURSOR,
        list_key="data",
        total=WRAPPED,
    ),
    ListEndpoint(
        path=f"/api/v1/audit?cluster_id={EMPTY_CLUSTER}&size=1",
        route_path="/api/v1/audit",
        family=CURSOR,
        list_key="data",
        total=WRAPPED,
    ),
    ListEndpoint(
        path=f"/api/v1/scanners/ingest-failures?cluster_id={EMPTY_CLUSTER}&scanner=trivy&size=1",
        route_path="/api/v1/scanners/ingest-failures",
        family=CURSOR,
        list_key="data",
        total=WRAPPED,
        why="search_after without a PIT (issue 357): an append-only newest-first read is stable "
        "without one — same three keys as the PIT-paged routes.",
    ),
    ListEndpoint(
        path=f"/api/v1/findings/groups?cluster_id={EMPTY_CLUSTER}&by=cve_id&size=1",
        route_path="/api/v1/findings/groups",
        family=CURSOR,
        list_key="data",
        total=ABSENT,
        why="DOCUMENTED EXCEPTION: cursor-paged but carries no total — composite-agg paging "
        "cannot cheaply produce one, so 'cursor implies three keys' does not hold.",
    ),
    # offset-paged (size/offset): named key, total already unwrapped to a plain number
    ListEndpoint(
        path=f"/api/v1/decisions/approvals?cluster_id={EMPTY_CLUSTER}&size=1",
        route_path="/api/v1/decisions/approvals",
        family=OFFSET,
        list_key="approvals",
        total=BARE,
        why="the route whose key #530 was found on — a rig read `.data` and got a silent 0.",
    ),
    ListEndpoint(
        path=f"/api/v1/decisions?cluster_id={EMPTY_CLUSTER}",
        route_path="/api/v1/decisions",
        family=OFFSET,
        list_key="decisions",
        total=BARE,
    ),
    ListEndpoint(
        path="/api/v1/admin/users",
        route_path="/api/v1/admin/users",
        family=OFFSET,
        list_key="users",
        total=BARE,
    ),
    ListEndpoint(
        path="/api/v1/admin/tokens",
        route_path="/api/v1/admin/tokens",
        family=OFFSET,
        list_key="tokens",
        total=BARE,
    ),
    # unpaged: named key, no total
    ListEndpoint(
        path=f"/api/v1/contributors?cluster_id={EMPTY_CLUSTER}",
        route_path="/api/v1/contributors",
        family=UNPAGED,
        list_key="leaderboard",
        total=ABSENT,
        why="also carries a SECOND array, `handled_over_time` — one route, two collections.",
    ),
    ListEndpoint(
        path=f"/api/v1/images?cluster_id={EMPTY_CLUSTER}",
        route_path="/api/v1/images",
        family=UNPAGED,
        list_key="images",
        total=ABSENT,
    ),
    ListEndpoint(
        path=f"/api/v1/images/timeline?cluster_id={EMPTY_CLUSTER}&image_repo=none/none&tag=none",
        route_path="/api/v1/images/timeline",
        family=UNPAGED,
        list_key="events",
        total=ABSENT,
    ),
    ListEndpoint(
        path=f"/api/v1/findings/top-components?cluster_id={EMPTY_CLUSTER}",
        route_path="/api/v1/findings/top-components",
        family=UNPAGED,
        list_key="components",
        total=ABSENT,
    ),
    ListEndpoint(
        path=f"/api/v1/scanners/provenance?cluster_id={EMPTY_CLUSTER}",
        route_path="/api/v1/scanners/provenance",
        family=UNPAGED,
        list_key="scanners",
        total=ABSENT,
    ),
    ListEndpoint(
        path=f"/api/v1/scanners/freshness?cluster_id={EMPTY_CLUSTER}",
        route_path="/api/v1/scanners/freshness",
        family=UNPAGED,
        list_key="scanners",
        total=ABSENT,
    ),
    ListEndpoint(
        path="/api/v1/admin/jobs",
        route_path="/api/v1/admin/jobs",
        family=UNPAGED,
        list_key="jobs",
        total=ABSENT,
    ),
    ListEndpoint(
        path="/api/v1/admin/roles",
        route_path="/api/v1/admin/roles",
        family=UNPAGED,
        list_key="roles",
        total=ABSENT,
    ),
    ListEndpoint(
        path="/api/v1/admin/snapshots",
        route_path="/api/v1/admin/snapshots",
        family=UNPAGED,
        list_key="snapshots",
        total=ABSENT,
    ),
    ListEndpoint(
        path="/api/v1/clusters",
        route_path="/api/v1/clusters",
        family=UNPAGED,
        list_key="clusters",
        total=ABSENT,
    ),
    ListEndpoint(
        path="/api/v1/views",
        route_path="/api/v1/views",
        family=UNPAGED,
        list_key="views",
        total=ABSENT,
    ),
    ListEndpoint(
        path="/api/v1/dashboards",
        route_path="/api/v1/dashboards",
        family=UNPAGED,
        list_key="dashboards",
        total=ABSENT,
    ),
    ListEndpoint(
        path="/api/v1/dashboards/roles",
        route_path="/api/v1/dashboards/roles",
        family=UNPAGED,
        list_key="roles",
        total=ABSENT,
    ),
    ListEndpoint(
        path="/api/v1/notifications",
        route_path="/api/v1/notifications",
        family=UNPAGED,
        list_key="items",
        total=ABSENT,
        why="DOCUMENTED EXCEPTION: the key is the generic `items`, not the resource noun, so "
        "'named key equals resource name' is not a reliable reading of the rule.",
    ),
)

# GET routes that are not list responses. Each states WHY — an exemption without a reason is
# indistinguishable from having forgotten the route.
EXEMPT_GET_ROUTES: dict[str, str] = {
    "/healthz": "liveness scalar",
    "/readyz": "readiness scalar",
    "/api/v1/meta": "one object: the running versions",
    "/metrics": "Prometheus text exposition, not JSON",
    "/auth/me": "one principal",
    "/api/v1/settings/sla": "one policy object",
    "/api/v1/settings/staleness": "timers object",
    "/api/v1/settings/retirement": "window object",
    "/api/v1/settings/data": "settings object",
    "/api/v1/settings/scan-scope": "scope object (its include/exclude are fields, not the payload)",
    "/api/v1/scan-scope": "same scope object, machine regime",
    "/api/v1/trends/scans": "series keyed by scanner, not a list envelope",
    "/api/v1/trends/findings": "series keyed by scanner, not a list envelope",
    "/api/v1/trends/ingest-failures": "series keyed by scanner, not a list envelope",
    "/api/v1/findings/facets": "aggregation buckets, own shape",
    "/api/v1/audit/facets": "aggregation buckets, own shape",
    "/api/v1/findings/export.csv": "CSV stream",
    "/api/v1/audit/export.csv": "CSV stream",
    "/api/v1/contributors/export.csv": "CSV stream",
    "/api/v1/decisions/approvals/export.csv": "CSV stream",
    "/api/v1/findings/export.vex": "OpenVEX/CycloneDX document",
    "/api/v1/reports/{report_id}": "one job status",
    "/api/v1/dashboards/{dashboard_id}": "one dashboard",
    "/api/v1/dashboards/export.ndjson": "NDJSON file, one dashboard on each line",
    "/api/v1/reports/{report_id}/download": "result chunk stream",
    "/api/v1/admin/opensearch-runtime": (
        "runtime-facts object; its `nodes` array is one field among version/health/heap/etc, "
        "not the collection the route serves"
    ),
}


def _get_paths(app: Any) -> set[str]:
    """Every GET path, read off the generated spec.

    NOT `app.routes`: FastAPI wraps included routers in `_IncludedRouter`, which exposes no
    `path`/`methods`/`routes`, so the obvious walk yields an empty set and any check built on it
    passes vacuously (issue 540). The spec is also what actually ships.
    """
    spec = app.openapi()
    return {path for path, ops in spec["paths"].items() if "get" in ops}


def test_every_get_route_is_registered_or_exempt() -> None:
    """A new list route cannot land undocumented: register it above and add its row to
    `api-design.md` § List response envelopes, or exempt it here with a reason."""
    covered = set(EXEMPT_GET_ROUTES) | {e.route_path for e in REGISTRY}
    unaccounted = sorted(_get_paths(create_app()) - covered)
    assert not unaccounted, (
        "GET routes missing from the list-envelope registry — register them (and add them to "
        f"api-design.md) or exempt them with a reason: {unaccounted}"
    )


def test_the_registry_matches_the_live_route_table() -> None:
    """The mirror of the check above: a registered route that no longer exists means the doc
    is describing something that shipped away."""
    live = _get_paths(create_app())
    stale = sorted({e.route_path for e in REGISTRY} - live)
    assert not stale, f"registered list routes that no longer exist: {stale}"

    stale_exempt = sorted(set(EXEMPT_GET_ROUTES) - live)
    assert not stale_exempt, f"exempted GET routes that no longer exist: {stale_exempt}"


def test_the_route_walk_would_not_pass_vacuously() -> None:
    """Guard the guard. Both checks above are set-differences against `_get_paths`; if it ever
    returns nothing they pass while asserting nothing — which is exactly how the RBAC presence
    check went blind (issue 540)."""
    found = _get_paths(create_app())
    assert len(found) > 20, (
        f"route enumeration returned {len(found)} GET paths — too few to be real. The checks "
        "above are set-differences against it, so they would now pass while asserting nothing."
    )


async def _app_client() -> tuple[httpx.AsyncClient, AsyncOpenSearch]:
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    return http, client


async def _login_all_capabilities(http: httpx.AsyncClient, client: AsyncOpenSearch) -> None:
    """`*` satisfies every `require_capability` gate (auth/capabilities.py:39) — this suite is
    about response shape, and the capability axis is `test_rbac_idor_contract.py`'s job."""
    username = f"u-{uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
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
    assert r.status_code == 200, r.text


@requires_opensearch
@pytest.mark.parametrize("endpoint", REGISTRY, ids=[e.route_path for e in REGISTRY])
async def test_list_envelope_shape(endpoint: ListEndpoint) -> None:
    http, client = await _app_client()
    try:
        await _login_all_capabilities(http, client)
        r = await http.get(endpoint.path)
        assert r.status_code == 200, f"{endpoint.route_path} -> {r.status_code}: {r.text[:200]}"
        body = r.json()

        assert endpoint.list_key in body, (
            f"{endpoint.route_path} should carry its rows under '{endpoint.list_key}' "
            f"(api-design.md § List response envelopes); got keys {sorted(body)}"
        )
        assert isinstance(body[endpoint.list_key], list), (
            f"{endpoint.route_path}.{endpoint.list_key} is not an array"
        )

        if endpoint.total == WRAPPED:
            assert isinstance(body.get("total"), dict) and "value" in body["total"], (
                f"{endpoint.route_path} is cursor-paged: total should be "
                f"{{value, relation}}, got {body.get('total')!r}"
            )
        elif endpoint.total == BARE:
            assert isinstance(body.get("total"), int) and not isinstance(body["total"], bool), (
                f"{endpoint.route_path} is offset-paged: total should be a plain int, "
                f"got {body.get('total')!r}"
            )
        else:
            assert "total" not in body, (
                f"{endpoint.route_path} is documented as carrying no total, but returned "
                f"{body['total']!r} — update api-design.md if this is intended"
            )

        if endpoint.family == CURSOR:
            assert "next_cursor" in body, f"{endpoint.route_path} is cursor-paged without a cursor"
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
async def test_the_wrong_key_is_silently_empty_not_an_error() -> None:
    """The defect #530 is about, pinned as behaviour rather than described in prose.

    Reading the wrong key does not raise — it is absent, and every idiom that treats "absent" as
    "empty" (jq's `null | length`, a JS `?? []`) turns it into a self-consistent 0. This is why
    `api-design.md` tells non-typed consumers to assert the key exists.
    """
    http, client = await _app_client()
    try:
        await _login_all_capabilities(http, client)
        r = await http.get(f"/api/v1/decisions/approvals?cluster_id={EMPTY_CLUSTER}&size=1")
        assert r.status_code == 200
        body = r.json()
        assert "approvals" in body  # the real key
        assert "data" not in body  # the cursor-family key a reader would guess, absent not empty
    finally:
        await http.aclose()
        await client.close()


def test_no_route_declares_a_response_model() -> None:
    """Doc-sync check for the claim in `api-design.md` § Reading one of these safely: the
    OpenAPI contract carries no response shape, so the generated TS client cannot protect a
    consumer from a wrong key (issue 539).

    If this fails, someone added response models — good. Update that paragraph, and narrow or
    delete this test rather than weakening it.
    """

    def json_200_schema(op: dict[str, Any]) -> dict[str, Any]:
        content = op.get("responses", {}).get("200", {}).get("content", {})
        return content.get("application/json", {}).get("schema", {})

    spec = create_app().openapi()
    typed = [
        f"{method.upper()} {path}"
        for path, ops in spec["paths"].items()
        for method, op in ops.items()
        if "$ref" in json_200_schema(op)
    ]
    assert not typed, (
        "these routes now declare a response model, so api-design.md's 'the generated client "
        f"does not protect you' paragraph is out of date: {typed}"
    )
