"""Bulk triage (M5d, FR-7/D38-H8/SND-8) — one action over a FROZEN id-set, ONE audit row.

Flow: the selector is resolved to a **frozen `target_ids` set at submit time** (paged
`search_after`, complete — never a live selector), the single audit row is journaled FIRST
(journal-before-commit, task A M-3: an orphan row is replay-tolerated, an orphan change never),
then the patch applies via `_bulk` partial-doc updates with `retry_on_conflict` (SND-8 — a
concurrent scanner merge or single-triage write retries in place, no lost update). The row
carries the frozen ids + `result_hash`/`result_count` (D38/H8) — never a selector, never a
per-finding fan-out of rows.

Bulk is a direct human action: it clears `state_decision_id` (direct action > auto-rule, M5c)
whenever it sets `state`. Target validation is TARGET-based (FR-7 has no forbidden from→to
pairs): `stale` is system-only, `vex_justification` iff `not_affected` — validated once for the
whole action, not per finding.
"""

import hashlib
import json
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_field_change
from backend.repositories.bulk import bulk_write
from backend.triage.state_machine import (
    CISA_JUSTIFICATIONS,
    HUMAN_TARGET_STATES,
    TransitionError,
)

log = structlog.get_logger()

_FREEZE_PAGE = 10_000
_SELECTOR_FIELDS = ("cve_id", "image_digest", "severity", "state", "assignee")


class SelectorTooBroad(Exception):
    """`freeze_targets` aborted mid-paging: the selector matches more than the hard cap
    (audit A-Mc/#189). Raised the moment the accumulated set exceeds the cap — the freeze never
    materializes an unbounded id list. The route translates it to 413 ("selector too broad")."""


def validate_bulk_patch(patch: dict[str, Any]) -> None:
    """Target-based validation, once per action (message is user-facing, 422)."""
    if not patch:
        raise TransitionError("empty bulk patch — set at least one field")
    state = patch.get("state")
    vex = patch.get("vex_justification")
    if state == "stale":
        raise TransitionError("stale is system-only — set by the staleness sweep, never by hand")
    if state is not None and state not in HUMAN_TARGET_STATES:
        raise TransitionError(f"unknown target state {state!r}")  # A-M1: closed vocabulary
    if state == "not_affected":
        if vex not in CISA_JUSTIFICATIONS:
            raise TransitionError("not_affected requires a vex_justification (CISA five)")
    elif vex is not None:
        raise TransitionError("vex_justification is only valid with not_affected")


async def freeze_targets(
    client: AsyncOpenSearch,
    cluster_id: str,
    selector: dict[str, Any],
    *,
    max_targets: int,
    prefix: str = "",
) -> list[str]:
    """Resolve the selector to the frozen, complete, sorted id-set (D38/H8), bounded by
    `max_targets`: pull at most one-over-cap per page and raise `SelectorTooBroad` the instant the
    accumulated set exceeds the cap (count-don't-collect — never materialize the whole match)."""
    filters: list[dict[str, Any]] = [
        {"term": {"cluster_id": cluster_id}},
        {"term": {"present": True}},  # bulk acts on the "now" grid, never tombstones
    ]
    for field in _SELECTOR_FIELDS:
        if selector.get(field) is not None:
            filters.append({"term": {field: selector[field]}})
    index = f"{prefix}findings"
    await client.indices.refresh(index=index)
    page = min(_FREEZE_PAGE, max_targets + 1)  # never pull more than one-over-cap in a page
    body: dict[str, Any] = {
        "size": page,
        "sort": [{"finding_key": "asc"}],
        "query": {"bool": {"filter": filters}},
        "_source": False,
    }
    ids: list[str] = []
    while True:
        resp = await client.search(index=index, body=body)
        hits = resp["hits"]["hits"]
        ids += [h["_id"] for h in hits]
        if len(ids) > max_targets:  # bail during paging — the freeze memory stays bounded
            raise SelectorTooBroad(f"selector too broad — matches more than {max_targets} findings")
        if len(hits) < page:
            return ids
        body = {**body, "search_after": hits[-1]["sort"]}


# the query form of state_machine.holds_risk_accept: risk_accepted, or stale keeping it
_HOLDS_RISK_ACCEPT: dict[str, Any] = {
    "bool": {
        "should": [
            {"term": {"state": "risk_accepted"}},
            {
                "bool": {
                    "filter": [
                        {"term": {"state": "stale"}},
                        {"term": {"pre_stale_status": "risk_accepted"}},
                    ]
                }
            },
        ],
        "minimum_should_match": 1,
    }
}


async def count_risk_accepted(
    client: AsyncOpenSearch, target_ids: list[str], *, prefix: str = ""
) -> int:
    """How many of the frozen findings a state change would take off a risk-accept (issue 892
    ruling 6). Counted in pages, so each query stays bounded however large the freeze cap is."""
    count = 0
    for start in range(0, len(target_ids), _FREEZE_PAGE):
        page = target_ids[start : start + _FREEZE_PAGE]
        query = {"bool": {"filter": [{"ids": {"values": page}}, _HOLDS_RISK_ACCEPT]}}
        count += (await client.count(index=f"{prefix}findings", body={"query": query}))["count"]
    return count


def risk_accept_refusal(held: int, total: int) -> str:
    """The user-facing reason a bulk state change is refused (shown by the bulk bar)."""
    verb = "is" if held == 1 else "are"
    return (
        f"{held} of the {total} selected findings {verb} risk-accepted. Changing their state "
        "requires can_accept_audit_final."
    )


def result_hash(target_ids: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(target_ids)).encode()).hexdigest()


async def apply_bulk_triage(
    client: AsyncOpenSearch,
    *,
    actor: str,
    cluster_id: str,
    target_ids: list[str],
    patch: dict[str, Any],
    prefix: str = "",
) -> int:
    """Journal ONE row (first), then apply the patch to the frozen set. Returns docs updated."""
    if not target_ids:
        return 0
    await append_field_change(
        client,
        actor=actor,
        action="bulk_triage",
        entity_type="finding",
        entity_id=f"bulk:{result_hash(target_ids)[:16]}",
        field="bulk_patch",
        old_value=None,
        new_value=None,
        new_value_json={
            "patch": patch,
            "target_ids": sorted(target_ids),  # FROZEN ids, never a selector (D38/H8)
            "result_count": len(target_ids),
            "result_hash": result_hash(target_ids),
        },
        revision=1,
        cluster_id=cluster_id,
        target_ids=sorted(target_ids),  # what the finding page's audit read matches on
        prefix=prefix,
    )
    doc = dict(patch)
    if "state" in doc:
        doc["state_decision_id"] = None  # a direct human action reclaims state (M5c)
        if doc["state"] != "not_affected":
            doc["vex_justification"] = None  # the two-field VEX pairing
    index = f"{prefix}findings"
    actions: list[dict[str, Any]] = []
    for fk in target_ids:
        actions += (
            {"update": {"_index": index, "_id": fk, "retry_on_conflict": 3}},  # SND-8
            {"doc": doc},
        )
    written = await bulk_write(client, actions)
    await client.indices.refresh(index=index)
    log.info("bulk triage applied", cluster_id=cluster_id, targets=len(target_ids), updated=written)
    return written
