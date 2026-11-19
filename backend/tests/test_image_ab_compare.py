"""The compare half of development/e2e/image-ab.sh (issue 1263): what fails the report and what
does not. The rig itself needs Docker and runs by hand; these cases hold its rules."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("image_ab", ROOT / "development/e2e/image_ab.py")
assert _spec and _spec.loader
ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ab)


def line(**rec: object) -> str:
    return json.dumps(rec)


# --- normalize: the values that change between two runs of the same code


def test_normalize_drops_the_values_of_a_run_and_keeps_the_data() -> None:
    a = {
        "scan_order": 3,
        "last_seen_at": "2026-11-19T10:00:00Z",
        "cluster_id": "c1",
        "count": 7,
        "severity": "high",
    }
    b = {
        "scan_order": 9,
        "last_seen_at": "2026-11-19T11:30:00Z",
        "cluster_id": "c2",
        "count": 7,
        "severity": "high",
    }
    assert ab.normalize(a) == ab.normalize(b)


def test_normalize_keeps_a_count_that_differs() -> None:
    assert ab.normalize({"count": 7}) != ab.normalize({"count": 8})


def test_normalize_replaces_a_time_in_a_list_value() -> None:
    assert ab.normalize(["2026-11-19T10:00:00.123Z", "x"]) == ["<time>", "x"]


def test_normalize_keeps_a_version_that_is_no_time() -> None:
    assert ab.normalize({"mapping_version": 23}) == {"mapping_version": 23}


# --- logs


def test_the_same_events_with_other_values_do_not_fail() -> None:
    old = [line(event="request", level="info", path="/a", ms=3)]
    new = [line(event="request", level="info", path="/b", ms=9)]
    assert ab.compare_logs(old, new)["failing"] == []


def test_a_new_warning_event_fails() -> None:
    old = [line(event="start", level="info")]
    new = [line(event="start", level="info"), line(event="pip missing", level="warning")]
    out = ab.compare_logs(old, new)
    assert out["only_new"] == ["pip missing"]
    assert any("pip missing" in f for f in out["failing"])


def test_a_new_info_event_is_reported_but_does_not_fail() -> None:
    out = ab.compare_logs(
        [line(event="a", level="info")],
        [line(event="a", level="info"), line(event="b", level="info")],
    )
    assert out["only_new"] == ["b"]
    assert not [f for f in out["failing"] if "event" in f]


def test_more_error_lines_fail() -> None:
    old = [line(event="x", level="error")]
    new = [line(event="x", level="error"), line(event="x", level="error")]
    assert any("error" in f for f in ab.compare_logs(old, new)["failing"])


def test_a_new_line_that_is_not_json_fails() -> None:
    out = ab.compare_logs(
        [line(event="a")], [line(event="a"), "Traceback (most recent call last):"]
    )
    assert out["new_plain"] == ["Traceback (most recent call last):"]
    assert out["failing"]


def test_a_key_that_an_event_lost_is_reported() -> None:
    old = [line(event="ingest", level="info", cluster_id="c", findings=3)]
    new = [line(event="ingest", level="info", cluster_id="c")]
    assert ab.compare_logs(old, new)["keys"] == {"ingest": (["findings"], [])}


# --- reads


def read(
    path: str, status: int = 200, body: object = None, times: tuple[float, ...] = (0.01,)
) -> dict:
    return {
        "path": path,
        "status": status,
        "body": body if body is not None else {"n": 1},
        "times": list(times),
    }


def test_the_same_reads_do_not_fail() -> None:
    rows, failing = ab.compare_reads([read("/a")], [read("/a")])
    assert failing == []
    assert rows[0][3] is True


def test_another_status_fails() -> None:
    _, failing = ab.compare_reads([read("/a")], [read("/a", status=500)])
    assert failing == ["`/a`: status 200 -> 500"]


def test_another_body_fails() -> None:
    _, failing = ab.compare_reads([read("/a", body={"n": 1})], [read("/a", body={"n": 2})])
    assert failing == ["`/a`: the body differs"]


def test_a_read_of_one_run_only_fails() -> None:
    _, failing = ab.compare_reads([read("/a"), read("/b")], [read("/a")])
    assert failing == ["`/b` was read in one run only"]


def test_timing_gives_milliseconds() -> None:
    assert ab.timing([0.010, 0.020, 0.030, 0.040]) == {"median": 25.0, "p95": 40.0, "n": 4}
    assert ab.timing([]) is None


# --- scan cycles


def test_the_same_findings_after_a_good_cycle_do_not_fail() -> None:
    rows = [["trivy", "CVE-1", "libc6", "2.41", "high", None, "javv-backend"]]
    res, failing = ab.compare_scan({"exit": 0, "findings": rows}, {"exit": 0, "findings": rows})
    assert failing == [] and res["same"]


def test_a_failed_cycle_fails() -> None:
    _, failing = ab.compare_scan({"exit": 0, "findings": []}, {"exit": 1, "findings": []})
    assert failing == ["scan cycle exit 0 -> 1"]


def test_other_findings_fail() -> None:
    a = [["trivy", "CVE-1", "libc6", "2.41", "high", None, "r"]]
    b = a + [["trivy", "CVE-2", "libc6", "2.41", "low", None, "r"]]
    _, failing = ab.compare_scan({"exit": 0, "findings": a}, {"exit": 0, "findings": b})
    assert failing == ["findings 1 -> 2 (0 only old, 1 only new)"]


# --- the routes that the reads walk


def test_routes_take_the_get_routes_without_a_path_value() -> None:
    spec = {
        "paths": {
            "/api/v1/meta": {"get": {}},
            "/api/v1/findings": {
                "get": {"parameters": [{"name": "cluster_id", "in": "query", "required": True}]}
            },
            "/api/v1/findings/groups": {
                "get": {
                    "parameters": [
                        {"name": "cluster_id", "in": "query", "required": True},
                        {"name": "by", "in": "query", "required": True},
                    ]
                }
            },
            "/api/v1/images/timeline": {
                "get": {"parameters": [{"name": "image_repo", "in": "query", "required": True}]}
            },
            "/api/v1/findings/{key}": {"get": {}},
            "/api/v1/mcp": {"get": {}},
            "/metrics": {"get": {}},
            "/api/v1/views": {"post": {}},
        }
    }
    assert ab.routes(spec) == [
        ("/api/v1/findings", {"cluster_id": "<cluster>"}),
        ("/api/v1/findings/groups", {"cluster_id": "<cluster>", "by": "severity"}),
        ("/api/v1/meta", {}),
    ]


def test_routes_of_the_repository_contract_are_many() -> None:
    spec = json.loads((ROOT / "frontend/openapi.json").read_text())
    paths = [p for p, _ in ab.routes(spec)]
    assert "/api/v1/findings" in paths and "/auth/me" in paths and "/readyz" in paths
    assert len(paths) >= 40


@pytest.mark.parametrize(
    ("ctype", "raw", "want"),
    [
        ("application/json", b'{"a": 1}', {"a": 1}),
        (
            "text/csv; charset=utf-8",
            b"id,name\n1,a\n2,b\n",
            {"content_type": "text/csv", "first_line": "id,name", "lines": 3},
        ),
        (
            "application/x-ndjson",
            b'{"a":1}\n{"b":2}\n',
            {"content_type": "application/x-ndjson", "first_line": '{"a":1}', "lines": 2},
        ),
    ],
)
def test_body_of_keeps_json_and_shapes_the_rest(ctype: str, raw: bytes, want: object) -> None:
    assert ab.body_of(ctype, raw) == want


# --- the findings of one image in each scanner's report


def test_summarize_vulns_splits_os_language_and_fix() -> None:
    trivy = {
        "Results": [
            {"Class": "os-pkgs", "Vulnerabilities": [{"Status": "affected"}, {"Status": "fixed"}]},
            {"Class": "lang-pkgs", "Vulnerabilities": [{"Status": "fixed"}]},
            {"Class": "os-pkgs"},
        ]
    }
    grype = {
        "matches": [
            {"artifact": {"type": "deb"}, "vulnerability": {"fix": {"state": "wont-fix"}}},
            {"artifact": {"type": "python"}, "vulnerability": {"fix": {"state": "fixed"}}},
            {"artifact": {"type": "apk"}, "vulnerability": {}},
        ]
    }
    assert ab.summarize_vulns(trivy, grype) == {
        "trivy_os": 2,
        "trivy_language": 1,
        "trivy_with_fix": 2,
        "grype_os": 2,
        "grype_language": 1,
        "grype_with_fix": 1,
    }
