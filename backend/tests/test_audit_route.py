"""GET /api/v1/audit (M8c slice 1, #240) — the plain-session audit read.

Contract pins: session required (401 anonymous); ordering is the `(@timestamp, event_id)` pair in
one direction (DoD); filters entity_type/action/actor narrow correctly, with several values each;
the cursor walk pages the whole log without gaps or duplicates and A-m1 semantics hold (tampered
cursor → 422, bad order → 422); tenant isolation (another cluster's rows never appear). Rows are
written through the real M5b writer — the read must see exactly what the journal contract
produces."""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_auth_event, append_field_change
from backend.auth.passwords import hash_password
from backend.core.settings import get_settings
from backend.main import create_app
from backend.query.audit import AuditFilters, build_audit_body
from os_env import OS_URL, requires_opensearch

PASSWORD = "audit-route-password"


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
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
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
            "created_at": "2026-07-08T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client
    await http.aclose()
    await client.close()


async def _journal(
    client: AsyncOpenSearch,
    cluster_id: str,
    *,
    n: int,
    actor: str = "u-audit-actor",
    action: str = "assign",
    entity_type: str = "finding",
) -> None:
    for i in range(n):
        await append_field_change(
            client,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=f"fk-{cluster_id}-{i}",
            field="assignee",
            old_value=None,
            new_value=actor,
            revision=1,
            cluster_id=cluster_id,
            finding_key=f"fk-{cluster_id}-{i}",
        )
    await client.indices.refresh(index="system-audit-log-*")


async def test_requires_a_session(env) -> None:
    _, client = env
    app = create_app()
    app.state.opensearch = client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as c:
        r = await c.get("/api/v1/audit", params={"cluster_id": "c-audit-anon"})
    assert r.status_code == 401


async def test_rows_come_back_ordered_filtered_and_tenant_scoped(env) -> None:
    # NB (fleet seam, issue 406): the shared log now also serves cluster-LESS fleet rows to
    # every tenant read, so assertions scope through per-test actors, never bare totals.
    http, client = env
    cid, other = (f"c-audit-{uuid.uuid4().hex[:8]}" for _ in range(2))
    mine, second, theirs = (f"u-audit-{uuid.uuid4().hex[:8]}" for _ in range(3))
    await _journal(client, cid, n=3, action="assign", actor=mine)
    await _journal(client, cid, n=2, actor=second, action="note")
    await _journal(client, other, n=4, actor=theirs)  # the other tenant's rows must never appear

    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "actor": mine})
    assert r.status_code == 200
    body = r.json()
    assert body["total"]["value"] == 3
    assert all(row["cluster_id"] == cid for row in body["data"])
    # DoD: ordered by the (@timestamp, event_id) pair — desc default, verified as sort keys.
    # OpenSearch compares dates at MILLISECOND precision (the store truncates); _source keeps
    # microseconds — compare what the engine compared or same-ms rows flake the assertion.
    keys = [(row["@timestamp"][:23], row["event_id"]) for row in body["data"]]
    assert keys == sorted(keys, reverse=True)

    r = await http.get(
        "/api/v1/audit", params={"cluster_id": cid, "action": "note", "actor": second}
    )
    assert [row["action"] for row in r.json()["data"]] == ["note", "note"]
    # tenant scope: the other cluster's rows are invisible under cid even by their own actor
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "actor": theirs})
    assert r.json()["total"]["value"] == 0
    r = await http.get(
        "/api/v1/audit", params={"cluster_id": cid, "entity_type": "decision", "actor": mine}
    )
    assert r.json()["data"] == [] and r.json()["total"]["value"] == 0


