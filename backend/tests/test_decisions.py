"""Decision lifecycle (M5b slice 4, FR-8/D39-H5-r2/D40-G-r3): `system-decisions` docs are
immutable except `revoked_at`. An edit (scope/justification/expiry) is revoke+create-new sharing
ONE `effective_at` (`revoked_at(old) = created_at(new)`), with the new doc carrying the pair's
`operation_id`; the NEW doc lands FIRST (a crash between the writes leaves overlap — duplicate
coverage — never a gap where a risk-acceptance silently lapses). Every lifecycle event is
journaled. Real OpenSearch, prefix-isolated."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.decisions.lifecycle import (
    DecisionPayload,
    create_decision,
    edit_decision,
    revoke_decision,
)
from os_env import requires_opensearch

pytestmark = requires_opensearch

# A year out from the run, never a fixed date: creating a decision projects it at the real clock
# (active iff `expiry > now`), so a fixed expiry makes every new decision born-expired once the
# calendar passes it and each "create → risk_accepted" assert below fails on that day.
EXPIRY = (datetime.now(UTC) + timedelta(days=365)).isoformat()


def _payload(**overrides) -> DecisionPayload:
    return DecisionPayload.model_validate(
        {
            "type": "risk_accepted",
            "cve_id": "CVE-2026-0001",
            "scope": {"namespaces": ["payments"], "images": []},
            "apply_both_scanners": True,
            "vex_justification": None,
            "justification": "compensating control in place",
            "expiry": EXPIRY,
            "cluster_id": "c-decisions",
            **overrides,
        }
    )


async def _get(client, prefix, decision_id) -> dict:
    return (await client.get(index=f"{prefix}system-decisions", id=decision_id))["_source"]


async def _audit(client, prefix, decision_id) -> list[dict]:
    await client.indices.refresh(index=f"{prefix}system-audit-log-*")
    hits = await client.search(
        index=f"{prefix}system-audit-log-*",
        body={"size": 20, "query": {"term": {"decision_id": decision_id}}},
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


async def test_create_stamps_identity_lifecycle_and_journals(real_os) -> None:
    client, prefix = real_os

    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    stored = await _get(client, prefix, doc["decision_id"])
    assert stored["type"] == "risk_accepted" and stored["created_by"] == "lead"
    assert stored["created_at"] == stored["effective_at"]  # create: effective_at = created_at
    assert stored["operation_id"] and stored["revoked_at"] is None
    rows = await _audit(client, prefix, doc["decision_id"])
    assert len(rows) == 1 and rows[0]["action"] == "decision_create"
    assert rows[0]["entity_type"] == "decision" and rows[0]["actor"] == "lead"


async def test_revoke_stamps_only_revoked_at(real_os) -> None:
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    await revoke_decision(client, actor="lead", decision_id=doc["decision_id"], prefix=prefix)

    after = await _get(client, prefix, doc["decision_id"])
    assert after["revoked_at"] is not None
    unchanged = {k: v for k, v in after.items() if k != "revoked_at"}
    assert unchanged == {k: v for k, v in doc.items() if k != "revoked_at"}  # immutable otherwise
    rows = await _audit(client, prefix, doc["decision_id"])
    assert {r["action"] for r in rows} == {"decision_create", "decision_revoke"}


async def test_edit_is_revoke_plus_create_under_one_effective_at(real_os) -> None:
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    old, new = await edit_decision(
        client,
        actor="lead",
        decision_id=doc["decision_id"],
        changes={"expiry": "2027-06-30T00:00:00+00:00"},
        prefix=prefix,
    )

    assert new["decision_id"] != old["decision_id"]
    # ONE effective_at knots the pair: revoked_at(old) = created_at(new) = effective_at (D40/G-r3)
    assert old["revoked_at"] == new["created_at"] == new["effective_at"]
    assert new["operation_id"] != doc["operation_id"]  # the pair's shared op id is the NEW one
    assert new["expiry"] == "2027-06-30T00:00:00+00:00"
    assert new["cve_id"] == doc["cve_id"]  # untouched fields carry over
    # the old doc mutated ONLY revoked_at
    stored_old = await _get(client, prefix, doc["decision_id"])
    assert {k: v for k, v in stored_old.items() if k != "revoked_at"} == {
        k: v for k, v in doc.items() if k != "revoked_at"
    }


async def test_editing_or_revoking_a_revoked_decision_is_refused(real_os) -> None:
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)
    await revoke_decision(client, actor="lead", decision_id=doc["decision_id"], prefix=prefix)

    with pytest.raises(ValueError, match="revoked"):
        await revoke_decision(client, actor="lead", decision_id=doc["decision_id"], prefix=prefix)
    with pytest.raises(ValueError, match="revoked"):
        await edit_decision(
            client,
            actor="lead",
            decision_id=doc["decision_id"],
            changes={"justification": "new words"},
            prefix=prefix,
        )


async def test_concurrent_revokes_cannot_double_stamp_revoked_at(real_os) -> None:
    # Audit M-2 (task A): revoke was check-then-act — two racers both passed the Python check and
    # the second overwrote the immutable revoked_at (corrupting past-T reconstruction). Exactly
    # one revoke may win; the loser gets the "already revoked" refusal.
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    results = await asyncio.gather(
        revoke_decision(
            client,
            actor="alice",
            decision_id=doc["decision_id"],
            effective_at="2026-08-01T00:00:00+00:00",
            prefix=prefix,
        ),
        revoke_decision(
            client,
            actor="bob",
            decision_id=doc["decision_id"],
            effective_at="2026-09-01T00:00:00+00:00",
            prefix=prefix,
        ),
        return_exceptions=True,
    )

    winners = [r for r in results if isinstance(r, dict)]
    losers = [r for r in results if isinstance(r, ValueError)]
    assert len(winners) == 1 and len(losers) == 1
    stored = await _get(client, prefix, doc["decision_id"])
    assert stored["revoked_at"] == winners[0]["revoked_at"]  # the stamp is single-writer
    rows = await _audit(client, prefix, doc["decision_id"])
    assert sum(1 for r in rows if r["action"] == "decision_revoke") == 1


async def test_concurrent_edits_leave_exactly_one_active_decision(real_os) -> None:
    # Audit M-2 (task A): two concurrent edits both created successors and both revoked the same
    # old doc → two active decisions forever, breaking the pairing invariant M5c's projection
    # needs. Exactly one edit may win; the loser compensates (its successor never stays active).
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)

    results = await asyncio.gather(
        edit_decision(
            client,
            actor="alice",
            decision_id=doc["decision_id"],
            changes={"justification": "alice's revision"},
            prefix=prefix,
        ),
        edit_decision(
            client,
            actor="bob",
            decision_id=doc["decision_id"],
            changes={"justification": "bob's revision"},
            prefix=prefix,
        ),
        return_exceptions=True,
    )

    ok = [r for r in results if isinstance(r, tuple)]
    failed = [r for r in results if isinstance(r, ValueError)]
    assert len(ok) == 1 and len(failed) == 1
    await client.indices.refresh(index=f"{prefix}system-decisions")
    active = await client.search(
        index=f"{prefix}system-decisions",
        body={"query": {"bool": {"must_not": [{"exists": {"field": "revoked_at"}}]}}},
    )
    assert active["hits"]["total"]["value"] == 1  # never two active successors
    winner_new = ok[0][1]
    assert active["hits"]["hits"][0]["_id"] == winner_new["decision_id"]


async def test_active_at_t_semantics_hold(real_os) -> None:
    # "Active at T" = created_at <= T AND (revoked_at null OR > T) AND (expiry null OR > T)
    client, prefix = real_os
    doc = await create_decision(client, actor="lead", payload=_payload(), prefix=prefix)
    await revoke_decision(client, actor="lead", decision_id=doc["decision_id"], prefix=prefix)
    stored = await _get(client, prefix, doc["decision_id"])

    t_during = stored["created_at"]  # instant of creation — active
    t_after = "2099-01-01T00:00:00+00:00"
    active_query = lambda t: {  # noqa: E731 — the M5c projection will own this as a real builder
        "bool": {
            "filter": [{"range": {"created_at": {"lte": t}}}],
            "must_not": [
                {"range": {"revoked_at": {"lte": t}}},
                {"range": {"expiry": {"lte": t}}},
            ],
        }
    }
    await client.indices.refresh(index=f"{prefix}system-decisions")
    during = await client.search(
        index=f"{prefix}system-decisions", body={"query": active_query(t_during)}
    )
    after = await client.search(
        index=f"{prefix}system-decisions", body={"query": active_query(t_after)}
    )
    assert during["hits"]["total"]["value"] == 1  # visible at its own creation instant
    assert after["hits"]["total"]["value"] == 0  # revoked + expired by then


# --- D22 scanner dimension (M5c): scanner-specific vs apply-both ---------------------


def test_payload_requires_scanner_iff_not_apply_both() -> None:
    """A scanner-specific decision must SAY which scanner (the INDEX-MAP lacked the field —
    added in M5c); an apply-both decision must not carry one (contradictory input = reject)."""
    base = {
        "type": "risk_accepted",
        "cve_id": "CVE-1",
        "scope": {"namespaces": [], "images": []},
        "justification": "j",
        "cluster_id": "c-decisions",
    }
    with pytest.raises(ValidationError, match="scanner"):
        DecisionPayload.model_validate({**base, "apply_both_scanners": False})
    with pytest.raises(ValidationError, match="scanner"):
        DecisionPayload.model_validate({**base, "apply_both_scanners": True, "scanner": "trivy"})
    ok = DecisionPayload.model_validate({**base, "apply_both_scanners": False, "scanner": "grype"})
    assert ok.scanner == "grype"
    assert DecisionPayload.model_validate({**base, "apply_both_scanners": True}).scanner is None


# --- M5c: projection round-trip on the findings cache -------------------------------


async def _seed_finding(client, prefix: str, **over):
    doc = {
        "finding_key": over.get("finding_key", f"fk-{uuid4().hex[:8]}"),
        "cluster_id": "c-decisions",
        "scanner": "trivy",
        "cve_id": "CVE-2026-0001",
        "image_digest": "sha256:aaa",
        "namespaces": ["payments"],
        "state": "open",
        "vex_justification": None,
        "state_decision_id": None,
        "present": True,
        **over,
    }
    await client.index(
        index=f"{prefix}findings", id=doc["finding_key"], body=doc, params={"refresh": "true"}
    )
    return doc["finding_key"]


async def _finding(client, prefix: str, key: str) -> dict:
    return (await client.get(index=f"{prefix}findings", id=key))["_source"]


async def test_create_projects_and_revoke_reverts(real_os) -> None:
    client, prefix = real_os
    fk = await _seed_finding(client, prefix)
    made = await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)

    got = await _finding(client, prefix, fk)
    assert (got["state"], got["state_decision_id"]) == ("risk_accepted", made["decision_id"])

    await revoke_decision(client, actor="ana", decision_id=made["decision_id"], prefix=prefix)
    got = await _finding(client, prefix, fk)
    assert (got["state"], got["state_decision_id"]) == ("open", None)  # fallback: open


async def test_not_affected_decision_round_trips_to_valid_vex(real_os) -> None:
    """A-M2 end-to-end (audit #185): a valid not_affected decision projects a CISA justification
    onto the finding, and both VEX serializers emit it — never a null status/justification and
    never a KeyError."""
    from backend.export.vex import to_cyclonedx, to_openvex

    client, prefix = real_os
    fk = await _seed_finding(client, prefix)
    await create_decision(
        client,
        actor="ana",
        payload=_payload(
            type="not_affected", vex_justification="component_not_present", expiry=None
        ),
        prefix=prefix,
    )
    got = await _finding(client, prefix, fk)
    assert (got["state"], got["vex_justification"]) == ("not_affected", "component_not_present")

    at = datetime(2026, 7, 6, tzinfo=UTC)
    ov = to_openvex([got], cluster_id="c-decisions", scanner="trivy", generated_at=at)
    assert ov["statements"][0]["status"] == "not_affected"
    assert ov["statements"][0]["justification"] == "component_not_present"
    cdx = to_cyclonedx([got], cluster_id="c-decisions", scanner="trivy", generated_at=at)
    assert cdx["vulnerabilities"][0]["analysis"]["justification"] == "code_not_present"


async def test_projection_never_overwrites_a_direct_human_state(real_os) -> None:
    client, prefix = real_os
    fk = await _seed_finding(client, prefix, state="acknowledged")  # human-set: provenance null
    await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)
    got = await _finding(client, prefix, fk)
    assert got["state"] == "acknowledged"  # direct action > auto-rule


async def test_edit_reprojects_once_after_both_writes(real_os) -> None:
    client, prefix = real_os
    fk = await _seed_finding(client, prefix, namespaces=["web"])
    made = await create_decision(
        client, actor="ana", payload=_payload(scope={"namespaces": [], "images": []}), prefix=prefix
    )
    assert (await _finding(client, prefix, fk))["state"] == "risk_accepted"

    # edit narrows scope to a namespace the finding is NOT in → projection must release it
    _, new = await edit_decision(
        client,
        actor="ana",
        decision_id=made["decision_id"],
        changes={"scope": {"namespaces": ["payments"], "images": []}},
        prefix=prefix,
    )
    got = await _finding(client, prefix, fk)
    assert (got["state"], got["state_decision_id"]) == ("open", None)
    assert new["operation_id"]  # the pair landed; projection ran after both (D40/G-r3)


async def test_ingest_projects_decisions_onto_newly_created_findings(real_os) -> None:
    """D19: projection-on-new-only at ingest — a pre-existing cluster-wide decision applies to
    findings a later scan CREATES, without a manual reproject. (Unchanged findings are only
    delta-checked — reproject writes deltas exclusively, so no-op writes never happen.)"""
    import json
    from pathlib import Path

    from backend.models.envelope import IngestEnvelope
    from backend.services.ingest import ingest_envelope

    client, prefix = real_os
    golden = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
    env = IngestEnvelope.model_validate(golden)
    made = await create_decision(
        client,
        actor="ana",
        payload=_payload(
            cve_id="CVE-2005-2541",
            cluster_id=env.cluster_id,
            scope={"namespaces": [], "images": []},
        ),
        prefix=prefix,
    )

    await ingest_envelope(client, env, prefix=prefix)

    await client.indices.refresh(index=f"{prefix}findings")
    resp = await client.search(
        index=f"{prefix}findings",
        body={
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"cluster_id": env.cluster_id}},
                        {"term": {"cve_id": "CVE-2005-2541"}},
                    ]
                }
            },
        },
    )
    hits = resp["hits"]["hits"]
    assert hits, "the golden envelope must create CVE-2005-2541 findings"
    for h in hits:
        assert h["_source"]["state"] == "risk_accepted"
        assert h["_source"]["state_decision_id"] == made["decision_id"]


async def test_daily_sweep_reprojects_expired_decisions(real_os) -> None:
    """SND-9/PLAN §5.7: expiry-refresh is the sweep's fallback arm — an expired decision stops
    projecting at the NEXT sweep (and the next applicable rule takes over, here: none → open)."""
    from backend.jobs.staleness import run_staleness_sweep

    client, prefix = real_os
    fk = await _seed_finding(client, prefix)
    expires = datetime.now(UTC) + timedelta(days=30)
    made = await create_decision(
        client,
        actor="ana",
        payload=_payload(expiry=expires.isoformat()),
        prefix=prefix,
    )
    assert (await _finding(client, prefix, fk))["state"] == "risk_accepted"

    # time passes: the decision is now expired (sweep runs with an injected `now` past expiry)
    result = await run_staleness_sweep(client, now=expires + timedelta(days=150), prefix=prefix)

    got = await _finding(client, prefix, fk)
    assert (got["state"], got["state_decision_id"]) == ("open", None)
    assert result["reprojected"] >= 1
    assert made["decision_id"]  # the doc itself is untouched (expiry is data, not deletion)


async def test_rebuild_state_reconstructs_the_projection_from_source(real_os) -> None:
    """Self-heal (M5c DoD): corrupt the projected cache directly — rebuild_state reproduces the
    identical projection from `system-decisions` source (both damage directions: an overwritten
    projection AND a phantom projection pointing at a decision that no longer wins)."""
    from backend.jobs.rebuild_state import rebuild_decision_projection

    client, prefix = real_os
    fk_projected = await _seed_finding(client, prefix)
    made = await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)
    fk_phantom = await _seed_finding(
        client, prefix, cve_id="CVE-none", state="risk_accepted", state_decision_id="ghost"
    )

    # damage 1: wipe the real projection; damage 2 is fk_phantom's ghost provenance
    await client.update(
        index=f"{prefix}findings",
        id=fk_projected,
        body={"doc": {"state": "open", "state_decision_id": None}},
        params={"refresh": "true"},
    )

    result = await rebuild_decision_projection(client, prefix=prefix)

    got = await _finding(client, prefix, fk_projected)
    assert (got["state"], got["state_decision_id"]) == ("risk_accepted", made["decision_id"])
    ghost = await _finding(client, prefix, fk_phantom)
    assert (ghost["state"], ghost["state_decision_id"]) == ("open", None)
    assert result["reprojected"] >= 2


# --- THE M5c GATE (D22, PLAN §8): apply_both independence + scanner override ---------


async def test_gate_apply_both_projects_independently_and_scanner_specific_overrides(
    real_os,
) -> None:
    """PLAN M5c gate: a both-scanners decision on (cluster, cve, scope) projects onto EACH
    scanner's finding independently and each closes on its own; a scanner-specific decision
    OUTRANKS the both-scanners one for that scanner only."""
    client, prefix = real_os
    fk_trivy = await _seed_finding(client, prefix, scanner="trivy")
    fk_grype = await _seed_finding(client, prefix, scanner="grype")

    both = await create_decision(
        client,
        actor="ana",
        payload=_payload(scope={"namespaces": [], "images": []}),
        prefix=prefix,
    )
    for fk in (fk_trivy, fk_grype):  # projects onto each scanner's finding independently
        got = await _finding(client, prefix, fk)
        assert (got["state"], got["state_decision_id"]) == ("risk_accepted", both["decision_id"])

    # a grype-specific not_affected outranks the both-scanners decision — for grype ONLY
    mine = await create_decision(
        client,
        actor="ana",
        payload=_payload(
            type="not_affected",
            apply_both_scanners=False,
            scanner="grype",
            vex_justification="component_not_present",
            scope={"namespaces": [], "images": []},
            expiry=None,
        ),
        prefix=prefix,
    )
    got_g = await _finding(client, prefix, fk_grype)
    assert (got_g["state"], got_g["state_decision_id"]) == ("not_affected", mine["decision_id"])
    assert got_g["vex_justification"] == "component_not_present"
    got_t = await _finding(client, prefix, fk_trivy)  # trivy still follows the both-scanners one
    assert (got_t["state"], got_t["state_decision_id"]) == ("risk_accepted", both["decision_id"])

    # each closes on its own: revoking the grype-specific one releases grype BACK to the
    # both-scanners decision (next applicable rule — never a gap to open)
    await revoke_decision(client, actor="ana", decision_id=mine["decision_id"], prefix=prefix)
    got_g = await _finding(client, prefix, fk_grype)
    assert (got_g["state"], got_g["state_decision_id"]) == ("risk_accepted", both["decision_id"])


async def test_concurrent_edits_leave_one_active_winner_and_a_consistent_projection(
    real_os,
) -> None:
    """DoD concurrency: racing edits on one decision — exactly one pair wins (the loser
    compensates, task A M-2) and the projection matches the surviving active decision."""
    from backend.decisions.lifecycle import DECISIONS_INDEX

    client, prefix = real_os
    fk = await _seed_finding(client, prefix)
    made = await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)

    async def racer(justification: str):
        try:
            return await edit_decision(
                client,
                actor="ana",
                decision_id=made["decision_id"],
                changes={"justification": justification},
                prefix=prefix,
            )
        except ValueError:
            return None  # lost the race — compensated (its successor is revoked)

    results = await asyncio.gather(racer("edit A"), racer("edit B"))
    winners = [r for r in results if r is not None]
    assert len(winners) == 1  # exactly one edit landed

    await client.indices.refresh(index=f"{prefix}{DECISIONS_INDEX}")
    resp = await client.search(
        index=f"{prefix}{DECISIONS_INDEX}",
        body={
            "size": 10,
            "query": {"bool": {"must_not": [{"exists": {"field": "revoked_at"}}]}},
        },
    )
    active = [h["_source"] for h in resp["hits"]["hits"]]
    assert len(active) == 1  # never two active decisions for the pair
    got = await _finding(client, prefix, fk)
    assert (got["state"], got["state_decision_id"]) == ("risk_accepted", active[0]["decision_id"])


# --- A-M3 / A-m10: reproject guarded RMW (audit #186) --------------------------------


async def test_concurrent_reprojects_do_not_500_and_converge(real_os) -> None:
    """A-M3 consequence 1 (deterministic): several reprojects race the SAME (cluster, cve).
    The guarded read-modify-write DRAINS version conflicts instead of raising BulkError out of
    the decision path — the unguarded write 500'd after the decision docs already committed."""
    from backend.decisions.reproject import reproject_cve

    client, prefix = real_os
    fk = await _seed_finding(client, prefix)
    await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)  # → risk_accepted
    # reset to open so a fresh reproject WANTS to change it, then race N reprojects at once
    await client.update(
        index=f"{prefix}findings",
        id=fk,
        body={"doc": {"state": "open", "state_decision_id": None, "vex_justification": None}},
        params={"refresh": "true"},
    )

    results = await asyncio.gather(
        *[reproject_cve(client, "c-decisions", "CVE-2026-0001", prefix=prefix) for _ in range(5)],
        return_exceptions=True,
    )
    assert all(not isinstance(r, Exception) for r in results), results  # no BulkError / 500
    got = await _finding(client, prefix, fk)
    assert got["state"] == "risk_accepted"  # converged to the projection


