"""Per-principal concurrent-PIT guard (M6, audit A-m12/#189) — the ingest/login limiter pattern
(module-level, in-memory PER POD: N replicas ⇒ N× the budget, an accepted MVP bound).

Every cursor-less findings page and every export opens a PIT that lives `keep_alive` unless the walk
finishes; an authenticated client looping page-1 opens can pile up open PIT contexts until the
CLUSTER PIT cap — at which point EVERYONE's paging and exports fail. This bounds simultaneous open
PITs per principal so one client can't starve the rest.

A slot is reserved on open (`acquire`), released when the walk finishes or an export completes
(`release`), and — for a walk the client simply abandons — is freed at the PIT's own horizon
(`keep_alive` + margin), because the abandoned PIT dies there server-side anyway. Leaky but bounded
is the accepted MVP shape: the cap is defense against a BURST faster than expiry, not a substitute
for it. Setting: `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL`; past it the route 429s.

A walk's slot also records the PIT its cursor carries (`settle`), so a client can close its own
walk early (`holds` + `release_pit`, issue 832) and nobody else's: the PIT id comes from a cursor
the caller sends, and only a slot of that caller can vouch for it. Each page of a walk restarts the
slot's horizon, as it restarts the PIT's keep-alive."""

import re
import time
from dataclasses import dataclass

from backend.core.metrics import LIMIT_REJECTIONS, PITS_OPEN
from backend.core.settings import get_settings

_MAX_KEYS = 100_000  # bound the map so a spray of principals can't leak it (login-lockout m-1)
_EXPIRY_MARGIN_S = 30.0  # past keep_alive the PIT is dead server-side — drop the stale slot


@dataclass
class Slot:
    """One reserved PIT slot. `pit_id` is set once a page hands the client a cursor on it."""

    touched_at: float
    pit_id: str | None = None


_slots: dict[str, list[Slot]] = {}


class PitCapExceeded(Exception):
    """The principal already holds the max concurrent open PITs (audit A-m12/#189) — the route
    answers 429 with a Retry-After."""


_KEEP_ALIVE = re.compile(r"^(\d+)(ms|s|m|h)$")
_UNIT_S = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def _keep_alive_s() -> float:
    """Parse `JAVV_SEARCH_PIT_KEEP_ALIVE` to seconds; the slot horizon. The grammar is validated
    at boot (#219) so a mismatch here is a real config bug — raise loud, no silent 120s fallback
    (06 §2 ruling: silent fallbacks hide exactly the class of bug the validation exists to kill)."""
    ka = get_settings().search_pit_keep_alive.strip()
    m = _KEEP_ALIVE.match(ka)
    if m is None:  # unreachable behind Settings validation; loud beats a masked misparse
        raise ValueError(f"search_pit_keep_alive {ka!r} is not <digits><ms|s|m|h>")
    return float(m.group(1)) * _UNIT_S[m.group(2)]


def _drop_expired(principal: str, now: float) -> list[Slot]:
    """Drop this principal's slots older than the PIT horizon; return the live remainder."""
    horizon = _keep_alive_s() + _EXPIRY_MARGIN_S
    live = [slot for slot in _slots.get(principal, ()) if now - slot.touched_at < horizon]
    if live:
        _slots[principal] = live
    else:
        _slots.pop(principal, None)
    return live


def _live_slots() -> int:
    """The slots still inside their horizon, across principals. The gauge reads this at each
    scrape: an abandoned slot expires without a take or a release, so a value set only on those
    two kept counting it (issue 832). Per pod, like the guard itself."""
    now = time.monotonic()
    horizon = _keep_alive_s() + _EXPIRY_MARGIN_S
    return sum(1 for q in list(_slots.values()) for slot in q if now - slot.touched_at < horizon)


PITS_OPEN.set_function(_live_slots)


def acquire(principal: str) -> Slot:
    """Reserve a PIT slot for the principal; raise `PitCapExceeded` if it is at the cap."""
    now = time.monotonic()
    live = _drop_expired(principal, now)
    if len(live) >= get_settings().max_concurrent_pits_per_principal:
        LIMIT_REJECTIONS.labels("pit_cap").inc()  # M-4 (#220)
        raise PitCapExceeded("too many concurrent open cursors/exports for this principal")
    if len(_slots) >= _MAX_KEYS and principal not in _slots:
        while len(_slots) >= _MAX_KEYS:  # FIFO hard-evict — the map can never exceed the cap
            del _slots[next(iter(_slots))]
    slot = Slot(touched_at=now)
    _slots.setdefault(principal, []).append(slot)
    return slot


def release(principal: str, slot: Slot | None) -> None:
    """Free exactly this slot. A no-op when it is None or already gone (expired, closed): an
    abandoned slot frees itself at the horizon, so a missed release only leaks it for that long."""
    q = _slots.get(principal)
    if slot is None or not q:
        return
    _slots[principal] = [s for s in q if s is not slot]
    if not _slots[principal]:
        del _slots[principal]


def _held(principal: str, pit_id: str) -> Slot | None:
    live = _drop_expired(principal, time.monotonic())
    return next((s for s in live if s.pit_id == pit_id), None)


def holds(principal: str, pit_id: str) -> bool:
    """True when a live slot of this principal holds `pit_id`."""
    return _held(principal, pit_id) is not None


def release_pit(principal: str, pit_id: str) -> None:
    """Free the slot that holds `pit_id`, if this principal has one."""
    release(principal, _held(principal, pit_id))


def settle(principal: str, slot: Slot | None, pit_id: str | None, *, ended: bool) -> None:
    """Account for a page that answered. `slot` is the one this request took (a first page) or
    None (a continuation, found by its PIT); `pit_id` is the walk's PIT, None only for a first page
    that was also its last. An ended walk frees its slot; an open one records its PIT and restarts
    the slot's horizon. A continuation whose slot is gone (expired, closed, or taken on another
    pod or before a restart) changes nothing."""
    held = slot if slot is not None else (_held(principal, pit_id) if pit_id else None)
    if held is None:
        return
    if ended:
        release(principal, held)
    else:
        held.pit_id = pit_id
        held.touched_at = time.monotonic()
