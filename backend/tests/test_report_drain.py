"""M7 slice 3 (#32) — the drain: claim → stream → chunk → publish → bell, against real OpenSearch.

Pins: the queued CSV path produces byte-identical output to the inline export for the same lens
(the golden-parity gate); results land chunked under the winning attempt_id; `done` carries
bytes/chunk_count/expires_at; the bell rings for the requester; over-ceiling → `failed`; an
`as_of_t` job fails loud with the M8b pointer; a fenced drain publishes nothing and rings nothing.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, get_args, get_origin, get_type_hints

import pytest
from opensearchpy import AsyncOpenSearch

from backend.jobs.report_drain import _filters_from_params, run_job
from backend.query.search import SearchFilters
from backend.reports.claim import claim_next
from backend.reports.models import (
    DONE,
    FAILED,
    NOTIFICATIONS_INDEX,
    REPORT_CHUNKS_INDEX,
    REPORTS_INDEX,
    RUNNING,
    ExportParams,
)
from backend.reports.storage import stream_chunks
from os_env import OS_URL, requires_opensearch

pytestmark = requires_opensearch


@pytest.fixture
async def client():
    c = AsyncOpenSearch(hosts=[OS_URL])
    yield c
    await c.close()


def _finding(cluster_id: str, i: int) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "finding_key": f"fk-{cluster_id}-{i}",
        "cluster_id": cluster_id,
        "scanner": "trivy",
        "cve_id": f"CVE-2026-{1000 + i}",
        "severity": "high",
        "severity_rank": 3,
        "state": "open",
        "vex_justification": None,
        "package_name": "libx",
        "installed_version": "1.0.0",
        "fixed_version": "1.0.1",
        "fixable": True,
        "kev": False,
        "epss": None,
        "cvss": 7.5,
        "image_repo": "nginx",
        "tag": "1.21",
        "image_digest": f"sha256:{i:064x}",
        "namespaces": ["default"],
        "assignee": None,
        "first_seen_at": now,
        "last_seen_at": now,
        "last_scan_at": now,
        "present": True,
        "state_decision_id": None,
        "schema_version": 2,
    }


async def _seed_findings(client, cluster_id: str, n: int) -> None:
    for i in range(n):
        doc = _finding(cluster_id, i)
        await client.index(index="findings", id=doc["finding_key"], body=doc)
    await client.indices.refresh(index="findings")


async def _enqueue(client, cluster_id: str, **over) -> str:
    report_id = uuid.uuid4().hex
    doc = {
        "report_id": report_id,
        "kind": "export",
        "status": "pending",
        "cluster_id": cluster_id,
        "requested_by": f"u-drain-{uuid.uuid4().hex[:8]}",
        "run_mode": "offpeak",
        "params": ExportParams().model_dump(),
        "scheduled_for": None,
        "as_of_t": None,
        "created_at": datetime.now(UTC).isoformat(),
        "retry_count": 0,
        "schema_version": 1,
    }
    doc.update(over)
    await client.index(index=REPORTS_INDEX, id=report_id, body=doc, params={"refresh": "true"})
    return report_id


async def _report(client, report_id: str) -> dict:
    return (await client.get(index=REPORTS_INDEX, id=report_id))["_source"]


async def test_drain_publishes_a_csv_identical_to_the_inline_export(client) -> None:
    """The golden-parity gate: queued path bytes == inline path bytes for the same lens."""
    from backend.export.csv_stream import stream_csv

    cluster_id = f"c-drain-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 3)
    report_id = await _enqueue(client, cluster_id)

    job = await claim_next(client, worker="w-drain", report_id=report_id)
    assert job is not None
    assert await run_job(client, job) is True

    doc = await _report(client, report_id)
    assert doc["status"] == DONE
    assert doc["chunk_count"] == 1 and doc["bytes"] > 0
    assert datetime.fromisoformat(doc["expires_at"]) > datetime.now(UTC)

    queued = "".join([d async for d in stream_chunks(client, report_id, doc["attempt_id"])])
    inline = "".join(
        [line async for line in stream_csv(client, cluster_id=cluster_id, filters=SearchFilters())]
    )
    assert queued == inline  # byte-identical to the inline path (bolt README golden gate)
    assert queued.count("\n") == 4  # header + 3 findings

    # the bell rang for the requester
    bell = await client.search(
        index=NOTIFICATIONS_INDEX, body={"query": {"term": {"ref": report_id}}}
    )
    assert bell["hits"]["total"]["value"] == 1
    hit = bell["hits"]["hits"][0]
    note = hit["_source"]
    assert note["type"] == "report_ready" and note["user_id"] == doc["requested_by"]
    assert note["read"] is False
    # the served notification_id IS the _id — mark-read gets by it, so two values
    # would make every real bell unmarkable (audit F-03; fixtures mirror this invariant)
    assert hit["_id"] == note["notification_id"]


async def test_drain_vex_export_is_valid_json_per_scanner(client) -> None:
    import json

    cluster_id = f"c-drainvex-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 2)
    report_id = await _enqueue(
        client, cluster_id, params=ExportParams(format="openvex", scanner="trivy").model_dump()
    )
    job = await claim_next(client, worker="w-drain", report_id=report_id)
    assert job is not None and await run_job(client, job) is True

    doc = await _report(client, report_id)
    body = "".join([d async for d in stream_chunks(client, report_id, doc["attempt_id"])])
    vex = json.loads(body)
    assert len(vex["statements"]) == 2  # one per finding, single scanner (sacred)


async def test_over_the_byte_ceiling_fails_the_job(client, monkeypatch) -> None:
    from backend.core.settings import get_settings

    cluster_id = f"c-drainbig-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 5)
    report_id = await _enqueue(client, cluster_id)
    settings = get_settings()
    monkeypatch.setattr(settings, "export_max_bytes", 64)  # absurdly small ceiling

    job = await claim_next(client, worker="w-drain", report_id=report_id)
    assert job is not None
    assert await run_job(client, job) is False
    doc = await _report(client, report_id)
    assert doc["status"] == FAILED and "exceeds" in doc["error"]


async def test_as_of_t_export_reconstructs_history(client) -> None:
    """UNPARKED by M8b slice 4 (#34): an as_of_t export drains to DONE with rows reconstructed
    from the append logs at T — not the parked FAILED of the M7 era."""
    import json as _json
    from pathlib import Path

    from backend.models.envelope import IngestEnvelope
    from backend.services.ingest import ingest_envelope

    golden = _json.loads(
        (Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text()
    )
    cluster_id = f"c-drainasof-{uuid.uuid4().hex[:8]}"
    golden["cluster_id"] = cluster_id
    await ingest_envelope(client, IngestEnvelope.model_validate(golden))
    for index in (f"javv-scan-events-{cluster_id}-*", "javv-finding-occurrences-*"):
        await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})

    report_id = await _enqueue(client, cluster_id, as_of_t=datetime.now(UTC).isoformat())
    job = await claim_next(client, worker="w-drain", report_id=report_id)
    assert job is not None
    assert await run_job(client, job) is True
    doc = await _report(client, report_id)
    assert doc["status"] == DONE and doc["chunk_count"] >= 1

    await client.indices.refresh(index="system-report-chunks")
    chunks = await client.search(
        index="system-report-chunks",
        body={
            "query": {"term": {"report_id": report_id}},
            "sort": [{"seq": "asc"}],
            "size": 10,
        },
    )
    csv_text = "".join(h["_source"]["data"] for h in chunks["hits"]["hits"])
    lines = [ln for ln in csv_text.splitlines() if ln]
    assert len(lines) == 1 + golden["counts"]["total"]  # header + one line per as-of-T row
    assert "CVE-2005-2541" in csv_text  # a golden CVE made it through the reconstruction


async def test_as_of_t_export_with_an_unanswerable_filter_fails_loud(client) -> None:
    # kev is not recorded in per-scan history — the reader raises, the job fails with the reason
    cluster_id = f"c-drainasofkev-{uuid.uuid4().hex[:8]}"
    report_id = await _enqueue(
        client,
        cluster_id,
        as_of_t=(datetime.now(UTC) - timedelta(days=7)).isoformat(),
        params={**ExportParams().model_dump(), "kev": True},
    )
    job = await claim_next(client, worker="w-drain", report_id=report_id)
    assert job is not None
    assert await run_job(client, job) is False
    doc = await _report(client, report_id)
    assert doc["status"] == FAILED and "kev" in doc["error"]


async def test_fenced_drain_publishes_nothing_and_rings_nothing(client) -> None:
    """A reclaimed job's original worker finishes its stream — but its publish is rejected and
    no bell rings (the M7-r2 rule carried through the whole pipeline)."""
    cluster_id = f"c-drainfence-{uuid.uuid4().hex[:8]}"
    await _seed_findings(client, cluster_id, 1)
    report_id = await _enqueue(client, cluster_id)

    job_a = await claim_next(client, worker="wA", report_id=report_id)
    assert job_a is not None
    # A stalls; its lease is force-expired and B reclaims
    stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    await client.update(
        index=REPORTS_INDEX,
        id=report_id,
        body={"doc": {"lease_expires_at": stale, "heartbeat_at": stale}},
        params={"refresh": "true"},
    )
    job_b = await claim_next(client, worker="wB", report_id=report_id)
    assert job_b is not None

    # A wakes and runs its (stale) job to the end — publish must be fenced, no bell
    assert await run_job(client, job_a) is False
    doc = await _report(client, report_id)
    assert doc["status"] == RUNNING and doc["attempt_id"] == job_b.attempt_id
    bell = await client.search(
        index=NOTIFICATIONS_INDEX, body={"query": {"term": {"ref": report_id}}}
    )
    assert bell["hits"]["total"]["value"] == 0

    # B runs and publishes normally; only B's chunks are canonical
    assert await run_job(client, job_b) is True
    doc = await _report(client, report_id)
    assert doc["status"] == DONE and doc["attempt_id"] == job_b.attempt_id
    orphans = await client.count(
        index=REPORT_CHUNKS_INDEX,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"report_id": report_id}},
                        {"term": {"attempt_id": job_a.attempt_id}},
                    ]
                }
            }
        },
    )
    assert orphans["count"] >= 1  # A's orphans exist — slice 4's sweep deletes them


def test_export_params_mirror_search_filters_one_to_one() -> None:
    """The stored params blob must keep mapping onto the M6 lens — drift here silently drops
    filters from queued exports (a tenant-scoping hazard)."""
    param_fields = set(ExportParams.model_fields) - {"format"}
    filter_fields = {f for f in SearchFilters.__dataclass_fields__}
    assert param_fields == filter_fields
    # and the same SHAPE (issue 949): a field that holds one string here but a list in
    # SearchFilters would queue an export the query cannot read
    filter_types = get_type_hints(SearchFilters)
    for name in filter_fields:
        param_type = ExportParams.model_fields[name].annotation
        assert _takes_a_list(param_type) == _takes_a_list(filter_types[name]), name


def _takes_a_list(annotation: Any) -> bool:
    return any(get_origin(a) is list for a in (get_args(annotation) or (annotation,)))


def test_a_stored_string_reaches_the_query_as_a_list() -> None:
    # issue 949: a job queued before the filters took lists stored one string
    filters = _filters_from_params(
        {"format": "csv", "namespace": "payments", "exclude_ptype": "os", "severity": ["low"]}
    )
    assert filters.namespace == ["payments"] and filters.exclude_ptype == ["os"]
    assert filters.severity == ["low"]


# issue 962: the four filters the schedule did not carry. Rows 1 and 2 have openssl, row 1 and
# row 3 share a CVE, and only row 1 has an owner.
_FOUR_FILTER_ROWS = {
    0: {"package_name": "libx", "cve_id": "CVE-2026-0100", "assignee": None},
    1: {"package_name": "openssl", "cve_id": "CVE-2026-0200", "assignee": "ana"},
    2: {"package_name": "openssl", "cve_id": "CVE-2026-0300", "assignee": None},
    3: {"package_name": "zlib", "cve_id": "CVE-2026-0200", "assignee": None},
}


@pytest.mark.parametrize(
    ("params", "kept"),
    [
        ({"package_name": ["openssl"]}, {1, 2}),
        ({"exclude_package_name": ["openssl"]}, {0, 3}),
        ({"exclude_cve_id": ["CVE-2026-0200"]}, {0, 2}),
        ({"unassigned": True}, {0, 2, 3}),
    ],
)
async def test_a_scheduled_export_keeps_the_rows_of_the_screen(client, params, kept) -> None:
    """The schedule dialog sends these four filters once issue 962 lets it. The job must give
    the rows the inline export gives for the same filter, and only those."""
    from backend.export.csv_stream import stream_csv

    cluster_id = f"c-drain-{uuid.uuid4().hex[:8]}"
    for i, fields in _FOUR_FILTER_ROWS.items():
        doc = {**_finding(cluster_id, i), **fields}
        await client.index(index="findings", id=doc["finding_key"], body=doc)
    await client.indices.refresh(index="findings")
    report_id = await _enqueue(
        client, cluster_id, params=ExportParams.model_validate(params).model_dump()
    )

    job = await claim_next(client, worker="w-drain", report_id=report_id)
    assert job is not None
    assert await run_job(client, job) is True
    doc = await _report(client, report_id)
    assert doc["status"] == DONE

    queued = "".join([d async for d in stream_chunks(client, report_id, doc["attempt_id"])])
    inline = "".join(
        [
            line
            async for line in stream_csv(
                client, cluster_id=cluster_id, filters=SearchFilters(**params)
            )
        ]
    )
    assert queued == inline
    keys = {line.split(",")[0] for line in queued.splitlines()[1:]}
    assert keys == {f"fk-{cluster_id}-{i}" for i in kept}
