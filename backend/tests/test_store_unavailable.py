"""An unreachable store is a 503, not a 500 (issue 832, observability.md §3).

Pins: a connection error, a timeout, or a 502/503/504 from OpenSearch (its "Security not
initialized" while it starts) answers the problem envelope with 503 "Search backend
unavailable", never a traceback; every one counts in `javv_store_unavailable_total`; the warning
is written at most once per window with the count it held back, since any sender can repeat the
request while the store is down; any other store error stays the app's 500.

A write the store's full disk blocks (its flood-stage watermark) answers 503 "The store is
read-only: its disk is full" with the problem type `store-read-only`, by the same window rule
(issue 832). The bodies below are what OpenSearch answered in an experiment on a real store."""

from typing import Any

import httpx
import pytest
import structlog
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import ConnectionTimeout, RequestError, TransportError
from prometheus_client import REGISTRY

from backend.core import errors as core_errors
from backend.main import create_app


def _unavailable() -> float:
    return REGISTRY.get_sample_value("javv_store_unavailable_total") or 0.0


def _read_only() -> float:
    return REGISTRY.get_sample_value("javv_store_read_only_total") or 0.0


def _busy() -> float:
    labels = {"kind": "429"}
    return REGISTRY.get_sample_value("javv_opensearch_request_errors_total", labels) or 0.0


_BREAKER = {
    "type": "circuit_breaking_exception",
    "reason": "[request] Data too large, data for [<agg [t]>] would be [5120/5kb], which is"
    " larger than the limit of [1024/1kb]",
    "bytes_wanted": 5120,
    "bytes_limit": 1024,
    "durability": "TRANSIENT",
}
# a terms aggregation past the request circuit breaker, recorded on a real store
CIRCUIT_BREAKER = TransportError(
    429,
    "search_phase_execution_exception",
    {
        "error": {
            "root_cause": [_BREAKER],
            "type": "search_phase_execution_exception",
            "reason": "all shards failed",
            "phase": "query",
            "grouped": True,
            "caused_by": _BREAKER,
        },
        "status": 429,
    },
)
# a full search queue; built by hand in the shape OpenSearch answers, since a single-node test
# store does not fill its queue on demand
REJECTED = TransportError(
    429,
    "es_rejected_execution_exception",
    {
        "error": {
            "type": "es_rejected_execution_exception",
            "reason": "rejected execution of a search task: queue capacity = 1000",
        },
        "status": 429,
    },
)


_FLOOD = (
    "index [system-sessions] blocked by: [TOO_MANY_REQUESTS/12/disk usage exceeded flood-stage"
    " watermark, index has read-only-allow-delete block];"
)
# an index, an op_type=create or an update into a blocked index: all three answered this
FLOOD_BLOCK = TransportError(
    429,
    "cluster_block_exception",
    {
        "error": {
            "root_cause": [{"type": "cluster_block_exception", "reason": _FLOOD}],
            "type": "cluster_block_exception",
            "reason": _FLOOD,
        },
        "status": 429,
    },
)


def _app_raising(exc: Exception) -> httpx.AsyncClient:
    app = create_app()

    @app.get("/reads")
    async def reads() -> None:
        raise exc

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="https://t")


@pytest.fixture(autouse=True)
def _fresh_window(monkeypatch: Any) -> None:
    for name in ("_store_warned", "_read_only_warned", "_busy_warned"):
        fresh = core_errors._StoreWarnings(
            getattr(core_errors, name).event, getattr(core_errors, name).counter
        )
        monkeypatch.setattr(core_errors, name, fresh)
    monkeypatch.setattr(core_errors, "log", structlog.get_logger())


