"""The wave replay script (issue 883): `development/scripts/replay_waves.py` pushes made-up scan
data as several scans over time, so first-seen, new-in-range and resolved get a spread on a fresh
store. The plan is pure and seeded; every envelope it builds must pass the real ingest model, and
the push is run against the real app on the test store."""

import importlib.util
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.models.envelope import IngestEnvelope
from os_env import OS_URL, requires_opensearch

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


# --- the push, against the app on the test store ----------------------------------------------
PASSWORD = "replay-waves-password"


@pytest.fixture
async def app_env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
            "capabilities": ["can_manage_tokens"],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-10-16T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    yield http, client, username
    await http.aclose()
    await client.close()


async def _findings(client: AsyncOpenSearch, cluster_id: str) -> list[dict]:
    await client.indices.refresh(index="findings")
    r = await client.search(
        index="findings",
        body={"query": {"term": {"cluster_id": cluster_id}}, "size": 10_000},
    )
    return [h["_source"] for h in r["hits"]["hits"]]


@requires_opensearch
async def test_a_replay_spreads_first_seen_and_resolves_what_a_wave_leaves_out(app_env) -> None:
    http, client, username = app_env
    cluster = f"c-rp-{uuid.uuid4().hex[:8]}"
    plan = rw.plan_waves(
        seed=5, images=3, findings=12, waves=3, span_hours=48.0, now=datetime.now(UTC)
    )
    summary = await rw.replay(
        http, plan, cluster_id=cluster, username=username, password=PASSWORD, say=lambda _: None
    )
    assert summary["committed"] == 3 * 2, "one committed inventory run for each wave and scanner"

    docs = await _findings(client, cluster)
    times = {w.at for w in plan.waves}
    first_seen = {datetime.fromisoformat(d["first_seen_at"]) for d in docs}
    assert first_seen <= times and len(first_seen) >= 2, "first seen spreads over the waves"

    resolved = [d for d in docs if not d["present"]]
    assert resolved, "a wave that leaves a finding out resolves it"
    assert {datetime.fromisoformat(d["resolved_at"]) for d in resolved} <= times

    last = plan.waves[-1]
    expected = {
        (scanner, digest, f.vuln_id, f.package_name)
        for (scanner, digest), rows in last.scans.items()
        for f in rows
    }
    present = {
        (d["scanner"], d["image_digest"], d["cve_id"], d["package_name"])
        for d in docs
        if d["present"]
    }
    assert present == expected, "what is present is exactly the last wave"


@requires_opensearch
async def test_a_replay_refuses_a_cluster_that_exists(app_env) -> None:
    http, client, username = app_env
    cluster = f"c-rp-{uuid.uuid4().hex[:8]}"
    plan = rw.plan_waves(
        seed=5, images=1, findings=3, waves=2, span_hours=1.0, now=datetime.now(UTC)
    )
    await rw.replay(
        http, plan, cluster_id=cluster, username=username, password=PASSWORD, say=lambda _: None
    )
    before = await _findings(client, cluster)
    with pytest.raises(rw.ReplayRefused, match="already exists"):
        await rw.replay(
            http, plan, cluster_id=cluster, username=username, password=PASSWORD, say=lambda _: None
        )
    assert await _findings(client, cluster) == before


@requires_opensearch
async def test_a_replay_stops_on_a_wrong_password(app_env) -> None:
    http, _, username = app_env
    plan = rw.plan_waves(
        seed=5, images=1, findings=3, waves=2, span_hours=1.0, now=datetime.now(UTC)
    )
    with pytest.raises(rw.ReplayRefused, match="sign-in failed"):
        await rw.replay(
            http,
            plan,
            cluster_id="c-rp-nopass00",
            username=username,
            password="wrong",
            say=lambda _: None,
        )


@requires_opensearch
async def test_a_replay_stops_for_an_account_that_must_change_its_password(app_env) -> None:
    http, client, username = app_env
    await client.update(
        index="system-users",
        id=username,
        body={"doc": {"must_change": True}},
        params={"refresh": "true"},
    )
    plan = rw.plan_waves(
        seed=5, images=1, findings=3, waves=2, span_hours=1.0, now=datetime.now(UTC)
    )
    with pytest.raises(rw.ReplayRefused, match="must change the password first"):
        await rw.replay(
            http,
            plan,
            cluster_id="c-rp-mustchg0",
            username=username,
            password=PASSWORD,
            say=lambda _: None,
        )


def test_the_command_line_requires_a_backend_and_a_password(monkeypatch, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        rw.main(["--cluster", "replay-0001"])
    assert exc.value.code == 2 and "--backend" in capsys.readouterr().err
    monkeypatch.delenv("JAVV_REPLAY_PASSWORD", raising=False)
    assert rw.main(["--backend", "http://127.0.0.1:9"]) == 2
    assert "JAVV_REPLAY_PASSWORD" in capsys.readouterr().err
