"""M7 slice 3 (#32) — the throttled report drain: claim → stream the export → chunk → publish.

Broker-free queue worker, run by the backend's scheduler (`jobs/scheduler.py`, issue 691) or by
hand: `uv run python -m backend.jobs.report_drain`. Each cycle drains due jobs one at a time:

  claim (OCC, fresh fencing `attempt_id`) → stream via M6's constant-memory export engine,
  sleeping `JAVV_REPORT_DRAIN_SLEEP_MS` per page so a big run never starves ingest (the PLAN
  gate) → write ~5 MiB chunks, heartbeating on every flush (a lost lease aborts mid-stream —
  the reclaimer owns the job now, our chunks are orphans for the sweep) → CAS-finalize `done`
  on our attempt_id (M7-r2: a fenced publish is rejected) → ring the bell (`report_ready`).

Failures finalize `failed` with the reason — over the byte ceiling, an unknown format, or a
filter history cannot answer. An `as_of_t` export is UNPARKED (M8b slice 4, #34): the drain
reconstructs the rows at T through the AsOfTReader (paged, throttled like any export) and
serializes them through the same CSV/VEX pipeline — results labelled as-scanned by construction
(occurrence-era fields; `kev`/`epss`/`image_repo` are null at a past T).
"""

import asyncio
import json
import socket
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch
from pydantic import ValidationError

from backend.admin.report_ttl import read_report_ttl_hours
from backend.core.opensearch_client import build_client
from backend.core.settings import get_settings
from backend.export.csv_stream import stream_csv
from backend.export.sweep import sweep_findings
from backend.export.vex import to_cyclonedx, to_openvex
from backend.query.search import SearchFilters
from backend.reports.claim import ClaimedJob, claim_next
from backend.reports.lease import finalize, heartbeat
from backend.reports.models import DONE, FAILED, NOTIFICATIONS_INDEX
from backend.reports.storage import ExportTooLarge, FencedOut, write_chunks
from backend.triage.bulk import apply_bulk_triage, validate_bulk_patch
from backend.triage.bulk_routes import BulkPatch

log = structlog.get_logger()

_THROTTLE_EVERY_ROWS = 500  # matches the sweep's internal page size — one sleep per page


def _filters_from_params(params: dict[str, Any]) -> SearchFilters:
    """The stored `params` blob → the M6 lens. Fields mirror 1:1 (asserted by test)."""
    known = {f for f in SearchFilters.__dataclass_fields__}
    return SearchFilters(**{k: v for k, v in params.items() if k in known})