async def test_cursor_walk_covers_the_log_without_gaps_or_duplicates(env) -> None:
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    walk_actor = f"u-walk-{uuid.uuid4().hex[:8]}"  # fleet seam: scope the walk to this test's rows
    await _journal(client, cid, n=5, actor=walk_actor)

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # 5 rows at size 2 → 3 pages; bound the loop against a paging bug
        params: dict[str, Any] = {"cluster_id": cid, "size": 2, "order": "asc", "actor": walk_actor}
        if cursor is not None:
            params["cursor"] = cursor
        r = await http.get("/api/v1/audit", params=params)
        assert r.status_code == 200
        page = r.json()
        seen.extend(row["event_id"] for row in page["data"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 5 and len(set(seen)) == 5  # every row exactly once


async def test_include_and_exclude_of_the_same_field_422_at_every_door(env) -> None:
    """issue 349 review: findings 422s the include+exclude conflict — the audit surfaces must
    answer the same malformed request identically, never silently AND a term with its own
    must_not into zero rows. One guard, all three doors (list, facets, export)."""
    http, _ = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    conflict = {"cluster_id": cid, "actor": "alice", "exclude_actor": "alice"}
    for path in ("/api/v1/audit", "/api/v1/audit/facets", "/api/v1/audit/export.csv"):
        r = await http.get(path, params=conflict)
        assert r.status_code == 422, path
        assert "mutually exclusive" in r.json()["title"]  # RFC 9457: detail → title
    # a different field on each side is a legitimate lens, not a conflict
    r = await http.get(
        "/api/v1/audit", params={"cluster_id": cid, "action": "login", "exclude_actor": "alice"}
    )
    assert r.status_code == 200


async def test_a_m1_cursor_and_order_semantics(env) -> None:
    http, _ = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "cursor": "not-a-cursor"})
    assert r.status_code == 422  # tampered/undecodable cursor — never a 500
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "order": "up"})
    assert r.status_code == 422
    # an empty lens is a real answer, not an error (actor-scoped — fleet rows share the log)
    r = await http.get(
        "/api/v1/audit", params={"cluster_id": cid, "actor": f"u-nobody-{uuid.uuid4().hex[:8]}"}
    )
    assert r.status_code == 200 and r.json()["data"] == []


def test_build_audit_body_is_the_fixed_pair_sort_plus_terms_filters() -> None:
    body = build_audit_body(
        AuditFilters(entity_type=["finding"], actor=["u1", "u2"]), size=10, order="asc"
    )
    assert body["sort"] == [{"@timestamp": {"order": "asc"}}, {"event_id": {"order": "asc"}}]
    assert {"terms": {"entity_type": ["finding"]}} in body["query"]["bool"]["filter"]
    assert {"terms": {"actor": ["u1", "u2"]}} in body["query"]["bool"]["filter"]
    assert body["track_total_hits"] is True
    with pytest.raises(ValueError):
        build_audit_body(AuditFilters(), size=10, order="sideways")
    assert "query" not in build_audit_body(AuditFilters(), size=10)  # unset filters add nothing
    # an empty list is no filter, never a clause that matches nothing
    assert "query" not in build_audit_body(AuditFilters(actor=[], exclude_action=[]), size=10)


def test_finding_key_filter_scopes_to_one_finding_and_the_bulk_rows_that_name_it() -> None:
    # M9b slice 4: the detail screen's per-finding activity list; issue 912: a bulk change names
    # its findings in `target_ids`, not in `finding_key`
    body = build_audit_body(AuditFilters(finding_key="fk-abc"), size=5)
    assert {
        "bool": {
            "should": [
                {"term": {"finding_key": "fk-abc"}},
                {"term": {"target_ids": "fk-abc"}},
            ],
            "minimum_should_match": 1,
        }
    } in body["query"]["bool"]["filter"]


def test_exclude_filters_become_must_not_clauses() -> None:
    # issue 349: the negation side of the rail dims — one mode per field, never both
    body = build_audit_body(
        AuditFilters(exclude_entity_type=["finding"], exclude_actor=["alice", "bob"]), size=10
    )
    assert {"terms": {"entity_type": ["finding"]}} in body["query"]["bool"]["must_not"]
    # issue 952: an exclusion with two values leaves out the rows of either
    assert {"terms": {"actor": ["alice", "bob"]}} in body["query"]["bool"]["must_not"]
    assert "filter" not in body["query"]["bool"]  # nothing included = no filter clause


def test_include_and_exclude_coexist_on_different_fields() -> None:
    body = build_audit_body(AuditFilters(action=["login"], exclude_actor=["alice"]), size=10)
    assert body["query"]["bool"]["filter"] == [{"terms": {"action": ["login"]}}]
    assert body["query"]["bool"]["must_not"] == [{"terms": {"actor": ["alice"]}}]


def test_facets_and_count_inherit_exclusion_from_the_shared_builder() -> None:
    # the rail counts and the export pre-count must describe the SAME lens as the walk
    from backend.query.audit import build_audit_facets_body

    facets = build_audit_facets_body(AuditFilters(exclude_action=["login"]))
    assert facets["query"]["bool"]["must_not"] == [{"terms": {"action": ["login"]}}]


