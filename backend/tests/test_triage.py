"""Triage service + PATCH route (M5b slice 3, FR-7/D17): CAS on the finding, `refresh=wait_for`,
and **one audit row per action** with the resulting `revision`. Ruling (recorded in the service):
a `not_affected` transition is ONE action — its CISA justification travels on the state row
(`new_value_json`), so the one-action-one-entry DoD holds while replay still sees the
justification. Triage writes ONLY the human fields (merge.py contract); a human override from
`stale` clears `pre_stale_status` so the sweep can't later revert it. Real OpenSearch."""

import asyncio
import contextlib
import uuid
from typing import Any

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "correct horse battery staple"


pytestmark = requires_opensearch


@pytest.fixture
async def triage_client():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://t") as http:
        yield http, client
    await client.close()


async def _login(http, client, *, capabilities: list[str]) -> str:
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
            "created_at": "2026-07-04T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return username


async def _seed_finding(client, *, state: str = "open", pre_stale: str | None = None) -> str:
    fk = f"fk-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="findings",
        id=fk,
        body={
            "finding_key": fk,
            "cluster_id": "c-triage",
            "scanner": "trivy",
            "image_digest": "sha256:abc",
            "present": True,
            "state": state,
            "pre_stale_status": pre_stale,
        },
        params={"refresh": "true"},
    )
    return fk


async def _audit_rows(client, fk: str) -> list[dict[str, Any]]:
    await client.indices.refresh(index="system-audit-log-*")
    hits = await client.search(
        index="system-audit-log-*",
        body={"size": 50, "query": {"term": {"finding_key": fk}}},
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


async def _doc(client, fk: str) -> dict[str, Any]:
    return (await client.get(index="findings", id=fk))["_source"]


def _patch(http, fk: str, body: dict) -> Any:
    return http.patch(f"/api/v1/findings/{fk}/triage", json=body)


# --- state transitions ---------------------------------------------------------------


async def test_acknowledge_writes_the_state_and_exactly_one_audit_row(triage_client) -> None:
    http, client = triage_client
    actor = await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)

    r = await _patch(http, fk, {"state": "acknowledged"})

    assert r.status_code == 200
    assert r.json()["finding"]["state"] == "acknowledged"
    assert (await _doc(client, fk))["state"] == "acknowledged"
    rows = await _audit_rows(client, fk)
    assert len(rows) == 1
    row = rows[0]
    assert row["action"] == "acknowledge" and row["actor"] == actor
    assert (row["field"], row["old_value"], row["new_value"]) == ("state", "open", "acknowledged")
    assert row["revision"] >= 1  # the finding's resulting CAS version
    assert row["cluster_id"] == "c-triage"
    # refresh=wait_for: the write is immediately searchable, not just GET-visible
    hit = await client.search(
        index="findings",
        body={"query": {"bool": {"filter": [{"term": {"finding_key": fk}}]}}, "size": 1},
    )
    assert hit["hits"]["hits"][0]["_source"]["state"] == "acknowledged"


async def test_not_affected_is_one_action_with_the_justification_on_the_row(triage_client) -> None:
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)

    r = await _patch(
        http, fk, {"state": "not_affected", "vex_justification": "component_not_present"}
    )

    assert r.status_code == 200
    doc = await _doc(client, fk)
    assert doc["state"] == "not_affected"
    assert doc["vex_justification"] == "component_not_present"
    (row,) = await _audit_rows(client, fk)  # ONE action, one row (DoD)
    assert row["action"] == "not_affected" and row["field"] == "state"
    assert row["new_value_json"] == {"vex_justification": "component_not_present"}


async def test_not_affected_without_justification_is_422(triage_client) -> None:
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)
    assert (await _patch(http, fk, {"state": "not_affected"})).status_code == 422


async def test_leaving_not_affected_clears_the_justification(triage_client) -> None:
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)
    await _patch(http, fk, {"state": "not_affected", "vex_justification": "component_not_present"})

    await _patch(http, fk, {"state": "open"})  # reopen

    doc = await _doc(client, fk)
    assert doc["state"] == "open" and doc["vex_justification"] is None


async def test_justification_only_correction_is_written_and_journaled(triage_client) -> None:
    # Audit M-1 (task A): not_affected → not_affected with a DIFFERENT justification is a real
    # correction — it must land on the doc and in the journal, not vanish in the same-state no-op.
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)
    await _patch(http, fk, {"state": "not_affected", "vex_justification": "component_not_present"})

    r = await _patch(
        http, fk, {"state": "not_affected", "vex_justification": "vulnerable_code_not_present"}
    )

    assert r.status_code == 200
    doc = await _doc(client, fk)
    assert doc["vex_justification"] == "vulnerable_code_not_present"
    corrections = [
        row for row in await _audit_rows(client, fk) if row["field"] == "vex_justification"
    ]
    assert len(corrections) == 1
    assert corrections[0]["old_value"] == "component_not_present"
    assert corrections[0]["new_value"] == "vulnerable_code_not_present"
    # same state + same justification stays a true no-op
    before = len(await _audit_rows(client, fk))
    await _patch(
        http, fk, {"state": "not_affected", "vex_justification": "vulnerable_code_not_present"}
    )
    assert len(await _audit_rows(client, fk)) == before


async def test_stale_is_never_a_human_target(triage_client) -> None:
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)
    assert (await _patch(http, fk, {"state": "stale"})).status_code == 422


