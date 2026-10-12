"""Deliver an envelope to the backend ingest endpoint.

The body is gzipped with a fixed mtime so the same envelope produces byte-identical content —
combined with the backend's deterministic `_id`, a re-sent push double-counts nothing (D18).
Transient failures (transport errors, 429, 5xx) are retried with exponential backoff + full
jitter — the only flow control without a broker — while the cycle's retry budget lasts (issue 832:
a store restart outlasted a fixed 5 tries). Permanent failures (other 4xx) or a spent budget are
written to a dead-letter sink so nothing is silently lost. Sync client: the scanner is a batch
CronJob, not an async request path.
"""

import gzip
import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog

from scanner.envelope import Envelope

INGEST_PATH = "/api/v1/ingest/scan"  # must match the backend router (M1)
BUDGET_SETTING = "JAVV_PUSH_RETRY_BUDGET_SECONDS"
DEFAULT_BUDGET_S = 360  # outlasts the 300 s a `helm upgrade javv` gives the backend to start
# the waits between tries: doubling from the first, each one at most the cap
FIRST_WAIT_S = 0.5
WAIT_CAP_S = 30.0


@dataclass(frozen=True)
class PushResult:
    delivered: bool
    attempts: int
    dead_lettered: bool


def _backoff(attempt: int, *, base: float, cap: float, rng: Callable[[], float]) -> float:
    ceiling = min(cap, base * 2 ** (attempt - 1))
    return rng() * ceiling  # full jitter


def _is_transient(resp: httpx.Response) -> bool:
    return resp.status_code == 429 or resp.is_server_error


log = structlog.get_logger()


@dataclass
class RetryBudget:
    """The time one cycle may spend retrying, shared by its pushes and its inventory commit. A
    call is charged from its first failure to its end: the waits and the tries after it. Once the
    budget is spent, a failing call gives up at once, so a dead backend costs the cycle about the
    budget, not the budget per image."""

    seconds: float
    spent: float = 0.0
    _warned: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "RetryBudget":
        raw = environ.get(BUDGET_SETTING, "").strip()
        try:
            seconds = int(raw) if raw else DEFAULT_BUDGET_S
        except ValueError:
            seconds = 0
        if seconds <= 0:
            raise ValueError(f"invalid {BUDGET_SETTING}: {raw!r} (want positive whole seconds)")
        return cls(seconds=seconds)

    def left(self) -> float:
        return max(0.0, self.seconds - self.spent)

    def give_up(self) -> None:
        if not self._warned:  # one line per cycle: each dead-lettered envelope logs its own
            self._warned = True
            log.warning("push retry budget spent", budget_s=self.seconds)


def send_with_retries(
    send: Callable[[], httpx.Response],
    *,
    budget: RetryBudget,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    rng: Callable[[], float] = random.random,
) -> tuple[httpx.Response | None, int]:
    """Call `send` until it answers anything but a transient failure, or the budget is spent.
    Returns the last answer (None after a network error) and the number of tries."""
    tries = 0
    failing_since: float | None = None
    while True:
        tries += 1
        try:
            resp: httpx.Response | None = send()
            transient = _is_transient(resp)
        except httpx.RequestError:
            resp, transient = None, True
        now = clock()
        if failing_since is not None:
            budget.spent += now - failing_since
        if not transient:
            return resp, tries
        failing_since = now
        if budget.left() <= 0:
            budget.give_up()
            return resp, tries
        sleep(min(_backoff(tries, base=FIRST_WAIT_S, cap=WAIT_CAP_S, rng=rng), budget.left()))


def _dead_letter(envelope: Envelope, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(envelope.model_dump_json() + "\n")
    # an envelope falling out of delivery is an operator signal (#156) — replay is manual
    log.warning(
        "envelope dead-lettered",
        image_digest=envelope.image_digest,
        scan_run_id=envelope.scan_run_id,
        path=str(path),
    )


def push_envelope(
    envelope: Envelope,
    *,
    client: httpx.Client,
    dead_letter_path: Path,
    budget: RetryBudget,
    path: str = INGEST_PATH,
    token: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    rng: Callable[[], float] = random.random,
) -> PushResult:
    body = gzip.compress(envelope.model_dump_json().encode(), mtime=0)
    headers = {"Content-Encoding": "gzip", "Content-Type": "application/json"}
    if token:  # ingest bearer token (D38/M14); never logged
        headers["Authorization"] = f"Bearer {token}"

    resp, tries = send_with_retries(
        lambda: client.post(path, content=body, headers=headers),
        budget=budget,
        sleep=sleep,
        clock=clock,
        rng=rng,
    )
    if resp is not None and resp.is_success:
        return PushResult(delivered=True, attempts=tries, dead_lettered=False)
    # a permanent client error (4xx, not 429), or a transient one the budget did not outlast
    _dead_letter(envelope, dead_letter_path)
    return PushResult(delivered=False, attempts=tries, dead_lettered=True)
