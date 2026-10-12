"""Push delivers an envelope to the backend ingest endpoint: gzipped body, idempotent
(deterministic content — a retried push double-counts nothing server-side, D18), transient
failures (network / 429 / 5xx) retried with backoff+jitter while the cycle's retry budget lasts,
permanent failures (other 4xx) or a spent budget written to a dead-letter sink. Tested with
httpx.MockTransport and a fake clock — no network, no real waits."""

import gzip
import json
from pathlib import Path

import httpx
import pytest
import structlog

from scanner import push as push_module
from scanner.envelope import Envelope, build_envelope, new_scan_run
from scanner.models import Finding
from scanner.push import RetryBudget, push_envelope

ERR = "ERR"  # sentinel: handler raises a transport error on this attempt


def make_envelope() -> Envelope:
    return build_envelope(
        new_scan_run(1),
        cluster_id="c",
        scanner="trivy",
        image_digest="sha256:x",
        findings=[Finding(vuln_id="CVE-1", package_name="p", package_version="1", severity="HIGH")],
    )


class Clock:
    """Time that only moves when a wait or a request moves it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


def client_for(
    steps: list[object], *, clock: Clock | None = None, took: float = 0.0
) -> tuple[httpx.Client, list[httpx.Request]]:
    """A client whose Nth request yields steps[N] (an int status or ERR sentinel), and moves the
    clock by `took` seconds per request."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        step = steps[len(requests)]
        requests.append(request)
        if clock is not None:
            clock.now += took
        if step == ERR:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(int(step))  # type: ignore[arg-type]

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://backend"), requests


def push(  # noqa: ANN201
    env: Envelope,
    client: httpx.Client,
    dead_letter: Path,
    *,
    budget: RetryBudget | None = None,
    clock: Clock | None = None,
    rng: float = 0.0,
):
    clock = clock or Clock()
    result = push_envelope(
        env,
        client=client,
        dead_letter_path=dead_letter,
        budget=budget or RetryBudget(seconds=360),
        sleep=clock.sleep,
        clock=clock,
        rng=lambda: rng,
    )
    return result, clock.waits


def test_delivers_gzipped_body_on_first_success(tmp_path: Path) -> None:
    env = make_envelope()
    client, requests = client_for([200])
    result, sleeps = push(env, client, tmp_path / "dl.jsonl")

    assert (result.delivered, result.attempts, result.dead_lettered) == (True, 1, False)
    assert sleeps == []
    req = requests[0]
    assert req.headers["content-encoding"] == "gzip"
    assert gzip.decompress(req.content).decode() == env.model_dump_json()  # body is the envelope


def test_gzip_body_is_deterministic_for_idempotent_retries(tmp_path: Path) -> None:
    env = make_envelope()
    c1, r1 = client_for([200])
    c2, r2 = client_for([200])
    push(env, c1, tmp_path / "a.jsonl")
    push(env, c2, tmp_path / "b.jsonl")
    assert r1[0].content == r2[0].content  # byte-identical → safe to re-send


@pytest.mark.parametrize("transient", [503, 429, 500, ERR])
def test_retries_transient_then_succeeds(tmp_path: Path, transient: object) -> None:
    client, requests = client_for([transient, 200])
    result, sleeps = push(make_envelope(), client, tmp_path / "dl.jsonl")
    assert result.delivered is True
    assert result.attempts == 2
    assert len(requests) == 2
    assert len(sleeps) == 1  # backed off once between the two attempts


def test_permanent_4xx_is_not_retried_and_is_dead_lettered(tmp_path: Path) -> None:
    env = make_envelope()
    dl = tmp_path / "dl.jsonl"
    client, requests = client_for([400, 200])  # 200 would be used if it (wrongly) retried
    result, sleeps = push(env, client, dl)

    assert (result.delivered, result.dead_lettered, result.attempts) == (False, True, 1)
    assert len(requests) == 1  # not retried
    assert sleeps == []
    lines = dl.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == json.loads(env.model_dump_json())


def test_a_spent_budget_dead_letters(tmp_path: Path) -> None:
    dl = tmp_path / "dl.jsonl"
    clock = Clock()
    client, requests = client_for([503] * 20, clock=clock)
    budget = RetryBudget(seconds=10)
    result, sleeps = push(make_envelope(), client, dl, budget=budget, clock=clock, rng=1.0)

    # waits of 0.5, 1, 2, 4, then the 2.5 s left; one more try after the last wait
    assert sleeps == [0.5, 1.0, 2.0, 4.0, 2.5]
    assert (result.delivered, result.dead_lettered, result.attempts) == (False, True, 6)
    assert len(requests) == 6
    assert budget.left() == 0
    assert len(dl.read_text().splitlines()) == 1


