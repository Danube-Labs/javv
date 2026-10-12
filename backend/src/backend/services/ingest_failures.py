"""Failed-ingest records (issue 357, option 2): one doc per rejected push, in the per-cluster
append series `javv-ingest-failures-<cluster_id>` — the data behind scanner status's
failed-ingests table (When · Scanner · Image · Stage · Error).

Only pushes that got PAST the token check are recorded. The caller guarantees it: the 401 and
the 429 are decided before any token is known, and a write per anonymous request would let a
sender choose our write volume. Past the token, the per-token rate limit bounds this write.

Routing is the token's scope, never the payload's: a `scope_mismatch` envelope's self-declared
cluster is exactly the value that can't be trusted.

Recording is bookkeeping on a rejection that has already been decided, so it must never change
that rejection: every failure here is swallowed and logged, and the caller re-raises the original
response untouched. Stored text is capped and stripped of control characters — `image_ref` and
validation locations can carry sender-chosen strings.
"""

import re
from datetime import UTC, datetime
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch

from backend.core.metrics import INGEST_FAILURES_UNRECORDED
from backend.services.aliases import ensure_write_alias

log = structlog.get_logger()

SERIES = "javv-ingest-failures"
SCHEMA_VERSION = 1
MAX_TEXT = 512  # mirrors the envelope's own `image_ref` cap (models/envelope.py)

# post-auth rejection reason (the INGEST_REJECTED label) → where in the pipeline the push died
STAGES: dict[str, str] = {
    "too_large": "receive",
    "bad_gzip": "decode",
    "bad_json": "decode",
    "invalid_envelope": "validate",
    "unallocated_order": "validate",
    "clock_skew": "validate",
    "scope_mismatch": "authorize",
    "storage_error": "store",
}

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(value: str) -> str:
    return _CONTROL.sub(" ", value)[:MAX_TEXT]


def build_failure_doc(
    *,
    cluster_id: str,
    scanner: str,
    reason: str,
    status: int,
    error: str,
    image_ref: str | None,
    now: datetime,
    failure_id: str,
) -> dict[str, Any]:
    stamp = now.isoformat()
    return {
        "@timestamp": stamp,
        "ingested_at": stamp,  # server clock, the lifecycle retention basis like every series
        "failure_id": failure_id,
        "cluster_id": cluster_id,
        "scanner": scanner,
        "stage": STAGES[reason],
        "reason": reason,
        "status": status,
        "error": clean_text(error),
        "image_ref": None if image_ref is None else clean_text(image_ref),
        "schema_version": SCHEMA_VERSION,
    }


async def record_ingest_failure(
    client: AsyncOpenSearch,
    *,
    failure_id: str,
    cluster_id: str,
    scanner: str,
    reason: str,
    status: int,
    error: str,
    image_ref: str | None = None,
    prefix: str = "",
) -> None:
    """Append one failure doc under `failure_id` — the id the route already put on its
    `ingest rejected` line, so a table row and its log line join. Never raises; a miss is a
    warning plus `javv_ingest_failures_unrecorded_total`, because the table can't show its own
    gaps. `prefix` isolates index names (tests only)."""
    try:
        doc = build_failure_doc(
            cluster_id=cluster_id,
            scanner=scanner,
            reason=reason,
            status=status,
            error=error,
            image_ref=image_ref,
            now=datetime.now(UTC),
            failure_id=failure_id,
        )
        alias = f"{prefix}{SERIES}-{cluster_id}"
        await ensure_write_alias(client, alias)
        await client.index(index=alias, id=failure_id, body=doc)
    except Exception as exc:  # noqa: BLE001 — see the module docstring: log, never raise
        INGEST_FAILURES_UNRECORDED.labels(reason=reason).inc()
        log.warning(
            "ingest failure not recorded",
            failure_id=failure_id,
            cluster_id=cluster_id,
            scanner=scanner,
            reason=reason,
            status=status,
            error=clean_text(str(exc)),
        )
