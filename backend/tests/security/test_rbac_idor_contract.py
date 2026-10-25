"""THE standing RBAC/IDOR negative-test suite (M5a slice 5, AUDIT N4 / SEC-4).

Every capability-gated **mutating** endpoint registers a `MutatingEndpoint` here; the parametrized
tests then assert, for each one: (a) no session → 401, (b) an authenticated principal WITHOUT the
capability → 403, (c) a `must_change` principal WITH the capability → 403 (SEC-6). The
**presence check** walks the live route table: a mutating route that is neither registered nor
explicitly exempt FAILS the build — forgetting to register is a test failure, not a silent gap.

⚠️ Enumerate routes through `app.openapi()` only (issue 540). The obvious walk over `app.routes`
filtering on `.methods` returns an EMPTY set once routers are `include_router`-ed, because FastAPI
wraps them in `_IncludedRouter` — which exposes no `path`, no `methods` and no `routes`. This file
did that for a while and saw 0 of 37 mutating routes, so the presence check below could not fail
at all. `test_the_route_enumeration_is_not_blind` now fails loudly if it is ever starved again.

Exemptions are endpoints with their own tested auth regime:
  - `/auth/*` — the session regime itself (test_auth_routes.py)
  - machine-token endpoints (ingest, scan-runs) — SEC-3 binding (test_ingest_route.py)

Cross-`cluster_id` IDOR (the suite's third axis): MVP = all-clusters-visible with `cluster_id` as
an always-applied data filter (D38/H9) — reads are guarded structurally by the tenant read path
(test_tenant_read_path.py). When per-user `allowed_cluster_ids` grants land post-MVP, this file
grows the cross-tenant case for every registered endpoint.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
import structlog
from opensearchpy import AsyncOpenSearch

from backend.auth import principal
from backend.auth.passwords import hash_password
from backend.core.metrics import AUTH_FAILURES
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"


@dataclass(frozen=True)
class MutatingEndpoint:
    """One registered capability-gated mutation. `path` is the concrete call target (sample ids
    inlined); `route_path` is the FastAPI template it corresponds to (for the presence check)."""

    method: str
    path: str
    route_path: str
    capability: str
    body: dict[str, Any] | None = field(default=None)


# ── THE REGISTRY — every new capability-gated mutating endpoint adds itself here ──────────────
REGISTRY: tuple[MutatingEndpoint, ...] = (
    MutatingEndpoint(  # M5a slice 6 — token admin (D38/M14)
        method="POST",
        path="/api/v1/admin/tokens",
        route_path="/api/v1/admin/tokens",
        capability="can_manage_tokens",
        body={"cluster_id": "c-rbac-suite", "scanner": "trivy"},
    ),
    MutatingEndpoint(
        method="POST",
        path="/api/v1/admin/tokens/t-sample/revoke",
        route_path="/api/v1/admin/tokens/{token_id}/revoke",
        capability="can_manage_tokens",
    ),
    MutatingEndpoint(
        method="POST",
        path="/api/v1/admin/tokens/t-sample/rotate",
        route_path="/api/v1/admin/tokens/{token_id}/rotate",
        capability="can_manage_tokens",
    ),
    MutatingEndpoint(  # M5b slice 3 — triage (FR-7)
        method="PATCH",
        path="/api/v1/findings/fk-rbac-suite/triage",
        route_path="/api/v1/findings/{finding_key}/triage",
        capability="can_triage",
        body={"state": "acknowledged"},
    ),
    MutatingEndpoint(  # task D (#141) — admin user management (FR-18)
        method="POST",
        path="/api/v1/admin/users",
        route_path="/api/v1/admin/users",
        capability="can_manage_users",
        body={"username": "u-rbac-sample", "temp_password": PASSWORD, "role": "viewer"},
    ),
    MutatingEndpoint(
        method="PATCH",
        path="/api/v1/admin/users/u-rbac-sample/role",
        route_path="/api/v1/admin/users/{username}/role",
        capability="can_manage_users",
        body={"role": "viewer"},
    ),
    MutatingEndpoint(
        method="PATCH",
        path="/api/v1/admin/users/u-rbac-sample/disabled",
        route_path="/api/v1/admin/users/{username}/disabled",
        capability="can_manage_users",
        body={"disabled": True},
    ),
    MutatingEndpoint(
        method="POST",
        path="/api/v1/admin/users/u-rbac-sample/password-reset",
        route_path="/api/v1/admin/users/{username}/password-reset",
        capability="can_manage_users",
        body={"temp_password": PASSWORD},
    ),
    # M5c — decisions (FR-8). can_triage is the gate for not_affected; risk_accepted and
    # ignore_rule additionally need accept_final to create, edit or revoke (issue 892), pinned
    # in test_decision_routes.py
    MutatingEndpoint(
        method="POST",
        path="/api/v1/decisions",
        route_path="/api/v1/decisions",
        capability="can_triage",
        body={
            "type": "not_affected",
            "vex_justification": "component_not_present",
            "cve_id": "CVE-1",
            "scope": {"namespaces": [], "images": []},
            "apply_both_scanners": True,
            "justification": "rbac probe",
            "cluster_id": "c-rbac-sample",
        },
    ),
    MutatingEndpoint(
        method="POST",
        path="/api/v1/decisions/d-rbac-sample/revoke",
        route_path="/api/v1/decisions/{decision_id}/revoke",
        capability="can_triage",
    ),
    MutatingEndpoint(
        method="PATCH",
        path="/api/v1/decisions/d-rbac-sample",
        route_path="/api/v1/decisions/{decision_id}",
        capability="can_triage",
        body={"justification": "rbac probe"},
    ),
    MutatingEndpoint(  # M5d — bulk triage (FR-7/D38-H8)
        method="POST",
        path="/api/v1/findings/bulk-triage",
        route_path="/api/v1/findings/bulk-triage",
        capability="can_triage",
        body={
            "cluster_id": "c-rbac-sample",
            "selector": {"cve_id": "CVE-1"},
            "patch": {"state": "acknowledged"},
        },
    ),
    MutatingEndpoint(  # M5d — SLA policy (FR-10; admin-gated settings write)
        method="PUT",
        path="/api/v1/settings/sla",
        route_path="/api/v1/settings/sla",
        capability="can_manage_settings",
        body={"critical_days": 2, "high_days": 7, "medium_days": 30, "low_days": 90, "kev_days": 1},
    ),
    MutatingEndpoint(  # M9e slice 3 — staleness timers (FR-6/D20; admin-gated settings write)
        method="PUT",
        path="/api/v1/settings/staleness",
        route_path="/api/v1/settings/staleness",
        capability="can_manage_settings",
        body={"freshness_days": 3, "scanner_down_days": 7},
    ),
    MutatingEndpoint(  # issue 765 — the cluster retirement window (settings-tier, journaled)
        method="PUT",
        path="/api/v1/settings/retirement",
        route_path="/api/v1/settings/retirement",
        capability="can_manage_settings",
        body={"retire_after_days": 45, "warn_days": 7, "cluster_id": "c-rbac-sample"},
    ),
    MutatingEndpoint(  # M9e slice 3 — scan scope write (D43; the bearer GET stays scanner-only)
        method="PUT",
        path="/api/v1/scan-scope",
        route_path="/api/v1/scan-scope",
        capability="can_manage_settings",
        body={"cluster_id": "c-rbac-sample", "ignore_namespaces": ["kube-system"]},
    ),
    MutatingEndpoint(  # M9e slice 4 — retention window (FR-19/D26; edits the lifecycle setting doc)
        method="PUT",
        path="/api/v1/settings/retention",
        route_path="/api/v1/settings/retention",
        capability="can_manage_retention",
        body={"retention_days": 90},
    ),
    MutatingEndpoint(  # M9e slice 4 — rollover thresholds (FR-19/D26)
        method="PUT",
        path="/api/v1/settings/rollover",
        route_path="/api/v1/settings/rollover",
        capability="can_manage_retention",
        body={"max_age_days": 30, "max_docs": 5_000_000, "max_size_gb": 50},
    ),
    MutatingEndpoint(  # M9e slice 4 — report/export TTL (row 11: now a runtime setting)
        method="PUT",
        path="/api/v1/settings/report-ttl",
        route_path="/api/v1/settings/report-ttl",
        capability="can_manage_retention",
        body={"hours": 24},
    ),
    MutatingEndpoint(  # M9e slice 4 — findings long-window cleanup (D37/M12)
        method="PUT",
        path="/api/v1/settings/findings-cleanup",
        route_path="/api/v1/settings/findings-cleanup",
        capability="can_manage_retention",
        body={"cleanup_days": 180},
    ),
    MutatingEndpoint(  # M9e slice 4 — manual snapshot (NFR-6; 409 without a repo, after the gate)
        method="POST",
        path="/api/v1/admin/snapshots",
        route_path="/api/v1/admin/snapshots",
        capability="can_manage_retention",
    ),
    MutatingEndpoint(  # M9e slice 4 — snapshot restore (destructive-adjacent; renames, never live)
        method="POST",
        path="/api/v1/admin/snapshots/manual-sample/restore",
        route_path="/api/v1/admin/snapshots/{snapshot_name}/restore",
        capability="can_restore_snapshot",
    ),
    MutatingEndpoint(  # M8c slice 2 — cluster rename (D-5 ruling; display-only cluster_name)
        method="PUT",
        path="/api/v1/clusters/c-rbac-sample1/name",
        route_path="/api/v1/clusters/{cluster_id}/name",
        capability="can_manage_settings",
        body={"cluster_name": "RBAC probe"},
    ),
    MutatingEndpoint(  # issue 765 — retire a cluster (off the list, its tokens revoked)
        method="POST",
        path="/api/v1/clusters/c-rbac-sample1/retire",
        route_path="/api/v1/clusters/{cluster_id}/retire",
        capability="can_manage_settings",
    ),
    MutatingEndpoint(  # issue 765 — delete a retired cluster (everything but its audit rows)
        method="DELETE",
        path="/api/v1/clusters/c-rbac-sample1",
        route_path="/api/v1/clusters/{cluster_id}",
        capability="can_manage_retention",
    ),
    MutatingEndpoint(  # issue 765 — bring a retired cluster back
        method="POST",
        path="/api/v1/clusters/c-rbac-sample1/unretire",
        route_path="/api/v1/clusters/{cluster_id}/unretire",
        capability="can_manage_settings",
    ),
    MutatingEndpoint(  # issue 406 repair actions — per-KIND capability inside the handler
        # (rebuild_state→can_rebuild_state, lifecycle_sweep→can_drop_index); the registry probes
        # the staleness kind, the other kinds' gates are asserted in test_admin_jobs
        method="POST",
        path="/api/v1/admin/jobs/staleness_sweep/run",
        route_path="/api/v1/admin/jobs/{kind}/run",
        capability="can_manage_settings",
        body={},
    ),
    MutatingEndpoint(  # #406 — the data-inspector proxy: POST by transport but READ by contract;
        # the allowlist inside the handler is the write-prevention, the capability is the gate
        method="POST",
        path="/api/v1/admin/opensearch/inspect",
        route_path="/api/v1/admin/opensearch/inspect",
        capability="can_inspect_store",
        body={"method": "GET", "path": "_cluster/health"},
    ),
    MutatingEndpoint(  # M7 slice 5 — the bulk_triage report kind (A-Mc): a scheduled bulk is a
        # WRITE, gated like the inline bulk. The gate is per-kind, checked before any store work;
        # the export kind on the same route is the next entry.
        method="POST",
        path="/api/v1/reports",
        route_path="/api/v1/reports",
        capability="can_triage",
        body={
            "kind": "bulk_triage",
            "cluster_id": "c-rbac-sample",
            "bulk_params": {
                "selector": {"cve_id": "CVE-1"},
                "patch": {"state": "acknowledged"},
            },
        },
    ),
    MutatingEndpoint(  # issue 243 — the export kind of the same route needs can_export, as the
        # inline export files do (their read-side gate: tests/security/test_export_capability.py)
        method="POST",
        path="/api/v1/reports",
        route_path="/api/v1/reports",
        capability="can_export",
        body={"kind": "export", "cluster_id": "c-rbac-sample"},
    ),
    MutatingEndpoint(  # issue 440 — dashboards: a write needs can_edit_dashboards; who sees one
        # (404) and the owner-or-admin rule (403) are asserted in test_dashboards_route
        method="POST",
        path="/api/v1/dashboards",
        route_path="/api/v1/dashboards",
        capability="can_edit_dashboards",
        body={"name": "rbac sample"},
    ),
    MutatingEndpoint(
        method="PATCH",
        path="/api/v1/dashboards/d-rbac-sample",
        route_path="/api/v1/dashboards/{dashboard_id}",
        capability="can_edit_dashboards",
        body={"revision": 1},
    ),
    MutatingEndpoint(
        method="DELETE",
        path="/api/v1/dashboards/d-rbac-sample?revision=1",
        route_path="/api/v1/dashboards/{dashboard_id}",
        capability="can_edit_dashboards",
    ),
)

# mutating routes with their own (tested) auth regime — NOT capability-gated
EXEMPT_ROUTE_PATHS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/auth/login"),  # the front door itself
        ("POST", "/auth/logout"),  # session regime (test_auth_routes)
        ("POST", "/auth/password"),  # session regime + must_change escape hatch
        ("POST", "/api/v1/ingest/scan"),  # machine token + SEC-3 binding (test_ingest_route)
        ("POST", "/api/v1/scan-runs"),  # machine token (test_scan_orders route tests)
        # M8a slice 2 — machine token + SEC-3 binding: the manifest is always for the token's own
        # cluster; written_count is counted server-side, never client-reported (test_inventory_runs)
        ("POST", "/api/v1/inventory-runs"),
        # M7 slice 3 — mark-read is strictly OWN-notification (user_id filter server-side; someone
        # else's id 404s, IDOR-tested in test_report_download). No capability: your own bell.
        ("PATCH", "/api/v1/notifications/{notification_id}/read"),
        # M9f slice 3 — dismiss shares the same own-or-404 gate (IDOR matrix alongside mark-read)
        ("DELETE", "/api/v1/notifications/{notification_id}"),
        # M8e (#242) — any authenticated user may save a view (owner = principal, C-6 ruling);
        # session-required asserted in test_views_route. PATCH/DELETE are the OWNER-OR-ADMIN
        # regime, not a capability gate: non-owner 403, admin override, owner immutable —
        # the IDOR matrix lives in test_views_route.
        ("POST", "/api/v1/views"),
        ("PATCH", "/api/v1/views/{view_id}"),
        ("DELETE", "/api/v1/views/{view_id}"),
        # issue 453 — the client-events beacon: any authenticated user's browser reports its OWN
        # warn/error events, so there is no capability to hold or withhold and the registry's
        # "principal WITHOUT the capability → 403" axis is unrepresentable here. The auth regime
        # it carries instead — 401 anonymous, 403 on a must_change session (SEC-6), and the
        # per-principal rate cap — is asserted in test_client_events_route.
        ("POST", "/api/v1/client-events"),
        # issue 832 — closing a cursor walk: any signed-in user closes only a walk that one of
        # their OWN PIT slots holds; another user's cursor answers the same 204 and closes nothing.
        # No capability to withhold, so the "WITHOUT the capability → 403" axis does not apply.
        # 401 anonymous, 403 must_change and the cross-user case are in test_cursor_close_route.
        ("POST", "/api/v1/cursors/close"),
    }
)

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


# ── presence check: an unregistered mutating route fails the build (AUDIT N4) ─────────────────


def _live_mutating_routes() -> set[tuple[str, str]]:
    """Every mutating (method, path) the app actually serves.

    Read off `app.openapi()`, NOT `app.routes`: FastAPI wraps included routers in
    `_IncludedRouter`, which exposes no `path`, no `methods` and no `routes`, so walking
    `app.routes` and filtering on `.methods` silently yields an EMPTY set — every check built on
    it then passes while asserting nothing. The spec is also what actually ships, and does not
    depend on a FastAPI internal that can change again.
    """
    spec = create_app().openapi()
    return {
        (method.upper(), path)
        for path, ops in spec["paths"].items()
        for method in ops
        if method.upper() in _MUTATING
    }


def test_the_route_enumeration_is_not_blind() -> None:
    """Guard the guard. The presence check below is a set-difference against
    `_live_mutating_routes()`, so a starved enumeration makes it pass while asserting nothing.
    Fail loudly on an implausible count instead of trusting a green set-difference."""
    live = _live_mutating_routes()
    assert len(live) > 20, (
        f"route enumeration found {len(live)} mutating routes — too few to be real. The presence "
        "check is a set-difference against this, so it would now pass while asserting nothing."
    )


def test_every_mutating_route_is_registered_or_exempt() -> None:
    covered = EXEMPT_ROUTE_PATHS | {(e.method, e.route_path) for e in REGISTRY}
    unaccounted = sorted(_live_mutating_routes() - covered)
    assert not unaccounted, (
        f"mutating routes missing from the RBAC/IDOR registry (register or exempt them): "
        f"{unaccounted}"
    )


def test_no_exemption_names_a_route_that_no_longer_exists() -> None:
    """A stale exemption fails silently in the worst direction: it covers nothing, while its route
    reappears as unaccounted with no hint that a typo'd path is the reason. Name it directly."""
    live = _live_mutating_routes()
    stale = sorted(EXEMPT_ROUTE_PATHS - live)
    assert not stale, f"exempted mutating routes that no longer exist: {stale}"


