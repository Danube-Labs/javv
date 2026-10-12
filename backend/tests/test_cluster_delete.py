"""Deleting a retired cluster (issue 765): `DELETE /api/v1/clusters/{cluster_id}`.

Contract pins: the delete leaves nothing of the cluster in any index JAVV writes but the audit
log; the other cluster is untouched byte for byte, even when the two ids are prefixes of each
other, and an index auto-created under the alias's own name goes too; a retry after a delete that
stopped halfway finishes it, through the route as well (503, then 200), for a cluster that only
its retirement record still names; the store away answers 503, a bug stays 500; the route
refuses a cluster that is not retired (409) or unknown (404), and journals before it deletes.
A delete marks its start before the tokens go (issue 778): while the mark stands, bringing the
cluster back is refused and the listing says so. A finished delete keeps it as a tombstone, and
the nightly sweep re-runs the data part of the delete for a cluster nothing names any more,
removing rows a push in flight wrote after the delete, until a second pass finds nothing; a
cluster onboarded again keeps its data and loses the tombstone.
The 401/403 axes live in the RBAC/IDOR suite."""

import gzip
import json
import uuid
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError
from opensearchpy.exceptions import ConnectionTimeout, RequestError
from prometheus_client import REGISTRY

from backend.admin import cluster_delete
from backend.admin import cluster_retirement as retirement_admin
from backend.admin.cluster_delete import (
    SHARED_INDICES,
    delete_cluster,
    delete_marker_id,
    deletes_started,
    recheck_deleted,
)
from backend.admin.cluster_registry import read_registry, set_registry_name
from backend.admin.cluster_retirement import (
    DeleteUnderway,
    read_retirements,
    retire_cluster,
    retirement_doc_id,
    unretire_cluster,
)
from backend.auth.passwords import hash_password
from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings
from backend.jobs import cluster_retirement
from backend.jobs.cluster_retirement import run_retirement_sweep
from backend.jobs.lifecycle import SERIES
from backend.main import create_app
from backend.reports.models import NOTIFICATIONS_INDEX, REPORT_CHUNKS_INDEX, REPORTS_INDEX
from backend.routers import clusters as clusters_router
from os_env import OS_URL, requires_opensearch

pytestmark = requires_opensearch

GONE = "c-del-abcdefgh"
KEPT = "c-del-abcdefgh-1234"  # GONE is a prefix of it: a wildcard on GONE would match KEPT
GOLDEN_ENVELOPE = Path(__file__).parent / "fixtures/envelope-trivy-golden.json"
CONFIG_KINDS = ("staleness", "lifecycle", "findings_cleanup", "retirement", "retirement-warned")


async def _put(client: AsyncOpenSearch, index: str, doc_id: str, body: dict[str, Any]) -> None:
    await client.index(index=index, id=doc_id, body=body, params={"refresh": "true"})


async def _seed(client: AsyncOpenSearch, prefix: str, cid: str) -> None:
    """One of everything JAVV keeps per cluster."""
    p = prefix
    await _put(
        client,
        f"{p}system-tokens",
        f"tok-{cid}",
        {"token_hash": f"h-{cid}", "cluster_id": cid, "scanner": "trivy", "disabled": False},
    )
    for series in SERIES:
        await _put(client, f"{p}{series}-{cid}-000001", f"h-{cid}", {"cluster_id": cid})
    for index in SHARED_INDICES:
        await _put(client, f"{p}{index}", f"{index}-{cid}", {"cluster_id": cid})
    await _put(
        client, f"{p}{REPORTS_INDEX}", f"r-{cid}", {"report_id": f"r-{cid}", "cluster_id": cid}
    )
    await _put(
        client, f"{p}{REPORT_CHUNKS_INDEX}", f"r-{cid}-0", {"report_id": f"r-{cid}", "seq": 0}
    )
    for doc_id in [f"scan_scope:{cid}"] + [f"{k}:{cid}" for k in CONFIG_KINDS]:
        await _put(client, f"{p}system-config", doc_id, {"key": doc_id, "value": {}})
    await set_registry_name(client, cid, f"name of {cid}", actor="t", prefix=prefix)


