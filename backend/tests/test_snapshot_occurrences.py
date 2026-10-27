"""M8a slice 1 (#33): per-scan occurrence snapshots. Unit tests pin the row builder to the
INDEX-MAP contract (identity reused from `build_docs`, no `severity_rank`, no state); the
integration tests prove the D39 ordering against a real OpenSearch — append is idempotent (D18),
a clean scan writes zero rows but still commits, and a failed occurrences bulk BLOCKS the catalog
commit so an uncertified snapshot is never read as "latest"."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from opensearchpy import AsyncOpenSearch, TransportError

from backend.core.bootstrap import _OCCURRENCES_PROPERTIES
from backend.models.envelope import IngestEnvelope
from backend.services.ingest import build_docs, ingest_envelope
from backend.snapshots.occurrences import (
    OCCURRENCES_SERIES,
    build_occurrence_rows,
    occurrence_id,
)
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())


def _golden_docs() -> dict[str, Any]:
    return build_docs(IngestEnvelope.model_validate(GOLDEN))


# --- unit: the row builder -----------------------------------------------------


def test_one_row_per_finding_with_reused_identity() -> None:
    docs = _golden_docs()
    rows = build_occurrence_rows(docs)
    assert len(rows) == len(docs["findings"]) == GOLDEN["counts"]["total"]
    for (row_id, row), f in zip(rows, docs["findings"], strict=True):
        # identity is REUSED from the cache path, never re-derived (single-source hashing)
        assert row["finding_key"] == f["finding_key"]
        assert row["commit_key"] == docs["commit_key"]
        assert row_id == occurrence_id(GOLDEN["scan_run_id"], f["finding_key"])


def test_row_carries_the_index_map_shape_and_nothing_else() -> None:
    _, row = build_occurrence_rows(_golden_docs())[0]
    # the mapping in bootstrap and the builder must agree exactly — no unmapped/dynamic drift
    assert set(row) == set(_OCCURRENCES_PROPERTIES)
    # deliberately absent: rank is findings-only (OE-5); presence/state have no meaning in history
    for banned in ("severity_rank", "state", "present", "first_seen_at"):
        assert banned not in row


def test_row_values_are_as_of_then_and_verbatim() -> None:
    docs = _golden_docs()
    _, row = build_occurrence_rows(docs)[0]
    f = docs["findings"][0]
    assert row["vuln_id"] == f["cve_id"] == "CVE-2005-2541"
    assert row["package_version"] == f["installed_version"]
    assert row["severity"] == "LOW"  # verbatim scanner word (D16) — the lc normalizer folds aggs
    assert row["scan_order"] == GOLDEN["scan_order"]
    assert row["scan_run_id"] == GOLDEN["scan_run_id"]
    assert row["@timestamp"] == f["last_seen_at"]
    assert row["ingested_at"] == docs["scan_event"]["ingested_at"]  # server stamp, shared


def test_row_records_the_kev_value_of_its_finding() -> None:
    """Issue 1000: a read at a past time gives a KEV finding the KEV deadline only if the history
    keeps the KEV value that the scan sent (grype sends it, trivy never does)."""
    env = dict(GOLDEN)
    env["findings"] = [dict(f, kev=(i == 0)) for i, f in enumerate(GOLDEN["findings"])]
    rows = build_occurrence_rows(build_docs(IngestEnvelope.model_validate(env)))
    assert [row["kev"] for _, row in rows] == [i == 0 for i in range(len(rows))]


def test_occurrence_id_is_deterministic_and_distinct() -> None:
    docs = _golden_docs()
    ids = [rid for rid, _ in build_occurrence_rows(docs)]
    assert ids == [rid for rid, _ in build_occurrence_rows(docs)]  # replay-stable (D18)
    assert len(set(ids)) == len(ids)  # distinct per finding


def test_clean_scan_builds_zero_rows() -> None:
    clean = dict(GOLDEN)
    clean["findings"] = []
    clean["counts"] = dict.fromkeys(GOLDEN["counts"], 0)
    docs = build_docs(IngestEnvelope.model_validate(clean))
    assert build_occurrence_rows(docs) == []


# --- integration: the D39 ordering against a real OpenSearch -------------------


async def _occurrence_hits(client: AsyncOpenSearch, prefix: str, cluster_id: str) -> list[dict]:
    index = f"{prefix}{OCCURRENCES_SERIES}-{cluster_id}-*"
    await client.indices.refresh(index=index)
    resp = await client.search(index=index, body={"size": 100, "query": {"match_all": {}}})
    return resp["hits"]["hits"]


async def _catalog_doc_exists(client: AsyncOpenSearch, prefix: str, env: IngestEnvelope) -> bool:
    index = f"{prefix}javv-scan-events-{env.cluster_id}-*"
    try:
        await client.indices.refresh(index=index)
    except Exception:
        return False
    resp = await client.search(
        index=index,
        body={"query": {"term": {"scan_run_id": env.scan_run_id}}, "size": 1},
    )
    return bool(resp["hits"]["hits"])


@requires_opensearch
async def test_snapshot_append_round_trip_is_idempotent(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    env = IngestEnvelope.model_validate(GOLDEN)
    await ingest_envelope(client, env, prefix=prefix)
    hits = await _occurrence_hits(client, prefix, env.cluster_id)
    assert len(hits) == env.counts.total
    commit_key = build_docs(env)["commit_key"]
    for h in hits:
        assert h["_source"]["commit_key"] == commit_key
        assert h["_source"]["scan_order"] == env.scan_order

    # the same envelope again (retry / idempotent replay) — no duplicate history (D18)
    await ingest_envelope(client, env, prefix=prefix)
    assert len(await _occurrence_hits(client, prefix, env.cluster_id)) == env.counts.total


@requires_opensearch
async def test_clean_scan_commits_catalog_with_zero_rows(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    clean = dict(GOLDEN)
    clean["findings"] = []
    clean["counts"] = dict.fromkeys(GOLDEN["counts"], 0)
    env = IngestEnvelope.model_validate(clean)
    await ingest_envelope(client, env, prefix=prefix)
    # zero occurrence rows — R-CATALOG reads the committed doc as CLEAN, not the prior snapshot
    assert await _occurrence_hits(client, prefix, env.cluster_id) == []
    assert await _catalog_doc_exists(client, prefix, env)


class _FailBulkOnIndex:
    """Delegating client whose `_bulk` fails hard when the payload targets `needle` — drives the
    commit-blocked-on-append-failure ordering proof without a broken cluster."""

    def __init__(self, inner: AsyncOpenSearch, needle: str):
        self._inner = inner
        self._needle = needle

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def bulk(self, *args: Any, **kwargs: Any) -> Any:
        body = kwargs.get("body") or (args[0] if args else [])
        for item in body:
            meta = item.get("index") or item.get("update") or {}
            if self._needle in str(meta.get("_index", "")):
                raise TransportError(500, "injected occurrences bulk failure")
        return await self._inner.bulk(*args, **kwargs)


@requires_opensearch
async def test_failed_occurrences_bulk_blocks_the_catalog_commit(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    env = IngestEnvelope.model_validate(GOLDEN)
    failing = cast(AsyncOpenSearch, _FailBulkOnIndex(client, OCCURRENCES_SERIES))
    with pytest.raises(TransportError):
        await ingest_envelope(failing, env, prefix=prefix)
    # D39: the snapshot never got certified — no catalog doc, so it can never be read as "latest"
    assert not await _catalog_doc_exists(client, prefix, env)
