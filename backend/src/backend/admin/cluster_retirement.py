"""Retired clusters (issue 765): a cluster that is gone leaves the cluster list, the switcher and
All clusters, and keeps all of its data. One `system-config` doc per retired cluster,
`cluster-retirement:<cluster_id>`. Un-retiring keeps the doc and stamps `returned_at`: the
retirement sweep counts a returned cluster's silence from then, so an un-retire is not undone by
the next night's sweep.

A manual retire also revokes the cluster's tokens, so a scanner still pushing gets 401, and the
cluster comes back on a scan sent with a newly minted token. An automatic one (the retirement
sweep) leaves them alone, so a cluster that was only silent comes back on its next scan. Both
journal first (D17): the audit rows land before anything changes, and the retirement doc is
written last, so a retire that failed halfway is re-driven by a retry instead of reading as done."""

from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError
from opensearchpy.exceptions import ConflictError
from pydantic import BaseModel, ConfigDict, Field

from backend.audit.writer import append_auth_event, append_field_change
from backend.core.metrics import CAS_CONFLICTS
from backend.core.settings import get_settings
from backend.core.stored_settings import parse_stored_setting
from backend.query.paging import search_to_exhaustion

log = structlog.get_logger()

RETIREMENT_PREFIX = "cluster-retirement:"


def retirement_doc_id(cluster_id: str) -> str:
    return f"{RETIREMENT_PREFIX}{cluster_id}"


class DeleteUnderway(Exception):
    """A delete of the cluster has started: bringing it back would list a half-deleted cluster."""


class Retirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    retired_at: datetime
    by: str  # a user_id, or "system" for the sweep
    mode: Literal["manual", "auto"]
    returned_at: datetime | None = None  # set by un-retire; the record is kept for the sweep


async def _write_retirement(
    client: AsyncOpenSearch,
    cluster_id: str,
    retirement: Retirement,
    actor: str,
    prefix: str,
    cas: dict[str, Any] | None = None,
) -> None:
    await client.index(
        index=f"{prefix}system-config",
        id=retirement_doc_id(cluster_id),
        body={
            "key": retirement_doc_id(cluster_id),
            "cluster_id": cluster_id,
            "value": retirement.model_dump(mode="json"),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": actor,
        },
        params={"refresh": "true", **(cas or {})},
    )


async def read_retirements(client: AsyncOpenSearch, *, prefix: str = "") -> dict[str, Retirement]:
    """Every retirement record, returned ones included: `{cluster_id → Retirement}`. Whether a
    cluster is retired NOW is `jobs/cluster_retirement.is_retired`. Bounded by the fleet size."""
    try:
        docs = await search_to_exhaustion(
            client,
            index=f"{prefix}system-config",
            body={
                "size": 1000,
                "query": {"prefix": {"key": RETIREMENT_PREFIX}},
                "sort": [{"key": "asc"}],  # the doc id: unique, so a total order for the walk
            },
        )
    except NotFoundError:
        return {}
    return {
        doc["key"][len(RETIREMENT_PREFIX) :]: parse_stored_setting(
            Retirement, doc["value"], key=doc["key"]
        )
        for doc in docs
    }


async def _live_token_ids(client: AsyncOpenSearch, cluster_id: str, prefix: str) -> list[str]:
    ids: list[str] = []
    after: list[Any] | None = None
    while True:
        body: dict[str, Any] = {
            "size": 1000,
            "_source": False,
            "query": {
                "bool": {
                    "filter": [{"term": {"cluster_id": cluster_id}}],
                    "must_not": [{"term": {"disabled": True}}],
                }
            },
            "sort": [{"token_hash": "asc"}],  # unique + immutable, as the staleness sweep walks it
        }
        if after is not None:
            body["search_after"] = after
        hits = (await client.search(index=f"{prefix}system-tokens", body=body))["hits"]["hits"]
        ids.extend(h["_id"] for h in hits)
        if len(hits) < 1000:
            return ids
        after = hits[-1]["sort"]


async def retire_cluster(
    client: AsyncOpenSearch,
    cluster_id: str,
    *,
    actor: str,
    mode: Literal["manual", "auto"],
    at: datetime | None = None,
    prefix: str = "",
) -> Retirement:
    """Retire one cluster. The caller has checked it is known and not already retired. `at` is
    the sweep's read time, so a scan accepted after that read brings the cluster straight back."""
    await append_field_change(
        client,
        actor=actor,
        action="cluster_retire",
        entity_type="config",
        entity_id=f"cluster:{cluster_id}",
        field="retired",
        old_value=None,
        new_value=mode,
        revision=1,
        cluster_id=cluster_id,
        prefix=prefix,
    )
    token_ids = await _live_token_ids(client, cluster_id, prefix) if mode == "manual" else []
    for token_id in token_ids:
        await append_auth_event(
            client,
            actor=actor,
            action="token_revoke",
            entity_type="token",
            entity_id=token_id,
            cluster_id=cluster_id,
            strict=True,
            prefix=prefix,
        )
    for token_id in token_ids:
        await client.update(
            index=f"{prefix}system-tokens",
            id=token_id,
            body={"doc": {"disabled": True}},
            params={"refresh": "true"},
        )
    retirement = Retirement(retired_at=at or datetime.now(UTC), by=actor, mode=mode)
    await _write_retirement(client, cluster_id, retirement, actor, prefix)
    return retirement


