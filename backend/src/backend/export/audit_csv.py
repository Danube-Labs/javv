"""Streaming CSV export of the audit lens (M9d, operator ruling — the prototype's Export CSV).

Same contract as the findings export: constant-memory PIT sweep over the current lens, every
cell through `sanitize_cell` (CSV injection), nothing buffers the whole result. Rows carry the
read-time decoration (`decorate_rows` per page), flattened into the finding's identity columns
— empty once the doc aged out, exactly like the screen."""

import csv
import io
from collections.abc import AsyncIterator
from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.core.settings import get_settings
from backend.export.csv_stream import csv_line
from backend.query.audit import (
    AuditFilters,
    audit_tenant_query,
    build_audit_body,
    decorate_rows,
)

_PATTERN = "system-audit-log-*"
_PAGE_SIZE = 500

AUDIT_CSV_COLUMNS = (
    "@timestamp",
    "actor",
    "action",
    "entity_type",
    "entity_id",
    "cve_id",
    "image_repo",
    "image_digest",
    "scanner",
    "package_name",
    "severity_canonical",
    "decision_type",
    "field",
    "old_value",
    "new_value",
    "revision",
    "cluster_id",
)


_DECO_COLS = (
    "cve_id",
    "image_repo",
    "image_digest",
    "scanner",
    "package_name",
    "severity_canonical",
)


def _flat(row: dict[str, Any]) -> list[Any]:
    deco = row.get("finding") or {}
    decision = row.get("decision") or {}
    merged = {
        **row,
        **{k: deco.get(k) for k in _DECO_COLS if deco},
        **(
            {"cve_id": decision.get("cve_id"), "decision_type": decision.get("type")}
            if decision
            else {}
        ),
    }
    return [merged.get(col) for col in AUDIT_CSV_COLUMNS]


async def count_audit_lens(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: AuditFilters,
    account_events: bool,
    prefix: str = "",
) -> int:
    """Cheap pre-count so the export can 413 BEFORE opening a PIT (audit A-M6 pattern)."""
    body = build_audit_body(filters, size=0)
    del body["track_total_hits"]
    del body["sort"]
    body = audit_tenant_query(cluster_id, body, account_events=account_events)
    resp = await client.count(index=f"{prefix}{_PATTERN}", body={"query": body["query"]})
    return int(resp["count"])


async def stream_audit_csv(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: AuditFilters,
    account_events: bool,
    prefix: str = "",
) -> AsyncIterator[str]:
    """Header, then one decorated, sanitized line per event — newest first, never buffered."""
    # the header cells are OUR constants, not data — `csv_line` would apostrophe-quote
    # `@timestamp` as a formula trigger
    header = io.StringIO()
    csv.writer(header, lineterminator="\n").writerow(AUDIT_CSV_COLUMNS)
    yield header.getvalue()
    keep_alive = get_settings().search_pit_keep_alive
    pit_id = (
        await client.create_pit(index=f"{prefix}{_PATTERN}", params={"keep_alive": keep_alive})
    )["pit_id"]
    try:
        search_after: list[Any] | None = None
        while True:
            body = build_audit_body(filters, size=_PAGE_SIZE, search_after=search_after)
            body = audit_tenant_query(cluster_id, body, account_events=account_events)
            body["pit"] = {"id": pit_id, "keep_alive": keep_alive}
            resp = await client.search(body=body)
            hits = resp["hits"]["hits"]
            if not hits:
                return
            rows = [h["_source"] for h in hits]
            await decorate_rows(client, cluster_id=cluster_id, rows=rows, prefix=prefix)
            for row in rows:
                yield csv_line(_flat(row))
            if len(hits) < _PAGE_SIZE:
                return
            search_after = hits[-1]["sort"]
    finally:
        await client.delete_pit(body={"pit_id": [pit_id]})
