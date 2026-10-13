"""/metrics expansion (#220, major-audit 02) — the read-path/auth/limit observability layer.

Pins the cardinality rules that make the metrics usable: route TEMPLATE labels (never raw
paths — an attacker scanning paths must not mint unbounded series), probe/self exclusion, and
the bounded label sets on the counters. Scrape stays storage-free (no OpenSearch at scrape)."""

import httpx
import pytest
from prometheus_client import REGISTRY

from backend.core.metrics import (
    AUTH_FAILURES,
    CAS_CONFLICTS,
    LIMIT_REJECTIONS,
    OS_BACKOFF_RETRIES,
)
from backend.main import create_app


def _pits_open() -> float | None:
    return REGISTRY.get_sample_value("javv_pits_open")


async def _scrape(c: httpx.AsyncClient) -> str:
    r = await c.get("/metrics")
    assert r.status_code == 200
    return r.text


class _NoStore:
    """Just enough OpenSearch for the anonymous 401 paths — no real store needed here."""

    async def get(self, *a: object, **k: object) -> dict:
        from opensearchpy import NotFoundError

        raise NotFoundError(404, "not_found", {})


def _client() -> httpx.AsyncClient:
    app = create_app()
    app.state.opensearch = _NoStore()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


# --- M-1: the request histogram ------------------------------------------------


async def test_requests_are_labeled_by_route_template_never_raw_path() -> None:
    async with _client() as c:
        await c.get("/api/v1/findings")  # 401s — still a routed request, still observed
        text = await _scrape(c)
    assert 'route="/api/v1/findings"' in text
    assert 'status="401"' in text


async def test_unrouted_paths_collapse_into_one_unmatched_series() -> None:
    async with _client() as c:
        await c.get("/api/v1/garbage-abc123")
        await c.get("/api/v1/garbage-def456")
        text = await _scrape(c)
    assert 'route="unmatched"' in text
    # the raw paths must never appear as label values (cardinality bomb otherwise)
    assert "garbage-abc123" not in text and "garbage-def456" not in text


async def test_probes_and_metrics_itself_are_excluded() -> None:
    async with _client() as c:
        await c.get("/healthz")
        await _scrape(c)  # first scrape — would observe itself if not excluded
        text = await _scrape(c)
    assert 'route="/metrics"' not in text
    assert 'route="/healthz"' not in text


# --- M-4: limit-rejection counter + PIT gauge -----------------------------------


def test_limit_rejections_is_one_counter_with_a_bounded_label() -> None:
    before = LIMIT_REJECTIONS.labels("pit_cap")._value.get()
    LIMIT_REJECTIONS.labels("pit_cap").inc()
    assert LIMIT_REJECTIONS.labels("pit_cap")._value.get() == before + 1


def test_pit_guard_publishes_the_open_gauge_and_counts_cap_hits(monkeypatch) -> None:
    from backend.core.settings import get_settings
    from backend.query import pit_guard

    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "1")
    get_settings.cache_clear()
    pit_guard._slots.clear()
    try:
        pit_guard.acquire("metrics-user")
        assert _pits_open() == 1
        before = LIMIT_REJECTIONS.labels("pit_cap")._value.get()
        with pytest.raises(pit_guard.PitCapExceeded):
            pit_guard.acquire("metrics-user")
        assert LIMIT_REJECTIONS.labels("pit_cap")._value.get() == before + 1
        pit_guard.release_one("metrics-user")
        assert _pits_open() == 0
    finally:
        pit_guard._slots.clear()
        get_settings.cache_clear()


async def test_the_open_gauge_drops_a_slot_at_its_horizon_with_no_take_or_release(
    monkeypatch,
) -> None:
    """Issue 832: an abandoned slot expires on its own, so the gauge must stop counting it then,
    not at the next take or release. Read through the real app's /metrics."""
    from backend.core.settings import get_settings
    from backend.query import pit_guard

    class _Clock:
        now = 1000.0

        def monotonic(self) -> float:
            return self.now

    clock = _Clock()
    monkeypatch.setattr(pit_guard, "time", clock)
    monkeypatch.setenv("JAVV_SEARCH_PIT_KEEP_ALIVE", "2m")
    get_settings.cache_clear()
    pit_guard._slots.clear()
    try:
        pit_guard.acquire("left-a-list")
        pit_guard.acquire("left-a-list")
        async with _client() as c:
            assert "javv_pits_open 2.0" in await _scrape(c)
            clock.now += 120 + 30 - 1  # just inside keep_alive + margin: still live
            assert "javv_pits_open 2.0" in await _scrape(c)
            clock.now += 2  # past it, and nothing took or released a slot
            assert "javv_pits_open 0.0" in await _scrape(c)
    finally:
        pit_guard._slots.clear()
        get_settings.cache_clear()


# --- M-2: backoff retries surface from the shared bulk helper -------------------


async def test_bulk_429_retries_increment_the_backoff_counter() -> None:
    from backend.repositories.bulk import bulk_write

    calls = {"n": 0}

    class Flaky:
        async def bulk(self, body):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"errors": True, "items": [{"index": {"status": 429}}]}
            return {"errors": False, "items": [{"index": {"status": 200}}]}

    async def no_sleep(_: float) -> None:
        return None

    before = OS_BACKOFF_RETRIES._value.get()
    written = await bulk_write(Flaky(), [{"index": {}}, {"doc": 1}], sleep=no_sleep)  # type: ignore[arg-type]
    assert written == 1
    assert OS_BACKOFF_RETRIES._value.get() == before + 1


# --- M-3 / M-5: the label sets exist and are usable ------------------------------


def test_cas_and_auth_counters_accept_their_bounded_sites() -> None:
    for site in ("watermarks", "scan_orders", "reproject"):
        CAS_CONFLICTS.labels(site).inc(0)
    for reason in (
        "bad_credentials",
        "locked_out",
        "expired_session",
        "missing_capability",
        "must_change",
    ):
        AUTH_FAILURES.labels(reason).inc(0)


async def test_auth_failures_count_reasons_never_usernames() -> None:
    async with _client() as c:
        before = AUTH_FAILURES.labels("expired_session")._value.get()
        await c.get("/api/v1/findings")  # no cookie → principal resolution 401s
        text = await _scrape(c)
    assert AUTH_FAILURES.labels("expired_session")._value.get() == before + 1
    assert 'username="' not in text  # reasons are the ONLY label — never a principal
