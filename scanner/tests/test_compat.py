"""The compatibility gate (M0b): a candidate scanner version is compatible only if its real
output still satisfies the JAVV adapter contracts — version provenance present, findings parse on
a known-vulnerable image, severities canonicalize, and the envelope builds. CI runs the real
binary per compatible version; these unit tests prove the checker bites on format drift."""

import gzip
import json
import os
from pathlib import Path

import httpx
import pytest

from scanner.adapters.grype import parse_grype, parse_grype_provenance
from scanner.compat import COMPAT_IMAGE, COMPAT_IMAGES, contract_violations, push_compat
from scanner.config import GrypeConfig
from scanner.models import Provenance, ScanResult

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_good_grype_output_satisfies_the_contract() -> None:
    data = load("grype-python-3.9.16-slim.json")
    result = ScanResult(findings=parse_grype(data), provenance=parse_grype_provenance(data))
    assert contract_violations(result, scanner="grype", expect_findings=True) == []


def test_missing_version_and_no_findings_is_flagged() -> None:
    # An empty result on an image that should have findings → the gate must go red.
    result = ScanResult(findings=[], provenance=Provenance())
    violations = contract_violations(result, scanner="grype", expect_findings=True)
    assert any("scanner_version" in v for v in violations)
    assert any("findings" in v for v in violations)


def test_renamed_output_key_drifts_to_zero_findings_and_is_flagged() -> None:
    # Simulate a future Grype that renamed "matches" → the adapter can't parse it.
    raw = load("grype-python-3.9.16-slim.json")
    drifted = {"results": raw["matches"], "descriptor": {"version": "9.9.9"}}
    result = ScanResult(findings=parse_grype(drifted), provenance=parse_grype_provenance(drifted))
    assert result.findings == []  # parse path broken by the rename
    assert contract_violations(result, scanner="grype", expect_findings=True)  # → not compatible


# --- the real compatibility run CI does per version (guarded) --------------


@pytest.mark.skipif(
    not os.environ.get("JAVV_COMPAT_VERIFY"),
    reason="runs the real installed scanner binary; set JAVV_COMPAT_VERIFY=1",
)
@pytest.mark.parametrize("scanner", ["trivy", "grype"])
def test_installed_binary_is_compatible(scanner: str) -> None:
    from scanner.compat import run_compat

    result, violations = run_compat(scanner, "python:3.9.16-slim")  # type: ignore[arg-type]
    assert violations == [], violations
    assert result.provenance.scanner_version


# --- --push: the real cycle over the compat image (issue 631) ----------------------------------

CLUSTER = "compat-cluster-01"


def _grype_scan(ref: str) -> ScanResult:
    data = load("grype-python-3.9.16-slim.json")
    return ScanResult(findings=parse_grype(data), provenance=parse_grype_provenance(data))