async def test_risk_accept_needs_the_final_word_capability(triage_client) -> None:
    # SEC-2/D33: can_triage alone can't risk-accept — can_accept_audit_final gates it
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)
    assert (await _patch(http, fk, {"state": "risk_accepted"})).status_code == 403

    await _login(http, client, capabilities=["can_triage", "can_accept_audit_final"])
    r = await _patch(http, fk, {"state": "risk_accepted"})
    assert r.status_code == 200
    assert (await _doc(client, fk))["state"] == "risk_accepted"


@pytest.mark.parametrize(
    ("state", "pre_stale"), [("risk_accepted", None), ("stale", "risk_accepted")]
)
async def test_undoing_a_risk_accept_needs_the_final_word_capability(
    triage_client, state, pre_stale
) -> None:
    """issue 892 rulings 1 and 7: a triager cannot move a finding off risk_accepted, nor off a
    stale state that keeps a risk-accept for the sweep to restore. A note still lands."""
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client, state=state, pre_stale=pre_stale)

    r = await _patch(http, fk, {"state": "open"})
    assert r.status_code == 403
    assert "can_accept_audit_final" in r.json()["title"]
    doc = await _doc(client, fk)
    assert (doc["state"], doc["pre_stale_status"]) == (state, pre_stale)  # nothing written
    assert await _audit_rows(client, fk) == []  # nothing journaled

    assert (await _patch(http, fk, {"notes": "seen"})).status_code == 200  # not an undo

    await _login(http, client, capabilities=["can_triage", "can_accept_audit_final"])
    assert (await _patch(http, fk, {"state": "open"})).status_code == 200
    assert (await _doc(client, fk))["state"] == "open"


async def test_human_override_from_stale_clears_pre_stale_status(triage_client) -> None:
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client, state="stale", pre_stale="acknowledged")

    await _patch(http, fk, {"state": "resolved"})

    doc = await _doc(client, fk)
    assert doc["state"] == "resolved"
    assert doc["pre_stale_status"] is None  # the sweep can never revert this human call


# --- assign / note --------------------------------------------------------------------


async def test_assign_and_note_each_append_one_typed_row(triage_client) -> None:
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)

    assert (await _patch(http, fk, {"assignee": "bob"})).status_code == 200
    assert (await _patch(http, fk, {"notes": "looking into it"})).status_code == 200

    rows = {r["action"]: r for r in await _audit_rows(client, fk)}
    assert set(rows) == {"assign", "note"}
    assert rows["assign"]["field"] == "assignee" and rows["assign"]["new_value"] == "bob"
    assert rows["note"]["field_type"] == "text"


async def test_a_noop_patch_writes_nothing(triage_client) -> None:
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client, state="acknowledged")

    r = await _patch(http, fk, {"state": "acknowledged"})  # already there

    assert r.status_code == 200
    assert await _audit_rows(client, fk) == []  # no change, no journal entry


async def test_unknown_finding_is_404_and_empty_patch_is_422(triage_client) -> None:
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    assert (await _patch(http, "fk-does-not-exist", {"state": "acknowledged"})).status_code == 404
    fk = await _seed_finding(client)
    assert (await _patch(http, fk, {})).status_code == 422  # at least one field required


# --- D17 completeness under partial failure (audit M-3, task A) ------------------------


async def test_journal_outage_cannot_orphan_an_applied_change(triage_client, monkeypatch) -> None:
    # Audit M-3: with write-then-journal, a journal failure after the CAS write leaves an
    # applied-but-unjournaled change; the client retry no-ops (state already there) and never
    # journals it. D17 requires: if the change is applied, a row for it must exist.
    import backend.triage.service as svc

    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)

    real_append = svc.append_field_change
    calls = {"n": 0}

    async def flaky_append(*args: Any, **kwargs: Any) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected audit outage")
        return await real_append(*args, **kwargs)

    monkeypatch.setattr(svc, "append_field_change", flaky_append)

    with contextlib.suppress(Exception):  # first attempt fails (audit outage) — that's expected
        await _patch(http, fk, {"state": "acknowledged"})
    r = await _patch(http, fk, {"state": "acknowledged"})  # the client retry
    assert r.status_code == 200

    doc = await _doc(client, fk)
    assert doc["state"] == "acknowledged"
    state_rows = [row for row in await _audit_rows(client, fk) if row["field"] == "state"]
    assert state_rows, "an applied change MUST have an audit row (D17)"
    latest = max(state_rows, key=lambda row: row["revision"])
    assert latest["new_value"] == "acknowledged"


# --- concurrency (DoD): racing writers resolve via CAS retry ---------------------------


async def test_concurrent_triage_writes_both_land_and_replay_correctly(triage_client) -> None:
    # Journal-before-commit (audit M-3 ruling): a lost CAS may leave a tolerated orphan row, so
    # the contract is NOT "exactly one row per action" under contention — it's the replay
    # contract: latest-per-field by revision reconstructs the doc.
    http, client = triage_client
    await _login(http, client, capabilities=["can_triage"])
    fk = await _seed_finding(client)

    r1, r2 = await asyncio.gather(
        _patch(http, fk, {"assignee": "bob"}),
        _patch(http, fk, {"notes": "racing note"}),
    )

    assert r1.status_code == 200 and r2.status_code == 200
    doc = await _doc(client, fk)
    assert doc["assignee"] == "bob" and doc["notes"] == "racing note"  # neither write lost
    rows = await _audit_rows(client, fk)
    assert {r["action"] for r in rows} == {"assign", "note"}
    for field, expected in (("assignee", "bob"), ("notes", "racing note")):
        field_rows = [r for r in rows if r["field"] == field]
        latest = max(field_rows, key=lambda r: r["revision"])
        assert latest["new_value"] == expected  # replay converges on the doc
