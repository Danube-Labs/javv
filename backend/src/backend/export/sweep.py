"""The export sweep (M6 slices 5–6): a constant-memory full walk of one grid lens.

This is the SWEEP case of PIT + `search_after` (day-one rule): the PIT lives exactly as long
as the walk and is deleted in `finally` — success, error, or an abandoned consumer (a client
that disconnects mid-stream closes the generator, which runs the `finally`). No opaque cursor
here: the server owns the whole lifecycle, nothing PIT-shaped ever reaches the client.

Tenancy: pages are built through `tenant_query`, so the `cluster_id` term filter is
structurally present on the index-less PIT path (SEC-4) — same guard as the grid search.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.core.settings import get_settings
from backend.query.search import SearchFilters, build_search_body
from backend.sla.overdue import overdue_cutoffs
from backend.sla.policy import read_sla_policy
from backend.tenancy.read_path import tenant_query

log = structlog.get_logger()

_PAGE_SIZE = 500  # small pages (FR-13) — constant memory whatever the lens size


async def _cutoffs(
    client: AsyncOpenSearch, filters: SearchFilters, prefix: str
) -> dict[str, str] | None:
    """An `overdue` lens (issue 363) needs live-policy cutoffs; resolved once per call —
    the sweep computes them BEFORE the walk, so the whole export judges one deadline."""
    if filters.overdue is None:
        return None
    return overdue_cutoffs(await read_sla_policy(client, prefix=prefix), now=datetime.now(UTC))


async def count_lens(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: SearchFilters,
    prefix: str = "",
) -> int:
    """Cheap pre-count of the lens through the tenant read path (audit A-M6/#189) — lets an
    export enforce its row cap with a clean 413 BEFORE opening a PIT / streaming a body."""
    body = build_search_body(
        filters,
        size=0,
        sort="first_seen_at",
        order="asc",
        sla_cutoffs=await _cutoffs(client, filters, prefix),
        now=datetime.now(UTC),
    )
    del body["track_total_hits"]  # count has its own total; drop the search-only setting
    body = tenant_query(cluster_id, body)  # SEC-4 — the cluster filter is forced in
    resp = await client.count(index=f"{prefix}findings", body={"query": body["query"]})
    return int(resp["count"])


async def sweep_findings(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: SearchFilters,
    prefix: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Yield every finding doc matching the lens, one page at a time."""
    keep_alive = get_settings().search_pit_keep_alive
    sla_cutoffs = await _cutoffs(client, filters, prefix)  # frozen for the whole walk
    now = datetime.now(UTC)  # and the end of "new in range" too (issue 1291)
    pit_id = (
        await client.create_pit(index=f"{prefix}findings", params={"keep_alive": keep_alive})
    )["pit_id"]
    try:
        search_after: list[Any] | None = None
        while True:
            body = build_search_body(
                filters,
                size=_PAGE_SIZE,
                sort="first_seen_at",
                order="asc",
                search_after=search_after,
                sla_cutoffs=sla_cutoffs,
                now=now,
            )
            body = tenant_query(cluster_id, body)  # SEC-4 — the only guard on the PIT path
            body["pit"] = {"id": pit_id, "keep_alive": keep_alive}
            del body["track_total_hits"]  # a sweep never needs the count
            resp = await client.search(body=body)
            hits = resp["hits"]["hits"]
            for h in hits:
                yield h["_source"]
            if len(hits) < _PAGE_SIZE:
                return
            search_after = hits[-1]["sort"]
    finally:
        await client.delete_pit(body={"pit_id": [pit_id]})  # sweep over = PIT gone, always