def _backend(ingest_status: int = 202, inventory: str = "committed", order_status: int = 200):
    """A fake backend for the three calls a cycle makes; records what it was sent."""
    seen: dict[str, list[httpx.Request]] = {"orders": [], "ingest": [], "inventory": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/scan-scope":
            return httpx.Response(200, json={})
        if request.url.path == "/api/v1/scan-runs":
            seen["orders"].append(request)
            return httpx.Response(order_status, json={"scan_order": 7})
        if request.url.path == "/api/v1/ingest/scan":
            seen["ingest"].append(request)
            return httpx.Response(ingest_status, json={})
        seen["inventory"].append(request)
        return httpx.Response(200, json={"status": inventory})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://backend")
    return client, seen


def _push(http: httpx.Client, tmp_path: Path, **kw):
    return push_compat(
        "grype",
        kw.pop("image", COMPAT_IMAGE),
        cluster_id=CLUSTER,
        scan_fn=kw.pop("scan_fn", _grype_scan),
        tuning=GrypeConfig(),
        http=http,
        token="tok-secret",
        dead_letter=tmp_path / "grype.dead-letter.jsonl",
    )


def test_push_runs_the_real_cycle_and_reports_what_it_sent(tmp_path: Path) -> None:
    http, seen = _backend()
    with http:
        result, summary, violations = _push(http, tmp_path)

    assert violations == []
    assert result is not None and summary is not None
    [ingest] = seen["ingest"]
    sent = json.loads(gzip.decompress(ingest.content))
    assert ingest.headers["Authorization"] == "Bearer tok-secret"
    assert sent["scan_order"] == 7 and sent["cluster_id"] == CLUSTER
    assert sent["image_digest"] == COMPAT_IMAGE.partition("@")[2]
    # the summary is exactly what went over the wire, so CI compares the store with the truth
    assert summary.counts == sent["counts"]
    assert summary.scan_run_id == sent["scan_run_id"]
    assert summary.counts["total"] == len(result.findings) > 0
    assert summary.delivered and summary.inventory_committed
    # envelope v4 requires what the cycle ran with (D44) — the compat envelope once lacked it
    assert set(sent["effective_config"]) == {"tuning", "scope"}
    assert sent["effective_config"]["scope"]["include_namespaces"] == []
    [inventory] = seen["inventory"]
    assert json.loads(inventory.content)["expected_count"] == 1


def test_the_summary_lists_the_paths_that_the_push_sent(tmp_path: Path) -> None:
    """Issue 1077: CI compares the paths in the store with these, so they are the paths of the
    envelope that went over the wire, not of the scan before the envelope."""
    http, seen = _backend()
    with http:
        _, summary, violations = _push(http, tmp_path)
    assert violations == [] and summary is not None
    [ingest] = seen["ingest"]
    sent = json.loads(gzip.decompress(ingest.content))
    assert sent["schema_version"] == 5
    wire = sorted({p for f in sent["findings"] for p in f["locations"]})
    assert summary.paths == wire
    assert "/usr/local/bin/python3.9" in wire  # the compat image has paths, so the check bites


def test_the_fixtures_are_pinned_by_digest_and_copied_by_the_workflow() -> None:
    """Each fixture image is served from the project registry, copied by digest by the manual
    workflow compat-fixture.yml (issue 631). A fixture that the workflow does not copy would make
    the CI round trip pull a missing image."""
    workflow = (Path(__file__).parents[2] / ".github/workflows/compat-fixture.yml").read_text()
    assert COMPAT_IMAGES["python"] == COMPAT_IMAGE
    assert set(COMPAT_IMAGES) == {"python", "go-binaries"}
    for image in COMPAT_IMAGES.values():
        name, _, digest = image.partition("@")
        assert name.startswith("ghcr.io/danube-labs/javv-compat-fixture:")
        assert digest.startswith("sha256:") and len(digest) == 71
        assert f"@{digest}" in workflow and name in workflow


def test_a_refused_push_is_a_violation_and_dead_letters(tmp_path: Path) -> None:
    http, _ = _backend(ingest_status=422)
    with http:
        _, summary, violations = _push(http, tmp_path)
    assert summary is not None and not summary.delivered
    assert any("did not accept" in v for v in violations)
    assert (tmp_path / "grype.dead-letter.jsonl").exists()


def test_an_uncommitted_inventory_run_is_a_violation(tmp_path: Path) -> None:
    http, _ = _backend(inventory="partial")
    with http:
        _, _, violations = _push(http, tmp_path)
    assert violations == ["the inventory run was not committed"]


def test_no_scan_order_means_nothing_is_scanned_or_pushed(tmp_path: Path) -> None:
    http, seen = _backend(order_status=500)
    scans: list[str] = []
    with http:
        _, summary, violations = _push(http, tmp_path, scan_fn=lambda r: scans.append(r))
    assert summary is None and scans == [] and seen["ingest"] == []
    assert any("scan_order" in v for v in violations)


def test_push_refuses_an_image_without_a_digest(tmp_path: Path) -> None:
    http, seen = _backend()
    with http:
        _, summary, violations = _push(http, tmp_path, image="python:3.9.16-slim")
    assert summary is None and seen["orders"] == []
    assert any("digest-pinned" in v for v in violations)


def test_a_failed_scan_is_a_violation_not_a_crash(tmp_path: Path) -> None:
    def broken(ref: str) -> ScanResult:
        raise RuntimeError("scanner exited 1")

    http, seen = _backend()
    with http:
        _, summary, violations = _push(http, tmp_path, scan_fn=broken)
    assert summary is None and seen["ingest"] == []
    assert any("scan failed" in v for v in violations)