def test_the_user_count_leaves_out_the_user_filter_and_nothing_else_does() -> None:
    """issue 952: a picked user must not hide the other users from the list, so the
    actor count runs without the user filter. Entity, action and the activity chart keep the
    whole set of filters, user filter included."""
    from backend.query.audit import build_audit_facets_body

    now = datetime(2026, 7, 10, tzinfo=UTC)
    filters = AuditFilters(actor=["alice"], exclude_action=["login"])
    body = build_audit_facets_body(filters, interval="day", window_days=2, now=now)
    full = build_audit_body(filters, size=0)["query"]
    # the main query has every filter but the user one
    assert body["query"] == {"bool": {"must_not": [{"terms": {"action": ["login"]}}]}}
    assert body["aggs"]["actor"] == {"terms": {"field": "actor", "size": 32}}
    for field in ("entity_type", "action"):
        assert body["aggs"][field] == {
            "filter": full,
            "aggs": {"values": {"terms": {"field": field, "size": 64}}},
        }
    window = {"range": {"@timestamp": {"gte": "2026-07-08T00:00:00+00:00", "lte": now.isoformat()}}}
    assert body["aggs"]["activity"]["filter"] == {"bool": {"filter": [full, window]}}
    assert "date_histogram" in body["aggs"]["activity"]["aggs"]["buckets"]
    # without a user filter nothing is wrapped: the body is the one it always was
    plain = build_audit_facets_body(AuditFilters(action=["login"]))
    assert plain["aggs"]["action"] == {"terms": {"field": "action", "size": 64}}
    assert plain["aggs"]["entity_type"] == {"terms": {"field": "entity_type", "size": 64}}
    assert plain["aggs"]["actor"] == {"terms": {"field": "actor", "size": 32}}
    assert plain["query"] == {"bool": {"filter": [{"terms": {"action": ["login"]}}]}}


def test_the_freed_user_count_keeps_the_time_limit_the_tenant_and_the_account_rule() -> None:
    """issue 952: the user count leaves out only the user filter. The `as_of` limit, the
    tenant guard and the account rule of issue 892 sit in the main query, which every count
    runs under, so a viewer's user count never lists a user who only signed in."""
    from backend.query.audit import audit_tenant_query, build_audit_facets_body

    t = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    body = build_audit_facets_body(AuditFilters(actor=["alice"], until=t))
    guarded = audit_tenant_query("c-1", body, account_events=False, dashboard_events=False)
    top = guarded["query"]["bool"]
    # the guard wraps the builder's query in its own bool, as a `must`
    assert top["must"] == [
        {"bool": {"filter": [{"range": {"@timestamp": {"lte": t.isoformat()}}}]}}
    ]
    assert {"terms": {"entity_type": ["token", "user"]}} in top["must_not"]
    assert {"terms": {"entity_type": ["dashboard"]}} in top["must_not"]
    assert {"term": {"cluster_id": "c-1"}} in top["filter"][0]["bool"]["should"]
    assert guarded["aggs"]["actor"] == {"terms": {"field": "actor", "size": 32}}
    # a manager's count has no account rule; the rest stays
    manager = audit_tenant_query(
        "c-1",
        build_audit_facets_body(AuditFilters(actor=["alice"])),
        account_events=True,
        dashboard_events=True,
    )
    assert "must_not" not in manager["query"]["bool"]


def test_until_bounds_the_walk_at_t() -> None:
    # M9d slice 1 (D28): a rewound picker must not see post-T events — full-precision lte
    t = datetime(2026, 7, 10, 12, 30, 45, 123456, tzinfo=UTC)
    body = build_audit_body(AuditFilters(until=t), size=10)
    assert {"range": {"@timestamp": {"lte": t.isoformat()}}} in body["query"]["bool"]["filter"]
    assert "query" not in build_audit_body(AuditFilters(), size=10)


