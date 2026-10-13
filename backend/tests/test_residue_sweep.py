"""When the test-residue sweep runs (issue 844): once, after the last test, never on an xdist
worker, whose session ends while the other worker may still use the swept users."""

from types import SimpleNamespace
from typing import Any

import pytest

import conftest


def _session(**config: Any) -> Any:
    return SimpleNamespace(config=SimpleNamespace(**config))


@pytest.fixture
def sweeps(monkeypatch) -> list[None]:
    calls: list[None] = []
    monkeypatch.setattr(conftest, "_sweep_residue", lambda: calls.append(None))
    monkeypatch.setattr(conftest, "opensearch_up", lambda: True)
    return calls


def test_a_worker_does_not_sweep(sweeps) -> None:
    conftest.pytest_sessionfinish(_session(workerinput={"workerid": "gw0"}))
    assert sweeps == []


def test_the_controller_or_a_run_without_xdist_sweeps_once(sweeps) -> None:
    conftest.pytest_sessionfinish(_session())
    assert len(sweeps) == 1


def test_no_sweep_while_opensearch_is_down(sweeps, monkeypatch) -> None:
    monkeypatch.setattr(conftest, "opensearch_up", lambda: False)
    conftest.pytest_sessionfinish(_session())
    assert sweeps == []


def test_a_failed_sweep_does_not_fail_the_run(monkeypatch) -> None:
    def broken() -> None:
        raise RuntimeError("store went away")

    monkeypatch.setattr(conftest, "_sweep_residue", broken)
    monkeypatch.setattr(conftest, "opensearch_up", lambda: True)
    conftest.pytest_sessionfinish(_session())
