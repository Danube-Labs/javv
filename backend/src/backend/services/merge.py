"""Partial-doc merge for the `findings` cache (D31/D16 — M3 slice 2).

Every scan refreshes the **scanner-owned** fields of a finding and NEVER touches the human/triage
fields — ingest must not reset an operator's `state`/`notes` (the M1 full-index write did exactly
that). The classification lives HERE and only here: the rebuild-state slice must import these same
allowlists, or merge and rebuild will diverge (CORRECTNESS-CONTRACT §6).

`first_seen_at` is upsert-only (a re-scan never moves it, D37/M13). The presence-field family moves
together (§7/§9): a finding re-appearing on a scan flips `present=true` and clears `resolved_at`.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.core.metrics import CAS_CONFLICTS
from backend.repositories.bulk import BulkError, bulk_write, race_backoff_delay

log = structlog.get_logger()

# refreshed on every scan (scanner-owned)
SCANNER_FIELDS = frozenset(
    {
        "image_repo",
        "tag",
        "namespaces",
        "severity",
        "severity_canonical",  # server-derived query key (D46/#274) — refreshed per scan
        "severity_rank",  # server-derived, but from scanner data — refreshed per scan
        "cvss",
        "fixable",
        "fixed_version",
        "epss",
        "kev",
        "ptype",  # M8d/B-1 — re-observed per scan; a v4 sweep heals v3-era nulls (D30)
        "locations",  # issue 1077: the files of the newest scan, as that scan found them
        "locations_total",
        "last_seen_at",
        "last_scan_run_id",
        "last_scan_order",
        "last_scan_at",
        "present",
        "resolved_at",  # presence family — cleared on re-appearance, set by reconcile
        "schema_version",
    }
)

# human/triage-owned — ingest NEVER writes these on an existing doc (D31)
HUMAN_FIELDS = frozenset(
    {"state", "vex_justification", "assignee", "notes", "pre_stale_status", "state_decision_id"}
)

# third family (M4/D5a): `disagree` is derived cross-scanner decoration — owned solely by
# services.disagreement.recompute_disagreement, deliberately in NEITHER allowlist so merges
# never overwrite it and rebuild-state recomputes it rather than replaying it

# newer-scan-wins per-doc guard (D40/audit M-1): on an EXISTING doc, apply the scanner fields only
# when strictly newer (`scan_order > last_scan_order`); else no-op. Closes the resurrection the
# per-digest watermark's check-then-write can't — `advance_watermark` and this cache write are
# separate awaits, so a delayed/out-of-order merge could otherwise overwrite a newer scan's row. On
# first sight the doc is absent, so the `upsert` inserts as-is (the script never runs for the create
# path — the watermark guards creates). `first_seen_at` is upsert-only either way.
_MERGE_SCRIPT = (
    "if (ctx._source.last_scan_order != null && params.f.last_scan_order != null "
    "&& params.f.last_scan_order <= ctx._source.last_scan_order) { ctx.op = 'noop'; return; } "
    "for (entry in params.f.entrySet()) { ctx._source[entry.getKey()] = entry.getValue(); }"
)


def merge_action(doc: dict[str, Any], *, index: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The `_bulk` update pair for one findings doc: a scripted update that refreshes the scanner
    fields only when the scan is newer (M-1 guard); `upsert` seeds the full doc (identity +
    `first_seen_at` + initial human state) on first sight."""
    partial = {k: v for k, v in doc.items() if k in SCANNER_FIELDS}
    partial["resolved_at"] = None  # re-appearance clears resolved-by-scan (presence family)
    return (
        {"update": {"_index": index, "_id": doc["finding_key"]}},
        {
            "script": {"lang": "painless", "source": _MERGE_SCRIPT, "params": {"f": partial}},
            "upsert": {**doc, "resolved_at": None},
        },
    )


# same sizing as reconcile's drain loop — the two guard the SAME race from opposite sides
_CONFLICT_RETRIES = 10


async def merge_findings(
    client: AsyncOpenSearch,
    actions: Sequence[dict[str, Any]],
    *,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    rng: random.Random | None = None,
) -> int:
    """Ingest 3b's writer: bulk merge with bounded re-issue of 409-conflicted pairs (issue 510).

    A 409 here is a concurrent reconcile `update_by_query` (or another merge) bumping the doc's
    version mid-bulk — the other arm of the commit race. Re-issuing is safe: `_MERGE_SCRIPT`
    self-guards on `scan_order`, so a re-run against the changed doc re-evaluates newer-wins and
    no-ops if the doc moved past us. Anything non-409 still raises from `bulk_write` unchanged."""
    sleep = sleep or asyncio.sleep
    rng = rng or random.Random()
    written = 0
    pending = list(actions)
    for attempt in range(_CONFLICT_RETRIES):
        got, conflicts = await bulk_write(client, pending, collect_conflicts=True)
        written += got
        if not conflicts:
            return written
        ids = {c["_id"] for c in conflicts}
        pending = [
            line
            for action, doc in zip(pending[::2], pending[1::2], strict=True)
            if action["update"]["_id"] in ids
            for line in (action, doc)
        ]
        CAS_CONFLICTS.labels("merge").inc()  # D40 early warning: multi-writer contention
        log.debug("merge: version conflicts, retrying", conflicts=len(ids))
        await sleep(rng.uniform(0.0, race_backoff_delay(attempt)))
    log.warning("merge: version conflicts did not drain", attempts=_CONFLICT_RETRIES)
    raise BulkError([{"status": "conflicts_did_not_drain", "count": len(pending) // 2}])