async def test_facets_count_the_rail_dims_tenant_scoped(env) -> None:
    # M9d rework: the rail needs real server counts (entity_type/action/actor terms aggs)
    http, client = env
    cid, other = (f"c-audit-{uuid.uuid4().hex[:8]}" for _ in range(2))
    facet_a, facet_b, theirs = (f"u-facet-{uuid.uuid4().hex[:8]}" for _ in range(3))
    await _journal(client, cid, n=3, action="assign", actor=facet_a)
    await _journal(client, cid, n=2, action="note", actor=facet_b)
    await _journal(client, other, n=7, action="assign", actor=theirs)  # invisible to cid

    # fleet seam (issue 406): the shared log serves cluster-less rows to every read and the
    # rail aggs are top-N capped — so counts are asserted through the per-test actor lens
    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid, "actor": facet_a})
    assert r.status_code == 200
    as_map = {b["key"]: b["count"] for b in r.json()["facets"]["action"]}
    assert as_map == {"assign": 3}
    # facets honor the active filters (counts describe the OTHER dims of the current lens)
    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid, "actor": facet_b})
    assert {b["key"]: b["count"] for b in r.json()["facets"]["action"]} == {"note": 2}
    # tenant guard: the other cluster's actor is invisible under cid
    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid, "actor": theirs})
    assert r.json()["facets"]["action"] == []


async def test_each_of_40_actions_gets_a_count(env) -> None:
    """issue 983: the Action list has 42 values. With 40 actions in the log, the count gives a
    bucket to each of them, not only to the top 32, so no action is left with no count."""
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    actor = f"u-many-{uuid.uuid4().hex[:8]}"
    actions = [f"action-{i:02d}" for i in range(40)]
    for i, action in enumerate(actions):
        await append_field_change(
            client,
            actor=actor,
            action=action,
            entity_type="finding",
            entity_id=f"fk-{cid}-{i}",
            field="assignee",
            old_value=None,
            new_value=actor,
            revision=1,
            cluster_id=cid,
            finding_key=f"fk-{cid}-{i}",
        )
    await client.indices.refresh(index="system-audit-log-*")

    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid, "actor": actor})
    assert r.status_code == 200
    assert sorted(b["key"] for b in r.json()["facets"]["action"]) == actions


async def test_several_values_match_any_of_them_at_every_door(env) -> None:
    """issue 952: `actor=a&actor=b` returns the rows of either user, and the CSV and the counts
    take the same filters. An exclusion with two values leaves out the rows of both."""
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    a, b, c = (f"u-multi-{uuid.uuid4().hex[:8]}" for _ in range(3))
    await _journal(client, cid, n=2, actor=a, action="assign")
    await _journal(client, cid, n=3, actor=b, action="note")
    await _journal(client, cid, n=1, actor=c, action="assign")

    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "actor": [a, b]})
    assert r.status_code == 200
    assert sorted({row["actor"] for row in r.json()["data"]}) == sorted([a, b])
    assert r.json()["total"]["value"] == 5
    r = await http.get(
        "/api/v1/audit", params={"cluster_id": cid, "actor": [a, b, c], "action": ["assign"]}
    )
    assert r.json()["total"]["value"] == 3  # OR inside a field, AND across fields
    r = await http.get(
        "/api/v1/audit",
        params={"cluster_id": cid, "actor": [a, b, c], "exclude_action": ["assign", "note"]},
    )
    assert r.json()["total"]["value"] == 0
    r = await http.get("/api/v1/audit/export.csv", params={"cluster_id": cid, "actor": [a, b]})
    assert r.status_code == 200
    assert len(r.text.strip().splitlines()) == 1 + 5  # the header, then the same five rows


