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


def alloc(ns: str, job: str, *tasks: tuple[str, str], parent: str = "", kind: str = "service"):
    """One running allocation of the Nomad API, with its docker tasks (name, image)."""
    return {
        "ID": f"{ns}-{job}",
        "Namespace": ns,
        "JobID": f"{parent}/periodic-1" if parent else job,
        "ClientStatus": "running",
        "TaskGroup": "g",
        "Job": {
            "ParentID": parent,
            "Type": kind,
            "TaskGroups": [
                {
                    "Name": "g",
                    "Tasks": [
                        {"Name": n, "Driver": "docker", "Config": {"image": i}} for n, i in tasks
                    ],
                }
            ],
        },
        "TaskStates": {n: {"State": "running"} for n, _ in tasks},
    }


CLUSTER = [
    alloc("default", "web", ("nginx", "nginx:1.27-alpine")),
    alloc("default", "web", ("nginx", "nginx:1.27-alpine")) | {"ID": "default-web-2"},
    alloc("billing", "web", ("nginx", "nginx:1.27-alpine")),
    alloc("billing", "billing-api", ("nginx", "nginx:1.27-alpine"), ("cache", "redis:7-alpine")),
    alloc(
        "default",
        "",
        ("push", "ghcr.io/danube-labs/javv-scanner-trivy:0.76.2"),
        parent="javv-scan-trivy",
    ),
    alloc("default", "nightly", ("run", "busybox:1.36"), parent="nightly", kind="batch"),
]


@pytest.fixture
def settings(monkeypatch):
    def make(**extra: str):
        for k, v in (REQUIRED | {"NOMAD_JOB_PARENT_ID": "javv-scan-trivy"} | extra).items():
            monkeypatch.setenv(k, v)
        return push.Settings()

    return make


@pytest.fixture
def nomad(monkeypatch):
    """The Nomad API of CLUSTER. Records the namespaces that the script asked for."""
    asked: list[str] = []

    def get(_s, path: str):
        if path.startswith("/v1/allocations?namespace="):
            ns = path.split("=", 1)[1]
            asked.append(ns)
            return [a for a in CLUSTER if ns == "%2A" or ns == "*" or a["Namespace"] == ns]
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


def test_the_job_skips_itself(settings, nomad):
    images, _ = push.running_images(settings(), {})
    assert not any("javv-scanner" in ref for ref in images)


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
