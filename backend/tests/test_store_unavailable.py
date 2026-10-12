"""An unreachable store is a 503, not a 500 (issue 832, observability.md §3).

Pins: a connection error, a timeout, or a 502/503/504 from OpenSearch (its "Security not
initialized" while it starts) answers the problem envelope with 503 "Search backend
unavailable", never a traceback; every one counts in `javv_store_unavailable_total`; the warning
is written at most once per window with the count it held back, since any sender can repeat the
request while the store is down; any other store error stays the app's 500."""

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


def _app_raising(exc: Exception) -> httpx.AsyncClient:
    app = create_app()

    @app.get("/reads")
    async def reads() -> None:
        raise exc

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="https://t")


@pytest.fixture(autouse=True)
def _fresh_window(monkeypatch: Any) -> None:
    monkeypatch.setattr(core_errors, "_store_warned", core_errors._StoreWarnings())
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
