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
    with pytest.raises(ValidationError):
        ExportParams.model_validate({name: "x" * 513})


def test_vex_export_requires_a_scanner() -> None:
    ExportParams(format="openvex", scanner="trivy")  # ok — one scanner
    for fmt in ("openvex", "cyclonedx"):
        with pytest.raises(ValidationError):
            ExportParams(format=fmt)  # per-scanner is sacred — a VEX doc speaks for ONE scanner


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
