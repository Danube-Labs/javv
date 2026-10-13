"""The retirement bell (issue 765): a cluster entering its warning window is announced once to
every user who can act on it, and not again for that window, even after a dismiss.

Pins: the plan lists the clusters inside their window and leaves out the ones retired by this run,
and a cluster left alone by them; recipients are the enabled users holding `can_manage_settings`
(role bundle or their own list; a missing role grants nothing); one notification each, with the
cluster and its retirement date; a second sweep sends nothing, nor does a settings change that
moves the dates; a dismissed notification does not come back; a new silence is announced again; a
run that stopped before its marker repeats none; every notice of a run goes in one `_bulk`, and
one the store refuses fails the run before any marker; with no recipient no marker is written; a
failed announcement leaves the run's retirements standing; a notice is withdrawn when its cluster
scans again or a new silence replaces it, and kept once the cluster is retired; a cluster delete
removes the marker."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from opensearchpy import AsyncOpenSearch
from prometheus_client import REGISTRY

from backend.admin.cluster_retirement import RetirementWindow
from backend.admin.retirement_notices import (
    NOTICE_TYPE,
    notify_retiring,
    settings_admins,
    warned_doc_id,
)
from backend.jobs import cluster_retirement
from backend.jobs.cluster_retirement import (
    TokenActivity,
    plan_sweep,
    run_retirement_sweep,
    schedule_for,
)
from backend.reports.models import NOTIFICATIONS_INDEX
from backend.repositories.bulk import BulkError
from os_env import requires_opensearch

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
WINDOW = RetirementWindow(retire_after_days=45, warn_days=7)


def _ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def test_the_plan_warns_the_clusters_inside_their_window_and_not_the_retired_ones() -> None:
    # 40 days silent: warning (38..45); 50: due and retired this run; 3: fine
    silent = {"warn": 40, "due": 50, "fine": 3}
    activity = {cid: TokenActivity(_ago(d), None) for cid, d in silent.items()}
    schedules = {cid: schedule_for(a, WINDOW, 7) for cid, a in activity.items()}
    plan = plan_sweep(schedules, activity, {}, NOW)
    assert (plan.retire, plan.warn) == (["due"], ["warn"])


def test_a_held_cluster_is_still_warned() -> None:
    silent = {"due": 50, "warn": 40}
    activity = {cid: TokenActivity(_ago(d), None) for cid, d in silent.items()}
    schedules = {cid: schedule_for(a, WINDOW, 7) for cid, a in activity.items()}
    plan = plan_sweep(schedules, activity, {}, NOW)
    assert (plan.held, plan.warn) == (["due"], ["due", "warn"])


def test_the_only_cluster_is_never_announced() -> None:
    activity = {"only": TokenActivity(_ago(40), None)}
    schedules = {"only": schedule_for(activity["only"], WINDOW, 7)}
    assert plan_sweep(schedules, activity, {}, NOW).warn == []


def test_a_cluster_left_alone_by_this_runs_retirements_is_not_announced() -> None:
    # "warn" counts as scanning for 60 days (its scanner-down override), so "due" is retired;
    # "warn" is then the only cluster listed, which the sweep never retires
    activity = {"due": TokenActivity(_ago(50), None), "warn": TokenActivity(_ago(55), None)}
    schedules = {
        "due": schedule_for(activity["due"], WINDOW, 7),
        "warn": schedule_for(activity["warn"], WINDOW, 60),
    }
    plan = plan_sweep(schedules, activity, {}, NOW)
    assert (plan.retire, plan.warn) == (["due"], [])


# --- against a store -----------------------------------------------------------------------


async def _put(client: AsyncOpenSearch, index: str, doc_id: str, body: dict[str, Any]) -> None:
    await client.index(index=index, id=doc_id, body=body, params={"refresh": "true"})


async def _people(client: AsyncOpenSearch, prefix: str) -> None:
    await _put(client, f"{prefix}system-roles", "admin", {"role": "admin", "capabilities": ["*"]})
    await _put(client, f"{prefix}system-roles", "viewer", {"role": "viewer", "capabilities": []})
    users = {
        "ann": {"role": "admin"},
        "vic": {"role": "viewer"},
        "dee": {"role": "admin", "disabled": True},
        # a denormalized list wins over the role, as at sign-in
        "sam": {"role": "viewer", "capabilities": ["can_manage_settings"]},
        "tom": {"role": "admin", "capabilities": ["can_triage"]},
        "rob": {"role": "gone"},  # a role with no doc grants nothing
    }
    for name, fields in users.items():
        await _put(
            client, f"{prefix}system-users", name, {"username": name, "disabled": False, **fields}
        )


async def _token(client: AsyncOpenSearch, prefix: str, cid: str, last: datetime) -> None:
    await _put(
        client,
        f"{prefix}system-tokens",
        f"tok-{cid}",
        {
            "token_hash": f"h-{cid}",
            "cluster_id": cid,
            "scanner": "trivy",
            "created_at": _ago(200).isoformat(),
            "last_ingest_at": last.isoformat(),
            "disabled": False,
        },
    )


async def _bell(client: AsyncOpenSearch, prefix: str) -> list[dict[str, Any]]:
    await client.indices.refresh(index=f"{prefix}{NOTIFICATIONS_INDEX}")
    resp = await client.search(
        index=f"{prefix}{NOTIFICATIONS_INDEX}",
        body={"size": 50, "query": {"term": {"type": NOTICE_TYPE}}},
    )
    return [h["_source"] for h in resp["hits"]["hits"]]


@requires_opensearch
async def test_recipients_are_the_enabled_users_who_can_manage_settings(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    assert sorted(await settings_admins(client, prefix=prefix)) == ["ann", "sam"]


@requires_opensearch
async def test_a_cluster_entering_its_window_is_announced_once(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    await _token(client, prefix, "c-warn-0001", _ago(40))
    await _token(client, prefix, "c-live-0001", _ago(1))  # scans flow: no hold

    counts = await run_retirement_sweep(client, now=NOW, prefix=prefix)

    assert counts["announced"] == 1
    bell = await _bell(client, prefix)
    assert sorted(n["user_id"] for n in bell) == ["ann", "sam"]
    retires_at = _ago(40 - 45).isoformat()
    assert {(n["cluster_id"], n["ref"], n["read"]) for n in bell} == {
        ("c-warn-0001", retires_at, False)
    }
    # the next night: nothing new
    again = await run_retirement_sweep(client, now=NOW + timedelta(days=1), prefix=prefix)
    assert again["announced"] == 0
    assert len(await _bell(client, prefix)) == 2


@requires_opensearch
async def test_a_dismissed_notice_does_not_come_back_but_a_new_window_does(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    await _token(client, prefix, "c-warn-0002", _ago(40))
    await _token(client, prefix, "c-live-0002", _ago(1))
    await run_retirement_sweep(client, now=NOW, prefix=prefix)
    for n in await _bell(client, prefix):
        await client.delete(
            index=f"{prefix}{NOTIFICATIONS_INDEX}",
            id=n["notification_id"],
            params={"refresh": "true"},
        )

    assert (await run_retirement_sweep(client, now=NOW, prefix=prefix))["announced"] == 0
    assert await _bell(client, prefix) == []

    # it scanned once more and went silent again: a new window, announced again
    await _token(client, prefix, "c-warn-0002", _ago(39))
    assert (await run_retirement_sweep(client, now=NOW, prefix=prefix))["announced"] == 1
    assert len(await _bell(client, prefix)) == 2


@requires_opensearch
async def test_with_no_one_to_tell_no_marker_is_written(real_os) -> None:
    client, prefix = real_os
    warns_at, retires_at = _ago(2), _ago(-5)
    assert (
        await notify_retiring(
            client, {"c-warn-0003": (warns_at, retires_at)}, now=NOW, prefix=prefix
        )
        == 0
    )
    assert not await client.exists(index=f"{prefix}system-config", id=warned_doc_id("c-warn-0003"))
    # an admin appears: the same window is announced
    await _people(client, prefix)
    assert (
        await notify_retiring(
            client, {"c-warn-0003": (warns_at, retires_at)}, now=NOW, prefix=prefix
        )
        == 1
    )


async def _put_window(
    client: AsyncOpenSearch, prefix: str, warn_days: int, retire_after_days: int = 45
) -> None:
    value = {"retire_after_days": retire_after_days, "warn_days": warn_days}
    await _put(
        client, f"{prefix}system-config", "retirement", {"key": "retirement", "value": value}
    )


@requires_opensearch
async def test_a_settings_change_that_moves_the_dates_sends_nothing_new(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    await _token(client, prefix, "c-warn-0004", _ago(40))
    await _token(client, prefix, "c-live-0004", _ago(1))
    assert (await run_retirement_sweep(client, now=NOW, prefix=prefix))["announced"] == 1

    await _put_window(client, prefix, warn_days=8)  # warns_at moves a day earlier, same silence
    assert (await run_retirement_sweep(client, now=NOW, prefix=prefix))["announced"] == 0
    assert len(await _bell(client, prefix)) == 2


@requires_opensearch
async def test_a_run_that_stopped_before_its_marker_repeats_no_notification(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    warning = {"c-warn-0005": (_ago(40), _ago(-5))}
    assert await notify_retiring(client, warning, now=NOW, prefix=prefix) == 1
    read = (await _bell(client, prefix))[0]["notification_id"]
    await client.update(
        index=f"{prefix}{NOTIFICATIONS_INDEX}",
        id=read,
        body={"doc": {"read": True}},
        params={"refresh": "true"},
    )
    # as if the run stopped after the notifications, before the marker
    await client.delete(
        index=f"{prefix}system-config", id=warned_doc_id("c-warn-0005"), params={"refresh": "true"}
    )

    assert await notify_retiring(client, warning, now=NOW, prefix=prefix) == 1
    bell = await _bell(client, prefix)
    assert len(bell) == 2
    assert {n["notification_id"]: n["read"] for n in bell}[read] is True  # not rewritten
    assert await client.exists(index=f"{prefix}system-config", id=warned_doc_id("c-warn-0005"))


@requires_opensearch
async def test_every_notice_of_a_run_goes_in_one_bulk_request(real_os, monkeypatch) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    real_bulk, real_index = client.bulk, client.index
    bulks: list[list[dict[str, Any]]] = []
    indexed: list[str] = []

    async def bulk(*args: Any, **kwargs: Any) -> Any:
        bulks.append(kwargs["body"])
        return await real_bulk(*args, **kwargs)

    async def index(*args: Any, **kwargs: Any) -> Any:
        indexed.append(kwargs["index"])
        return await real_index(*args, **kwargs)

    monkeypatch.setattr(client, "bulk", bulk)
    monkeypatch.setattr(client, "index", index)
    warning = {"c-warn-0007": (_ago(40), _ago(-5)), "c-warn-0008": (_ago(41), _ago(-4))}

    assert await notify_retiring(client, warning, now=NOW, prefix=prefix) == 2

    assert len(bulks) == 1
    creates = [a["create"]["_index"] for a in bulks[0][::2]]
    assert creates == [f"{prefix}{NOTIFICATIONS_INDEX}"] * 4  # 2 clusters x ann and sam
    assert f"{prefix}{NOTIFICATIONS_INDEX}" not in indexed  # no one-by-one writes are left
    assert len(await _bell(client, prefix)) == 4


@requires_opensearch
async def test_a_notice_the_store_refuses_fails_the_run_before_any_marker(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    warning = {"c-warn-0009": (_ago(40), _ago(-5))}
    blocked = {"index.blocks.write": True}
    await client.indices.put_settings(index=f"{prefix}{NOTIFICATIONS_INDEX}", body=blocked)
    try:
        with pytest.raises(BulkError):
            await notify_retiring(client, warning, now=NOW, prefix=prefix)
    finally:
        await client.indices.put_settings(
            index=f"{prefix}{NOTIFICATIONS_INDEX}", body={"index.blocks.write": None}
        )
    assert not await client.exists(index=f"{prefix}system-config", id=warned_doc_id("c-warn-0009"))
    # nothing marked it sent, so the next run announces it
    assert await notify_retiring(client, warning, now=NOW, prefix=prefix) == 1
    assert len(await _bell(client, prefix)) == 2


def _notify_failures() -> float:
    return REGISTRY.get_sample_value("javv_cluster_retirement_notify_failures_total") or 0.0


@requires_opensearch
async def test_a_failed_announcement_leaves_the_runs_retirements_standing(
    real_os, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, prefix = real_os

    async def unavailable(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("notifications unavailable")

    monkeypatch.setattr(cluster_retirement, "notify_retiring", unavailable)
    await _token(client, prefix, "c-due-0006", _ago(50))
    await _token(client, prefix, "c-warn-0006", _ago(40))
    await _token(client, prefix, "c-live-0006", _ago(1))
    before = _notify_failures()

    counts = await run_retirement_sweep(client, now=NOW, prefix=prefix)

    assert (counts["retired"], counts["announced"]) == (1, 0)
    assert _notify_failures() == before + 1


@requires_opensearch
async def test_a_cluster_that_scans_again_loses_its_notice(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    await _token(client, prefix, "c-warn-0007", _ago(40))
    await _token(client, prefix, "c-live-0007", _ago(1))
    await run_retirement_sweep(client, now=NOW, prefix=prefix)
    assert len(await _bell(client, prefix)) == 2

    await _token(client, prefix, "c-warn-0007", _ago(0.5))  # it scanned
    counts = await run_retirement_sweep(client, now=NOW, prefix=prefix)

    assert (counts["withdrawn"], counts["announced"]) == (1, 0)
    assert await _bell(client, prefix) == []
    assert not await client.exists(index=f"{prefix}system-config", id=warned_doc_id("c-warn-0007"))


@requires_opensearch
async def test_a_new_silence_replaces_the_notice_with_its_own_date(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    await _token(client, prefix, "c-warn-0008", _ago(40))
    await _token(client, prefix, "c-live-0008", _ago(1))
    await run_retirement_sweep(client, now=NOW, prefix=prefix)

    # it scanned once and went silent again, still inside the warning window
    await _token(client, prefix, "c-warn-0008", _ago(39))
    counts = await run_retirement_sweep(client, now=NOW, prefix=prefix)

    assert (counts["withdrawn"], counts["announced"]) == (1, 1)
    assert {(n["user_id"], n["ref"]) for n in await _bell(client, prefix)} == {
        ("ann", _ago(39 - 45).isoformat()),
        ("sam", _ago(39 - 45).isoformat()),
    }


@requires_opensearch
async def test_a_retired_cluster_keeps_its_notice(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    await _token(client, prefix, "c-warn-0009", _ago(40))  # retires 5 days from NOW
    await _token(client, prefix, "c-live-0009", _ago(1))
    await run_retirement_sweep(client, now=NOW, prefix=prefix)

    later = NOW + timedelta(days=5.5)  # due, and the live cluster still counts as scanning
    counts = await run_retirement_sweep(client, now=later, prefix=prefix)

    assert (counts["retired"], counts["withdrawn"]) == (1, 0)
    assert len(await _bell(client, prefix)) == 2
    # and a later run does not withdraw it either
    again = await run_retirement_sweep(client, now=later + timedelta(days=0.2), prefix=prefix)
    assert again["withdrawn"] == 0


@requires_opensearch
async def test_a_window_moved_past_the_warning_keeps_the_notice_for_that_silence(real_os) -> None:
    client, prefix = real_os
    await _people(client, prefix)
    await _token(client, prefix, "c-warn-0010", _ago(40))
    await _token(client, prefix, "c-live-0010", _ago(1))
    await run_retirement_sweep(client, now=NOW, prefix=prefix)

    # 60 days now: the warning starts 13 days from NOW; the silence is the same one
    await _put_window(client, prefix, warn_days=7, retire_after_days=60)
    counts = await run_retirement_sweep(client, now=NOW, prefix=prefix)
    assert (counts["withdrawn"], counts["announced"]) == (0, 0)
    assert len(await _bell(client, prefix)) == 2

    # back inside the warning, same silence: nothing new, and a dismissed notice stays dismissed
    first = (await _bell(client, prefix))[0]["notification_id"]
    await client.delete(
        index=f"{prefix}{NOTIFICATIONS_INDEX}", id=first, params={"refresh": "true"}
    )
    later = await run_retirement_sweep(client, now=NOW + timedelta(days=14), prefix=prefix)
    assert (later["withdrawn"], later["announced"]) == (0, 0)
    assert len(await _bell(client, prefix)) == 1


@requires_opensearch
async def test_a_failed_withdrawal_still_announces(
    real_os, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, prefix = real_os

    async def unavailable(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("store away")

    monkeypatch.setattr(cluster_retirement, "withdraw_stale", unavailable)
    await _people(client, prefix)
    await _token(client, prefix, "c-warn-0011", _ago(40))
    await _token(client, prefix, "c-live-0011", _ago(1))
    before = _notify_failures()

    counts = await run_retirement_sweep(client, now=NOW, prefix=prefix)

    assert (counts["withdrawn"], counts["announced"]) == (0, 1)
    assert _notify_failures() == before + 1