async def test_reproject_does_not_overwrite_a_concurrent_human_triage(real_os) -> None:
    """A-M3 consequence 2: a direct human triage that lands mid-reproject MUST survive — the
    guarded RMW re-checks ownership on the fresh source and keeps its hands off (the unguarded
    write silently overwrote it, breaking 'direct action > auto-rule' and defeating rebuild)."""
    from backend.triage.service import TriagePatch, apply_triage

    client, prefix = real_os
    fk = await _seed_finding(client, prefix)
    made = await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)
    assert (await _finding(client, prefix, fk))["state"] == "risk_accepted"

    # race the decision revoke (reprojects toward open) against a human acknowledging the finding
    await asyncio.gather(
        revoke_decision(client, actor="ana", decision_id=made["decision_id"], prefix=prefix),
        apply_triage(
            client,
            actor="human",
            finding_key=fk,
            patch=TriagePatch(state="acknowledged"),
            may_undo_risk_accept=True,  # a lead's override: this test races the write path
            prefix=prefix,
        ),
        return_exceptions=True,
    )
    got = await _finding(client, prefix, fk)
    assert got["state"] == "acknowledged"  # the direct human action wins
    assert got["state_decision_id"] is None  # provenance cleared — not decision-owned


async def test_reproject_pages_beyond_one_batch(real_os, monkeypatch) -> None:
    """A-m10: reproject must not silently truncate at the page bound — the old bare `assert
    len(hits) < _PAGE` vanished under `python -O`, projecting only the first page. Shrink the
    page and assert EVERY finding still reprojects."""
    from backend.decisions import reproject as reproject_mod

    monkeypatch.setattr(reproject_mod, "_PAGE", 2)
    client, prefix = real_os
    fks = [
        await _seed_finding(client, prefix, finding_key=f"fk-page-{i}", image_digest=f"sha256:{i}")
        for i in range(5)
    ]
    await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)
    for fk in fks:
        assert (await _finding(client, prefix, fk))["state"] == "risk_accepted"  # all 5, not 2