async def _snapshot(client: AsyncOpenSearch, prefix: str, cid: str) -> dict[str, Any]:
    """Every doc the cluster owns, by index and id, with its source."""
    shot: dict[str, Any] = {}
    indices = [f"{prefix}system-tokens", f"{prefix}{REPORTS_INDEX}"] + [
        f"{prefix}{i}" for i in SHARED_INDICES
    ]
    indices += [f"{prefix}{s}-{cid}-000001" for s in SERIES]
    for index in indices:
        resp = await client.search(
            index=index,
            body={"size": 100, "query": {"term": {"cluster_id": cid}}},
            params={"ignore_unavailable": "true"},
        )
        for hit in resp["hits"]["hits"]:
            shot[f"{hit['_index']}/{hit['_id']}"] = hit["_source"]
    chunk = await client.get(index=f"{prefix}{REPORT_CHUNKS_INDEX}", id=f"r-{cid}-0")
    shot["chunk"] = chunk["_source"]
    for doc_id in [f"scan_scope:{cid}"] + [f"{k}:{cid}" for k in CONFIG_KINDS]:
        shot[doc_id] = (await client.get(index=f"{prefix}system-config", id=doc_id))["_source"]
    shot["name"] = (await read_registry(client, prefix=prefix)).get(cid)
    return shot


async def _left(client: AsyncOpenSearch, prefix: str, cid: str) -> list[str]:
    """Whatever of the cluster is still there, outside the audit log."""
    left: list[str] = []
    for index in ["system-tokens", REPORTS_INDEX, *SHARED_INDICES]:
        n = (
            await client.count(
                index=f"{prefix}{index}", body={"query": {"term": {"cluster_id": cid}}}
            )
        )["count"]
        if n:
            left.append(f"{index}: {n}")
    for series in SERIES:
        if await client.indices.exists(index=f"{prefix}{series}-{cid}-000001"):
            left.append(f"{series} index")
    if await client.exists(index=f"{prefix}{REPORT_CHUNKS_INDEX}", id=f"r-{cid}-0"):
        left.append("report chunk")
    for doc_id in [f"scan_scope:{cid}", f"cluster-retirement:{cid}"] + [
        f"{k}:{cid}" for k in CONFIG_KINDS
    ]:
        if await client.exists(index=f"{prefix}system-config", id=doc_id):
            left.append(doc_id)
    if cid in await read_registry(client, prefix=prefix):
        left.append("registry name")
    return left