# ── the parametrized negative axes over every registered endpoint ─────────────────────────────


async def _app_client() -> tuple[httpx.AsyncClient, AsyncOpenSearch]:
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    return http, client


async def _login_as(
    http: httpx.AsyncClient,
    client: AsyncOpenSearch,
    *,
    capabilities: list[str],
    must_change: bool = False,
) -> str:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
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


def _ids() -> list[str]:
    return [f"{e.method} {e.route_path}" for e in REGISTRY]


@requires_opensearch
@pytest.mark.parametrize("endpoint", REGISTRY, ids=_ids())
async def test_no_session_is_401(endpoint: MutatingEndpoint) -> None:
    http, client = await _app_client()
    try:
        r = await http.request(endpoint.method, endpoint.path, json=endpoint.body)
        assert r.status_code == 401
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
@pytest.mark.parametrize("endpoint", REGISTRY, ids=_ids())
async def test_missing_capability_is_403(endpoint: MutatingEndpoint) -> None:
    http, client = await _app_client()
    try:
        await _login_as(http, client, capabilities=[])  # authenticated, zero capabilities
        r = await http.request(endpoint.method, endpoint.path, json=endpoint.body)
        assert r.status_code == 403
    finally:
        await http.aclose()
        await client.close()


@requires_opensearch
@pytest.mark.parametrize("endpoint", REGISTRY, ids=_ids())
async def test_must_change_is_403_even_with_the_capability(endpoint: MutatingEndpoint) -> None:
    http, client = await _app_client()
    try:
        await _login_as(http, client, capabilities=[endpoint.capability], must_change=True)
        r = await http.request(endpoint.method, endpoint.path, json=endpoint.body)
        assert r.status_code == 403  # SEC-6: nothing but /auth/* until the password changes
    finally:
        await http.aclose()
        await client.close()


