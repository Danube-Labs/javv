"""The envelope is the current-only, per-image, per-scanner push payload (D38): severity
buckets (D16/INDEX-MAP), the findings (verbatim severity + EPSS/KEV kept), and run identity —
`scan_run_id` + monotonic `scan_order` (D40) + full-precision `last_seen_at` (D37/D38). Per D30
every scan emits a full envelope even when nothing changed (no skip-unchanged), with a fresh
`scan_run_id` and a strictly greater `scan_order`."""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from scanner.adapters.grype import parse_grype
from scanner.adapters.trivy import parse_trivy
from scanner.envelope import (
    SCHEMA_VERSION,
    Envelope,
    build_envelope,
    new_scan_run,
)
from scanner.normalize import COUNT_COLUMN, SEVERITIES

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _trivy_env() -> Envelope:
    findings = parse_trivy(load("trivy-python-3.9.16-slim.json"))
    return build_envelope(
        new_scan_run(1),
        cluster_id="cluster-abc",
        scanner="trivy",
        image_digest="sha256:deadbeef",
        findings=findings,
    )


# --- counts / bucketing ----------------------------------------------------


def test_counts_bucket_every_finding_and_total_is_the_sum() -> None:
    findings = parse_trivy(load("trivy-python-3.9.16-slim.json"))
    env = build_envelope(
        new_scan_run(1),
        cluster_id="c",
        scanner="trivy",
        image_digest="sha256:x",
        findings=findings,
    )
    tally = Counter(f.severity_canonical for f in findings)
    for sev in SEVERITIES:
        assert getattr(env.counts, COUNT_COLUMN.get(sev, sev)) == tally.get(sev, 0)
    bucket_sum = sum(getattr(env.counts, COUNT_COLUMN.get(s, s)) for s in SEVERITIES)
    assert env.counts.total == bucket_sum == len(findings)
    assert env.counts.fixable == sum(1 for f in findings if f.fixable)


def test_clean_scan_still_emits_a_full_envelope_with_zero_counts() -> None:
    # alpine:3.14 → Trivy finds nothing; D30 says still emit (no skip).
    env = build_envelope(
        new_scan_run(1),
        cluster_id="c",
        scanner="trivy",
        image_digest="sha256:x",
        findings=parse_trivy(load("trivy-alpine-3.14.json")),
    )
    assert env.counts.total == 0
    assert env.findings == []
    assert all(getattr(env.counts, COUNT_COLUMN.get(s, s)) == 0 for s in SEVERITIES)


# --- identity / payload ----------------------------------------------------


def test_envelope_carries_the_run_and_image_identity() -> None:
    env = _trivy_env()
    assert env.cluster_id == "cluster-abc"
    assert env.scanner == "trivy"
    assert env.image_digest == "sha256:deadbeef"
    assert env.schema_version == SCHEMA_VERSION
    assert env.scan_run_id and isinstance(env.scan_order, int)


def test_envelope_carries_observed_topology() -> None:
    env = build_envelope(
        new_scan_run(1),
        cluster_id="c",
        scanner="trivy",
        image_digest="sha256:x",
        image_ref="nginx:1.21.6",
        namespaces=["team-a", "team-b"],
        replicas=3,
        findings=[],
    )
    assert env.image_ref == "nginx:1.21.6"
    assert env.namespaces == ["team-a", "team-b"]
    assert env.replicas == 3
    assert env.schema_version == 5  # v5 = the paths of a finding (issue 1077); v4 = ptype
    # and it survives serialization (what the backend ingests)
    dumped = json.loads(env.model_dump_json())
    assert dumped["namespaces"] == ["team-a", "team-b"] and dumped["replicas"] == 3
    assert "namespace" not in dumped  # the old singular field is gone


def test_last_seen_at_is_tz_aware_full_precision() -> None:
    env = _trivy_env()
    assert isinstance(env.last_seen_at, datetime)
    assert env.last_seen_at.tzinfo is not None  # UTC, not naive
    # full precision survives JSON round-trip
    iso = json.loads(env.model_dump_json())["last_seen_at"]
    assert datetime.fromisoformat(iso) == env.last_seen_at


def test_provenance_flows_onto_the_envelope() -> None:
    from datetime import UTC, datetime

    from scanner.models import Provenance

    built = datetime(2026, 6, 29, 8, 3, 40, tzinfo=UTC)
    env = build_envelope(
        new_scan_run(1),
        cluster_id="c",
        scanner="grype",
        image_digest="sha256:x",
        findings=[],
        provenance=Provenance(scanner_version="0.115.0", db_version="v6.1.7", db_built=built),
    )
    assert env.scanner_version == "0.115.0"
    assert env.scanner_db_version == "v6.1.7"
    assert env.scanner_db_built == built


def test_provenance_defaults_to_none_when_absent() -> None:
    env = _trivy_env()
    assert env.scanner_version is None  # no provenance passed → nullable fields stay None


def test_scanner_name_is_constrained_to_trivy_or_grype() -> None:
    with pytest.raises(ValidationError):
        build_envelope(
            new_scan_run(1),
            cluster_id="c",
            scanner="nessus",  # type: ignore[arg-type]
            image_digest="sha256:x",
            findings=[],
        )


def test_grype_envelope_preserves_epss_and_verbatim_severity_in_payload() -> None:
    findings = parse_grype(load("grype-python-3.9.16-slim.json"))
    env = build_envelope(
        new_scan_run(1),
        cluster_id="c",
        scanner="grype",
        image_digest="sha256:x",
        findings=findings,
    )
    dumped = json.loads(env.model_dump_json())
    f = next(f for f in dumped["findings"] if f["vuln_id"] == "CVE-2005-2541")
    assert f["severity"] == "Negligible"  # verbatim kept
    assert f["severity_canonical"] == "negligible"  # computed bucket serialized
    assert f["epss"] == pytest.approx(0.03992)  # EPSS preserved


# --- monotonic run ordering (D40) ------------------------------------------


def test_new_scan_run_ids_unique_and_order_is_the_backend_allocated_one() -> None:
    # D45: ordering is the backend's job — the run just carries the allocated value verbatim
    r1, r2 = new_scan_run(1), new_scan_run(2)
    assert r1.scan_run_id != r2.scan_run_id
    assert (r1.scan_order, r2.scan_order) == (1, 2)


def test_two_no_change_scans_emit_full_envelopes_new_run_greater_order() -> None:
    findings = parse_trivy(load("trivy-python-3.9.16-slim.json"))
    e1 = build_envelope(
        new_scan_run(1), cluster_id="c", scanner="trivy", image_digest="sha256:x", findings=findings
    )
    e2 = build_envelope(
        new_scan_run(2), cluster_id="c", scanner="trivy", image_digest="sha256:x", findings=findings
    )
    assert e1.scan_run_id != e2.scan_run_id
    assert e2.scan_order > e1.scan_order  # backend allocation guarantees this across cycles (D45)
    assert e1.counts == e2.counts  # identical content
    assert len(e2.findings) == len(findings) > 0  # full envelope, not skipped
