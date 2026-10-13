"""The one JAVV logging pipeline (D9 + #156) — shared by backend and scanner so the redaction
processor (a security control) can never fork between components.

Structlog → JSON lines with a real level threshold: `JAVV_LOG_LEVEL` (or the explicit arg),
default `info`, unknown value fails fast. Redaction is a processor, not a convention — values
under token/secret-ish keys are masked and `Bearer …` substrings are scrubbed wherever they
appear. The key match is deliberately BROAD (fail-safe): a non-secret key like `system-tokens`
is masked too; fix noisy call sites, never loosen the regex.

The stdlib bridge routes every `logging` record (uvicorn, opensearch-py, kubernetes-client, …)
through the same processors, so the whole process emits ONE redacted JSON stream and bound
contextvars (request_id, scanner, scan_run_id, …) appear on foreign lines too. Two library
loggers get special handling: `opensearch` per-request lines are DEBUG-gated (at info they'd log
every touch, drowning the stream), and `opensearchpy.trace` — which logs full request BODIES —
is always off (bodies can carry payload data no redaction regex should be trusted with). The
`opensearch` logger also drops its failed-request warnings for 404 and 409, which the callers
expect and handle (issue 831); every other failed request keeps its warning.
"""

import logging
import os
import re
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

_SENSITIVE_KEY = re.compile(
    r"token|secret|password|authorization|pepper|session|cookie", re.IGNORECASE
)
_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)

REDACTED = "[REDACTED]"

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _BEARER.sub(REDACTED, value)
    if isinstance(value, dict):
        return {
            k: (REDACTED if _SENSITIVE_KEY.search(k) else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


def redact_processor(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Mask sensitive keys + scrub bearer tokens from every log event (SEC: never log tokens)."""
    return {
        k: (REDACTED if _SENSITIVE_KEY.search(k) else _redact_value(v))
        for k, v in event_dict.items()
    }


_LEAD_KEYS = ("timestamp", "level", "event")  # the reading order of a log line


def order_keys(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Emit `timestamp, level, event` first — that's what an operator scans for — then the rest
    in their natural insertion order. JSONRenderer serializes in dict order, so ordering the
    dict IS ordering the line."""
    return {
        **{k: event_dict[k] for k in _LEAD_KEYS if k in event_dict},
        **{k: v for k, v in event_dict.items() if k not in _LEAD_KEYS},
    }


def _resolve_level(level: str | None) -> int:
    name = (level or os.environ.get("JAVV_LOG_LEVEL") or "info").lower()
    if name not in _LEVELS:
        raise ValueError(f"unknown log level {name!r} (want {'/'.join(_LEVELS)})")
    return _LEVELS[name]


class _ExpectedStoreAnswers(logging.Filter):
    """Drops opensearch-py's failed-request warning when the status is 404 or 409. The client logs
    `"%s %s [status:%s request:%.3fs]"` with the status third; a 404 is a read of something not
    there yet (a first watermark) and a 409 an `op_type=create` that lost (the seeded roles on
    every start). Both reach their caller as an exception it handles."""

    _FORMAT = "%s %s [status:%s request:%.3fs]"

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        expected = (
            record.msg == self._FORMAT
            and isinstance(args, tuple)
            and len(args) == 4
            and args[2] in (404, 409)
        )
        return not expected


def configure_logging(level: str | None = None) -> None:
    """Configure the process-wide pipeline. Idempotent — safe to call again (tests, reloads)."""
    threshold = _resolve_level(level)

    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # exc_info → an `exception` traceback string. Must run before redaction: a raw exc_info
        # renders as `true` (native) or an unwalked tuple repr (bridged) that redaction misses.
        structlog.processors.format_exc_info,
        redact_processor,
        order_keys,
    ]
    structlog.configure(
        processors=[*shared, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(threshold),
        cache_logger_on_first_use=True,
    )

    # stdlib bridge → same processors, same redaction, same JSON shape (stderr)
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                order_keys,  # remove_processors_meta perturbs the dict — re-order after it
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared,
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(threshold)

    # uvicorn installs its own plain-text handlers before the app imports — strip them so its
    # records propagate to the root JSON handler instead (no-op outside a uvicorn process)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # opensearch-py: per-request lines (INFO on its logger) only when explicitly debugging.
    # Bodies NEVER — the client logs full request/response bodies at its DEBUG level (one scan
    # cycle produced a 6 MB log), so the logger is capped at INFO even under JAVV_LOG_LEVEL=debug;
    # `opensearchpy.trace` (the curl-style body mirror) is always off for the same reason.
    client_logger = logging.getLogger("opensearch")
    client_logger.setLevel(logging.INFO if threshold <= logging.DEBUG else logging.WARNING)
    if not any(isinstance(f, _ExpectedStoreAnswers) for f in client_logger.filters):
        client_logger.addFilter(_ExpectedStoreAnswers())
    logging.getLogger("opensearchpy.trace").setLevel(logging.CRITICAL + 1)
