"""Unit: per-principal concurrent-PIT guard (audit A-m12/#189).

The cap bounds simultaneous open PITs per principal; a release frees exactly its slot; a different
principal is unaffected; an abandoned slot is freed at the PIT horizon (keep_alive + margin). A
walk's slot records its PIT, so only its owner can close it early (issue 832). No OpenSearch —
these are pure slot mechanics."""

import pytest

import backend.query.pit_guard as pit_guard
from backend.core.settings import get_settings


@pytest.fixture(autouse=True)
def _reset():
    pit_guard._slots.clear()
    get_settings.cache_clear()
    yield
    pit_guard._slots.clear()
    get_settings.cache_clear()


def test_cap_release_and_per_principal_isolation(monkeypatch) -> None:
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "2")
    get_settings.cache_clear()

    first = pit_guard.acquire("alice")
    pit_guard.acquire("alice")
    with pytest.raises(pit_guard.PitCapExceeded):
        pit_guard.acquire("alice")  # at the cap

    pit_guard.acquire("bob")  # a DIFFERENT principal has its own budget

    pit_guard.release("alice", first)  # frees one of alice's slots
    pit_guard.acquire("alice")  # fits again
    with pytest.raises(pit_guard.PitCapExceeded):
        pit_guard.acquire("alice")


def test_release_is_a_noop_when_none_held() -> None:
    pit_guard.release("nobody", None)  # must not raise / underflow
    pit_guard.release("nobody", pit_guard.Slot(touched_at=0.0))
    assert "nobody" not in pit_guard._slots


def test_release_frees_exactly_its_own_slot() -> None:
    """Not the oldest one: a finished export must never free the slot a live walk holds, or a
    close of that walk would find nothing to vouch for it."""
    walk = pit_guard.acquire("alice")
    pit_guard.settle("alice", walk, "pit-walk", ended=False)
    export = pit_guard.acquire("alice")
    pit_guard.release("alice", export)
    assert pit_guard.holds("alice", "pit-walk")
    assert pit_guard._slots["alice"] == [walk]


def test_a_walk_slot_holds_its_pit_for_its_owner_only() -> None:
    slot = pit_guard.acquire("alice")
    assert not pit_guard.holds("alice", "pit-1")  # no cursor handed out yet
    pit_guard.settle("alice", slot, "pit-1", ended=False)
    assert pit_guard.holds("alice", "pit-1")
    assert not pit_guard.holds("bob", "pit-1")  # a cursor someone else sends vouches for nothing
    assert not pit_guard.holds("alice", "pit-2")

    pit_guard.release_pit("bob", "pit-1")  # not bob's: nothing happens
    assert pit_guard.holds("alice", "pit-1")
    pit_guard.release_pit("alice", "pit-1")
    assert not pit_guard.holds("alice", "pit-1")
    assert "alice" not in pit_guard._slots


def test_settle_frees_an_ended_walk_and_finds_a_continuation_by_its_pit() -> None:
    one_page = pit_guard.acquire("alice")
    pit_guard.settle("alice", one_page, None, ended=True)  # a first page that was also its last
    assert "alice" not in pit_guard._slots

    walk = pit_guard.acquire("alice")
    other = pit_guard.acquire("alice")
    pit_guard.settle("alice", walk, "pit-walk", ended=False)
    pit_guard.settle("alice", other, "pit-other", ended=False)
    pit_guard.settle("alice", None, "pit-walk", ended=True)  # the walk's last page
    assert not pit_guard.holds("alice", "pit-walk")
    assert pit_guard.holds("alice", "pit-other")  # the other walk keeps its slot

    pit_guard.settle("alice", None, "pit-gone", ended=True)  # no slot holds it: changes nothing
    pit_guard.settle("alice", None, "pit-gone", ended=False)
    assert pit_guard._slots["alice"] == [other]


def test_abandoned_slot_frees_itself_at_horizon(monkeypatch) -> None:
    class _Clock:
        now = 0.0

        def monotonic(self) -> float:
            return self.now

    clock = _Clock()
    monkeypatch.setattr(pit_guard, "time", clock)
    monkeypatch.setenv("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "1")
    monkeypatch.setenv("JAVV_SEARCH_PIT_KEEP_ALIVE", "2m")
    get_settings.cache_clear()

    pit_guard.acquire("x")
    with pytest.raises(pit_guard.PitCapExceeded):
        pit_guard.acquire("x")  # still within the horizon — the slot is live

    clock.now = 120 + 30 + 1  # past keep_alive (120s) + margin (30s)
    pit_guard.acquire("x")  # the stale slot dropped → the new open fits


def test_each_page_restarts_the_walk_slot_horizon(monkeypatch) -> None:
    """A page restarts the PIT's keep-alive, so it restarts the slot's horizon too: a slow walk
    keeps a slot that vouches for its live PIT, and a close of it still works."""

    class _Clock:
        now = 0.0

        def monotonic(self) -> float:
            return self.now

    clock = _Clock()
    monkeypatch.setattr(pit_guard, "time", clock)
    monkeypatch.setenv("JAVV_SEARCH_PIT_KEEP_ALIVE", "2m")
    get_settings.cache_clear()

    slot = pit_guard.acquire("x")
    pit_guard.settle("x", slot, "pit-x", ended=False)
    for _ in range(3):  # three pages, each 100 s apart: 300 s in all, past one horizon
        clock.now += 100
        assert pit_guard.holds("x", "pit-x")
        pit_guard.settle("x", None, "pit-x", ended=False)

    clock.now += 151  # then the user leaves it: the slot goes at the horizon
    assert not pit_guard.holds("x", "pit-x")