@pytest.mark.parametrize(
    "exc",
    [
        OSConnectionError("N/A", "connection refused", None),
        ConnectionTimeout("TIMEOUT", "read timed out", None),
        TransportError(503, "OpenSearch Security not initialized.", None),
        TransportError(502, "bad gateway", None),
        TransportError(504, "gateway timeout", None),
    ],
)
async def test_an_unreachable_store_is_a_503_envelope(exc: Exception) -> None:
    before = _unavailable()
    async with _app_raising(exc) as client:
        with structlog.testing.capture_logs() as logs:
            r = await client.get("/reads")
    assert r.status_code == 503
    body = r.json()
    assert (body["title"], body["detail"]) == (
        "Search backend unavailable",
        "The search backend is not reachable.",
    )
    assert "opensearch" not in r.text.lower()  # the body names no internals
    assert body["request_id"]
    assert _unavailable() == before + 1
    (line,) = [e for e in logs if e["event"] == "store unavailable"]
    assert line["log_level"] == "warning" and line["held_back"] == 0
    assert not [e for e in logs if e["log_level"] == "error"]  # no traceback, no error line


async def test_any_other_store_error_stays_a_500() -> None:
    async with _app_raising(RequestError(400, "parsing_exception", None)) as client:
        r = await client.get("/reads")
    assert r.status_code == 500


async def test_the_warning_is_written_once_per_window_with_the_count_it_held(monkeypatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(core_errors, "_now", lambda: clock[0])
    before = _unavailable()
    async with _app_raising(OSConnectionError("N/A", "refused", None)) as client:
        with structlog.testing.capture_logs() as logs:
            for _ in range(3):  # inside one window
                assert (await client.get("/reads")).status_code == 503
            clock[0] += core_errors.STORE_WARN_WINDOW_S
            assert (await client.get("/reads")).status_code == 503
    lines = [e for e in logs if e["event"] == "store unavailable"]
    assert [e["held_back"] for e in lines] == [0, 2]
    assert _unavailable() == before + 4  # the counter counts every one


async def test_a_write_the_full_disk_blocks_is_a_503_read_only() -> None:
    before, unavailable = _read_only(), _unavailable()
    async with _app_raising(FLOOD_BLOCK) as client:
        with structlog.testing.capture_logs() as logs:
            r = await client.get("/reads")
    assert r.status_code == 503
    body = r.json()
    assert body["type"] == "store-read-only"
    assert body["title"] == "The store is read-only: its disk is full"
    assert "opensearch" not in r.text.lower()
    assert _read_only() == before + 1
    assert _unavailable() == unavailable  # not counted as an unreachable store
    (line,) = [e for e in logs if e["event"] == "store read-only"]
    assert line["log_level"] == "warning" and line["held_back"] == 0
    assert not [e for e in logs if e["log_level"] == "error"]


async def test_the_read_only_warning_is_written_once_per_window(monkeypatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(core_errors, "_now", lambda: clock[0])
    before = _read_only()
    async with _app_raising(FLOOD_BLOCK) as client:
        with structlog.testing.capture_logs() as logs:
            for _ in range(3):
                assert (await client.get("/reads")).status_code == 503
            clock[0] += core_errors.STORE_WARN_WINDOW_S
            assert (await client.get("/reads")).status_code == 503
    assert [e["held_back"] for e in logs if e["event"] == "store read-only"] == [0, 2]
    assert _read_only() == before + 4


@pytest.mark.parametrize("exc", [CIRCUIT_BREAKER, REJECTED], ids=["breaker", "rejected"])
async def test_an_overloaded_store_is_a_429_busy_with_retry_after(exc: Exception) -> None:
    before, read_only = _busy(), _read_only()
    async with _app_raising(exc) as client:
        with structlog.testing.capture_logs() as logs:
            r = await client.get("/reads")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "5"
    assert r.json()["title"] == "The search backend is busy"
    assert "opensearch" not in r.text.lower()
    assert _busy() == before + 1
    assert _read_only() == read_only
    (line,) = [e for e in logs if e["event"] == "store busy"]
    assert line["log_level"] == "warning" and line["held_back"] == 0
    assert not [e for e in logs if e["log_level"] == "error"]


async def test_the_busy_warning_is_written_once_per_window(monkeypatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(core_errors, "_now", lambda: clock[0])
    async with _app_raising(CIRCUIT_BREAKER) as client:
        with structlog.testing.capture_logs() as logs:
            for _ in range(3):
                assert (await client.get("/reads")).status_code == 429
            clock[0] += core_errors.STORE_WARN_WINDOW_S
            assert (await client.get("/reads")).status_code == 429
    assert [e["held_back"] for e in logs if e["event"] == "store busy"] == [0, 2]
