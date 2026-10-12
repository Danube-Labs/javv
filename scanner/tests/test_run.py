"""The runnable core: each adapter drives its scanner binary (subprocess) and parses stdout;
the orchestrator runs one scan cycle — discover → drive → envelope → push — sharing a single
ScanRun across all images (one scan_run_id/scan_order per cycle). The subprocess runner is
injected so this is unit-testable without invoking real trivy/grype."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scanner import run
from scanner.adapters.grype import scan_grype
from scanner.adapters.trivy import TrivyDbInfo, scan_trivy, trivy_db_info
from scanner.config import GrypeConfig, TrivyConfig
from scanner.discovery import ImageTarget, Location
from scanner.envelope import EffectiveConfig, Envelope
from scanner.models import Finding, Provenance, ScanResult
from scanner.push import PushResult
from scanner.run import (
    STDERR_TAIL_CHARS,
    STDERR_TAIL_LINES,
    PushFn,
    ScanFn,
    failure_detail,
    scan_all,
)
from scanner.scope import ScanScope

FIXTURES = Path(__file__).parent / "fixtures"


def runner_returning(stdout: str, expect_cmd: list[str] | None = None) -> Any:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if expect_cmd is not None:
            assert cmd == expect_cmd
        assert kw.get("capture_output") and kw.get("text") and kw.get("check")
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    return run


def target(digest: str, ref: str) -> ImageTarget:
    return ImageTarget(
        image_digest=digest,
        image_ref=ref,
        pull_ref=ref,
        locations=(Location(namespace="javv-smoke", pod="p", container="c"),),
    )


# --- drivers ---------------------------------------------------------------


def test_scan_trivy_runs_pinned_command_parses_and_stamps_version() -> None:
    out = (FIXTURES / "trivy-python-3.9.16-slim.json").read_text()
    # default config → the previously-pinned command, verbatim (#91 no-behaviour-change contract)
    img = "python:3.9.16-slim"
    expect = ["trivy", "image", "--quiet", "--scanners", "vuln", "--format", "json", img]
    result = scan_trivy(img, runner=runner_returning(out, expect))
    assert len(result.findings) > 0
    assert all(isinstance(f, Finding) for f in result.findings)
    assert result.provenance.scanner_version == "0.71.2"  # from Trivy.Version
    assert result.provenance.db_version is None  # Trivy standalone JSON has no DB info


def test_scan_grype_runs_parses_epss_and_stamps_version_and_db() -> None:
    out = (FIXTURES / "grype-python-3.9.16-slim.json").read_text()
    result = scan_grype("python:3.9.16-slim", runner=runner_returning(out))
    assert any(f.epss is not None for f in result.findings)  # grype-only signal survives the drive
    assert result.provenance.scanner_version == "0.115.0"
    assert result.provenance.db_version == "v6.1.7"
    assert result.provenance.db_built is not None  # descriptor.db.status.built


# --- orchestrator ----------------------------------------------------------


def test_scan_all_emits_one_envelope_per_target_under_one_run() -> None:
    targets = [target("sha256:a", "nginx:1.21.6"), target("sha256:b", "python:3.9.16-slim")]
    scanned: list[str] = []
    pushed: list[Envelope] = []

    def scan_fn(ref: str) -> ScanResult:
        scanned.append(ref)
        return ScanResult(
            findings=[
                Finding(vuln_id="CVE-1", package_name="p", package_version="1", severity="HIGH")
            ],
            provenance=Provenance(scanner_version="0.71.2"),
        )

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    results = scan_all(
        targets, scanner="trivy", cluster_id="c", scan_fn=scan_fn, push_fn=push_fn, scan_order=1
    )

    assert len(results) == 2
    assert scanned == ["nginx:1.21.6", "python:3.9.16-slim"]  # scanned by ref
    assert [e.image_digest for e in pushed] == ["sha256:a", "sha256:b"]
    assert {e.scanner for e in pushed} == {"trivy"}
    assert {e.scanner_version for e in pushed} == {"0.71.2"}  # provenance flows to the envelope
    # one cycle → one shared run identity across every image
    assert len({e.scan_run_id for e in pushed}) == 1
    assert len({e.scan_order for e in pushed}) == 1


def test_scan_all_stamps_observed_topology_from_discovery() -> None:
    # only the scanner observes where/how many an image runs — it must flow onto the envelope.
    tgt = ImageTarget(
        image_digest="sha256:a",
        image_ref="nginx:1.21.6",
        pull_ref="nginx@sha256:a",
        locations=(
            Location(namespace="team-a", pod="p1", container="c"),
            Location(namespace="team-a", pod="p2", container="c"),
            Location(namespace="team-b", pod="p3", container="c"),
        ),
    )
    pushed: list[Envelope] = []

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    scan_all(
        [tgt],
        scanner="trivy",
        cluster_id="c",
        scan_fn=lambda ref: ScanResult(),
        push_fn=push_fn,
        scan_order=1,
    )

    env = pushed[0]
    assert env.image_ref == "nginx:1.21.6"
    assert env.namespaces == ["team-a", "team-b"]  # sorted distinct
    assert env.replicas == 3  # three running pods
    assert env.schema_version == 4


def test_scan_all_isolates_a_failing_image_and_finishes_the_cycle() -> None:
    # D30: scan everything every cycle — one un-pullable image / scanner error
    # must not abort the rest.
    targets = [
        target("sha256:a", "good-1:1"),
        target("sha256:boom", "broken:1"),
        target("sha256:c", "good-2:1"),
    ]
    pushed: list[Envelope] = []

    def scan_fn(ref: str) -> ScanResult:
        if ref == "broken:1":
            raise subprocess.CalledProcessError(1, ["trivy"], stderr="image not found")
        return ScanResult(provenance=Provenance(scanner_version="0.71.2"))

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    results = scan_all(
        targets, scanner="trivy", cluster_id="c", scan_fn=scan_fn, push_fn=push_fn, scan_order=1
    )

    # the failing image is skipped; the two healthy ones still scan + push
    assert [e.image_digest for e in pushed] == ["sha256:a", "sha256:c"]
    assert len(results) == 2


def test_scan_trivy_passes_a_subprocess_timeout() -> None:
    seen: dict[str, Any] = {}

    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    scan_trivy("img:1", runner=runner)
    assert isinstance(seen.get("timeout"), int | float) and seen["timeout"] > 0


def test_scan_grype_passes_a_subprocess_timeout() -> None:
    seen: dict[str, Any] = {}

    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    scan_grype("img:1", runner=runner)
    assert isinstance(seen.get("timeout"), int | float) and seen["timeout"] > 0


def test_scan_all_with_no_targets_pushes_nothing() -> None:
    assert (
        scan_all(
            [],
            scanner="grype",
            cluster_id="c",
            scan_fn=lambda r: ScanResult(),
            push_fn=lambda e: PushResult(True, 1, False),
            scan_order=1,
        )
        == []
    )


def test_main_rejects_unknown_scanner_before_doing_anything(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # a typo'd JAVV_SCANNER must not silently run grype (#97)
    monkeypatch.setenv("JAVV_SCANNER", "trvy")
    assert run.main() == 2
    assert "JAVV_SCANNER" in capsys.readouterr().out  # JSON log line (shared pipeline, #156)


def test_main_rejects_garbage_backend_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JAVV_BACKEND_URL", "localhost:8000")  # missing scheme
    assert run.main() == 2
    assert "JAVV_BACKEND_URL" in capsys.readouterr().out


def test_main_rejects_malformed_cluster_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # mirrors the backend's shape rule — garbage here would 422 on every push
    monkeypatch.setenv("JAVV_CLUSTER_ID", "Bad_Cluster!")
    assert run.main() == 2
    assert "JAVV_CLUSTER_ID" in capsys.readouterr().out


@pytest.mark.parametrize("bad", ["abc", "0", "-1"])
def test_main_rejects_a_bad_retry_budget(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    monkeypatch.setenv("JAVV_PUSH_RETRY_BUDGET_SECONDS", bad)
    assert run.main() == 2  # before the scanner reads the cluster
    assert "JAVV_PUSH_RETRY_BUDGET_SECONDS" in capsys.readouterr().out


# --- cluster identity is asserted, not assumed (issue 470) -------------------


def test_cluster_id_defaults_to_the_cluster_the_kube_client_reached() -> None:
    assert run.resolve_cluster_id("live-uid-0001", None) == "live-uid-0001"


def test_cluster_id_matching_the_reached_cluster_is_accepted() -> None:
    assert run.resolve_cluster_id("live-uid-0001", "live-uid-0001") == "live-uid-0001"


def test_cluster_id_naming_another_cluster_refuses_the_cycle(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # the whole point: scanning beta and pushing it as alpha succeeds at every other layer, and
    # reconcile-on-commit then retires alpha's real inventory. Refuse before a single push.
    assert run.resolve_cluster_id("beta-uid-0002", "alpha-uid-0001") is None
    out = capsys.readouterr().out
    assert "alpha-uid-0001" in out and "beta-uid-0002" in out


# --- trivy vuln-DB provenance (#96) ------------------------------------------


def test_trivy_db_info_parses_the_version_command_output() -> None:
    out = (FIXTURES / "trivy-version.json").read_text()
    expect = ["trivy", "version", "--format", "json"]
    info = trivy_db_info(runner=runner_returning(out, expect))
    assert info.version == "2"
    assert info.built is not None and info.built.isoformat().startswith("2026-07-02T01:09:26")


def test_trivy_db_info_is_best_effort_never_fatal() -> None:
    assert trivy_db_info(runner=runner_returning("not json")) == TrivyDbInfo(None, None)

    def boom(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, cmd, stderr="no cache")

    assert trivy_db_info(runner=boom) == TrivyDbInfo(None, None)


def test_scan_trivy_stamps_the_cycle_db_info_into_provenance() -> None:
    out = (FIXTURES / "trivy-python-3.9.16-slim.json").read_text()
    db = TrivyDbInfo(version="2", built=datetime(2026, 7, 2, tzinfo=UTC))
    result = scan_trivy("python:3.9.16-slim", runner=runner_returning(out), db=db)
    assert result.provenance.scanner_version == "0.71.2"  # still from the scan report
    assert result.provenance.db_version == "2"
    assert result.provenance.db_built == db.built


# --- effective_config stamp (D44/FR-25, schema v3) ----------------------------


def test_scan_all_stamps_effective_config_and_schema_v3() -> None:
    cfg = EffectiveConfig(
        tuning=TrivyConfig(severities="CRITICAL,HIGH"),
        scope=ScanScope(ignore_namespaces=("kube-system",)),
    )
    pushed: list[Envelope] = []

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    scan_all(
        [target("sha256:a", "img:1")],
        scanner="trivy",
        cluster_id="c",
        scan_fn=lambda ref: ScanResult(),
        push_fn=push_fn,
        scan_order=7,
        effective_config=cfg,
    )
    env = pushed[0]
    assert env.schema_version == 4
    assert env.effective_config is not None
    dumped = env.effective_config.model_dump()
    assert dumped["tuning"]["severities"] == "CRITICAL,HIGH"
    assert dumped["scope"]["ignore_namespaces"] == ("kube-system",)


def test_effective_config_serializes_grype_tuning_distinctly() -> None:
    cfg = EffectiveConfig(tuning=GrypeConfig(only_fixed=True), scope=ScanScope())
    dumped = cfg.model_dump()
    assert dumped["tuning"] == {"only_fixed": True, "scope": None, "scan_timeout": 600}


# --- logging (#156): per-image progress is the cycle's observable heartbeat -----


def test_scan_all_logs_per_image_progress_at_info() -> None:
    """Operator ask (#156): a big image can scan for minutes looking hung — every image gets
    `scanning image` → `scan done` (findings + position) so progress is visible at INFO."""
    import structlog.testing

    run.log = structlog.get_logger()  # fresh proxy — an earlier main() cached the prod pipeline

    targets = [target("sha256:a", "nginx:1.21.6"), target("sha256:b", "python:3.9.16-slim")]

    def scan_fn(ref: str) -> ScanResult:
        return ScanResult(
            findings=[
                Finding(vuln_id="CVE-1", package_name="p", package_version="1", severity="HIGH")
            ],
            provenance=Provenance(scanner_version="0.71.2"),
        )

    def push_fn(env: Envelope) -> PushResult:
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    with structlog.testing.capture_logs() as logs:
        scan_all(
            targets, scanner="trivy", cluster_id="c", scan_fn=scan_fn, push_fn=push_fn, scan_order=1
        )

    scanning = [e for e in logs if e["event"] == "scanning image"]
    done = [e for e in logs if e["event"] == "scan done"]
    assert [e["image_ref"] for e in scanning] == ["nginx:1.21.6", "python:3.9.16-slim"]
    assert [e["position"] for e in scanning] == ["1/2", "2/2"]
    assert all(e["log_level"] == "info" for e in scanning + done)
    assert [e["findings"] for e in done] == [1, 1]
    assert all("duration_s" in e for e in done)


def test_scan_all_logs_a_failed_image_as_a_warning() -> None:
    """The skip-and-continue path (D30) must leave a WARNING — today it's a stderr traceback."""
    import structlog.testing

    run.log = structlog.get_logger()  # fresh proxy — an earlier main() cached the prod pipeline

    targets = [target("sha256:boom", "broken:1")]

    def scan_fn(ref: str) -> ScanResult:
        raise subprocess.CalledProcessError(1, ["trivy"], stderr="image not found")

    def push_fn(env: Envelope) -> PushResult:  # pragma: no cover — never reached
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    with structlog.testing.capture_logs() as logs:
        results = scan_all(
            targets, scanner="trivy", cluster_id="c", scan_fn=scan_fn, push_fn=push_fn, scan_order=1
        )

    assert results == []
    warnings = [e for e in logs if e["event"] == "scan failed, image skipped"]
    assert warnings and warnings[0]["log_level"] == "warning"
    assert warnings[0]["image_ref"] == "broken:1"


def test_cycle_lines_render_as_json_with_the_standard_keys(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tests above use capture_logs, which stops before the renderer — this one runs the
    production pipeline, so a line that loses its context or its traceback fails here, not in
    an operator's log search."""
    import json
    import logging

    import structlog
    from javv_common.logging import configure_logging

    configure_logging(level="info")
    monkeypatch.setattr(run, "log", structlog.get_logger())  # fresh proxy, restored after
    structlog.contextvars.bind_contextvars(scanner="trivy", cluster_id="c-json")  # as main() does

    def scan_fn(ref: str) -> ScanResult:
        if ref == "broken:1":
            raise subprocess.CalledProcessError(1, ["trivy"], stderr="image not found")
        return ScanResult(findings=[], provenance=Provenance(scanner_version="0.71.2"))

    def push_fn(env: Envelope) -> PushResult:
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    try:
        scan_all(
            [target("sha256:a", "nginx:1.21.6"), target("sha256:b", "broken:1")],
            scanner="trivy",
            cluster_id="c-json",
            scan_fn=scan_fn,
            push_fn=push_fn,
            scan_order=7,
        )
    finally:
        structlog.contextvars.clear_contextvars()
        structlog.reset_defaults()
        logging.getLogger().handlers.clear()

    lines = [json.loads(raw) for raw in capsys.readouterr().out.splitlines() if raw.strip()]
    assert [e["event"] for e in lines] == [
        "scanning image",
        "scan done",
        "scanning image",
        "scan failed, image skipped",
    ]
    for line in lines:
        assert list(line)[:3] == ["timestamp", "level", "event"]
        assert line["scanner"] == "trivy" and line["cluster_id"] == "c-json"
        assert line["scan_order"] == 7 and line["scan_run_id"]
    assert len({e["scan_run_id"] for e in lines}) == 1  # one cycle, one run id
    failed = lines[-1]
    assert failed["level"] == "warning" and "exc_info" not in failed
    assert "CalledProcessError" in failed["exception"]
    # the scanner's own words, not just "exit status 1" (issue 633)
    assert failed["reason"] == "scanner_exit" and failed["exit_code"] == 1
    assert failed["scanner_stderr"] == "image not found"


def test_scan_all_certifies_the_cycle_inventory_at_the_end() -> None:
    # commit_fn fires once with the cycle's shared run id and the SCANNED count: an image that
    # could not be scanned is left out, so one image its registry no longer serves cannot keep
    # every run partial (issue 633)
    targets = [
        target("sha256:a", "good-1:1"),
        target("sha256:boom", "broken:1"),
    ]
    pushed: list[Envelope] = []
    commits: list[tuple[str, int, datetime]] = []

    def scan_fn(ref: str) -> ScanResult:
        if ref == "broken:1":
            raise subprocess.CalledProcessError(1, ["trivy"], stderr="image not found")
        return ScanResult(provenance=Provenance(scanner_version="0.71.2"))

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    scan_all(
        targets,
        scanner="trivy",
        cluster_id="c",
        scan_fn=scan_fn,
        push_fn=push_fn,
        scan_order=1,
        commit_fn=lambda run_id, expected, started: commits.append((run_id, expected, started)),
    )

    assert len(commits) == 1
    run_id, expected, started = commits[0]
    assert run_id == pushed[0].scan_run_id  # the cycle's ONE shared identity
    assert expected == 1  # scanned, not discovered: the broken image is not expected
    assert started.tzinfo is not None


def _expected_count(scan_fn: ScanFn, push_fn: PushFn, refs: list[str]) -> int:
    commits: list[int] = []
    scan_all(
        [target(f"sha256:{i}", ref) for i, ref in enumerate(refs)],
        scanner="trivy",
        cluster_id="c",
        scan_fn=scan_fn,
        push_fn=push_fn,
        scan_order=1,
        commit_fn=lambda run_id, expected, started: commits.append(expected),
    )
    [expected] = commits
    return expected


def _ok_scan(ref: str) -> ScanResult:
    return ScanResult(provenance=Provenance(scanner_version="0.71.2"))


def _delivered(env: Envelope) -> PushResult:
    return PushResult(delivered=True, attempts=1, dead_lettered=False)


def test_a_cycle_with_no_failure_expects_every_discovered_image() -> None:
    assert _expected_count(_ok_scan, _delivered, ["a:1", "b:1", "c:1"]) == 3


def test_a_dead_lettered_push_still_counts_as_expected() -> None:
    # the image scanned, so its doc SHOULD land; it did not, and the run must stay partial
    def dead_letter(env: Envelope) -> PushResult:
        return PushResult(delivered=False, attempts=5, dead_lettered=True)

    assert _expected_count(_ok_scan, dead_letter, ["a:1", "b:1"]) == 2


def test_a_timed_out_scan_is_not_expected_either() -> None:
    def scan_fn(ref: str) -> ScanResult:
        if ref == "slow:1":
            raise subprocess.TimeoutExpired(["trivy"], 600)
        return _ok_scan(ref)

    assert _expected_count(scan_fn, _delivered, ["a:1", "slow:1", "b:1"]) == 2


def test_a_cycle_where_every_scan_fails_keeps_the_discovered_count() -> None:
    # nothing landed, so the backend calls the run partial and the last good inventory keeps
    # answering; expecting 0 would certify an empty inventory for a cluster that runs images
    def scan_fn(ref: str) -> ScanResult:
        raise subprocess.CalledProcessError(1, ["trivy"], stderr="no route to registry")

    assert _expected_count(scan_fn, _delivered, ["a:1", "b:1"]) == 2


def test_a_cluster_that_runs_nothing_expects_nothing() -> None:
    # a real empty inventory is still certified as empty
    assert _expected_count(_ok_scan, _delivered, []) == 0


def test_failure_detail_carries_the_exit_code_and_the_scanners_last_lines() -> None:
    stderr = "pulling layers\nFATAL image scan error\nUNAUTHORIZED: authentication required\n"
    detail = failure_detail(subprocess.CalledProcessError(1, ["trivy"], stderr=stderr))
    assert detail == {
        "reason": "scanner_exit",
        "exit_code": 1,
        "scanner_stderr": stderr.strip(),
    }


def test_failure_detail_keeps_only_the_tail_of_a_long_stderr() -> None:
    lines = [f"line {i}" for i in range(40)]
    detail = failure_detail(subprocess.CalledProcessError(2, ["grype"], stderr="\n".join(lines)))
    assert detail["scanner_stderr"] == "\n".join(lines[-STDERR_TAIL_LINES:])


def test_failure_detail_caps_one_enormous_line() -> None:
    detail = failure_detail(
        subprocess.CalledProcessError(1, ["trivy"], stderr="x" * 50_000 + "END")
    )
    tail = detail["scanner_stderr"]
    assert isinstance(tail, str) and len(tail) == STDERR_TAIL_CHARS and tail.endswith("END")


@pytest.mark.parametrize("stderr", [None, "", "   \n", b"bytes, not text"])
def test_failure_detail_with_no_usable_stderr_is_an_empty_tail(
    stderr: str | bytes | None,
) -> None:
    detail = failure_detail(subprocess.CalledProcessError(1, ["trivy"], stderr=stderr))
    assert detail == {"reason": "scanner_exit", "exit_code": 1, "scanner_stderr": ""}


def test_failure_detail_names_a_timeout() -> None:
    detail = failure_detail(subprocess.TimeoutExpired(["trivy"], 600))
    assert detail == {"reason": "timeout", "timeout_s": 600}


def test_failure_detail_for_any_other_error_claims_nothing_about_the_scanner() -> None:
    assert failure_detail(json.JSONDecodeError("bad", "", 0)) == {"reason": "error"}


def test_the_scan_pulls_the_digest_and_the_envelope_shows_the_tag() -> None:
    tgt = ImageTarget(
        image_digest="sha256:" + "d" * 64,
        image_ref="registry.io/app:1",
        pull_ref="registry.io/app@sha256:" + "d" * 64,
        locations=(Location(namespace="ns", pod="p", container="c"),),
    )
    pulled: list[str] = []
    pushed: list[Envelope] = []

    def scan_fn(ref: str) -> ScanResult:
        pulled.append(ref)
        return ScanResult()

    def push_fn(env: Envelope) -> PushResult:
        pushed.append(env)
        return PushResult(delivered=True, attempts=1, dead_lettered=False)

    scan_all([tgt], scanner="trivy", cluster_id="c", scan_fn=scan_fn, push_fn=push_fn, scan_order=1)

    assert pulled == [tgt.pull_ref]
    assert pushed[0].image_ref == "registry.io/app:1"


@pytest.mark.parametrize(
    ("env", "named"),
    [
        ({"JAVV_TRIVY_SCANNERS": "bogus"}, "JAVV_TRIVY_SCANNERS"),
        ({"JAVV_SCANNER": "grype", "JAVV_GRYPE_SCOPE": "everything"}, "JAVV_GRYPE_SCOPE"),
    ],
)
def test_main_rejects_a_bad_scan_setting_with_exit_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    env: dict[str, str],
    named: str,
) -> None:
    # CONFIGURATION.md: a value that is not valid stops the scanner with exit code 2
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert run.main() == 2  # before the scanner reads the cluster
    out = capsys.readouterr().out
    assert named in out and "Traceback" not in out
