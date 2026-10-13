"""The single error envelope (RFC 9457 problem-details) every non-2xx response uses.

Routers never hand-roll error bodies — they raise, and the handlers here render the envelope so a
client error maps 1:1 to logs via `request_id`: the id the request-line middleware chose (the
inbound `X-Request-ID` if well-formed, else minted) and logged the request under.
"""

import time
from collections.abc import Callable, Mapping

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import TransportError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.metrics import OS_REQUEST_ERRORS, STORE_READ_ONLY, STORE_UNAVAILABLE

PROBLEM_MEDIA_TYPE = "application/problem+json"

log = structlog.get_logger()


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    request_id: str | None = None


def problem_response(
    status: int,
    title: str,
    detail: str | None = None,
    request_id: str | None = None,
    headers: Mapping[str, str] | None = None,
    type_: str = "about:blank",
) -> JSONResponse:
    body = Problem(type=type_, title=title, status=status, detail=detail, request_id=request_id)
    return JSONResponse(
        status_code=status,
        content=body.model_dump(),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


# the same window as the frontend server's 502 (.claude/rules/logging.md): any sender can repeat a
# request while the store is down, so it must not choose our log volume
STORE_WARN_WINDOW_S = 10.0


def store_unavailable(exc: BaseException) -> bool:
    """The store is away or still starting: a connection error or timeout, or a 502, 503 or 504
    from OpenSearch ("Security not initialized" while it starts). Its own refusals are not."""
    if isinstance(exc, OSConnectionError):
        return True
    return isinstance(exc, TransportError) and exc.status_code in (502, 503, 504)


# the block OpenSearch puts on an index past its flood-stage disk watermark; its id and status
# are in the reason of every write it refuses ("[TOO_MANY_REQUESTS/12/disk usage exceeded …]")
_FLOOD_STAGE_BLOCK = "TOO_MANY_REQUESTS/12/"

STORE_READ_ONLY_TYPE = "store-read-only"

# the same wait JAVV's own 429s ask for (the per-user search cap, `Retry-After: 5`); the UI never
# retries by itself, so this only guides a script
STORE_BUSY_RETRY_AFTER_S = 5


def store_read_only(exc: BaseException) -> bool:
    """A write the store refused because its disk is past the flood-stage watermark. Reads still
    work, so this is not an unreachable store."""
    return (
        isinstance(exc, TransportError)
        and exc.status_code == 429
        and _FLOOD_STAGE_BLOCK in str(exc.info)
    )


def _now() -> float:
    return time.monotonic()


class _StoreWarnings:
    """Counts every one; at most one warning per window, with the count held back since the last
    one."""

    def __init__(self, event: str, counter: Callable[[], None]) -> None:
        self.event = event
        self.counter = counter
        self.last: float | None = None
        self.held = 0

    def note(self, request: Request, exc: BaseException) -> None:
        self.counter()
        now = _now()
        if self.last is not None and now - self.last < STORE_WARN_WINDOW_S:
            self.held += 1
            return
        log.warning(
            self.event,
            error=type(exc).__name__,
            path=request.url.path,
            held_back=self.held,
            request_id=_request_id(request),
        )
        self.last, self.held = now, 0


_store_warned = _StoreWarnings("store unavailable", STORE_UNAVAILABLE.inc)
_read_only_warned = _StoreWarnings("store read-only", STORE_READ_ONLY.inc)
_busy_warned = _StoreWarnings("store busy", OS_REQUEST_ERRORS.labels("429").inc)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # preserve response headers a route attached to the exception (e.g. Retry-After on a 429)
        return problem_response(
            exc.status_code,
            title=str(exc.detail),
            request_id=_request_id(request),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem_response(
            422, title="Validation error", detail=str(exc.errors()), request_id=_request_id(request)
        )

    @app.exception_handler(TransportError)
    async def _store(request: Request, exc: TransportError) -> JSONResponse:
        if store_read_only(exc):
            _read_only_warned.note(request, exc)
            request_id = _request_id(request)
            return problem_response(
                503,
                title="The store is read-only: its disk is full",
                detail="Reads work. Changes are not saved until the store has free disk space.",
                request_id=request_id,
                headers={"X-Request-ID": request_id} if request_id else None,
                type_=STORE_READ_ONLY_TYPE,
            )
        if exc.status_code == 429:  # overloaded: a full queue or a circuit breaker
            _busy_warned.note(request, exc)
            request_id = _request_id(request)
            headers = {"Retry-After": str(STORE_BUSY_RETRY_AFTER_S)}
            if request_id:
                headers["X-Request-ID"] = request_id
            return problem_response(
                429,
                title="The search backend is busy",
                detail="Try again in a few seconds.",
                request_id=request_id,
                headers=headers,
            )
        if not store_unavailable(exc):
            raise exc  # to the generic handler below: logged, then a 500
        _store_warned.note(request, exc)
        request_id = _request_id(request)
        return problem_response(
            503,
            title="Search backend unavailable",
            detail="The search backend is not reachable.",
            request_id=request_id,
            headers={"X-Request-ID": request_id} if request_id else None,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Runtime errors must not crash the app — return the envelope (D9 / observability).
        # This runs outside the request-line middleware: its bound log context and its response
        # header don't reach here, so both are set explicitly (issue 644). The stack is logged
        # here, once; uvicorn's duplicate traceback is filtered in core/logging.py.
        request_id = _request_id(request)
        log.error(
            "unhandled error",
            exc_info=exc,
            request_id=request_id,
            method=request.method,
            path=request.url.path,  # never the query string, like the request line
        )
        return problem_response(
            500,
            title="Internal server error",
            request_id=request_id,
            headers={"X-Request-ID": request_id} if request_id else None,
        )
