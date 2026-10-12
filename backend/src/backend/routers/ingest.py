"""POST /api/v1/ingest/scan — the hardened untrusted-input surface (M1, SEC-3/D38).

Order of defenses: rate limit → bearer token (peppered-SHA-256 lookup, constant-time) → streamed
compressed-size cap (Content-Length is never trusted) → gzip decompression cap (zip bomb) → JSON
parse → full-envelope `extra="forbid"` validation → token↔payload scope binding (a team-A token
cannot push team-B data) → commit-then-cache writes. 401 is generic (no token-existence oracle);
tokens are never logged. Every rejection past the token check is also recorded for the
failed-ingests table (`services/ingest_failures.py`, issue 357) without changing the response.
"""

import json
import uuid
import zlib
from datetime import UTC, datetime
from typing import Any, TypedDict, cast

import structlog
from fastapi import APIRouter, HTTPException, Request
from opensearchpy.exceptions import ConflictError
from pydantic import ValidationError

from backend.core.metrics import FINDINGS_WRITTEN, INGEST_ACCEPTED, INGEST_REJECTED
from backend.core.rate_limit import SlidingWindowLimiter
from backend.core.security import hash_token, token_expired, tokens_match
from backend.core.settings import get_settings
from backend.models.envelope import IngestEnvelope
from backend.repositories.bulk import BulkError
from backend.services.ingest import ingest_envelope
from backend.services.ingest_failures import clean_text, record_ingest_failure

log = structlog.get_logger()


class _Scope(TypedDict):
    """The authenticated token's scope, named on every post-auth rejection line."""

    cluster_id: str
    scanner: str


class _Rejection(HTTPException):
    """An ingest refusal, carrying what the failed-ingests record needs beyond the response."""

    def __init__(
        self,
        status: int,
        detail: str,
        reason: str,
        record: str,
        image_ref: str | None,
        failure_id: str | None,
    ):
        super().__init__(status, detail)
        self.reason = reason
        self.record = record
        self.image_ref = image_ref
        self.failure_id = failure_id


def _reject(
    status: int,
    reason: str,
    detail: str,
    *,
    warn: bool = True,
    scope: _Scope | None = None,
    record: str | None = None,
    image_ref: str | None = None,
    **fields: Any,
) -> _Rejection:
    """Count + raise, and log a warning unless `warn=False`. `reason` is a bounded metric label
    (never user input). A rejection an unauthenticated sender can repeat with no budget (401)
    passes `warn=False`: a line per request would let it choose our log volume (logging.md).

    `scope` = the rejection came after the token check. Only those are recorded for the
    failed-ingests table, so only they get a `failure_id`: the warning carries it and the record
    is written under it, which joins a table row to its log line. `record` is the table's Error
    text when it says more than `detail`."""
    INGEST_REJECTED.labels(reason=reason).inc()
    failure_id = None if scope is None else uuid.uuid4().hex
    if scope is not None:
        fields |= {"failure_id": failure_id, **scope}
    if warn:
        log.warning("ingest rejected", reason=reason, status=status, **fields)
    return _Rejection(status, detail, reason, record or detail, image_ref, failure_id)


def _image_ref_of(parsed: Any) -> str | None:
    """Best-effort image for a body that parsed but failed validation — untrusted, so only a
    string is taken, and the recorder caps and strips it."""
    if isinstance(parsed, dict):
        ref = cast(dict[str, Any], parsed).get("image_ref")
        if isinstance(ref, str):
            return ref
    return None


def _first_error(exc: ValidationError) -> str:
    """`findings.3.severity: missing` — the location comes from the schema, except where a
    forbidden extra key names itself; the recorder caps it either way. The rejected input is
    never echoed."""
    first = exc.errors()[0]
    loc = ".".join(clean_text(str(part))[:64] for part in first["loc"])
    return f"{loc}: {first['type']}" if loc else first["type"]


router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

# Its own instance, keyed on token hashes: an unauthenticated flood here must never spend the
# budget of a logged-in principal's telemetry (516). This is the map the m-1 hard eviction in
# `SlidingWindowLimiter` exists for — the key space is attacker-supplied and reached BEFORE the
# token is verified, so it grows on garbage.
_limiter = SlidingWindowLimiter()
# The 429 is decided before the token is verified, so its key is whatever a sender puts in the
# header. At most one warning per key per window; the metric still counts every rejection.
_rate_limit_warned = SlidingWindowLimiter()


