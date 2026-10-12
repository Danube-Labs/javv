"""Deleting a retired cluster (issue 765, ruled 2026-10-06): everything JAVV holds for one
`cluster_id`, except its audit rows. Manual only, `can_manage_retention`, and only after the
cluster is retired; the route checks both.

**What goes, in this order**, after a `system-config` marker `cluster-delete:<cluster_id>` that
says the delete has started (issue 778): while it stands, the cluster cannot be brought back, so a
half-deleted cluster is never put back on the list with part of its data gone.
1. its token docs, first, so a scanner still pushing gets 401 from here on;
2. its five history series (occurrences, scan-events, images, inventory runs, ingest failures),
   as whole-index drops. Indices are matched by exact name, `<series>-<cluster_id>-NNNNNN`, never
   by the `-<cluster_id>-*` wildcard alone: two valid ids can be prefixes of each other
   (`abcdefgh` and `abcdefgh-1234`), and the wildcard would take the other cluster's history.
   `<series>-<cluster_id>` itself is dropped too: a write to the alias landing between the drop
   and its re-creation auto-creates a concrete index under the alias's name;
3. its rows in the shared indices: `findings`, `javv-scan-watermarks`, `javv-scan-orders`,
   `system-decisions`, `system-reports` (with their chunks) and `system-notifications`;
4. its `system-config` docs: scan scope, the four per-cluster overrides, its retirement-warning
   marker, its registry name;
5. its retirement record, so a delete that stopped halfway still reads as a retired cluster and a
   retry finishes it;
6. last, the marker is stamped `finished_at` and kept as a tombstone.

**The next-night pass** (`recheck_deleted`, run by the retirement sweep; operator ruling on issue
778): a push already past its token check when the tokens went can still write after a step's
pass, and once the retirement record is gone no route reaches those rows. For every tombstone
whose cluster nothing names any more (no token, no registry name, no retirement record), the
pass re-runs steps 1 to 3, warns and counts when it found rows, and drops the tombstone once a
second pass finds nothing. A cluster onboarded again under the same id keeps its data and loses
the tombstone. A marker that never finished (a delete that stopped after its retirement record)
is handled the same way.

**`delete_by_query` here is a sanctioned use** (operator ruling on issue 765, named in the backend
rules): every query is an exact `term` on `cluster_id`, so it can only ever match that tenant (the
report chunks go by `report_id`, taken from that cluster's reports).
The append series are still whole-index drops. Every step can be re-run.

Snapshots taken before the delete still hold the data; deleting does not reach them."""

import contextlib
import re
from datetime import UTC, datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError
from opensearchpy.exceptions import ConflictError

from backend.admin.cluster_registry import read_registry, set_registry_name
from backend.admin.cluster_retirement import WINDOW_KEY, read_retirements, retirement_doc_id
from backend.admin.retirement_notices import warned_doc_id
from backend.admin.scan_scope import scan_scope_doc_id
from backend.audit.writer import append_field_change
from backend.core.metrics import CLUSTER_DELETE_LEFTOVERS
from backend.jobs.findings_cleanup import FINDINGS_CLEANUP_KEY
from backend.jobs.lifecycle import LIFECYCLE_KEY, SERIES
from backend.jobs.staleness import STALENESS_KEY
from backend.query.paging import search_to_exhaustion
from backend.reports.models import NOTIFICATIONS_INDEX, REPORT_CHUNKS_INDEX, REPORTS_INDEX

log = structlog.get_logger()

# the shared (non-partitioned) indices holding rows keyed by `cluster_id` (INDEX-MAP)
SHARED_INDICES = (
    "findings",
    "javv-scan-watermarks",
    "javv-scan-orders",
    "system-decisions",
    NOTIFICATIONS_INDEX,
)
_PER_CLUSTER_CONFIG = (STALENESS_KEY, LIFECYCLE_KEY, FINDINGS_CLEANUP_KEY, WINDOW_KEY)
_RETRIES = 5  # delete_by_query passes per index while concurrent writes conflict
DELETE_MARKER_PREFIX = "cluster-delete:"


def delete_marker_id(cluster_id: str) -> str:
    return f"{DELETE_MARKER_PREFIX}{cluster_id}"


async def _markers(client: AsyncOpenSearch, prefix: str) -> list[dict[str, Any]]:
    try:
        return await search_to_exhaustion(
            client,
            index=f"{prefix}system-config",
            body={
                "size": 500,
                "sort": [{"key": "asc"}],
                "query": {"prefix": {"key": DELETE_MARKER_PREFIX}},
            },
        )
    except NotFoundError:
        return []


