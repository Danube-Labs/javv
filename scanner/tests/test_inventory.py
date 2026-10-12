"""Inventory commit, scanner side (M8a slice 2): the cycle-END certification call. Best-effort —
unlike the fail-closed cycle-start fetches, a failed commit loses nothing (every envelope is
already pushed); the run just stays uncertified. It retries within the cycle's retry budget."""

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from scanner.inventory import commit_inventory
from scanner.push import RetryBudget

STARTED = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://backend")


def test_commit_posts_the_cycle_identity_and_reports_committed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/api/v1/inventory-runs"
        assert request.headers["Authorization"] == "Bearer tok"
        body = json.loads(request.content)
        assert body == {
            "scan_run_id": "run-1",
            "expected_count": 3,
            "started_at": "2026-07-07T12:00:00+00:00",
        }
        return httpx.Response(
            200, json={"status": "committed", "expected_count": 3, "written_count": 3}
        )

    with _client(handler) as http:
        assert commit_inventory(
            http,
            token="tok",
            scan_run_id="run-1",
            expected_count=3,
            started_at=STARTED,
            budget=RetryBudget(seconds=0),
        )


def test_commit_reports_a_partial_run_as_uncommitted() -> None:
    partial = httpx.Response(
        200, json={"status": "partial", "expected_count": 3, "written_count": 2}
    )
    with _client(lambda r: partial) as http:
        assert not commit_inventory(
            http,
            token="tok",
            scan_run_id="run-1",
            expected_count=3,
            started_at=STARTED,
            budget=RetryBudget(seconds=0),
        )


def test_commit_is_best_effort_on_any_backend_failure() -> None:
    # 5xx / transport error with no budget left → False, never an exception — the cycle's pushes
    # already landed
    with _client(lambda r: httpx.Response(503)) as http:
        assert not commit_inventory(
            http,
            token="tok",
            scan_run_id="run-1",
            expected_count=1,
            started_at=STARTED,
            budget=RetryBudget(seconds=0),
        )

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("backend down")

    with _client(boom) as http:
        assert not commit_inventory(
            http,
            token="tok",
            scan_run_id="run-1",
            expected_count=1,
            started_at=STARTED,
            budget=RetryBudget(seconds=0),
        )


def test_a_commit_retries_a_store_restart_within_the_budget() -> None:
    answers = [httpx.Response(503), httpx.Response(200, json={"status": "committed"})]

    def handler(request: httpx.Request) -> httpx.Response:
        return answers.pop(0)

    budget = RetryBudget(seconds=5)
    with _client(handler) as http:
        assert commit_inventory(
            http,
            token="tok",
            scan_run_id="run-1",
            expected_count=1,
            started_at=STARTED,
            budget=budget,
        )
    assert answers == []
    assert 0 < budget.spent < 5
