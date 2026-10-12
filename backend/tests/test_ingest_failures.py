"""Failed-ingest records (issue 357): the doc shape, the caps on sender-influenced text, the
never-raise guarantee, and a real round-trip through the template. Which rejections get
recorded, under whose scope, lives with the route's other rejection tests (test_ingest_route.py)."""

from datetime import UTC, datetime
from typing import Any, cast

import structlog
from opensearchpy import AsyncOpenSearch

from backend.core.metrics import INGEST_FAILURES_UNRECORDED
from backend.services import ingest_failures
from backend.services.ingest_failures import (
    MAX_TEXT,
    STAGES,
    build_failure_doc,
    record_ingest_failure,
)
from os_env import requires_opensearch

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def test_the_doc_shape() -> None:
    doc = build_failure_doc(
        cluster_id="c-shape",
        scanner="grype",
        reason="invalid_envelope",
        status=422,
        error="envelope rejected: 1 error(s); first: extra: extra_forbidden",
        image_ref="registry.example.com/team/api:v1",
        now=NOW,
        failure_id="f00d",
    )
    assert doc == {
        "@timestamp": "2026-09-26T12:00:00+00:00",
        "ingested_at": "2026-09-26T12:00:00+00:00",
        "failure_id": "f00d",
        "cluster_id": "c-shape",
        "scanner": "grype",
        "stage": "validate",
        "reason": "invalid_envelope",
        "status": 422,
        "error": "envelope rejected: 1 error(s); first: extra: extra_forbidden",
        "image_ref": "registry.example.com/team/api:v1",
        "schema_version": 1,
    }


def test_every_post_auth_reason_has_a_stage_and_no_pre_auth_one_does() -> None:
    assert set(STAGES) == {
        "too_large",
        "bad_gzip",
        "bad_json",
        "invalid_envelope",
        "unallocated_order",
        "clock_skew",
        "scope_mismatch",
        "storage_error",
    }
    assert "bad_token" not in STAGES and "rate_limited" not in STAGES


def test_sender_influenced_text_is_capped_and_stripped() -> None:
    hostile = "evil\x00\n\r\x1b[31m" + "x" * 10_000
    doc = build_failure_doc(
        cluster_id="c-caps",
        scanner="trivy",
        reason="invalid_envelope",
        status=422,
        error=hostile,
        image_ref=hostile,
        now=NOW,
        failure_id="f",
    )
    for field in ("error", "image_ref"):
        assert len(doc[field]) == MAX_TEXT
        assert not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in doc[field]), field
        assert doc[field].startswith("evil")


class _StoreDown:
    class indices:  # noqa: N801 — mirrors the client attribute
        @staticmethod
        async def exists_alias(**_: Any) -> bool:
            raise ConnectionError("store unreachable")


async def test_a_failing_store_is_logged_never_raised(monkeypatch: Any) -> None:
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(ingest_failures, "log", structlog.wrap_logger(None, processors=[capture]))
    unrecorded = INGEST_FAILURES_UNRECORDED.labels(reason="storage_error")
    before = unrecorded._value.get()

    await record_ingest_failure(
        cast(AsyncOpenSearch, _StoreDown()),
        failure_id="f-down",
        cluster_id="c-down",
        scanner="trivy",
        reason="storage_error",
        status=503,
        error="storage temporarily unavailable",
    )

    [line] = capture.entries
    assert (line["event"], line["log_level"]) == ("ingest failure not recorded", "warning")
    assert line["failure_id"] == "f-down"  # the same id the route's `ingest rejected` line has
    # the table can't show its own gaps, so a miss is also a metric an alert can watch
    assert unrecorded._value.get() == before + 1
    assert (line["cluster_id"], line["scanner"], line["reason"]) == (
        "c-down",
        "trivy",
        "storage_error",
    )


@requires_opensearch
async def test_round_trip_through_the_template(real_os: Any) -> None:
    client, prefix = real_os
    await record_ingest_failure(
        client,
        failure_id="f-roundtrip",
        cluster_id="c-roundtrip",
        scanner="grype",
        reason="scope_mismatch",
        status=403,
        error="token not valid for this cluster/scanner",
        image_ref="registry.example.com/team/api:v1",
        prefix=prefix,
    )
    series = f"{prefix}javv-ingest-failures-c-roundtrip"
    await client.indices.refresh(index=f"{series}-*")
    hits = (await client.search(index=f"{series}-*", body={"query": {"match_all": {}}}))["hits"]
    [hit] = hits["hits"]
    assert hit["_source"]["stage"] == "authorize"
    assert hit["_id"] == hit["_source"]["failure_id"] == "f-roundtrip"

    # the template applied: strict mapping, filterable scope, and `error` is display-only
    mapping = await client.indices.get_mapping(index=f"{series}-*")
    props = next(iter(mapping.values()))["mappings"]["properties"]
    assert props["error"] == {"type": "keyword", "index": False, "doc_values": False}
    found = await client.count(
        index=f"{series}-*",
        body={"query": {"bool": {"filter": [{"term": {"scanner": "grype"}}]}}},
    )
    assert found["count"] == 1