async def test_reproject_warns_when_it_drains_a_conflict_storm(real_os, monkeypatch) -> None:
    """Observability nicety (#186): a (cluster, cve) that has to DRAIN conflicts is contention-hot;
    reproject emits a warning above the info line so ops can spot it. Force one drain round (stub
    the guarded write to 409 once) with the threshold at 1, and assert the warning fires — while
    the finding still converges via the re-read + retry."""
    import structlog

    from backend.decisions import reproject as reproject_mod

    client, prefix = real_os
    fk = await _seed_finding(client, prefix)  # open → projects to risk_accepted
    monkeypatch.setattr(reproject_mod, "_HOT_PAIR_CONFLICTS", 1)
    monkeypatch.setattr(reproject_mod, "log", structlog.get_logger())  # capture the module logger

    real_bulk = reproject_mod.bulk_write
    forced = {"done": False}

    async def _bulk_conflict_once(client, actions, **kw):
        # reproject writes pass collect_conflicts=True; force the first to 409 to drive a drain
        if kw.get("collect_conflicts") and not forced["done"]:
            forced["done"] = True
            return 0, [{"_id": actions[0]["update"]["_id"], "status": 409}]
        return await real_bulk(client, actions, **kw)

    monkeypatch.setattr(reproject_mod, "bulk_write", _bulk_conflict_once)

    with structlog.testing.capture_logs() as logs:
        await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)

    assert forced["done"]  # the stub actually fired
    assert any("conflict" in entry["event"].lower() for entry in logs)  # storm warning emitted
    assert (await _finding(client, prefix, fk))["state"] == "risk_accepted"  # converged anyway


