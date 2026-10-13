"""The retirement bell (issue 765): when a cluster enters its warning window (`warn_days` before
automatic retirement), every user who can act on it, by changing its window or bringing it back
(`can_manage_settings`), gets one `cluster_retiring` notification. Once per silence, not once per
night: a `system-config` marker `retirement-warned:<cluster_id>` keeps the `silent_since` it was
sent for, so a dismissed notification (dismiss deletes it) is not sent again, and neither is one
for a settings change that moves the dates of the same silence. A cluster that scans and goes
silent again has a new `silent_since`, and is announced again.

Notification ids are derived from (cluster, user, silent_since) and written in one `_bulk` of
`create` actions, so a sweep that stopped between the notifications and the marker repeats none
still in the bell on its next run (one dismissed in between is written again).

A notice lives as long as its silence (operator ruling, 2026-10-08): when the cluster scans
again, or a return from retirement starts a new silence, its notices and marker are deleted, and
a later silence is announced afresh. A settings change that moves the dates keeps them. A retired
cluster keeps its notice; the bell row then says it has been retired."""

import contextlib
import hashlib
from datetime import UTC, datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.auth.capabilities import ROLES_INDEX
from backend.auth.principal import USERS_INDEX
from backend.query.paging import search_to_exhaustion
from backend.reports.models import NOTIFICATIONS_INDEX
from backend.repositories.bulk import bulk_write

log = structlog.get_logger()

NOTICE_TYPE = "cluster_retiring"
WARNED_PREFIX = "retirement-warned:"
_CAPABILITY = "can_manage_settings"


def warned_doc_id(cluster_id: str) -> str:
    return f"{WARNED_PREFIX}{cluster_id}"


def _notice_id(cluster_id: str, user_id: str, silent_since: datetime) -> str:
    key = f"{NOTICE_TYPE}|{cluster_id}|{user_id}|{silent_since.isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


async def settings_admins(client: AsyncOpenSearch, *, prefix: str = "") -> list[str]:
    """The enabled users holding `can_manage_settings`: their own capability list when it is
    denormalized on the user doc, else their role's bundle (the order sign-in resolves them)."""
    try:
        roles = await search_to_exhaustion(
            client,
            index=f"{prefix}{ROLES_INDEX}",
            body={"size": 100, "sort": [{"role": "asc"}], "query": {"match_all": {}}},
        )
        users = await search_to_exhaustion(
            client,
            index=f"{prefix}{USERS_INDEX}",
            body={
                "size": 500,
                "sort": [{"username": "asc"}],
                "_source": ["username", "role", "capabilities", "disabled"],
                "query": {"bool": {"must_not": [{"term": {"disabled": True}}]}},
            },
        )
    except NotFoundError:
        return []
    bundles = {r["role"]: set(r.get("capabilities") or []) for r in roles}

    def can_act(user: dict[str, Any]) -> bool:
        caps = user.get("capabilities")
        held = set(caps) if caps is not None else bundles.get(user.get("role") or "", set())
        return "*" in held or _CAPABILITY in held

    return [u["username"] for u in users if can_act(u)]


async def _already_warned(
    client: AsyncOpenSearch, silences: dict[str, datetime], prefix: str
) -> set[str]:
    resp = await client.mget(
        index=f"{prefix}system-config", body={"ids": [warned_doc_id(c) for c in silences]}
    )
    sent: set[str] = set()
    for doc in resp["docs"]:
        if not doc.get("found"):
            continue
        cid = doc["_source"]["cluster_id"]
        if doc["_source"]["value"].get("silent_since") == silences[cid].isoformat():
            sent.add(cid)
    return sent


