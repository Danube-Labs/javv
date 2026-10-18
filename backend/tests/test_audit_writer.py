"""The structured audit writer (M5b slice 2, D32/D17) — one immutable row per field change,
append-only BY CONSTRUCTION (`_id` = `event_id`, `op_type=create` — an overwrite is impossible,
not just forbidden). Replay ordering: `(@timestamp, event_id)` across entities, `revision` for
same-`(entity, field)` causality (D40/H-r3). Absorbs M5a's thin auth appender (same rows, one
writer). Real OpenSearch, prefix-isolated."""

import pytest

from backend.audit.writer import (
    AUDIT_SCHEMA_VERSION,
    append_auth_event,
    append_field_change,
)
from os_env import requires_opensearch

pytestmark = requires_opensearch


async def _rows(client, prefix) -> list[dict]:
    await client.indices.refresh(index=f"{prefix}system-audit-log-*")
    hits = await client.search(
        index=f"{prefix}system-audit-log-*", body={"size": 100, "query": {"match_all": {}}}
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


async def test_field_change_row_carries_the_full_d32_contract(real_os) -> None:
    client, prefix = real_os

    event_id = await append_field_change(
        client,
        actor="alice",
        action="risk_accept",
        entity_type="finding",
        entity_id="fk-1",
        finding_key="fk-1",
        field="state",
        old_value="open",
        new_value="risk_accepted",
        revision=7,
        cluster_id="c-1",
        prefix=prefix,
    )

    rows = await _rows(client, prefix)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_id"] == event_id and row["@timestamp"]  # the ordering pair (D39)
    assert row["actor"] == "alice" and row["action"] == "risk_accept"
    assert (row["entity_type"], row["entity_id"], row["finding_key"]) == ("finding", "fk-1", "fk-1")
    assert (row["field"], row["field_type"]) == ("state", "scalar")
    assert (row["old_value"], row["new_value"]) == ("open", "risk_accepted")
    assert row["revision"] == 7  # same-(entity,field) causal order (D40/H-r3)
    assert row["cluster_id"] == "c-1"
    assert row["schema_version"] == AUDIT_SCHEMA_VERSION


async def test_target_ids_ride_the_row_only_when_a_caller_gives_them(real_os) -> None:
    # issue 912: a bulk row names its targets at the top level, where a term query reaches them
    client, prefix = real_os
    common: dict = dict(
        actor="alice",
        entity_type="finding",
        field="state",
        old_value=None,
        new_value=None,
        revision=1,
        cluster_id="c-1",
        prefix=prefix,
    )
    await append_field_change(
        client, action="bulk_triage", entity_id="bulk:1", target_ids=["fk-1", "fk-2"], **common
    )
    await append_field_change(client, action="acknowledge", entity_id="fk-3", **common)

    rows = {r["entity_id"]: r for r in await _rows(client, prefix)}
    assert rows["bulk:1"]["target_ids"] == ["fk-1", "fk-2"]
    assert "target_ids" not in rows["fk-3"]


async def test_notes_are_text_typed(real_os) -> None:
    client, prefix = real_os
    await append_field_change(
        client,
        actor="alice",
        action="note",
        entity_type="finding",
        entity_id="fk-1",
        finding_key="fk-1",
        field="notes",
        old_value=None,
        new_value="looked into it",
        revision=2,
        cluster_id="c-1",
        prefix=prefix,
    )
    (row,) = await _rows(client, prefix)
    assert row["field_type"] == "text"
    assert row.get("old_value") is None  # first write — no before-image


async def test_rows_are_append_only_by_construction(real_os) -> None:
    # the row _id IS the event_id and writes use op_type=create — a second write under the same
    # identity cannot silently overwrite history (SEC-1's create-only role is the deploy backstop)
    client, prefix = real_os
    event_id = await append_field_change(
        client,
        actor="alice",
        action="assign",
        entity_type="finding",
        entity_id="fk-1",
        finding_key="fk-1",
        field="assignee",
        old_value=None,
        new_value="bob",
        revision=1,
        cluster_id="c-1",
        prefix=prefix,
    )
    from opensearchpy.exceptions import ConflictError

    with pytest.raises(ConflictError):
        await client.index(
            index=f"{prefix}system-audit-log",
            id=event_id,
            body={"event_id": event_id, "actor": "mallory"},
            params={"op_type": "create"},
        )


async def test_append_is_immediately_searchable(real_os) -> None:
    # read-your-writes (A-m2/#191 pattern: WRITES refresh, reads never do): the detail screen
    # refetches its activity feed right after a triage save — a journal row that only turns up
    # after the next refresh tick looks like a lost action to the operator.
    client, prefix = real_os
    await append_field_change(
        client,
        actor="alice",
        action="not_affected",
        entity_type="finding",
        entity_id="fk-1",
        finding_key="fk-1",
        field="state",
        old_value="open",
        new_value="not_affected",
        revision=3,
        cluster_id="c-1",
        prefix=prefix,
    )
    hits = await client.search(  # NO index refresh — exactly what the /audit read path sees
        index=f"{prefix}system-audit-log-*", body={"size": 10, "query": {"match_all": {}}}
    )
    assert hits["hits"]["total"]["value"] == 1


async def test_the_absorbed_auth_appender_writes_the_same_shape(real_os) -> None:
    client, prefix = real_os

    await append_auth_event(
        client, actor="alice", action="login", entity_type="user", entity_id="alice", prefix=prefix
    )

    (row,) = await _rows(client, prefix)
    assert row["action"] == "login" and row["entity_type"] == "user"
    assert row["schema_version"] == AUDIT_SCHEMA_VERSION
    assert row["event_id"] and row["@timestamp"]


def test_no_writer_stamps_the_legacy_fleet_literal() -> None:
    """A fleet-wide row is written with no cluster_id, the class the Audit screen's reader was
    built for (issue 559). `"fleet"` survives only as the reader's legacy constant, for rows
    written before the fix; a writer passing it again would bring back the second spelling."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "backend"
    stamp = re.compile(r"""cluster_id\s*=\s*[^,\n]*["']fleet["']""")
    offenders = [
        f"{path.relative_to(src)}:{lineno}"
        for path in sorted(src.rglob("*.py"))
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if stamp.search(line)
    ]
    assert offenders == []
