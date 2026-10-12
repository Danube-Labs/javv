"""The single error envelope (RFC 9457 problem-details) every non-2xx response uses.

Routers never hand-roll error bodies — they raise, and the handlers here render the envelope so a
client error maps 1:1 to logs via `request_id`: the id the request-line middleware chose (the
inbound `X-Request-ID` if well-formed, else minted) and logged the request under.
"""

import time
from collections.abc import Mapping

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import TransportError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.metrics import STORE_UNAVAILABLE

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
) -> JSONResponse:
    body = Problem(title=title, status=status, detail=detail, request_id=request_id)
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


def _now() -> float:
    return time.monotonic()


class _StoreWarnings:
    """At most one warning per window, with the count held back since the last one."""

    def __init__(self) -> None:
        self.last: float | None = None
        self.held = 0

    def note(self, request: Request, exc: BaseException) -> None:
        STORE_UNAVAILABLE.inc()
        now = _now()
        if self.last is not None and now - self.last < STORE_WARN_WINDOW_S:
            self.held += 1
            return
        log.warning(
            "store unavailable",
            error=type(exc).__name__,
            path=request.url.path,
            held_back=self.held,
            request_id=_request_id(request),
        )
        self.last, self.held = now, 0


_store_warned = _StoreWarnings()


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
