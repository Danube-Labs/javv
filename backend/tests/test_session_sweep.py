"""Session sweep (issue 532): `system-sessions` rows whose `expires_at` is older than
`now - grace` are deleted — the third sanctioned `delete_by_query` site. Everything a lookup could
still accept, and every expiry inside the grace, survives. Each run journals one audit row the
Audit screen can show. Real OpenSearch, prefix-isolated, with a frozen `NOW` passed to the job so
no seeded date can drift across the cutoff between seeding and sweeping (issue 533)."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.audit.writer import ALIAS as AUDIT_ALIAS
from backend.auth.sessions import INDEX as SESSIONS_INDEX
from backend.core.settings import get_settings
from backend.jobs.session_sweep import sweep_sessions
from backend.query.audit import audit_tenant_query
from os_env import requires_opensearch

pytestmark = requires_opensearch

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
GRACE = 24.0


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _seed(client, prefix: str, sid: str, *, expires_in_hours: float, revoked=False) -> None:
    await client.index(
        index=f"{prefix}{SESSIONS_INDEX}",
        id=sid,
        body={
            "session_id": sid,
            "user_id": "u-sweep",
            "created_at": (NOW - timedelta(hours=48)).isoformat(),
            "expires_at": (NOW + timedelta(hours=expires_in_hours)).isoformat(),
            "revoked": revoked,
        },
        params={"refresh": "true"},
    )


async def _ids(client, prefix: str) -> set[str]:
    index = f"{prefix}{SESSIONS_INDEX}"
    await client.indices.refresh(index=index)
    resp = await client.search(index=index, body={"size": 100, "query": {"match_all": {}}})
    return {h["_id"] for h in resp["hits"]["hits"]}


async def _run_rows(client, prefix: str) -> list[dict]:
    await client.indices.refresh(index=f"{prefix}{AUDIT_ALIAS}*")
    resp = await client.search(
        index=f"{prefix}{AUDIT_ALIAS}*",
        body={"size": 10, "query": {"term": {"action": "session_sweep_run"}}},
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


async def test_only_rows_expired_past_the_grace_are_deleted(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, "expired-long", expires_in_hours=-(GRACE + 1))
    await _seed(client, prefix, "revoked-expired-long", expires_in_hours=-(GRACE + 1), revoked=True)
    await _seed(client, prefix, "live", expires_in_hours=5)
    await _seed(client, prefix, "expired-inside-grace", expires_in_hours=-(GRACE - 1))
    # revoked but not yet expired: refused on lookup, but its TTL hasn't run — it waits its turn
    await _seed(client, prefix, "revoked-live", expires_in_hours=5, revoked=True)

    counts = await sweep_sessions(client, now=NOW, grace_hours=GRACE, prefix=prefix)

    assert counts == {"sessions_deleted": 2}
    assert await _ids(client, prefix) == {"live", "expired-inside-grace", "revoked-live"}


async def test_a_second_run_deletes_nothing(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, "expired-long", expires_in_hours=-(GRACE + 1))

    assert (await sweep_sessions(client, now=NOW, grace_hours=GRACE, prefix=prefix)) == {
        "sessions_deleted": 1
    }
    assert (await sweep_sessions(client, now=NOW, grace_hours=GRACE, prefix=prefix)) == {
        "sessions_deleted": 0
    }


async def test_the_grace_defaults_to_the_setting(real_os, monkeypatch) -> None:
    client, prefix = real_os
    monkeypatch.setenv("JAVV_SESSION_SWEEP_GRACE_HOURS", "2")
    await _seed(client, prefix, "expired-3h", expires_in_hours=-3)
    await _seed(client, prefix, "expired-1h", expires_in_hours=-1)

    await sweep_sessions(client, now=NOW, prefix=prefix)

    assert await _ids(client, prefix) == {"expired-1h"}


async def test_each_run_journals_its_counts_where_the_audit_screen_can_see_them(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, "expired-long", expires_in_hours=-(GRACE + 1))

    await sweep_sessions(client, now=NOW, grace_hours=GRACE, prefix=prefix)
    # a run that deletes nothing still journals, so the screen shows the sweep is alive
    await sweep_sessions(client, now=NOW, grace_hours=GRACE, prefix=prefix)

    rows = await _run_rows(client, prefix)
    assert len(rows) == 2
    assert all(r["actor"] == "session-sweep-job" and r["entity_type"] == "job" for r in rows)
    assert sorted(r["new_value_json"]["sessions_deleted"] for r in rows) == [0, 1]
    assert all(r["new_value_json"]["grace_hours"] == GRACE for r in rows)

    # fleet-wide rows are written with no cluster_id (issue 559); "fleet" is a legacy spelling
    assert all(r.get("cluster_id") is None for r in rows)
    # and the Audit screen, which reads through audit_tenant_query, returns them for any cluster
    body = audit_tenant_query(
        "0f0e6c4e-0000-4000-8000-000000000000",
        {"size": 10, "query": {"bool": {"filter": [{"term": {"action": "session_sweep_run"}}]}}},
        account_events=False,  # a job row, not an account event: every session sees it
    )
    visible = await client.search(index=f"{prefix}{AUDIT_ALIAS}*", body=body)
    assert len(visible["hits"]["hits"]) == 2


def test_the_sweep_has_exactly_one_bounded_delete() -> None:
    """The sanctioned exception is ONE `delete_by_query`, bounded by the expiry range — never a
    match-all, and never a whole-index drop."""
    import inspect

    from backend.jobs import session_sweep

    source = inspect.getsource(session_sweep)
    assert source.count("delete_by_query(") == 1
    assert "match_all" not in source
    assert "indices.delete(" not in source