async def test_a_delete_leaves_nothing_and_the_other_cluster_byte_for_byte(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await _seed(client, prefix, KEPT)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    # a write to the alias that landed while the series was gone: a concrete index under the
    # alias's own name, for each cluster
    stray = {cid: f"{prefix}{SERIES[0]}-{cid}" for cid in (GONE, KEPT)}
    for cid, name in stray.items():
        await _put(client, name, f"s-{cid}", {"cluster_id": cid})
    before = await _snapshot(client, prefix, KEPT)

    counts = await delete_cluster(client, GONE, actor="t", prefix=prefix)

    assert await _left(client, prefix, GONE) == []
    assert not await client.indices.exists(index=stray[GONE])
    assert await client.indices.exists(index=stray[KEPT])
    assert await _snapshot(client, prefix, KEPT) == before
    assert counts["history_indices"] == len(SERIES) + 1
    assert counts["tokens"] == 1 and counts["findings"] == 1
    assert counts[REPORTS_INDEX] == 1 and counts[REPORT_CHUNKS_INDEX] == 1
    assert counts[NOTIFICATIONS_INDEX] == 1


async def test_the_audit_log_keeps_the_cluster_and_records_the_delete(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)

    await delete_cluster(client, GONE, actor="the-admin", prefix=prefix)

    await client.indices.refresh(index=f"{prefix}system-audit-log-*")
    rows = await client.search(
        index=f"{prefix}system-audit-log-*",
        body={"size": 20, "query": {"term": {"cluster_id": GONE}}},
    )
    actions = {h["_source"]["action"] for h in rows["hits"]["hits"]}
    assert {"cluster_retire", "cluster_delete"} <= actions


async def test_a_delete_that_stopped_halfway_is_finished_by_a_retry(real_os, monkeypatch) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)

    async def contended(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(cluster_delete, "set_registry_name", contended)
    with pytest.raises(cluster_delete.DeleteIncomplete):
        await delete_cluster(client, GONE, actor="t", prefix=prefix)
    # the tokens and the data went; the retirement record stayed, so it still reads as retired
    assert GONE in await read_retirements(client, prefix=prefix)
    assert "registry name" in await _left(client, prefix, GONE)

    monkeypatch.undo()
    await delete_cluster(client, GONE, actor="t", prefix=prefix)
    assert await _left(client, prefix, GONE) == []


async def test_a_delete_marks_its_start_before_the_tokens_go(real_os, monkeypatch) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await _seed(client, prefix, KEPT)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    seen: list[bool] = []
    real_delete_rows = cluster_delete._delete_rows

    async def tokens_step(client_: Any, index: str, query: dict[str, Any]) -> int:
        if index.endswith("system-tokens"):  # the first step: the mark must already stand
            seen.append(GONE in await deletes_started(client, prefix=prefix))
        return await real_delete_rows(client_, index, query)

    async def stopped(*_args: Any, **_kwargs: Any) -> list[str]:
        raise cluster_delete.DeleteIncomplete("stopped after the tokens")

    monkeypatch.setattr(cluster_delete, "_delete_rows", tokens_step)
    monkeypatch.setattr(cluster_delete, "_history_indices", stopped)
    with pytest.raises(cluster_delete.DeleteIncomplete):
        await delete_cluster(client, GONE, actor="the-admin", prefix=prefix)

    assert seen == [True]
    assert await deletes_started(client, prefix=prefix) == {GONE}  # kept: the delete stopped
    mark = await client.get(index=f"{prefix}system-config", id=delete_marker_id(GONE))
    assert mark["_source"]["value"]["by"] == "the-admin"
    # a retry that stops again keeps the first start and who made it
    with pytest.raises(cluster_delete.DeleteIncomplete):
        await delete_cluster(client, GONE, actor="someone-else", prefix=prefix)
    again = await client.get(index=f"{prefix}system-config", id=delete_marker_id(GONE))
    assert again["_source"]["value"] == mark["_source"]["value"]

    monkeypatch.undo()
    await delete_cluster(client, GONE, actor="t", prefix=prefix)
    assert await deletes_started(client, prefix=prefix) == set()
    # kept as a tombstone, finished, for the next sweep's pass
    tomb = await client.get(index=f"{prefix}system-config", id=delete_marker_id(GONE))
    assert tomb["_source"]["value"]["finished_at"]


async def test_a_second_delete_of_the_same_id_starts_its_own_marker(real_os, monkeypatch) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    await delete_cluster(client, GONE, actor="t", prefix=prefix)
    await recheck_deleted(client, prefix=prefix)  # one clean pass: `rechecked_at` on the tombstone
    # onboarded again under the same id before the tombstone went, retired, and deleted again
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)

    async def stopped(*_args: Any, **_kwargs: Any) -> list[str]:
        raise cluster_delete.DeleteIncomplete("stopped after the tokens")

    monkeypatch.setattr(cluster_delete, "_history_indices", stopped)
    with pytest.raises(cluster_delete.DeleteIncomplete):
        await delete_cluster(client, GONE, actor="second-admin", prefix=prefix)

    # the half-deleted cluster reads as such: bringing it back stays refused
    assert await deletes_started(client, prefix=prefix) == {GONE}
    mark = (await client.get(index=f"{prefix}system-config", id=delete_marker_id(GONE)))["_source"]
    assert mark["value"]["by"] == "second-admin"
    assert "finished_at" not in mark["value"] and "rechecked_at" not in mark["value"]

    monkeypatch.undo()
    await delete_cluster(client, GONE, actor="second-admin", prefix=prefix)
    # a fresh tombstone: two clean passes before it goes, as for any delete
    assert (await recheck_deleted(client, prefix=prefix))["dropped"] == 0
    assert await _tombstoned(client, prefix, GONE)
    assert (await recheck_deleted(client, prefix=prefix))["dropped"] == 1