# ── a must_change session reaches nothing but /auth/*: every route, reads included ────────────
# The registry above holds the gated writes only, which is how reads stayed open to a temporary
# password (issue 803). This axis walks the whole route table instead, so a new read is covered
# without registering it.

# routes outside the session regime: the anonymous probes, the machine-token surface, and /auth/*
# itself, the only way out of a must_change session
_NOT_SESSION_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/healthz"),
        ("GET", "/readyz"),
        ("GET", "/metrics"),
        ("POST", "/api/v1/ingest/scan"),
        ("GET", "/api/v1/scan-scope"),
        ("POST", "/api/v1/scan-runs"),
        ("POST", "/api/v1/inventory-runs"),
    }
)


def _session_routes() -> list[tuple[str, str]]:
    spec = create_app().openapi()  # app.routes is blind to included routers (module docstring)
    return sorted(
        (method.upper(), path)
        for path, ops in spec["paths"].items()
        for method in ops
        if not path.startswith("/auth/") and (method.upper(), path) not in _NOT_SESSION_ROUTES
    )


def test_the_session_route_walk_is_not_blind() -> None:
    routes = _session_routes()
    assert len(routes) > 60, f"the walk found {len(routes)} session routes: too few to be real"
    assert ("GET", "/api/v1/findings") in routes  # the read this axis exists for