def _finished(marker: dict[str, Any]) -> bool:
    return bool((marker.get("value") or {}).get("finished_at"))


async def deletes_started(client: AsyncOpenSearch, *, prefix: str = "") -> set[str]:
    """The clusters whose delete has started and not finished."""
    return {
        m["key"].removeprefix(DELETE_MARKER_PREFIX)
        for m in await _markers(client, prefix)
        if not _finished(m)
    }


async def _mark_started(client: AsyncOpenSearch, cluster_id: str, actor: str, prefix: str) -> None:
    """A retry keeps the first start and who made it. A finished marker is the tombstone of an
    earlier delete of the same id (the cluster was onboarded again): this delete replaces it, or
    the half-deleted cluster would read as deleted and could be brought back."""
    doc_id = delete_marker_id(cluster_id)
    now = datetime.now(UTC).isoformat()
    body = {
        "key": doc_id,
        "cluster_id": cluster_id,
        "value": {"started_at": now, "by": actor},
        "updated_at": now,
        "updated_by": actor,
    }
    index = f"{prefix}system-config"
    try:
        await client.index(
            index=index, id=doc_id, body=body, params={"op_type": "create", "refresh": "true"}
        )
        return
    except ConflictError:
        pass
    try:
        got = await client.get(index=index, id=doc_id)
    except NotFoundError:  # dropped since: start again from nothing
        return await _mark_started(client, cluster_id, actor, prefix)
    if not _finished(got["_source"]):
        return
    cas = {"if_seq_no": got["_seq_no"], "if_primary_term": got["_primary_term"]}
    # a conflict: another delete of this id replaced it first, and that start stands, as for a retry
    with contextlib.suppress(ConflictError):
        await client.index(index=index, id=doc_id, body=body, params={"refresh": "true", **cas})


class DeleteIncomplete(Exception):
    """A step could not finish (a contended doc, or rows still conflicting). Everything done so
    far stays done; a retry finishes it."""


def _history_index_re(prefix: str, series: str, cluster_id: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(prefix + series)}-{re.escape(cluster_id)}(-\d{{6}})?$")


async def _history_indices(client: AsyncOpenSearch, cluster_id: str, prefix: str) -> list[str]:
    found: list[str] = []
    for series in SERIES:
        base = f"{prefix}{series}-{cluster_id}"
        try:
            got = await client.indices.get(
                index=f"{base},{base}-*",
                params={"allow_no_indices": "true", "ignore_unavailable": "true"},
            )
        except NotFoundError:
            continue
        exact = _history_index_re(prefix, series, cluster_id)
        found.extend(sorted(name for name in got if exact.match(name)))
    return found


async def _delete_rows(client: AsyncOpenSearch, index: str, query: dict[str, Any]) -> int:
    deleted = 0
    for _ in range(_RETRIES):
        try:
            resp = await client.delete_by_query(
                index=index,
                body={"query": query},
                params={"conflicts": "proceed", "refresh": "true"},
            )
        except NotFoundError:
            return deleted
        deleted += int(resp.get("deleted", 0))
        if not resp.get("version_conflicts"):
            return deleted
    raise DeleteIncomplete(f"{index}: rows kept changing while being deleted")


async def _report_ids(client: AsyncOpenSearch, cluster_id: str, prefix: str) -> list[str]:
    try:
        docs = await search_to_exhaustion(
            client,
            index=f"{prefix}{REPORTS_INDEX}",
            body={
                "size": 1000,
                "_source": ["report_id"],
                "query": {"term": {"cluster_id": cluster_id}},
                "sort": [{"report_id": "asc"}],
            },
        )
    except NotFoundError:
        return []
    return [d["report_id"] for d in docs if d.get("report_id")]


async def _delete_data(client: AsyncOpenSearch, cluster_id: str, prefix: str) -> dict[str, int]:
    """Steps 1 to 3: the tokens, the history series and the shared-index rows. Returns what went."""
    term = {"term": {"cluster_id": cluster_id}}
    counts: dict[str, int] = {}

    counts["tokens"] = await _delete_rows(client, f"{prefix}system-tokens", term)

    indices = await _history_indices(client, cluster_id, prefix)
    for name in indices:
        with contextlib.suppress(NotFoundError):  # a retry after this drop landed
            await client.indices.delete(index=name)
            log.info("index dropped", index=name, cluster_id=cluster_id)
    counts["history_indices"] = len(indices)

    for index in SHARED_INDICES:
        counts[index] = await _delete_rows(client, f"{prefix}{index}", term)

    report_ids = await _report_ids(client, cluster_id, prefix)
    if report_ids:
        counts[REPORT_CHUNKS_INDEX] = await _delete_rows(
            client, f"{prefix}{REPORT_CHUNKS_INDEX}", {"terms": {"report_id": report_ids}}
        )
    counts[REPORTS_INDEX] = await _delete_rows(client, f"{prefix}{REPORTS_INDEX}", term)
    return counts


