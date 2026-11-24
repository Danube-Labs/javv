"""M8b slice 4 (#34): trends + contributors at T. The scans trend and the contributors board
are anchored-window queries over append logs (same builders as current-state — single source);
the findings trend derives from occurrences (the cache's `resolved_at` clears on reappearance,
so history must come from the logs). Each surface walks a real T boundary."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from opensearchpy import AsyncOpenSearch

from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.query.as_of_t import AsOfTQuery
from backend.query.search import SearchFilters
from backend.services.ingest import build_docs, ingest_envelope
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
CLUSTER = GOLDEN["cluster_id"]
ORDER = GOLDEN["scan_order"]
READER = AsOfTQuery()


def _envelope(keep: int, scan_order: int, run_id: str, seen_at: str) -> IngestEnvelope:
    e = dict(GOLDEN)
    findings = GOLDEN["findings"][:keep]
    counts: dict[str, int] = dict.fromkeys(
        ("crit", "high", "med", "low", "negligible", "unknown"), 0
    )
    for f in findings:
        # D46/#274: canonical is full-word; count COLUMN names stay short (Option A)
        bucket = canonical_severity(f["severity"])
        counts[{"critical": "crit", "medium": "med"}.get(bucket, bucket)] += 1
    e |= {
        "findings": findings,
        "counts": {
            **counts,
            "total": len(findings),
            "fixable": sum(1 for f in findings if f.get("fixable")),
        },
        "scan_order": scan_order,
        "scan_run_id": run_id,
        "last_seen_at": seen_at,
    }
    return IngestEnvelope.model_validate(e)


async def _now(client: AsyncOpenSearch, prefix: str) -> datetime:
    for index in (
        f"{prefix}javv-scan-events-*",
        f"{prefix}javv-finding-occurrences-*",
        f"{prefix}system-audit-log-*",
    ):
        await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})
    t = datetime.now(UTC)
    await asyncio.sleep(0.002)
    return t


@requires_opensearch
async def test_scans_trend_window_anchors_at_t(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    t0 = await _now(client, prefix)
    await ingest_envelope(client, IngestEnvelope.model_validate(GOLDEN), prefix=prefix)
    t1 = await _now(client, prefix)

    # before the ingest: an anchored window ending at t0 must see nothing (ingested_at > t0)
    before = await READER.trends_scans(client, cluster_id=CLUSTER, t=t0, days=30, prefix=prefix)
    assert sum(p["scans"] for pts in before["series"].values() for p in pts) == 0
    after = await READER.trends_findings(  # placeholder that keeps the line count accurate
        client, cluster_id=CLUSTER, t=t0, days=30, prefix=prefix
    )
    assert after["days"] == 30

    at1 = await READER.trends_scans(client, cluster_id=CLUSTER, t=t1, days=30, prefix=prefix)
    assert sum(p["scans"] for p in at1["series"]["trivy"]) == 1  # cardinality(commit_key)
    with pytest.raises(ValueError, match="days"):
        await READER.trends_scans(client, cluster_id=CLUSTER, t=t1, days=0, prefix=prefix)


@requires_opensearch
async def test_findings_trend_derives_new_and_resolved_from_history(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    # `first_seen_at` is the envelope's own `last_seen_at` (`services/ingest.py:52`), so ingesting
    # the fixture verbatim dates these findings to its fixed day — one that recedes from `now` by
    # another day every day until it falls out of any `days`-bounded window. Stamp run 1 live, as
    # run 2 already is. The failure mode is worth knowing: `trends_findings` omits the scanner key
    # entirely when nothing lands in range, so an aged-out window raises KeyError, not a zero.
    run1 = _envelope(
        len(GOLDEN["findings"]), ORDER, GOLDEN["scan_run_id"], datetime.now(UTC).isoformat()
    )
    await ingest_envelope(client, run1, prefix=prefix)
    t1 = await _now(client, prefix)
    run2 = _envelope(24, ORDER + 1, "goldenrun0002", datetime.now(UTC).isoformat())
    await ingest_envelope(client, run2, prefix=prefix)
    t2 = await _now(client, prefix)

    at1 = await READER.trends_findings(client, cluster_id=CLUSTER, t=t1, days=30, prefix=prefix)
    assert sum(p["count"] for p in at1["new"]["trivy"]) == 29  # every finding is a first appearance
    assert sum(p["count"] for p in at1["resolved"].get("trivy", [])) == 0  # nothing gone yet
    assert at1["resolved_semantics"] == "scan_resolved"

    at2 = await READER.trends_findings(client, cluster_id=CLUSTER, t=t2, days=30, prefix=prefix)
    assert sum(p["count"] for p in at2["new"]["trivy"]) == 29
    assert sum(p["count"] for p in at2["resolved"]["trivy"]) == 5  # resolved by run 2, at run 2
    # the axis is continuous + zero-filled, like the date_histogram it mirrors
    assert len(at2["new"]["trivy"]) == 31


@requires_opensearch
async def test_contributors_board_anchors_at_t(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    await ingest_envelope(client, IngestEnvelope.model_validate(GOLDEN), prefix=prefix)
    fks = [f["finding_key"] for f in build_docs(IngestEnvelope.model_validate(GOLDEN))["findings"]]
    t0 = await _now(client, prefix)

    from backend.triage.service import TriagePatch, apply_triage

    await apply_triage(
        client,
        finding_key=fks[0],
        patch=TriagePatch(state="acknowledged"),
        actor="alice",
        prefix=prefix,
    )
    t1 = await _now(client, prefix)

    at0 = await READER.contributors(client, cluster_id=CLUSTER, t=t0, days=30, prefix=prefix)
    assert at0["leaderboard"] == []  # nothing had happened by t0
    assert at0["totals"]["handled"] == 0  # the zero contract holds at a rewound T too

    at1 = await READER.contributors(client, cluster_id=CLUSTER, t=t1, days=30, prefix=prefix)
    board = {row["actor"]: row for row in at1["leaderboard"]}
    assert board["alice"]["actions"] == 1 and board["alice"]["handled"] == 1
    assert board["alice"]["median_ttr_seconds"] is not None  # first_seen → handled sample
    assert sum(p["count"] for p in at1["handled_over_time"]) == 1
    # contract parity with the live route (M9d slice 3): the KPI totals ride the T-read too
    assert at1["totals"]["handled"] == 1 and at1["totals"]["by_action"] == {"acknowledge": 1}
    with pytest.raises(ValueError, match="days"):
        await READER.contributors(client, cluster_id=CLUSTER, t=t1, days=999, prefix=prefix)


def _totals(out: dict[str, Any]) -> dict[str, int]:
    return {sev: sum(p["count"] for p in points) for sev, points in out["series"].items()}


@requires_opensearch
async def test_new_findings_trend_at_t_follows_the_filters_and_presence(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    """Issue 1292: the New findings strip at a past time. The rows as they stood at T, under the
    filters of the table, counted by first appearance and canonical severity."""
    client, prefix = real_os
    t0 = await _now(client, prefix)
    # the scanner sends its own words (CRITICAL, HIGH, ...): the buckets are the canonical ones
    seen = datetime.now(UTC).isoformat()
    run1 = _envelope(len(GOLDEN["findings"]), ORDER, GOLDEN["scan_run_id"], seen)
    await ingest_envelope(client, run1, prefix=prefix)
    t1 = await _now(client, prefix)
    run2 = _envelope(24, ORDER + 1, "goldenrun0002", datetime.now(UTC).isoformat())
    await ingest_envelope(client, run2, prefix=prefix)
    t2 = await _now(client, prefix)

    async def at(t: datetime, **filters: Any) -> dict[str, Any]:
        return await READER.trends_new_findings(
            client,
            cluster_id=CLUSTER,
            t=t,
            days=30,
            filters=SearchFilters(**filters),
            prefix=prefix,
        )

    assert (await at(t0))["series"] == {}  # nothing scanned yet
    at1 = await at(t1)
    assert _totals(at1) == {"critical": 4, "high": 8, "medium": 8, "low": 5, "unknown": 4}
    assert at1["days"] == 30
    assert at1["interval"] == "day"  # daily buckets at a past time (ruling 5 of issue 1291)
    assert len(at1["series"]["critical"]) == 31  # continuous and zero-filled
    # run 2 dropped the last five findings: at T2 they are gone, and present=false shows them
    assert _totals(await at(t2)) == {"critical": 4, "high": 8, "medium": 4, "low": 4, "unknown": 4}
    assert _totals(await at(t2, present=False)) == {"medium": 4, "low": 1}
    assert _totals(await at(t2, severity=["critical"])) == {"critical": 4}
    assert _totals(await at(t2, scanner="grype")) == {}
    assert _totals(await at(t2, exclude_severity=["unknown", "high"])) == {
        "critical": 4,
        "medium": 4,
        "low": 4,
    }

    # the filters the history does not record refuse before any work, as on Findings
    for unrecorded in ({"kev": True}, {"disagree": True}, {"new_within_days": 7}):
        with pytest.raises(ValueError, match="not recorded"):
            await at(t2, **unrecorded)
    with pytest.raises(ValueError, match="days"):
        await READER.trends_new_findings(
            client, cluster_id=CLUSTER, t=t2, days=0, filters=SearchFilters(), prefix=prefix
        )