def _checked_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """The enqueue route's checks, again: a job queued before the route checked its patch
    (issue 854) can hold any field, and `apply_bulk_triage` copies every key onto each finding.
    The reason names the field, never its value, because the job's `error` is shown to the user."""
    try:
        BulkPatch.model_validate(patch)
    except ValidationError as exc:
        reasons = ", ".join(
            f"{'.'.join(str(part) for part in error['loc'])} {error['type']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ValueError(f"patch not valid: {reasons}") from None
    validate_bulk_patch(patch)
    return patch


async def _throttled(pieces: AsyncIterator[str], sleep_ms: int) -> AsyncIterator[str]:
    rows = 0
    async for piece in pieces:
        yield piece
        rows += 1
        if sleep_ms and rows % _THROTTLE_EVERY_ROWS == 0:
            await asyncio.sleep(sleep_ms / 1000)


async def _rows_at(
    client: AsyncOpenSearch, *, cluster_id: str, t: datetime, filters: SearchFilters, prefix: str
) -> AsyncIterator[dict[str, Any]]:
    """The as-of-T export sweep: reconstructed rows via the reader's stateless pages — the
    reader re-validates the filters (a `kev` filter at past T raises → the job fails loud)."""
    from backend.query.as_of_t import AsOfTQuery

    reader = AsOfTQuery()  # the drain is its own process — no app lifespan/registry here
    # ONE reconstruction for the whole sweep (F-09) — paging findings_page rebuilt and
    # re-sorted the entire cluster per 500 rows; the snapshot is the same list, held once
    rows = await reader.findings_snapshot(
        client,
        cluster_id=cluster_id,
        t=t,
        filters=filters,
        sort="severity_rank",
        order="desc",
        prefix=prefix,
    )
    for row in rows:
        yield row


async def _csv_pieces_at(
    client: AsyncOpenSearch, *, cluster_id: str, t: datetime, filters: SearchFilters, prefix: str
) -> AsyncIterator[str]:
    from backend.export.csv_stream import CSV_COLUMNS, csv_line

    yield csv_line(CSV_COLUMNS)
    async for doc in _rows_at(client, cluster_id=cluster_id, t=t, filters=filters, prefix=prefix):
        yield csv_line([doc.get(col) for col in CSV_COLUMNS])


async def _vex_pieces(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: SearchFilters,
    fmt: str,
    t: datetime | None = None,
    prefix: str = "",
) -> AsyncIterator[str]:
    # a VEX document is one JSON object — built in memory (statements are small), then chunked.
    # The byte ceiling still bounds the OUTPUT; CSV is the huge-export path.
    if (
        filters.scanner is None
    ):  # enqueue validates this (per-scanner is sacred) — hand-written docs
        raise ValueError("VEX export requires a scanner filter (per-scanner is sacred)")
    if t is not None:  # as-of-T: the reconstructed rows feed the same serializers (M8b)
        findings = [
            doc
            async for doc in _rows_at(
                client, cluster_id=cluster_id, t=t, filters=filters, prefix=prefix
            )
        ]
    else:
        findings = [
            doc async for doc in sweep_findings(client, cluster_id=cluster_id, filters=filters)
        ]
    serialize = to_openvex if fmt == "openvex" else to_cyclonedx
    yield json.dumps(
        serialize(
            findings,
            cluster_id=cluster_id,
            scanner=filters.scanner,
            generated_at=datetime.now(UTC),
        )
    )


async def _ring_bell(client: AsyncOpenSearch, job: ClaimedJob, *, prefix: str = "") -> None:
    doc = job.doc
    # ONE id for both _id and notification_id — the list serves notification_id, mark-read
    # gets by _id; two values would make every real notification unmarkable (404)
    notification_id = uuid.uuid4().hex
    await client.index(
        index=f"{prefix}{NOTIFICATIONS_INDEX}",
        id=notification_id,
        body={
            "notification_id": notification_id,
            "user_id": doc["requested_by"],
            "type": "report_ready",
            "ref": job.report_id,
            "cluster_id": doc["cluster_id"],
            "created_at": datetime.now(UTC).isoformat(),
            "read": False,
        },
        params={"refresh": "true"},
    )


async def run_job(client: AsyncOpenSearch, job: ClaimedJob, *, prefix: str = "") -> bool:
    """Execute one claimed job to a terminal state. Returns True when OUR publish landed."""
    settings = get_settings()
    doc = job.doc
    boundlog = log.bind(report_id=job.report_id, kind=doc.get("kind"))

    as_of_t = datetime.fromisoformat(doc["as_of_t"]) if doc.get("as_of_t") else None
    params = doc.get("params") or {}
    cluster_id = doc["cluster_id"]

    if doc.get("kind") == "bulk_triage":
        # slice 5 (A-Mc): apply the ENQUEUE-frozen set — never a live selector at drain time.
        # apply_bulk_triage journals first (one row, frozen ids + result_hash); the partial-doc
        # patch is idempotent, so a reclaimed retry re-applies safely (a second audit row with
        # the same result_hash is replay-tolerated — an orphan CHANGE is what's forbidden).
        try:
            updated = await apply_bulk_triage(
                client,
                actor=doc["requested_by"],
                cluster_id=cluster_id,
                target_ids=params.get("target_ids") or [],
                patch=_checked_patch(params.get("patch") or {}),
                prefix=prefix,
            )
        except Exception as exc:
            await finalize(
                client,
                job.report_id,
                job.attempt_id,
                status=FAILED,
                error=f"{type(exc).__name__}: {exc}",
                prefix=prefix,
            )
            boundlog.error("report drain: bulk_triage job failed", error=str(exc))
            return False
        expires_at = (
            datetime.now(UTC) + timedelta(hours=await read_report_ttl_hours(client, prefix=prefix))
        ).isoformat()
        published = await finalize(
            client,
            job.report_id,
            job.attempt_id,
            status=DONE,
            bytes_=None,
            chunk_count=updated,  # for bulk jobs the count IS the result (no chunks)
            expires_at=expires_at,
            prefix=prefix,
        )
        if not published:
            boundlog.warning("report drain: bulk publish fenced out — a reclaimer won, no bell")
            return False
        await _ring_bell(client, job, prefix=prefix)
        boundlog.info("report drain: bulk_triage applied", updated=updated)
        return True

    fmt = params.get("format", "csv")
    filters = _filters_from_params(params)
    if fmt == "csv":
        # as-of-T (M8b, #34): the reconstructed sweep; current-state: the M6 engine
        if as_of_t is not None:
            pieces = _csv_pieces_at(
                client, cluster_id=cluster_id, t=as_of_t, filters=filters, prefix=prefix
            )
        else:
            pieces = stream_csv(client, cluster_id=cluster_id, filters=filters)
    elif fmt in ("openvex", "cyclonedx"):
        pieces = _vex_pieces(
            client, cluster_id=cluster_id, filters=filters, fmt=fmt, t=as_of_t, prefix=prefix
        )
    else:  # enqueue validates the Literal — belt and braces for hand-written docs
        await finalize(
            client,
            job.report_id,
            job.attempt_id,
            status=FAILED,
            error=f"unknown export format {fmt!r}",
            prefix=prefix,
        )
        return False

    async def _on_flush() -> bool:
        return await heartbeat(client, job.report_id, job.attempt_id, prefix=prefix)

    try:
        total_bytes, chunk_count = await write_chunks(
            client,
            job.report_id,
            job.attempt_id,
            _throttled(pieces, settings.report_drain_sleep_ms),
            max_bytes=settings.export_max_bytes,
            on_flush=_on_flush,
            prefix=prefix,
        )
    except ExportTooLarge as exc:
        await finalize(
            client, job.report_id, job.attempt_id, status=FAILED, error=str(exc), prefix=prefix
        )
        boundlog.warning("report drain: result over the byte ceiling", error=str(exc))
        return False
    except FencedOut:
        boundlog.warning("report drain: lease lost mid-stream — standing down, chunks orphaned")
        return False  # the reclaimer owns the job; do NOT finalize
    except Exception as exc:  # a failed job must land as failed, not vanish as pending forever
        await finalize(
            client,
            job.report_id,
            job.attempt_id,
            status=FAILED,
            error=f"{type(exc).__name__}: {exc}",
            prefix=prefix,
        )
        boundlog.error("report drain: job failed", error=str(exc))
        return False

    expires_at = (
        datetime.now(UTC) + timedelta(hours=await read_report_ttl_hours(client, prefix=prefix))
    ).isoformat()
    published = await finalize(
        client,
        job.report_id,
        job.attempt_id,
        status=DONE,
        bytes_=total_bytes,
        chunk_count=chunk_count,
        expires_at=expires_at,
        prefix=prefix,
    )
    if not published:
        boundlog.warning("report drain: publish fenced out — a reclaimer won, no bell")
        return False
    await _ring_bell(client, job, prefix=prefix)
    boundlog.info("report drain: published", bytes=total_bytes, chunks=chunk_count)
    return True


async def drain(client: AsyncOpenSearch, *, worker: str | None = None, prefix: str = "") -> int:
    """One drain cycle: claim + run jobs until the queue has nothing due. Returns jobs touched."""
    worker = worker or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    handled = 0
    while True:
        job = await claim_next(client, worker=worker, prefix=prefix)
        if job is None:
            return handled
        handled += 1
        await run_job(client, job, prefix=prefix)


async def _main() -> int:
    settings = get_settings()
    client = build_client(settings)
    try:
        from backend.jobs.registry import run_job

        result = await run_job(client, "report_drain")
        if result is not None:
            log.info("report drain: cycle complete", jobs=result["jobs"])
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
