"""scan_order allocation (D45) — the backend-minted, per-`(cluster_id, scanner)` ordering key.

The counter doc lives in `javv-scan-orders` (its own tiny mutable index — AUTHORITATIVE, unlike the
derived watermarks: rebuild-state never touches it; see CORRECTNESS-CONTRACT §2). Allocation is a
CAS loop on `_seq_no`/`_primary_term`, with a **forward-only self-heal**: the allocation base is
`max(counter, max committed scan_order in the catalog)`, so a restored/stale/fresh counter can never
re-issue an order the catalog already committed (and existing clusters transition seamlessly off the
old `time.time_ns()` orders — the sequence continues above them). Gaps from crashed cycles are fine:
the contract is monotonicity, not density.
"""

import asyncio
import random
from datetime import UTC, datetime
from typing import Any

from opensearchpy import AsyncOpenSearch, ConflictError, NotFoundError

from backend.core.metrics import CAS_CONFLICTS

INDEX = "javv-scan-orders"
# generous: real contention is ~1 (one CronJob per scanner, Forbid), but the CAS must also
# survive pathological races (the keystone test runs 10 allocators at once)
_CAS_RETRIES = 32


def _doc_id(cluster_id: str, scanner: str) -> str:
    return f"{cluster_id}:{scanner}"


def _doc(cluster_id: str, scanner: str, order: int) -> dict[str, Any]:
    return {
        "cluster_id": cluster_id,
        "scanner": scanner,
        "max_allocated_scan_order": order,
        "allocated_at": datetime.now(UTC).isoformat(),
        "schema_version": 1,
    }


async def _max_committed(
    client: AsyncOpenSearch, cluster_id: str, scanner: str, *, prefix: str = ""
) -> int:
    """The highest committed `scan_order` in the catalog (0 if none) — the self-heal floor.

    Read via sort + `_source`, NEVER a `max` metric agg (#257): metric aggs return doubles, and a
    pre-D45 `time.time_ns()`-era order (~1.75e18) exceeds float64's 53-bit mantissa — the floor
    could round DOWN and re-issue a committed order after a stale-counter restore. Sort compares
    the long field natively and `_source` returns the exact JSON integer."""
    resp = await client.search(
        index=f"{prefix}javv-scan-events-{cluster_id}-*",
        body={
            "size": 1,
            "query": {"term": {"scanner": scanner}},
            "sort": [{"scan_order": "desc"}],
            "_source": ["scan_order"],
        },
        params={"ignore_unavailable": "true"},
    )
    hits = resp["hits"]["hits"]
    return int(hits[0]["_source"]["scan_order"]) if hits else 0


async def max_allocated(
    client: AsyncOpenSearch, cluster_id: str, scanner: str, *, prefix: str = ""
) -> int:
    """The highest order `allocate_scan_order` has handed out for the pair; 0 before any. A
    get by id, so an allocation made a moment ago is already seen."""
    try:
        got = await client.get(index=f"{prefix}{INDEX}", id=_doc_id(cluster_id, scanner))
    except NotFoundError:
        return 0
    return int(got["_source"]["max_allocated_scan_order"])


async def allocate_scan_order(
    client: AsyncOpenSearch, cluster_id: str, scanner: str, *, prefix: str = ""
) -> int:
    """Allocate the next `scan_order` for `(cluster_id, scanner)` — strictly increasing, never
    reused, never a clock (D45). Raises after exhausted CAS retries (caller surfaces a 5xx; the
    scanner treats that as fail-closed and skips the cycle)."""
    index = f"{prefix}{INDEX}"
    doc_id = _doc_id(cluster_id, scanner)
    committed = await _max_committed(client, cluster_id, scanner, prefix=prefix)

    for _ in range(_CAS_RETRIES):
        try:
            got = await client.get(index=index, id=doc_id)
        except NotFoundError:
            order = committed + 1
            try:
                await client.index(
                    index=index,
                    id=doc_id,
                    body=_doc(cluster_id, scanner, order),
                    params={"op_type": "create", "refresh": "true"},
                )
                return order
            except ConflictError:
                continue  # another allocator created it first — retry via the get path
        order = max(int(got["_source"]["max_allocated_scan_order"]), committed) + 1
        try:
            await client.index(
                index=index,
                id=doc_id,
                body=_doc(cluster_id, scanner, order),
                params={
                    "if_seq_no": got["_seq_no"],
                    "if_primary_term": got["_primary_term"],
                    "refresh": "true",
                },
            )
            return order
        except ConflictError:
            CAS_CONFLICTS.labels("scan_orders").inc()  # M-3 (#220)
            await asyncio.sleep(random.uniform(0, 0.02))  # jitter so racers don't lockstep
            continue  # lost the CAS race — re-read and retry
    raise RuntimeError("scan-order allocation: CAS retries exhausted")