async def test_the_user_count_keeps_the_other_users_and_the_action_count_follows_the_pick(
    env,
) -> None:
    """issue 952, against the store: with one user picked, the user count still lists
    the others with their real counts, while the action count stays that user's."""
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    a, b = (f"u-count-{uuid.uuid4().hex[:8]}" for _ in range(2))
    # fleet rows of other tests share the log and the user count is top-32, so a kind of row
    # of this test's own scopes the rows; it stays in the main query, the user filter does not
    kind = f"kind-{uuid.uuid4().hex[:8]}"
    await _journal(client, cid, n=2, actor=a, action="assign", entity_type=kind)
    await _journal(client, cid, n=3, actor=b, action="note", entity_type=kind)
    scope = {"cluster_id": cid, "entity_type": [kind]}

    r = await http.get(
        "/api/v1/audit/facets",
        params={**scope, "actor": [a], "interval": "day", "window_days": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert {f["key"]: f["count"] for f in body["facets"]["actor"]} == {a: 2, b: 3}
    assert {f["key"]: f["count"] for f in body["facets"]["action"]} == {"assign": 2}
    assert {f["key"]: f["count"] for f in body["facets"]["entity_type"]} == {kind: 2}
    assert sum(day["count"] for day in body["activity"]) == 2  # the chart keeps the user pick
    # an excluded user stays in the user count too, so it can be taken back out of the filter
    r = await http.get("/api/v1/audit/facets", params={**scope, "exclude_actor": [a]})
    assert {f["key"]: f["count"] for f in r.json()["facets"]["actor"]} == {a: 2, b: 3}
    assert {f["key"]: f["count"] for f in r.json()["facets"]["action"]} == {"note": 3}


async def test_a_filter_takes_at_most_32_values_at_every_door(env) -> None:
    """The cap of the findings filters (issue 949), at all three doors. Each value also keeps
    the length cap it had as one string."""
    http, _ = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    users = [f"u-{i}" for i in range(33)]
    for path in ("/api/v1/audit", "/api/v1/audit/facets", "/api/v1/audit/export.csv"):
        r = await http.get(path, params={"cluster_id": cid, "actor": users})
        assert r.status_code == 422, path
        r = await http.get(path, params={"cluster_id": cid, "exclude_action": users})
        assert r.status_code == 422, path
        r = await http.get(path, params={"cluster_id": cid, "entity_type": ["x" * 65]})
        assert r.status_code == 422, path
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "actor": users[:32]})
    assert r.status_code == 200


async def test_fleet_events_are_visible_under_any_cluster(env) -> None:
    # the operator catch (issue 406, 2026-07-18): auth/admin/inspect/job rows carry NO
    # cluster_id — the plain tenant term filter hid them from the screen entirely. The
    # widened audit guard keeps them visible under every cluster context; other tenants'
    # CLUSTER rows stay invisible (asserted in the tenant-scope test above).
    http, client = env
    actor = f"u-fleet-{uuid.uuid4().hex[:8]}"
    await append_auth_event(
        client,
        actor=actor,
        action="job_trigger",
        entity_type="job",
        entity_id="staleness_sweep attempt:test",
        strict=True,
    )
    await client.indices.refresh(index="system-audit-log-*")

    for cid in (f"c-audit-{uuid.uuid4().hex[:8]}", f"c-audit-{uuid.uuid4().hex[:8]}"):
        r = await http.get("/api/v1/audit", params={"cluster_id": cid, "actor": actor})
        assert r.status_code == 200
        rows = r.json()["data"]
        assert [row["action"] for row in rows] == ["job_trigger"]
        assert rows[0].get("cluster_id") is None  # fleet-scoped, no tenant claims it
    # and the rail facet sees the fleet row too
    r = await http.get(
        "/api/v1/audit/facets",
        params={"cluster_id": f"c-anywhere-{uuid.uuid4().hex[:8]}", "actor": actor},
    )
    assert {b["key"]: b["count"] for b in r.json()["facets"]["action"]} == {"job_trigger": 1}


async def test_rows_stamped_with_the_legacy_fleet_literal_are_visible_under_any_cluster(
    env,
) -> None:
    # Before issue 559 the fleet-wide settings writers stamped cluster_id="fleet" — neither the
    # selected tenant nor cluster-less — so the screen never showed them. Those rows stay in
    # the append-only log as written; the read must reach them in the list, the rail facets and
    # the CSV export alike, while another tenant's cluster row stays out.
    http, client = env
    actor = f"u-legacy-{uuid.uuid4().hex[:8]}"
    await append_field_change(
        client,
        actor=actor,
        action="sla_policy_change",
        entity_type="config",
        entity_id="sla_policy",
        field="policy",
        old_value=None,
        new_value=None,
        revision=1,
        cluster_id="fleet",
    )
    await _journal(client, f"c-audit-{uuid.uuid4().hex[:8]}", n=1, actor=actor)  # another tenant
    await client.indices.refresh(index="system-audit-log-*")

    for cid in (f"c-audit-{uuid.uuid4().hex[:8]}", f"c-audit-{uuid.uuid4().hex[:8]}"):
        r = await http.get("/api/v1/audit", params={"cluster_id": cid, "actor": actor})
        assert r.status_code == 200
        assert [row["action"] for row in r.json()["data"]] == ["sla_policy_change"]

        r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid, "actor": actor})
        assert {b["key"]: b["count"] for b in r.json()["facets"]["action"]} == {
            "sla_policy_change": 1
        }

        r = await http.get("/api/v1/audit/export.csv", params={"cluster_id": cid, "actor": actor})
        assert r.status_code == 200
        lines = r.text.strip().splitlines()
        assert len(lines) == 2 and "sla_policy_change" in lines[1]  # header + the fleet row