async def notify_retiring(
    client: AsyncOpenSearch,
    warning: dict[str, tuple[datetime, datetime]],
    *,
    now: datetime,
    prefix: str = "",
) -> int:
    """Announce each cluster in `warning` ({cluster_id: (silent_since, retires_at)}) not yet
    announced for that silence. Returns how many clusters were announced."""
    if not warning:
        return 0
    sent = await _already_warned(client, {c: s for c, (s, _) in warning.items()}, prefix)
    due = {c: v for c, v in warning.items() if c not in sent}
    if not due:
        return 0
    recipients = await settings_admins(client, prefix=prefix)
    if not recipients:
        # no marker either: an admin added later still hears about this silence
        log.info(
            "cluster retirement not announced: no user holds the capability", clusters=len(due)
        )
        return 0
    actions: list[dict[str, Any]] = []
    for cid, (silent_since, retires_at) in sorted(due.items()):
        for user in recipients:
            notice_id = _notice_id(cid, user, silent_since)
            actions.append(
                {"create": {"_index": f"{prefix}{NOTIFICATIONS_INDEX}", "_id": notice_id}}
            )
            actions.append(
                {
                    "notification_id": notice_id,
                    "user_id": user,
                    "type": NOTICE_TYPE,
                    "ref": retires_at.isoformat(),
                    "cluster_id": cid,
                    "created_at": now.isoformat(),
                    "read": False,
                }
            )
    # a 409 is a notice sent by a run that stopped before its marker: collected, not rewritten.
    # Any other failed item raises, before any marker, so the next run sends the rest.
    await bulk_write(client, actions, collect_conflicts=True)
    for cid, (silent_since, _) in sorted(due.items()):
        await client.index(
            index=f"{prefix}system-config",
            id=warned_doc_id(cid),
            body={
                "key": warned_doc_id(cid),
                "cluster_id": cid,
                "value": {"silent_since": silent_since.isoformat()},
                "updated_at": datetime.now(UTC).isoformat(),
                "updated_by": "system",
            },
        )
        log.info("cluster retirement announced", cluster_id=cid, recipients=len(recipients))
    # the markers are found by search when a notice is withdrawn
    await client.indices.refresh(index=f"{prefix}{NOTIFICATIONS_INDEX},{prefix}system-config")
    return len(due)


async def withdraw_stale(
    client: AsyncOpenSearch, keep: dict[str, datetime | None], *, prefix: str = ""
) -> int:
    """Withdraw the notices of every announced cluster not in `keep` ({cluster_id: the
    silent_since its notice must be for, or None to keep it whatever it says}): its notifications
    first, then its marker, so a run that stops halfway withdraws the rest next time. Returns how
    many clusters' notices were withdrawn."""
    try:
        markers = await search_to_exhaustion(
            client,
            index=f"{prefix}system-config",
            body={
                "size": 500,
                "sort": [{"key": "asc"}],
                "query": {"prefix": {"key": WARNED_PREFIX}},
            },
        )
    except NotFoundError:
        return 0

    def stale(marker: dict[str, Any]) -> bool:
        cid = marker["cluster_id"]
        if cid not in keep:
            return True
        since = keep[cid]
        return since is not None and marker["value"].get("silent_since") != since.isoformat()

    gone = [m["cluster_id"] for m in markers if stale(m)]
    for cid in gone:
        notices = await search_to_exhaustion(
            client,
            index=f"{prefix}{NOTIFICATIONS_INDEX}",
            body={
                "size": 500,
                "sort": [{"notification_id": "asc"}],
                "_source": ["notification_id"],
                "query": {
                    "bool": {
                        "filter": [{"term": {"type": NOTICE_TYPE}}, {"term": {"cluster_id": cid}}]
                    }
                },
            },
        )
        for notice in notices:
            with contextlib.suppress(NotFoundError):  # dismissed meanwhile
                await client.delete(
                    index=f"{prefix}{NOTIFICATIONS_INDEX}", id=notice["notification_id"]
                )
        with contextlib.suppress(NotFoundError):
            await client.delete(index=f"{prefix}system-config", id=warned_doc_id(cid))
        log.info("cluster retirement notice withdrawn", cluster_id=cid, notices=len(notices))
    if gone:
        await client.indices.refresh(index=f"{prefix}{NOTIFICATIONS_INDEX}")
    return len(gone)
