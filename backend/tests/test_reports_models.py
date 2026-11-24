"""M7 enqueue contract (#32) — the pure request model + `pending`-doc builder (no OpenSearch)."""

import pytest
from pydantic import ValidationError

from backend.query.search import LIST_FILTER_FIELDS
from backend.reports.models import (
    PENDING,
    EnqueueReport,
    ExportParams,
    new_report_doc,
    public_report,
)


def test_new_report_doc_builds_a_pending_job() -> None:
    body = EnqueueReport(
        cluster_id="c-reports",
        run_mode="offpeak",
        params=ExportParams(format="csv", severity=["critical"]),
    )
    report_id, doc = new_report_doc(body, requested_by="ana")

    assert doc["report_id"] == report_id and len(report_id) == 32
    assert doc["status"] == PENDING and doc["kind"] == "export"
    assert doc["cluster_id"] == "c-reports" and doc["requested_by"] == "ana"
    assert doc["run_mode"] == "offpeak"
    assert doc["params"]["format"] == "csv" and doc["params"]["severity"] == ["critical"]
    assert doc["retry_count"] == 0 and doc["created_at"]
    assert doc["scheduled_for"] is None and doc["as_of_t"] is None
    # a pending job has no result yet — the drain stamps these at completion
    assert "expires_at" not in doc and "attempt_id" not in doc and "bytes" not in doc


@pytest.mark.parametrize("name", LIST_FILTER_FIELDS)
def test_one_string_reads_as_a_list_of_that_value(name: str) -> None:
    # issue 949: a client that still sends one string keeps working; the cap still applies
    assert getattr(ExportParams.model_validate({name: "os"}), name) == ["os"]
    assert getattr(ExportParams.model_validate({name: ["os", "npm"]}), name) == ["os", "npm"]
    assert getattr(ExportParams.model_validate({name: None}), name) is None
    with pytest.raises(ValidationError) as err:
        ExportParams.model_validate({name: "x" * 513})
    assert err.value.errors()[0]["type"] == "string_too_long"  # not list_type: read as a list


def test_vex_export_requires_a_scanner() -> None:
    ExportParams(format="openvex", scanner="trivy")  # ok — one scanner
    for fmt in ("openvex", "cyclonedx"):
        with pytest.raises(ValidationError):
            ExportParams(format=fmt)  # per-scanner is sacred — a VEX doc speaks for ONE scanner


# one value for each filter that has an exclude side; the pairs Findings refuses with a 422
_ONE_VALUE = {
    "severity": ["high"],
    "state": ["open"],
    "scanner": "trivy",
    "assignee": ["ana"],
    "image_repo": ["nginx"],
    "namespace": ["default"],
    "ptype": ["os"],
    "cve_id": ["CVE-2021-3711"],
    "package_name": ["openssl"],
    "tag": ["1.4.2"],
}


def test_every_exclude_filter_has_a_case_here() -> None:
    excludes = {
        n.removeprefix("exclude_") for n in ExportParams.model_fields if n.startswith("exclude_")
    }
    assert excludes == set(_ONE_VALUE)


@pytest.mark.parametrize("name", sorted(_ONE_VALUE))
def test_a_filter_and_its_exclude_side_are_refused_together(name: str) -> None:
    value = _ONE_VALUE[name]
    ExportParams.model_validate({name: value})
    ExportParams.model_validate({f"exclude_{name}": value})
    with pytest.raises(ValidationError, match=f"{name} and exclude_{name} are mutually exclusive"):
        ExportParams.model_validate({name: value, f"exclude_{name}": value})


@pytest.mark.parametrize("unassigned", [True, False])
def test_assignee_and_unassigned_are_refused_together(unassigned: bool) -> None:
    ExportParams(unassigned=unassigned)
    ExportParams(unassigned=unassigned, exclude_assignee=["ana"])  # Findings takes this pair
    with pytest.raises(ValidationError, match="assignee and unassigned are mutually exclusive"):
        ExportParams(assignee=["ana"], unassigned=unassigned)


@pytest.mark.parametrize("untagged", [True, False])
def test_tag_and_untagged_are_refused_together(untagged: bool) -> None:
    # issue 1294, on the pattern of assignee and unassigned
    ExportParams(untagged=untagged)
    ExportParams(untagged=untagged, exclude_tag=["1.4.2"])  # Findings takes this pair
    with pytest.raises(ValidationError, match="tag and untagged are mutually exclusive"):
        ExportParams(tag=["1.4.2"], untagged=untagged)


def test_a_tag_value_keeps_the_oci_length_cap() -> None:
    ExportParams(tag=["x" * 128])
    for name in ("tag", "exclude_tag"):
        with pytest.raises(ValidationError) as err:
            ExportParams.model_validate({name: ["x" * 129]})
        assert err.value.errors()[0]["type"] == "string_too_long"


def test_enqueue_rejects_unknown_kind_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EnqueueReport(cluster_id="c-reports", kind="bulk_triage")  # type: ignore[arg-type]  # not a valid kind yet
    with pytest.raises(ValidationError):
        EnqueueReport(cluster_id="c-reports", nope=1)  # type: ignore[call-arg]  # extra=forbid
    with pytest.raises(ValidationError):
        EnqueueReport()  # type: ignore[call-arg]  # cluster_id is required


def test_public_report_hides_internals() -> None:
    doc = {
        "report_id": "r1",
        "status": "running",
        "cluster_id": "c-reports",
        "params": {"secret": "lens"},
        "attempt_id": "att-1",
        "lease_expires_at": "2026-07-07T00:00:00+00:00",
        "heartbeat_at": "2026-07-07T00:00:00+00:00",
    }
    pub = public_report(doc)
    assert pub["report_id"] == "r1" and pub["status"] == "running"
    for hidden in ("params", "attempt_id", "lease_expires_at", "heartbeat_at"):
        assert hidden not in pub  # the status view never leaks the lens or the claim internals


def test_the_two_ranges_of_new_in_range_are_refused_together() -> None:
    """Issue 1291: whole days or the exact range of 2 days or less, never both, as /findings."""
    with pytest.raises(ValidationError, match="new_within_days and new_within_seconds"):
        ExportParams.model_validate({"new_within_days": 1, "new_within_seconds": 3600})
    assert ExportParams.model_validate({"new_within_seconds": 3600}).new_within_seconds == 3600
    for bad in (59, 172_801):
        with pytest.raises(ValidationError):
            ExportParams.model_validate({"new_within_seconds": bad})