async def _read_capped(request: Request, cap: int, scope: _Scope) -> bytes:
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > cap:  # enforced while reading — the header may lie
            raise _reject(
                413, "too_large", "compressed body too large", limit_bytes=cap, scope=scope
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _decompress_capped(raw: bytes, cap: int, scope: _Scope) -> bytes:
    d = zlib.decompressobj(wbits=31)  # gzip container
    try:
        out = d.decompress(raw, cap + 1)
    except zlib.error as exc:
        raise _reject(400, "bad_gzip", "invalid gzip body", scope=scope) from exc
    if len(out) > cap or d.unconsumed_tail:
        raise _reject(  # zip bomb
            413, "too_large", "decompressed body too large", limit_bytes=cap, scope=scope
        )
    return out


@router.post("/scan", status_code=202)
async def ingest_scan(request: Request) -> dict[str, Any]:
    settings = get_settings()
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or len(auth) > 512:
        raise _reject(401, "bad_token", "invalid token", warn=False)
    candidate = hash_token(auth.removeprefix("Bearer "), pepper=settings.secret_key)

    if _limiter.is_limited(candidate, settings.ingest_rate_limit_per_minute):
        first_in_window = not _rate_limit_warned.is_limited(candidate, 1)
        raise _reject(429, "rate_limited", "rate limit exceeded", warn=first_in_window)

    client = cast(Any, request.app.state.opensearch)
    hits = await client.search(
        index="system-tokens",
        body={"query": {"term": {"token_hash": candidate}}, "size": 1},
    )
    docs = hits["hits"]["hits"]
    token = docs[0]["_source"] if docs else None
    if (
        token is None
        or not tokens_match(candidate, token["token_hash"])  # constant-time, belt & braces
        or token.get("disabled")
        or token_expired(token)  # lifecycle: an expired token is dead (audit m-3)
    ):
        raise _reject(401, "bad_token", "invalid token", warn=False)  # generic — no oracle

    # authenticated from here on, and already rate-limited per token: every rejection below logs
    # a bounded warning naming whose scanner it was (the token's scope, never the token), and is
    # recorded for the failed-ingests table under that same scope
    scope = _Scope(cluster_id=token["cluster_id"], scanner=token["scanner"])
    try:
        return await _ingest_authenticated(request, client, docs[0]["_id"], scope)
    except _Rejection as exc:
        await record_ingest_failure(
            client,
            # every site below the token check passes `scope`, so the id is always set; the
            # fallback only keeps a site that forgot it recorded rather than dropped
            failure_id=exc.failure_id or uuid.uuid4().hex,
            cluster_id=scope["cluster_id"],
            scanner=scope["scanner"],
            reason=exc.reason,
            status=exc.status_code,
            error=exc.record,
            image_ref=exc.image_ref,
        )
        raise


async def _ingest_authenticated(
    request: Request, client: Any, token_doc_id: str, scope: _Scope
) -> dict[str, Any]:
    settings = get_settings()
    raw = await _read_capped(request, settings.ingest_max_compressed_bytes, scope)
    if request.headers.get("content-encoding", "").lower() == "gzip":
        raw = _decompress_capped(raw, settings.ingest_max_body_bytes, scope)
    elif len(raw) > settings.ingest_max_body_bytes:
        raise _reject(
            413,
            "too_large",
            "body too large",
            limit_bytes=settings.ingest_max_body_bytes,
            scope=scope,
        )

    try:
        parsed = json.loads(raw)
    # RecursionError: valid JSON nested past the decoder's limit, which no envelope needs
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise _reject(400, "bad_json", "body is not valid JSON", scope=scope) from exc
    try:
        env = IngestEnvelope.model_validate(parsed)
    except ValidationError as exc:
        detail = f"envelope rejected: {exc.error_count()} error(s)"
        raise _reject(
            422,
            "invalid_envelope",
            detail,
            record=f"{detail}; first: {_first_error(exc)}",
            image_ref=_image_ref_of(parsed),
            errors=exc.error_count(),
            scope=scope,
        ) from exc

    # authz binding (SEC-3): the token's scope must match the payload it pushes
    if env.cluster_id != scope["cluster_id"] or env.scanner != scope["scanner"]:
        raise _reject(
            403,
            "scope_mismatch",
            "token not valid for this cluster/scanner",
            image_ref=env.image_ref,
            payload_cluster_id=env.cluster_id,
            payload_scanner=env.scanner,
            scope=scope,
        )

    structlog.contextvars.bind_contextvars(cluster_id=env.cluster_id, scanner=env.scanner)
    try:
        written = await ingest_envelope(client, env)
    except BulkError as exc:
        raise _reject(
            503,
            "storage_error",
            "storage temporarily unavailable",
            image_ref=env.image_ref,
            scope=scope,
        ) from exc

    INGEST_ACCEPTED.labels(scanner=env.scanner).inc()
    FINDINGS_WRITTEN.labels(scanner=env.scanner).inc(written)
    log.info("ingest committed", scan_run_id=env.scan_run_id, findings=written)

    # server-side timestamp — the scanner-down guard must not be gameable by a client clock (M-3);
    # this records when the backend last accepted a push, not the scanner's self-reported scan
    # time. Best-effort: the ingest is already committed, so a version conflict here (two
    # same-token pushes racing the stamp — found by the #117 bench) must not 500 an accepted
    # push; the racer just wrote an equally-fresh timestamp.
    try:
        await client.update(
            index="system-tokens",
            id=token_doc_id,
            body={"doc": {"last_ingest_at": datetime.now(UTC).isoformat()}},
            params={"retry_on_conflict": "3"},
        )
    except ConflictError:
        log.warning("last_ingest_at stamp lost a write race — a racer stamped fresher")
    return {"accepted": True, "findings": written, "commit": env.scan_run_id}