def test_no_non_session_route_is_stale() -> None:
    spec = create_app().openapi()
    live = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    assert not sorted(_NOT_SESSION_ROUTES - live)


@requires_opensearch
@pytest.mark.parametrize("route", _session_routes(), ids=lambda r: f"{r[0]} {r[1]}")
async def test_a_must_change_session_gets_403_on_every_session_route(
    route: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    method, template = route
    # any value fills a path parameter: the refusal comes before the route reads it
    path = re.sub(r"\{[^}]+\}", "sample-0803", template)
    http, client = await _app_client()
    try:
        username = await _login_as(http, client, capabilities=["*"], must_change=True)
        # create_app() re-configures structlog, so capture_logs() would see nothing: give the
        # module its own capturing logger instead
        capture = structlog.testing.LogCapture()
        monkeypatch.setattr(principal, "log", structlog.wrap_logger(None, processors=[capture]))
        before = AUTH_FAILURES.labels("must_change")._value.get()
        r = await http.request(method, path, params={"cluster_id": "c-rbac-sample1"}, json={})
        assert r.status_code == 403, f"{method} {template} answered {r.status_code}"
        assert r.json()["title"] == "password change required"
        assert AUTH_FAILURES.labels("must_change")._value.get() == before + 1
        warnings = [e for e in capture.entries if e["log_level"] == "warning"]
        assert [(e["event"], e["username"]) for e in warnings] == [
            ("password change required", username)
        ]
    finally:
        await http.aclose()
        await client.close()