async def unretire_cluster(
    client: AsyncOpenSearch,
    cluster_id: str,
    *,
    actor: str,
    at: datetime | None = None,
    expected: Retirement | None = None,
    prefix: str = "",
) -> bool:
    """Bring a retired cluster back to the list; False when there was nothing to bring back. Its
    revoked tokens stay revoked: a scanner needs a new token to push again. Raises
    `DeleteUnderway` when a delete of the cluster has started.

    `expected` is the record the caller planned on (the sweep's read): if another write replaced
    it since, such as an admin retiring the cluster by hand, nothing changes. The write itself is
    a seq_no CAS, so a retire landing between this read and the write is never overwritten. The
    delete marker is checked after that read, and a delete rewrites the record under its own
    CAS after marking its start, so of the two writes the later one always conflicts."""
    from backend.admin.cluster_delete import deletes_started  # it imports this module

    try:
        got = await client.get(index=f"{prefix}system-config", id=retirement_doc_id(cluster_id))
    except NotFoundError:
        return False
    current = parse_stored_setting(
        Retirement, got["_source"]["value"], key=retirement_doc_id(cluster_id)
    )
    if current.returned_at is not None or (expected is not None and current != expected):
        return False
    if cluster_id in await deletes_started(client, prefix=prefix):
        raise DeleteUnderway(cluster_id)
    await append_field_change(
        client,
        actor=actor,
        action="cluster_unretire",
        entity_type="config",
        entity_id=f"cluster:{cluster_id}",
        field="retired",
        old_value="retired",
        new_value=None,
        revision=1,
        cluster_id=cluster_id,
        prefix=prefix,
    )
    returned = current.model_copy(update={"returned_at": at or datetime.now(UTC)})
    cas = {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}
    try:
        await _write_retirement(client, cluster_id, returned, actor, prefix, cas)
    except ConflictError:
        # journaled, then lost to a concurrent write: that write is the newer truth
        CAS_CONFLICTS.labels("retirement").inc()
        log.warning("un-retire lost a write race", cluster_id=cluster_id)
        if cluster_id in await deletes_started(client, prefix=prefix):
            raise DeleteUnderway(cluster_id) from None
        return False
    return True


async def retired_record(
    client: AsyncOpenSearch, cluster_id: str, *, prefix: str = ""
) -> tuple[Retirement, dict[str, Any]] | None:
    """The cluster's retirement record and the CAS params of this read, for a delete that must
    not run on a cluster brought back meanwhile; None when there is no record."""
    try:
        got = await client.get(index=f"{prefix}system-config", id=retirement_doc_id(cluster_id))
    except NotFoundError:
        return None
    record = parse_stored_setting(
        Retirement, got["_source"]["value"], key=retirement_doc_id(cluster_id)
    )
    return record, {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}


async def confirm_retired(
    client: AsyncOpenSearch,
    cluster_id: str,
    held: tuple[Retirement, dict[str, Any]],
    *,
    actor: str,
    prefix: str = "",
) -> bool:
    """Rewrite the record unchanged under the CAS of `retired_record`'s read. False when another
    write landed since, such as a bring back, which then wins."""
    record, cas = held
    try:
        await _write_retirement(client, cluster_id, record, actor, prefix, cas)
    except ConflictError:
        CAS_CONFLICTS.labels("retirement").inc()
        return False
    return True


WINDOW_KEY = (
    "retirement"  # the fleet-wide default doc _id; per-cluster is `retirement:<cluster_id>`
)


def _window_id(cluster_id: str | None) -> str:
    return WINDOW_KEY if cluster_id is None else f"{WINDOW_KEY}:{cluster_id}"


def _seed_retire_after() -> float | None:
    return get_settings().cluster_retire_after_days or None  # 0 in the env = never


def _seed_warn_days() -> float:
    return get_settings().cluster_retirement_warn_days


class RetirementWindow(BaseModel):
    """How long a cluster may go without an accepted scan before the sweep retires it. `None` =
    never: a per-cluster override for a cluster scanned rarely on purpose, or the fleet default
    turned off. Tier-③ runtime config (D26 pattern: per-cluster override over a fleet default),
    seeded by `JAVV_CLUSTER_RETIRE_AFTER_DAYS` / `JAVV_CLUSTER_RETIREMENT_WARN_DAYS` until a
    value is saved, as the report TTL is."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retire_after_days: float | None = Field(default_factory=_seed_retire_after, gt=0)
    # how long before retirement the banner counts down and the admins' bell rings
    warn_days: float = Field(default_factory=_seed_warn_days, gt=0)


async def _read_window(
    client: AsyncOpenSearch, doc_id: str, prefix: str
) -> RetirementWindow | None:
    try:
        got = await client.get(index=f"{prefix}system-config", id=doc_id)
    except NotFoundError:
        return None
    return parse_stored_setting(RetirementWindow, got["_source"]["value"], key=doc_id)


async def has_window_override(
    client: AsyncOpenSearch, cluster_id: str, *, prefix: str = ""
) -> bool:
    return await _read_window(client, _window_id(cluster_id), prefix) is not None


async def read_retirement_window(
    client: AsyncOpenSearch, *, cluster_id: str | None = None, prefix: str = ""
) -> RetirementWindow:
    """The cluster's override if set, else the fleet default, else the env seed."""
    if cluster_id is not None:
        per_cluster = await _read_window(client, _window_id(cluster_id), prefix)
        if per_cluster is not None:
            return per_cluster
    return await _read_window(client, WINDOW_KEY, prefix) or RetirementWindow()


async def write_retirement_window(
    client: AsyncOpenSearch,
    window: RetirementWindow,
    *,
    updated_by: str,
    cluster_id: str | None = None,
    prefix: str = "",
) -> None:
    doc_id = _window_id(cluster_id)
    await client.index(
        index=f"{prefix}system-config",
        id=doc_id,
        body={
            "key": doc_id,
            "value": window.model_dump(),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": updated_by,
        },
        params={"refresh": "true"},
    )
