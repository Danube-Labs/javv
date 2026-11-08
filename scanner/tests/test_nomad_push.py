"""The rules of the Nomad scan job script (deploy/nomad/javv_nomad_push.py, issue 1155): the place
of a job, the skip of the job itself, the skip settings, the scan scope of JAVV, expected_count and
the settings that the script refuses. The script is a standalone file: the test loads it by path.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "nomad" / "javv_nomad_push.py"
spec = importlib.util.spec_from_file_location("javv_nomad_push", SCRIPT)
assert spec and spec.loader
push = importlib.util.module_from_spec(spec)
spec.loader.exec_module(push)

REQUIRED = {
    "JAVV_BACKEND_URL": "http://javv.test",
    "JAVV_TOKEN": "t",
    "JAVV_CLUSTER_ID": "nomad-test-01",
    "JAVV_SCANNER": "trivy",
}


def alloc(
    ns: str,
    job: str,
    *tasks: tuple[str, str],
    parent: str = "",
    kind: str = "service",
    meta: dict[str, str] | None = None,
    status: str = "running",
    driver: str = "docker",
    state: str = "running",
):
    """One allocation of the Nomad API, with its tasks (name, image)."""
    return {
        "ID": f"{ns}-{job or parent}",
        "Namespace": ns,
        "JobID": f"{parent}/periodic-1" if parent else job,
        "ClientStatus": status,
        "TaskGroup": "g",
        "Job": {
            "ParentID": parent,
            "Type": kind,
            "Meta": meta,
            "TaskGroups": [
                {
                    "Name": "g",
                    "Tasks": [
                        {"Name": n, "Driver": driver, "Config": {"image": i}} for n, i in tasks
                    ],
                }
            ],
        },
        "TaskStates": {n: {"State": state} for n, _ in tasks},
    }


SCAN = {"javv_scan": "true"}
CLUSTER = [
    alloc("default", "web", ("nginx", "nginx:1.27-alpine")),
    alloc("default", "web", ("nginx", "nginx:1.27-alpine")) | {"ID": "default-web-2"},
    alloc("billing", "web", ("nginx", "nginx:1.27-alpine")),
    alloc("billing", "billing-api", ("nginx", "nginx:1.27-alpine"), ("cache", "redis:7-alpine")),
    alloc(
        "default", "", ("push", "javv-scanner-trivy:0.76.2"), parent="javv-scan-trivy", meta=SCAN
    ),
    alloc(
        "default", "", ("push", "javv-scanner-grype:0.121.1"), parent="javv-scan-grype", meta=SCAN
    ),
    alloc("other", "javv-scan-trivy", ("app", "lookalike:1")),
    alloc("default", "nightly", ("run", "busybox:1.36"), parent="nightly", kind="batch"),
    alloc("default", "pair", ("a", "alpine:3.20"), ("b", "alpine:3.20")),
    alloc(
        "default", "mesh", ("app", "app:1"), ("connect-proxy-app", "${meta.connect.sidecar_image}")
    ),
    alloc("default", "done", ("run", "done:1"), status="complete"),
    alloc("default", "raw", ("run", "raw:1"), driver="raw_exec"),
    alloc("default", "starting", ("run", "starting:1"), state="pending"),
]


@pytest.fixture
def settings(monkeypatch):
    def make(**extra: str):
        base = REQUIRED | {"NOMAD_JOB_PARENT_ID": "javv-scan-trivy", "NOMAD_NAMESPACE": "default"}
        for k, v in (base | extra).items():
            monkeypatch.setenv(k, v)
        return push.Settings()

    return make


@pytest.fixture
def nomad(monkeypatch):
    """The Nomad API of CLUSTER. Records the namespaces that the script asked for. All namespaces
    is `*`, which the URL must carry quoted (`%2A`), as the real API got it."""
    asked: list[str] = []

    def get(_s, path: str):
        if path.startswith("/v1/allocations?namespace="):
            ns = path.split("=", 1)[1]
            asked.append(ns)
            return [a for a in CLUSTER if ns == "%2A" or a["Namespace"] == ns]
        alloc_id = path.split("/v1/allocation/", 1)[1].split("?", 1)[0]
        return next(a for a in CLUSTER if a["ID"] == alloc_id)

    monkeypatch.setattr(push, "nomad_get", get)
    return asked


def test_place_is_the_job_in_default_and_namespace_slash_job_elsewhere(settings, nomad):
    images, _ = push.running_images(settings(), {})
    assert images["nginx:1.27-alpine"] == {
        "places": {"web", "billing/web", "billing/billing-api"},
        "replicas": 4,
    }
    assert images["redis:7-alpine"] == {"places": {"billing/billing-api"}, "replicas": 1}


def test_a_periodic_run_counts_as_its_parent_job(settings, nomad):
    images, _ = push.running_images(settings(), {})
    assert images["busybox:1.36"]["places"] == {"nightly"}


def test_the_scan_jobs_skip_themselves_and_each_other(settings, nomad):
    images, _ = push.running_images(settings(), {})
    assert not any("javv-scanner" in ref for ref in images)
    # a job with the same ID in another namespace, and with no meta, is not the job itself
    assert images["lookalike:1"]["places"] == {"other/javv-scan-trivy"}


def test_all_namespaces_go_to_nomad_quoted(settings, nomad):
    push.running_images(settings(), {})
    assert nomad == ["%2A"]


def test_only_running_docker_tasks_count(settings, nomad):
    images, _ = push.running_images(settings(), {})
    assert not {"done:1", "raw:1", "starting:1"} & set(images)


def test_an_image_that_nomad_sets_at_start_is_skipped(settings, nomad):
    images, skipped = push.running_images(settings(), {})
    assert skipped["unresolved"] == ["${meta.connect.sidecar_image}"]
    assert images["app:1"] == {"places": {"mesh"}, "replicas": 1}


def test_replicas_count_allocations_as_the_scanners_count_pods(settings, nomad):
    images, _ = push.running_images(settings(), {})
    assert images["alpine:3.20"] == {"places": {"pair"}, "replicas": 1}


def test_skip_jobs_takes_patterns_on_the_job_id(settings, nomad):
    images, skipped = push.running_images(settings(JAVV_NOMAD_SKIP_JOBS="billing-*, nightly"), {})
    assert skipped["job"] == ["billing-api", "nightly"]
    # the job "web" of the namespace billing has a job ID that the pattern does not match
    assert images["nginx:1.27-alpine"]["places"] == {"web", "billing/web"}
    assert "redis:7-alpine" not in images


def test_namespaces_limits_the_api_calls(settings, nomad):
    images, _ = push.running_images(settings(JAVV_NOMAD_NAMESPACES="default"), {})
    assert nomad == ["default"]
    assert images["nginx:1.27-alpine"] == {"places": {"web"}, "replicas": 2}


def test_the_scope_of_javv_applies_to_places_kinds_and_images(settings, nomad):
    s = settings()
    images, skipped = push.running_images(s, {"ignore_namespaces": ["billing/*"]})
    assert skipped["namespace"] == ["billing/billing-api", "billing/web"]
    assert images["nginx:1.27-alpine"]["places"] == {"web"}

    images, skipped = push.running_images(s, {"include_namespaces": ["billing/*"]})
    assert set(images) == {"nginx:1.27-alpine", "redis:7-alpine"}

    images, skipped = push.running_images(s, {"ignore_kinds": ["batch"]})
    assert skipped["kind"] == ["nightly"]

    images, skipped = push.running_images(s, {"exclude_images": ["redis:*"]})
    assert skipped["image"] == ["redis:7-alpine"]
    assert "redis:7-alpine" not in images


def test_expected_count_keeps_the_cycle_partial_when_nothing_scanned():
    assert push.expected_count(scanned=2, found=3) == 2
    assert push.expected_count(scanned=0, found=3) == 3
    assert push.expected_count(scanned=0, found=0) == 0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JAVV_TRIVY_SEVERITIES", "URGENT"),
        ("JAVV_TRIVY_SCANNERS", "vuln,virus"),
        ("JAVV_TRIVY_TIMEOUT", "ten minutes"),
        ("JAVV_PUSH_RETRY_BUDGET_SECONDS", "0"),
        ("JAVV_SCANNER", "clair"),
        ("JAVV_BACKEND_URL", "javv.example.com"),
        ("JAVV_CLUSTER_ID", "Nomad_Prod"),
    ],
)
def test_a_setting_that_is_not_valid_stops_the_job(settings, name, value):
    with pytest.raises(push.SettingError, match=name):
        settings(**{name: value})


def test_the_settings_go_into_the_scan_settings(settings):
    s = settings(JAVV_TRIVY_SEVERITIES="high,critical", JAVV_TRIVY_IGNORE_UNFIXED="true")
    assert s.tuning == {
        "scanners": "vuln",
        "ignore_unfixed": True,
        "severities": "HIGH,CRITICAL",
        "pkg_types": None,
        "timeout": None,
    }
    g = settings(JAVV_SCANNER="grype", JAVV_GRYPE_SCOPE="All-Layers")
    assert g.tuning == {"only_fixed": False, "scope": "all-layers", "scan_timeout": 600}


def test_counts_use_the_severity_word_of_the_scanner():
    # raw scanner casing, as Grype and Trivy write it
    findings = [
        {"severity": "High", "fixable": True},
        {"severity": "MODERATE", "fixable": False},
        {"severity": "Negligible", "fixable": False},
        {"severity": "whatever", "fixable": True},
    ]
    assert push.counts(findings) == {
        "crit": 0,
        "high": 1,
        "med": 1,
        "low": 0,
        "negligible": 1,
        "unknown": 1,
        "total": 4,
        "fixable": 2,
    }


class FakeJavv:
    """The JAVV API for main(): records each call, answers from `replies` by path."""

    def __init__(self, replies: dict[str, tuple[int | None, object]]):
        self.calls: list[tuple[str, str, object, bool]] = []
        self.replies = replies

    def __call__(self, method: str, path: str, body=None, gz: bool = False):
        self.calls.append((method, path, body, gz))
        return self.replies.get(path, (200, {}))


GOOD = {
    "/api/v1/scan-scope": (200, {}),
    "/api/v1/scan-runs": (200, {"scan_order": 7}),
    "/api/v1/ingest/scan": (202, {"accepted": True}),
    "/api/v1/inventory-runs": (200, {"status": "committed"}),
}


@pytest.fixture
def cycle(settings, nomad, monkeypatch):
    """Runs main() against the fake Nomad and a fake JAVV; each image scans to its own digest."""

    def run(replies=GOOD, digest=lambda ref: "sha256:" + format(abs(hash(ref)), "x")[:12], **env):
        settings(**env)
        javv = FakeJavv(replies)
        monkeypatch.setattr(push.Javv, "call", lambda _api, *a, **k: javv(*a, **k))
        monkeypatch.setattr(
            push, "scan_trivy", lambda _s, ref: (digest(ref), [], "0.76.2", "2", None)
        )
        return push.main(), javv.calls

    return run


def test_a_cycle_compresses_only_the_envelopes(cycle):
    code, calls = cycle()
    assert code == 0
    assert {(m, p, gz) for m, p, _, gz in calls} == {
        ("GET", "/api/v1/scan-scope", False),
        ("POST", "/api/v1/scan-runs", False),
        ("POST", "/api/v1/ingest/scan", True),
        ("POST", "/api/v1/inventory-runs", False),
    }
    pushes = [b for _, p, b, _ in calls if p == "/api/v1/ingest/scan"]
    assert all(b["scan_order"] == 7 for b in pushes)
    inventory = next(b for _, p, b, _ in calls if p == "/api/v1/inventory-runs")
    assert inventory["expected_count"] == len(pushes)


def test_no_scope_from_javv_means_no_scan(cycle):
    code, calls = cycle(replies=GOOD | {"/api/v1/scan-scope": (None, {"error": "down"})})
    assert code == 1
    assert [p for _, p, _, _ in calls] == ["/api/v1/scan-scope"]


def test_a_refused_push_fails_the_run_and_still_counts(cycle):
    code, calls = cycle(replies=GOOD | {"/api/v1/ingest/scan": (403, {"detail": "x"})})
    assert code == 1
    pushes = [p for _, p, _, _ in calls if p == "/api/v1/ingest/scan"]
    inventory = next(b for _, p, b, _ in calls if p == "/api/v1/inventory-runs")
    assert inventory["expected_count"] == len(pushes) > 0


def test_no_digest_fails_the_run_and_keeps_the_cycle_partial(cycle):
    code, calls = cycle(digest=lambda ref: None)
    assert code == 1
    assert not [p for _, p, _, _ in calls if p == "/api/v1/ingest/scan"]
    inventory = next(b for _, p, b, _ in calls if p == "/api/v1/inventory-runs")
    assert inventory["expected_count"] > 0  # the images found, not 0


def test_a_log_level_that_is_not_valid_stops_the_job(cycle):
    code, calls = cycle(JAVV_LOG_LEVEL="verbose")
    assert code == 2
    assert calls == []


class Reply:
    def __init__(self, status: int, body: bytes):
        self.status, self.body = status, body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def http_error(code: int, body: bytes):
    import io
    import urllib.error

    return urllib.error.HTTPError("http://javv.test", code, "x", {}, io.BytesIO(body))  # type: ignore[arg-type]


def test_javv_retries_a_5xx_with_a_page_that_is_not_json(settings, monkeypatch):
    answers = [http_error(502, b"<html>bad gateway</html>"), Reply(200, b'{"scan_order": 1}')]

    def urlopen(_req, timeout):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(push.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(push.time, "sleep", lambda _s: None)
    assert push.Javv(settings()).call("POST", "/api/v1/scan-runs") == (200, {"scan_order": 1})


def test_javv_does_not_retry_a_refusal(settings, monkeypatch):
    seen = []

    def urlopen(_req, timeout):
        seen.append(1)
        raise http_error(422, b"<html>not json</html>")

    monkeypatch.setattr(push.urllib.request, "urlopen", urlopen)
    status, body = push.Javv(settings()).call("POST", "/api/v1/ingest/scan", {}, gz=True)
    assert (status, len(seen)) == (422, 1)
    assert body == {"text": "<html>not json</html>"}


def test_javv_has_one_retry_budget_for_the_cycle(settings, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(push.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(push.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))

    def urlopen(_req, timeout):
        raise http_error(503, b"")

    monkeypatch.setattr(push.urllib.request, "urlopen", urlopen)
    api = push.Javv(settings(JAVV_PUSH_RETRY_BUDGET_SECONDS="40"))
    assert api.call("GET", "/api/v1/scan-scope")[0] is None
    used = clock[0]
    assert 0 < used <= 40
    assert api.call("POST", "/api/v1/scan-runs")[0] is None
    assert clock[0] - used < 30  # the second call gets only what is left of the 40 s


def test_grype_sends_only_a_repository_digest(settings, monkeypatch):
    report = {
        "matches": [],
        "descriptor": {},
        "source": {"target": {"manifestDigest": "sha256:62223d"}},
    }
    monkeypatch.setattr(push, "run", lambda cmd, timeout=None: report)
    assert push.scan_grype(settings(JAVV_SCANNER="grype"), "nginx:1.27-alpine")[0] is None
    report["source"]["target"]["repoDigests"] = ["nginx@sha256:65645c"]
    assert (
        push.scan_grype(settings(JAVV_SCANNER="grype"), "nginx:1.27-alpine")[0] == "sha256:65645c"
    )