# --- A-M5: journal-first — no applied-but-unjournaled decision (audit #188) ----------


def _fail_audit_once(monkeypatch) -> dict:
    """Make the NEXT audit append raise (a transient audit-index hiccup), then heal."""
    from backend.audit import writer

    real = writer._append
    state = {"fired": False}

    async def flaky(*args, **kwargs):
        if not state["fired"]:
            state["fired"] = True
            raise RuntimeError("audit index hiccup")
        return await real(*args, **kwargs)

    monkeypatch.setattr(writer, "_append", flaky)
    return state


async def test_decision_create_not_left_unjournaled_on_audit_failure(real_os, monkeypatch) -> None:
    """A-M5: journal-first — an audit-append failure must not leave a live-but-unjournaled decision
    (which the client's retry would turn into a SECOND active decision). No doc on failure; a retry
    creates exactly one decision with exactly one create row."""
    client, prefix = real_os
    idx = f"{prefix}system-decisions"
    _fail_audit_once(monkeypatch)

    with pytest.raises(Exception):  # noqa: B017 — the audit hiccup surfaces (500), not swallowed
        await create_decision(
            client, actor="ana", payload=_payload(cve_id="CVE-J-1"), prefix=prefix
        )
    await client.indices.refresh(index=idx)
    n = await client.count(index=idx, body={"query": {"term": {"cve_id": "CVE-J-1"}}})
    assert n["count"] == 0  # no orphan decision — the create never landed

    made = await create_decision(
        client, actor="ana", payload=_payload(cve_id="CVE-J-1"), prefix=prefix
    )
    await client.indices.refresh(index=idx)
    assert (await client.count(index=idx, body={"query": {"term": {"cve_id": "CVE-J-1"}}}))[
        "count"
    ] == 1
    rows = await _audit(client, prefix, made["decision_id"])
    assert sum(1 for r in rows if r["action"] == "decision_create") == 1


async def test_decision_revoke_not_left_unjournaled_on_audit_failure(real_os, monkeypatch) -> None:
    """A-M5: journal-first with a deterministic id — an audit failure means the CAS never stamps
    (still active); a retry revokes it, and even across the failure there is exactly one revoke
    row (the deterministic id dedups)."""
    client, prefix = real_os
    made = await create_decision(client, actor="ana", payload=_payload(), prefix=prefix)
    _fail_audit_once(monkeypatch)

    with pytest.raises(Exception):  # noqa: B017
        await revoke_decision(client, actor="ana", decision_id=made["decision_id"], prefix=prefix)
    assert (await _get(client, prefix, made["decision_id"]))["revoked_at"] is None  # never stamped

    await revoke_decision(client, actor="ana", decision_id=made["decision_id"], prefix=prefix)
    assert (await _get(client, prefix, made["decision_id"]))["revoked_at"] is not None
    rows = await _audit(client, prefix, made["decision_id"])
    assert sum(1 for r in rows if r["action"] == "decision_revoke") == 1