def test_a_48_second_store_restart_is_outlasted(tmp_path: Path) -> None:
    # issue 832: during a 48 s restart, 5 tries (7.5 s of waits) dead-lettered 5 of 6 envelopes
    clock = Clock()

    def until_up(request: httpx.Request) -> httpx.Response:
        clock.now += 0.2  # each try takes a little time
        return httpx.Response(503 if clock.now < 48 else 202)

    client = httpx.Client(transport=httpx.MockTransport(until_up), base_url="http://backend")
    result, _ = push(make_envelope(), client, tmp_path / "dl.jsonl", clock=clock, rng=1.0)

    assert (result.delivered, result.dead_lettered) == (True, False)
    assert clock.now >= 48


def test_each_wait_is_at_most_30_seconds(tmp_path: Path) -> None:
    clock = Clock()
    client, _ = client_for([503] * 40, clock=clock)
    push(make_envelope(), client, tmp_path / "dl.jsonl", clock=clock, rng=1.0)

    assert max(clock.waits) == 30.0
    assert round(sum(clock.waits)) == 360  # the budget, all of it waits here


def test_the_tries_count_against_the_budget_too(tmp_path: Path) -> None:
    clock = Clock()
    client, requests = client_for([503] * 20, clock=clock, took=5.0)
    budget = RetryBudget(seconds=12)
    push(make_envelope(), client, tmp_path / "dl.jsonl", budget=budget, clock=clock, rng=1.0)

    # 5 s per try: after the first failure, wait 0.5 + try 5 + wait 1 + try 5 = 11.5, then a
    # wait of the 0.5 left and a last try: 17 s charged, more than 12, and no try after that
    assert len(requests) == 4
    assert budget.spent == pytest.approx(17.0)


def test_one_budget_for_the_cycle(tmp_path: Path) -> None:
    clock = Clock()
    budget = RetryBudget(seconds=5)
    first, _ = client_for([503] * 20, clock=clock)
    push(make_envelope(), first, tmp_path / "dl.jsonl", budget=budget, clock=clock, rng=1.0)
    waited = len(clock.waits)

    second, requests = client_for([503, 202], clock=clock)
    result, _ = push(make_envelope(), second, tmp_path / "dl.jsonl", budget=budget, clock=clock)

    # the first push spent it: the second tries once, with no wait, and is dead-lettered
    assert len(clock.waits) == waited
    assert len(requests) == 1
    assert result.dead_lettered is True


def test_a_spent_budget_is_logged_once_per_cycle(tmp_path: Path, monkeypatch) -> None:
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(push_module, "log", structlog.wrap_logger(None, processors=[capture]))
    clock = Clock()
    budget = RetryBudget(seconds=1)
    for _ in range(3):
        client, _ = client_for([503] * 20, clock=clock)
        push(make_envelope(), client, tmp_path / "dl.jsonl", budget=budget, clock=clock, rng=1.0)

    spent = [e for e in capture.entries if e["event"] == "push retry budget spent"]
    assert [(e["log_level"], e["budget_s"]) for e in spent] == [("warning", 1)]
    lost = [e for e in capture.entries if e["event"] == "envelope dead-lettered"]
    assert len(lost) == 3  # each envelope still logs its own


def test_the_budget_setting() -> None:
    assert RetryBudget.from_env({}).seconds == 360
    assert RetryBudget.from_env({"JAVV_PUSH_RETRY_BUDGET_SECONDS": " 120 "}).seconds == 120
    for bad in ("abc", "0", "-5", "1.5"):
        with pytest.raises(ValueError, match=f"JAVV_PUSH_RETRY_BUDGET_SECONDS: '{bad}'"):
            RetryBudget.from_env({"JAVV_PUSH_RETRY_BUDGET_SECONDS": bad})


def test_dead_letter_logs_a_warning(tmp_path: Path) -> None:
    """An envelope falling out of delivery is an operator signal (#156) — WARNING, with the path."""
    push_module.log = structlog.get_logger()  # fresh proxy (cached-pipeline trap)

    env = make_envelope()
    dl = tmp_path / "dl.jsonl"
    client, _ = client_for([400])

    with structlog.testing.capture_logs() as logs:
        push(env, client, dl)

    warnings = [e for e in logs if e["event"] == "envelope dead-lettered"]
    assert warnings and warnings[0]["log_level"] == "warning"
    assert warnings[0]["path"] == str(dl)
