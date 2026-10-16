"""The wave replay script (issue 883): `development/scripts/replay_waves.py` pushes made-up scan
data as several scans over time, so first-seen, new-in-range and resolved get a spread on a fresh
store. The plan is pure and seeded; every envelope it builds must pass the real ingest model."""

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.models.envelope import IngestEnvelope

SCRIPT = Path(__file__).resolve().parents[2] / "development" / "scripts" / "replay_waves.py"
_spec = importlib.util.spec_from_file_location("replay_waves", SCRIPT)
assert _spec and _spec.loader
rw = importlib.util.module_from_spec(_spec)
sys.modules["replay_waves"] = rw  # dataclasses resolve their module by name
_spec.loader.exec_module(rw)

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def _plan(**kw):
    args = {"seed": 7, "images": 8, "findings": 30, "waves": 4, "span_hours": 60.0, "now": NOW}
    return rw.plan_waves(**(args | kw))


def _present(plan, scanner: str) -> list[set[tuple[str, str]]]:
    """For each wave: the (digest, vuln_id) pairs that one scanner reports."""
    return [
        {
            (digest, f.vuln_id)
            for (s, digest), rows in wave.scans.items()
            if s == scanner
            for f in rows
        }
        for wave in plan.waves
    ]


def test_wave_times_are_spread_over_the_span_and_end_now() -> None:
    times = [w.at for w in _plan().waves]
    assert times[0] == NOW - timedelta(hours=60)
    assert times[-1] == NOW
    assert times == sorted(times) and len(set(times)) == 4


def test_the_same_seed_gives_the_same_plan() -> None:
    assert _plan() == _plan()
    assert _plan() != _plan(seed=8)


@pytest.mark.parametrize("scanner", ["trivy", "grype"])
def test_findings_are_born_resolved_and_come_back_across_the_waves(scanner: str) -> None:
    present = _present(_plan(), scanner)
    first, last = present[0], present[-1]
    from_start = {digest for digest, _ in first}  # an image that joins later adds findings too
    assert {p for p in last - first if p[0] in from_start}, "a finding born after the first wave"
    assert first - last, "a finding seen early and resolved by the last wave"
    assert any(
        (present[i - 1] - present[i]) & present[i + 1] for i in range(1, len(present) - 1)
    ), "a finding missing from one wave and back in the next"


def test_some_images_join_after_the_first_wave() -> None:
    plan = _plan()
    digests = [{d for (_, d) in w.scans} for w in plan.waves]
    assert digests[-1] - digests[0]
    assert all(a <= b for a, b in zip(digests, digests[1:], strict=False)), "images only join"


def test_the_two_scanners_do_not_report_the_same_set() -> None:
    plan = _plan()
    assert _present(plan, "trivy")[-1] != _present(plan, "grype")[-1]


def test_every_envelope_passes_the_ingest_model() -> None:
    plan = _plan()
    seen = 0
    for wave in plan.waves:
        for (scanner, digest), rows in wave.scans.items():
            body = rw.build_envelope(
                "c-replay-test", scanner, plan.images[digest], rows, wave, 11, f"run-{wave.index}"
            )
            env = IngestEnvelope.model_validate(body)
            assert env.last_seen_at == wave.at and env.scan_order == 11
            seen += 1
    assert seen > 0


def test_severities_keep_each_scanner_s_own_casing() -> None:
    plan = _plan()
    words = {
        scanner: {
            f.severity
            for w in plan.waves
            for (s, _), rows in w.scans.items()
            if s == scanner
            for f in rows
        }
        for scanner in ("trivy", "grype")
    }
    assert words["trivy"] <= {"CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"}
    assert words["grype"] <= {"Critical", "High", "Medium", "Low", "Negligible", "Unknown"}


@pytest.mark.parametrize(
    ("kw", "message"),
    [
        ({"span_hours": 72.0}, "shorter than 72 hours"),
        ({"span_hours": 0.0}, "more than 0 hours"),
        ({"waves": 1}, "at least 2 waves"),
        ({"images": 0}, "at least 1 image"),
        ({"findings": 0}, "at least 1 finding"),
    ],
)
def test_a_plan_outside_the_limits_is_refused(kw: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _plan(**kw)