async def test_the_marker_outlives_the_retirement_record(real_os, monkeypatch) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    real_delete = client.delete

    async def record_step_fails(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("id") == retirement_doc_id(GONE):
            raise cluster_delete.DeleteIncomplete("stopped at the retirement record")
        return await real_delete(*args, **kwargs)

    monkeypatch.setattr(client, "delete", record_step_fails)
    with pytest.raises(cluster_delete.DeleteIncomplete):
        await delete_cluster(client, GONE, actor="t", prefix=prefix)
    assert GONE in await read_retirements(client, prefix=prefix)
    assert await deletes_started(client, prefix=prefix) == {GONE}


async def test_a_bring_back_that_lands_first_stops_the_delete(real_os, monkeypatch) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    real_mark = cluster_delete._mark_started

    async def bring_back_first(*args: Any, **kwargs: Any) -> Any:
        # an admin brought it back after this delete read the record, before its mark
        assert await unretire_cluster(client, GONE, actor="other-admin", prefix=prefix)
        return await real_mark(*args, **kwargs)

    monkeypatch.setattr(cluster_delete, "_mark_started", bring_back_first)
    with pytest.raises(cluster_delete.NotRetired):
        await delete_cluster(client, GONE, actor="t", prefix=prefix)

    assert not await _tombstoned(client, prefix, GONE)  # its own marker went with it
    assert await client.exists(index=f"{prefix}findings", id=f"findings-{GONE}")
    assert (await read_retirements(client, prefix=prefix))[GONE].returned_at is not None


async def test_a_delete_that_lands_first_stops_the_bring_back(real_os, monkeypatch) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    real_journal = retirement_admin.append_field_change

    async def stopped(*_args: Any, **_kwargs: Any) -> list[str]:
        raise cluster_delete.DeleteIncomplete("stopped after the tokens")

    async def delete_in_between(*args: Any, **kwargs: Any) -> Any:
        # the bring back has read the record and found no marker; a delete starts now
        with pytest.raises(cluster_delete.DeleteIncomplete):
            await delete_cluster(client, GONE, actor="t", prefix=prefix)
        return await real_journal(*args, **kwargs)

    monkeypatch.setattr(cluster_delete, "_history_indices", stopped)
    monkeypatch.setattr(retirement_admin, "append_field_change", delete_in_between)
    with pytest.raises(DeleteUnderway):
        await unretire_cluster(client, GONE, actor="other-admin", prefix=prefix)

    assert (await read_retirements(client, prefix=prefix))[GONE].returned_at is None
    assert await deletes_started(client, prefix=prefix) == {GONE}


class _ConflictsOnce:
    """A store whose first delete pass hits a doc updated since the last refresh."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.indices = self

    async def delete_by_query(self, **_kw: Any) -> dict[str, int]:
        self.calls.append("delete")
        conflicted = self.calls.count("refresh") == 0
        return {"deleted": 0 if conflicted else 1, "version_conflicts": 1 if conflicted else 0}

    async def refresh(self, **_kw: Any) -> dict[str, Any]:
        self.calls.append("refresh")
        return {}


async def test_a_pass_that_conflicts_refreshes_before_the_next() -> None:
    store = _ConflictsOnce()
    deleted = await cluster_delete._delete_rows(
        cast(Any, store), "system-tokens", {"term": {"cluster_id": GONE}}
    )
    assert deleted == 1
    assert store.calls == ["delete", "refresh", "delete"]


def _leftovers() -> float:
    return REGISTRY.get_sample_value("javv_cluster_delete_leftovers_total") or 0.0


async def _late_push(client: AsyncOpenSearch, prefix: str, cid: str) -> None:
    """What a push already past its token check writes after the delete's passes."""
    await _put(client, f"{prefix}findings", f"late-{cid}", {"cluster_id": cid})
    await _put(client, f"{prefix}{SERIES[0]}-{cid}-000001", f"late-{cid}", {"cluster_id": cid})


async def _tombstoned(client: AsyncOpenSearch, prefix: str, cid: str) -> bool:
    return bool(await client.exists(index=f"{prefix}system-config", id=delete_marker_id(cid)))


async def test_the_next_pass_removes_what_a_late_push_left(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await _seed(client, prefix, KEPT)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    await delete_cluster(client, GONE, actor="t", prefix=prefix)
    await _late_push(client, prefix, GONE)
    before, kept = _leftovers(), await _snapshot(client, prefix, KEPT)

    first = await recheck_deleted(client, prefix=prefix)

    assert first == {"rechecked": 1, "with_leftovers": 1, "dropped": 0}
    assert _leftovers() == before + 1
    assert await _left(client, prefix, GONE) == []
    assert await _snapshot(client, prefix, KEPT) == kept
    assert await _tombstoned(client, prefix, GONE)  # one more clean pass before it goes
    second = await recheck_deleted(client, prefix=prefix)
    assert second == {"rechecked": 1, "with_leftovers": 0, "dropped": 1}
    assert not await _tombstoned(client, prefix, GONE)


async def test_a_cluster_onboarded_again_keeps_its_data(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    await delete_cluster(client, GONE, actor="t", prefix=prefix)
    # a new token for the same id, and its first scan
    await _put(
        client,
        f"{prefix}system-tokens",
        f"tok-new-{GONE}",
        {"token_hash": "h-new", "cluster_id": GONE, "scanner": "trivy", "disabled": False},
    )
    await _put(client, f"{prefix}findings", f"new-{GONE}", {"cluster_id": GONE})

    assert await recheck_deleted(client, prefix=prefix) == {
        "rechecked": 0,
        "with_leftovers": 0,
        "dropped": 1,
    }
    assert await client.exists(index=f"{prefix}findings", id=f"new-{GONE}")
    assert not await _tombstoned(client, prefix, GONE)


async def test_a_stray_marker_for_a_cluster_nothing_names_is_cleared(real_os) -> None:
    client, prefix = real_os
    stray = "c-del-stray0001"  # a delete that stopped between its last two steps
    await _put(
        client,
        f"{prefix}system-config",
        delete_marker_id(stray),
        {"key": delete_marker_id(stray), "cluster_id": stray, "value": {"started_at": "x"}},
    )
    await recheck_deleted(client, prefix=prefix)
    assert await _tombstoned(client, prefix, stray)  # a clean pass, then one more
    await recheck_deleted(client, prefix=prefix)
    assert not await _tombstoned(client, prefix, stray)


async def test_a_delete_still_running_is_left_alone(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    await _put(
        client,
        f"{prefix}system-config",
        delete_marker_id(GONE),
        {"key": delete_marker_id(GONE), "cluster_id": GONE, "value": {"started_at": "x"}},
    )
    # its retirement record still names it: the delete (or its retry) owns it
    assert (await recheck_deleted(client, prefix=prefix))["rechecked"] == 0
    assert await client.exists(index=f"{prefix}findings", id=f"findings-{GONE}")
    assert await deletes_started(client, prefix=prefix) == {GONE}


async def test_the_retirement_sweep_runs_the_pass(real_os) -> None:
    client, prefix = real_os
    await _seed(client, prefix, GONE)
    await retire_cluster(client, GONE, actor="t", mode="manual", prefix=prefix)
    await delete_cluster(client, GONE, actor="t", prefix=prefix)
    await _late_push(client, prefix, GONE)

    counts = await run_retirement_sweep(client, prefix=prefix)

    assert counts["delete_rechecked"] == 1
    assert await _left(client, prefix, GONE) == []


async def test_a_failed_pass_does_not_fail_the_sweep(real_os, monkeypatch) -> None:
    client, prefix = real_os

    async def store_away(*_args: Any, **_kwargs: Any) -> dict[str, int]:
        raise RuntimeError("store away")

    monkeypatch.setattr(cluster_retirement, "recheck_deleted", store_away)
    before = REGISTRY.get_sample_value("javv_cluster_delete_recheck_failures_total") or 0.0

    counts = await run_retirement_sweep(client, prefix=prefix)

    assert counts["delete_rechecked"] == 0
    after = REGISTRY.get_sample_value("javv_cluster_delete_recheck_failures_total") or 0.0
    assert after == before + 1


# --- the route --------------------------------------------------------------------------------


PASSWORD = "cluster-delete-password"


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
            "capabilities": ["can_manage_retention", "can_manage_settings"],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-10-07T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    yield http, client
    await http.aclose()
    await client.close()


async def _route_cluster(client: AsyncOpenSearch) -> str:
    cid = f"c-delr-{uuid.uuid4().hex[:8]}"
    await _put(
        client,
        "system-tokens",
        f"tok-{cid}",
        {"token_hash": uuid.uuid4().hex, "cluster_id": cid, "scanner": "trivy", "disabled": False},
    )
    return cid


async def test_the_route_refuses_a_cluster_that_is_not_retired_or_unknown(env) -> None:
    http, client = env
    cid = await _route_cluster(client)
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 409
    assert await client.exists(index="system-tokens", id=f"tok-{cid}")  # nothing deleted
    assert (await http.delete("/api/v1/clusters/c-delr-unknown1")).status_code == 404
    assert (await http.delete("/api/v1/clusters/BAD_ID")).status_code == 422


async def test_the_route_deletes_a_retired_cluster_and_it_leaves_every_listing(env) -> None:
    http, client = env
    cid = await _route_cluster(client)
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 200

    r = await http.delete(f"/api/v1/clusters/{cid}")

    assert r.status_code == 200
    assert r.json()["cluster_id"] == cid and r.json()["deleted"]["tokens"] == 1
    with pytest.raises(NotFoundError):  # an ingest with its old token now finds none: 401
        await client.get(index="system-tokens", id=f"tok-{cid}")
    listed = await http.get("/api/v1/clusters", params={"include_retired": "true"})
    assert cid not in {c["cluster_id"] for c in listed.json()["clusters"]}
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 404


def _incomplete() -> float:
    return REGISTRY.get_sample_value("javv_cluster_delete_incomplete_total") or 0.0


async def test_the_route_finishes_a_delete_that_stopped_halfway(env, monkeypatch) -> None:
    http, client = env
    cid = await _route_cluster(client)  # never renamed: no registry name
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 200
    before = _incomplete()

    async def stopped(*_args: Any, **_kwargs: Any) -> list[str]:
        raise cluster_delete.DeleteIncomplete("stopped after the tokens")

    monkeypatch.setattr(cluster_delete, "_history_indices", stopped)
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 503
    assert _incomplete() == before + 1
    # its tokens are gone and it has no name: only its retirement record still names it
    with pytest.raises(NotFoundError):
        await client.get(index="system-tokens", id=f"tok-{cid}")
    listed = await http.get("/api/v1/clusters", params={"include_retired": "true"})
    assert cid in {c["cluster_id"] for c in listed.json()["clusters"]}

    monkeypatch.undo()
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 200
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 404


async def test_the_store_away_answers_503_and_a_bug_stays_500(env, monkeypatch) -> None:
    http, client = env
    cid = await _route_cluster(client)
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 200

    async def timed_out(*_args: Any, **_kwargs: Any) -> list[str]:
        raise ConnectionTimeout("TIMEOUT", "read timed out", None)

    monkeypatch.setattr(cluster_delete, "_history_indices", timed_out)
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 503

    async def malformed(*_args: Any, **_kwargs: Any) -> list[str]:
        raise RequestError(400, "parsing_exception", None)

    monkeypatch.setattr(cluster_delete, "_history_indices", malformed)
    with pytest.raises(RequestError):  # unhandled: the app's 500, not a "retry it" 503
        await http.delete(f"/api/v1/clusters/{cid}")


async def test_bring_back_is_refused_once_a_delete_has_started(env, monkeypatch) -> None:
    http, client = env
    cid = await _route_cluster(client)
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 200
    listed = await http.get("/api/v1/clusters", params={"include_retired": "true"})
    row = {c["cluster_id"]: c for c in listed.json()["clusters"]}[cid]
    assert row["delete_started"] is False

    async def stopped(*_args: Any, **_kwargs: Any) -> list[str]:
        raise cluster_delete.DeleteIncomplete("stopped after the tokens")

    monkeypatch.setattr(cluster_delete, "_history_indices", stopped)
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 503

    r = await http.post(f"/api/v1/clusters/{cid}/unretire")
    assert r.status_code == 409
    assert r.json()["title"] == "its delete did not finish: delete it again"
    assert cid in await read_retirements(client)  # still retired, nothing stamped
    assert (await read_retirements(client))[cid].returned_at is None
    listed = await http.get("/api/v1/clusters", params={"include_retired": "true"})
    row = {c["cluster_id"]: c for c in listed.json()["clusters"]}[cid]
    assert (row["retired"], row["delete_started"]) == (True, True)

    monkeypatch.undo()
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 200
    assert (await http.post(f"/api/v1/clusters/{cid}/unretire")).status_code == 404


async def test_a_delete_that_lost_to_a_bring_back_answers_409(env, monkeypatch) -> None:
    http, client = env
    cid = await _route_cluster(client)
    assert (await http.post(f"/api/v1/clusters/{cid}/retire")).status_code == 200

    async def lost(*_args: Any, **_kwargs: Any) -> dict[str, int]:
        raise cluster_delete.NotRetired

    monkeypatch.setattr(clusters_router, "delete_cluster", lost)
    r = await http.delete(f"/api/v1/clusters/{cid}")
    assert (r.status_code, r.json()["title"]) == (409, "cluster is not retired")


async def test_a_push_after_the_delete_gets_401_and_writes_nothing(env) -> None:
    """Issue 787 item 3, closed by this: once the delete took the tokens, a scanner still
    pushing cannot write, so nothing is left behind for the next-night pass to miss."""
    http, client = env
    cid = f"c-delr-{uuid.uuid4().hex[:8]}"
    raw = mint_token()
    await _put(
        client,
        "system-tokens",
        f"tok-{cid}",
        {
            "token_hash": hash_token(raw, pepper=get_settings().secret_key),
            "cluster_id": cid,
            "scanner": "trivy",
            "disabled": False,
        },
    )
    envelope = json.loads(GOLDEN_ENVELOPE.read_text()) | {"cluster_id": cid}

    async def push() -> int:
        r = await http.post(
            "/api/v1/ingest/scan",
            content=gzip.compress(json.dumps(envelope).encode()),
            headers={
                "Authorization": f"Bearer {raw}",
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        )
        return r.status_code

    # the control: this token and envelope are accepted. The push also stamps the token without
    # a refresh, which the delete right after must get past (its passes refresh before a retry)
    assert await push() == 202
    # an automatic retire keeps the token live, so only the delete stands between it and a push
    await retire_cluster(client, cid, actor="t", mode="auto")
    assert (await http.delete(f"/api/v1/clusters/{cid}")).status_code == 200

    assert await push() == 401
    assert await _left(client, "", cid) == []
    history = await client.indices.get(
        index=f"javv-*-{cid}*", params={"allow_no_indices": "true", "ignore_unavailable": "true"}
    )
    assert list(history) == []


async def test_a_live_cluster_with_a_stray_marker_is_not_retired(env) -> None:
    http, client = env
    cid = await _route_cluster(client)  # live: never retired
    await client.index(
        index="system-config",
        id=delete_marker_id(cid),
        body={"key": delete_marker_id(cid), "cluster_id": cid, "value": {"started_at": "x"}},
        params={"refresh": "true"},
    )
    try:
        r = await http.post(f"/api/v1/clusters/{cid}/unretire")
        assert (r.status_code, r.json()["title"]) == (409, "cluster is not retired")
    finally:
        await client.delete(
            index="system-config", id=delete_marker_id(cid), params={"refresh": "true"}
        )