async def delete_cluster(
    client: AsyncOpenSearch, cluster_id: str, *, actor: str, prefix: str = ""
) -> dict[str, int]:
    """Delete everything for one retired cluster but its audit rows. Returns what went."""
    await append_field_change(
        client,
        actor=actor,
        action="cluster_delete",
        entity_type="config",
        entity_id=f"cluster:{cluster_id}",
        field="deleted",
        old_value=None,
        new_value="deleted",
        revision=1,
        cluster_id=cluster_id,
        prefix=prefix,
    )
    await _mark_started(client, cluster_id, actor, prefix)
    counts = await _delete_data(client, cluster_id, prefix)

    config_ids = [scan_scope_doc_id(cluster_id), warned_doc_id(cluster_id)] + [
        f"{k}:{cluster_id}" for k in _PER_CLUSTER_CONFIG
    ]
    for doc_id in config_ids:
        with contextlib.suppress(NotFoundError):
            await client.delete(
                index=f"{prefix}system-config", id=doc_id, params={"refresh": "true"}
            )
    if not await set_registry_name(client, cluster_id, None, actor=actor, prefix=prefix):
        raise DeleteIncomplete("the cluster registry stayed contended")

    with contextlib.suppress(NotFoundError):
        await client.delete(
            index=f"{prefix}system-config",
            id=retirement_doc_id(cluster_id),
            params={"refresh": "true"},
        )
    await _stamp(client, cluster_id, prefix, finished_at=datetime.now(UTC).isoformat())
    log.info("cluster deleted", cluster_id=cluster_id, counts=counts)
    return counts


async def _stamp(client: AsyncOpenSearch, cluster_id: str, prefix: str, **fields: str) -> None:
    with contextlib.suppress(NotFoundError):
        await client.update(
            index=f"{prefix}system-config",
            id=delete_marker_id(cluster_id),
            body={"doc": {"value": fields}},
            params={"refresh": "true"},
        )


async def _drop(client: AsyncOpenSearch, cluster_id: str, prefix: str) -> None:
    with contextlib.suppress(NotFoundError):
        await client.delete(
            index=f"{prefix}system-config",
            id=delete_marker_id(cluster_id),
            params={"refresh": "true"},
        )


async def recheck_deleted(
    client: AsyncOpenSearch, *, now: datetime | None = None, prefix: str = ""
) -> dict[str, int]:
    """The next-night pass over deleted clusters (module docstring). Returns counts
    {rechecked, with_leftovers, dropped}."""
    out = {"rechecked": 0, "with_leftovers": 0, "dropped": 0}
    marks = await _markers(client, prefix)
    if not marks:
        return out
    at = (now or datetime.now(UTC)).isoformat()
    names = await read_registry(client, prefix=prefix)
    retirements = await read_retirements(client, prefix=prefix)
    for mark in marks:
        cluster_id = mark["key"].removeprefix(DELETE_MARKER_PREFIX)
        tokens = await client.count(
            index=f"{prefix}system-tokens",
            body={"query": {"term": {"cluster_id": cluster_id}}},
            params={"ignore_unavailable": "true"},
        )
        if cluster_id in retirements or cluster_id in names or tokens["count"]:
            # named again after its delete: its data is new, keep it. Unfinished: the delete,
            # or its retry from the route, still owns it
            if _finished(mark):
                await _drop(client, cluster_id, prefix)
                out["dropped"] += 1
            continue
        counts = await _delete_data(client, cluster_id, prefix)
        out["rechecked"] += 1
        if any(counts.values()):
            out["with_leftovers"] += 1
            CLUSTER_DELETE_LEFTOVERS.inc()
            log.warning("cluster delete leftovers removed", cluster_id=cluster_id, counts=counts)
        elif (mark.get("value") or {}).get("rechecked_at"):
            await _drop(client, cluster_id, prefix)
            out["dropped"] += 1
            continue
        finished = (mark.get("value") or {}).get("finished_at") or at
        await _stamp(client, cluster_id, prefix, finished_at=finished, rechecked_at=at)
    return out