async def test_finding_rows_are_decorated_with_their_identity(env) -> None:
    # M9d rework (operator): an opaque finding_key answers nothing — rows carry the finding's
    # (cve, image, scanner) at read time; a finding aged out of the store degrades gracefully
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    fk = f"fk-{cid}-0"
    await client.index(
        index="findings",
        id=fk,
        body={
            "finding_key": fk,
            "cluster_id": cid,
            "cve_id": "CVE-2024-0001",
            "image_repo": "bench/app",
            "image_digest": "sha256:aa00",
            "scanner": "trivy",
            "package_name": "openssl",
            "severity_canonical": "high",
        },
        params={"refresh": "true"},
    )
    deco_actor = f"u-deco-{uuid.uuid4().hex[:8]}"
    await _journal(client, cid, n=2, actor=deco_actor)  # row 0 → the doc; row 1 → no finding doc

    r = await http.get(
        "/api/v1/audit", params={"cluster_id": cid, "order": "asc", "actor": deco_actor}
    )
    rows = {row["entity_id"]: row for row in r.json()["data"]}
    deco = rows[fk]["finding"]
    assert deco["cve_id"] == "CVE-2024-0001"
    assert deco["image_repo"] == "bench/app"
    assert deco["scanner"] == "trivy"
    assert rows[f"fk-{cid}-1"]["finding"] is None  # aged out — the bare key stays accurate


async def test_decoration_never_crosses_the_tenant_boundary(env) -> None:
    # the mget path bypasses tenant_query — the cluster check must happen per doc (SEC-4)
    http, client = env
    cid, other = (f"c-audit-{uuid.uuid4().hex[:8]}" for _ in range(2))
    fk = f"fk-{cid}-0"
    await client.index(
        index="findings",
        id=fk,
        body={"finding_key": fk, "cluster_id": other, "cve_id": "CVE-LEAK", "scanner": "trivy"},
        params={"refresh": "true"},
    )
    leak_actor = f"u-leak-{uuid.uuid4().hex[:8]}"
    await _journal(client, cid, n=1, actor=leak_actor)
    r = await http.get("/api/v1/audit", params={"cluster_id": cid, "actor": leak_actor})
    assert r.json()["data"][0]["finding"] is None  # same key, other tenant's doc — no leak


async def test_facets_activity_histogram_buckets_the_window(env) -> None:
    # M9d lens: audit events over time under the current lens — server-side date_histogram
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    hist_actor = f"u-hist-{uuid.uuid4().hex[:8]}"
    await _journal(client, cid, n=3, actor=hist_actor)

    r = await http.get(
        "/api/v1/audit/facets",
        params={"cluster_id": cid, "interval": "day", "window_days": 7, "actor": hist_actor},
    )
    assert r.status_code == 200
    body = r.json()
    activity = body["activity"]
    assert sum(b["count"] for b in activity) == 3  # today's bucket holds the three rows
    assert len(activity) >= 7  # extended_bounds: quiet days render as zero bars, not gaps
    assert all(set(b) == {"date", "count"} for b in activity)

    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid, "interval": "week"})
    assert r.status_code == 422  # not day|hour
    # no interval → facets only, no activity key (the read stays cheap for the rail)
    r = await http.get("/api/v1/audit/facets", params={"cluster_id": cid})
    assert "activity" not in r.json()


async def test_export_csv_streams_decorated_sanitized_rows(env, monkeypatch) -> None:
    # M9d (operator): the prototype's Export CSV — same lens, injection-sanitized, decorated
    http, client = env
    cid = f"c-audit-{uuid.uuid4().hex[:8]}"
    fk = f"fk-{cid}-0"
    await client.index(
        index="findings",
        id=fk,
        body={
            "finding_key": fk,
            "cluster_id": cid,
            "cve_id": "CVE-2024-0002",
            "image_repo": "bench/app",
            "scanner": "grype",
        },
        params={"refresh": "true"},
    )
    await append_field_change(
        client,
        actor="u-csv-actor",
        action="note",
        entity_type="finding",
        entity_id=fk,
        field="notes",
        old_value=None,
        new_value="=HYPERLINK() would arm in a spreadsheet",
        revision=1,
        cluster_id=cid,
        finding_key=fk,
    )
    await client.indices.refresh(index="system-audit-log-*")

    r = await http.get(
        "/api/v1/audit/export.csv", params={"cluster_id": cid, "actor": "u-csv-actor"}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    header, row = lines[0], lines[1]
    assert header.split(",")[:4] == ["@timestamp", "actor", "action", "entity_type"]
    assert "CVE-2024-0002" in row and "bench/app" in row  # decoration rides the export
    assert "'=HYPERLINK" in row  # CSV-injection neutralized

    await _journal(client, cid, n=2, actor="u-csv-actor")  # lens now holds 3 rows
    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "1")
    get_settings.cache_clear()
    r = await http.get(
        "/api/v1/audit/export.csv", params={"cluster_id": cid, "actor": "u-csv-actor"}
    )
    assert r.status_code == 413  # over the cap → clean reject before any stream


async def test_failed_decorate_on_a_nonfinal_page_reclaims_the_opened_pit(monkeypatch) -> None:
    """decorate_rows runs after the search call's reclaim guard — a failure there on a
    NON-final page must still delete the PIT this call opened, or it leaks until keep_alive
    (issue 509 sweep). A final page has already deleted it; a cursor PIT stays the client's."""
    from backend.query import audit as audit_module

    class _Stub:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def create_pit(self, *a: Any, **kw: Any) -> dict[str, Any]:
            return {"pit_id": "pit-1"}

        async def delete_pit(self, body: dict[str, Any]) -> dict[str, Any]:
            self.deleted += body["pit_id"]
            return {}

        async def search(self, **kw: Any) -> dict[str, Any]:
            hits = [
                {"_source": {"action": "login", "event_id": f"e{i}"}, "sort": [i, f"e{i}"]}
                for i in range(2)
            ]
            return {"hits": {"total": {"value": 5, "relation": "eq"}, "hits": hits}}

    async def boom(*a: Any, **kw: Any) -> None:
        raise RuntimeError("decorate exploded")

    monkeypatch.setattr(audit_module, "decorate_rows", boom)
    stub = _Stub()
    with pytest.raises(RuntimeError, match="decorate exploded"):
        await audit_module.run_audit_search(
            stub,  # type: ignore[arg-type]
            cluster_id="c-unit-audit",
            filters=AuditFilters(),
            size=2,
            account_events=False,
            dashboard_events=False,
        )
    assert stub.deleted == ["pit-1"]


async def _session_with(client: AsyncOpenSearch, capabilities: list[str]) -> httpx.AsyncClient:
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
            "role": "custom",
            "capabilities": capabilities,
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
    return http


async def test_account_events_need_can_manage_users(env) -> None:
    """issue 892 ruling 3: the sign-ins, password, user, role and token events (entity_type
    `user` and `token`) reach only `can_manage_users`, in the list, the rail facets and the CSV
    alike. The other fleet rows stay open to every session."""
    viewer, client = env
    actor = f"u-acct-{uuid.uuid4().hex[:8]}"
    for action, entity_type in (("login", "user"), ("token_mint", "token"), ("job_trigger", "job")):
        await append_auth_event(
            client,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=f"{entity_type}:{actor}",
            strict=True,
        )
    await client.indices.refresh(index="system-audit-log-*")
    params = {"cluster_id": f"c-audit-{uuid.uuid4().hex[:8]}", "actor": actor}

    async def seen(http: httpx.AsyncClient) -> tuple[list[str], set[str], int]:
        rows = (await http.get("/api/v1/audit", params=params)).json()["data"]
        facets = (await http.get("/api/v1/audit/facets", params=params)).json()["facets"]
        csv = (await http.get("/api/v1/audit/export.csv", params=params)).text
        return (
            sorted(row["action"] for row in rows),
            {b["key"] for b in facets["entity_type"]},
            len(csv.strip().splitlines()) - 1,  # minus the header
        )

    assert await seen(viewer) == (["job_trigger"], {"job"}, 1)
    manager = await _session_with(client, ["can_manage_users", "can_export"])
    try:
        assert await seen(manager) == (
            ["job_trigger", "login", "token_mint"],
            {"job", "token", "user"},
            3,
        )
    finally:
        await manager.aclose()
