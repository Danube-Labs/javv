"""M8b slice 3 (#34): the AsOfTReader findings surfaces. The centerpiece is the **I11
consistency keystone**: after real ingests + real triage + a real decision, the reconstruction
at T=just-now must agree with the MATERIALIZED current-state read on every field history can
answer — the two read paths (cache vs replay) may never tell different stories. Around it: the
timeline walk through the same surfaces, the re-validation contract (raw delegated inputs →
ValueError), tombstone parity, and stateless paging."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from opensearchpy import AsyncOpenSearch

from backend.decisions.lifecycle import DecisionPayload, DecisionScope, create_decision
from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.query.as_of_t import AsOfTQuery
from backend.query.search import SearchFilters, run_search
from backend.services.ingest import build_docs, ingest_envelope
from backend.sla.overdue import compute_overdue
from backend.sla.policy import read_sla_policy
from backend.triage.bulk import apply_bulk_triage
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
CLUSTER = GOLDEN["cluster_id"]
DIGEST = GOLDEN["image_digest"]
ORDER = GOLDEN["scan_order"]

# every findings-doc field the per-scan history records — the I11 comparison surface
RECONSTRUCTABLE = (
    "finding_key",
    "cluster_id",
    "scanner",
    "image_digest",
    "cve_id",
    "package_name",
    "installed_version",
    "severity",
    "severity_rank",
    "cvss",
    "fixable",
    "fixed_version",
    "ptype",  # M8d/B-1 — recorded on occurrences, reconstructable like the other scanner facts
    "present",
    "state",
    "assignee",
    "notes",
    "vex_justification",
    "last_scan_run_id",
    "last_scan_order",
)


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
    """A padded instant (ms truncation — see test_human_at) with the read indices refreshed."""
    for index in (
        f"{prefix}findings",
        f"{prefix}javv-scan-events-*",
        f"{prefix}javv-finding-occurrences-*",
        f"{prefix}system-audit-log-*",
    ):
        await client.indices.refresh(index=index, params={"ignore_unavailable": "true"})
    t = datetime.now(UTC)
    await asyncio.sleep(0.002)
    return t


READER = AsOfTQuery()


async def _seed(client: AsyncOpenSearch, prefix: str) -> dict[str, Any]:
    """Real history: full scan → triage (direct + bulk) + a decision → rescan resolving 5."""
    run1 = IngestEnvelope.model_validate(GOLDEN)
    await ingest_envelope(client, run1, prefix=prefix)
    fks = [f["finding_key"] for f in build_docs(run1)["findings"]]

    # direct triage on one finding + a bulk risk-accept on two others (real writers)
    from backend.triage.service import TriagePatch, apply_triage

    await apply_triage(
        client,
        finding_key=fks[0],
        patch=TriagePatch(state="acknowledged"),
        actor="alice",
        prefix=prefix,
    )
    await apply_bulk_triage(
        client,
        actor="bob",
        cluster_id=CLUSTER,
        target_ids=[fks[1], fks[2]],
        patch={"state": "risk_accepted"},
        prefix=prefix,
    )
    # a cluster-wide decision on a CVE nobody touched directly (projection territory)
    decided_cve = GOLDEN["findings"][5]["vuln_id"]
    await create_decision(
        client,
        actor="carol",
        payload=DecisionPayload(
            type="risk_accepted",
            cve_id=decided_cve,
            scope=DecisionScope(),
            apply_both_scanners=True,
            justification="accepted for the demo window",
            cluster_id=CLUSTER,
        ),
        prefix=prefix,
    )
    t_triaged = await _now(client, prefix)

    # run 2's scan time must sit BETWEEN t1 and t2 on the WALL clock — the ≤ T cut compares
    # @timestamp, so a fixed logical date here would leak the rescan into t1's view
    run2 = _envelope(24, ORDER + 1, "goldenrun0002", datetime.now(UTC).isoformat())
    await ingest_envelope(client, run2, prefix=prefix)
    t_final = await _now(client, prefix)
    return {"fks": fks, "decided_cve": decided_cve, "t1": t_triaged, "t2": t_final}


@requires_opensearch
async def test_i11_keystone_replay_to_now_matches_materialized_state(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    seeded = await _seed(client, prefix)

    # materialized current state (the cache path, exactly what the route serves)
    current = await run_search(
        client,
        cluster_id=CLUSTER,
        filters=SearchFilters(present=True),
        size=500,
        prefix=prefix,
    )
    materialized = {d["finding_key"]: d for d in current["data"]}

    # reconstructed at T=just-now (the replay path)
    page = await READER.findings_page(
        client,
        cluster_id=CLUSTER,
        t=seeded["t2"],
        filters=SearchFilters(present=True),
        sort="severity_rank",
        order="desc",
        size=500,
        cursor=None,
        prefix=prefix,
    )
    reconstructed = {d["finding_key"]: d for d in page["data"]}

    assert set(reconstructed) == set(materialized)  # identical membership — no ghosts, no loss
    for fk, cache_doc in materialized.items():
        replay_doc = reconstructed[fk]
        for field in RECONSTRUCTABLE:
            assert replay_doc[field] == cache_doc.get(field), (
                f"I11 divergence on {field} for {fk}: "
                f"replay={replay_doc[field]!r} cache={cache_doc.get(field)!r}"
            )


async def _seed_kev(client: AsyncOpenSearch, prefix: str) -> tuple[str, datetime, datetime]:
    """One scan 3 days ago whose first finding (severity Low, 90 days) is KEV (1 day): KEV makes
    it overdue now, its severity alone would not. Returns (its finding_key, seen_at, T)."""
    seen = (datetime.now(UTC) - timedelta(days=3)).replace(microsecond=0)
    env = dict(GOLDEN) | {
        "findings": [dict(f, kev=(i == 0)) for i, f in enumerate(GOLDEN["findings"])],
        "last_seen_at": seen.isoformat(),
    }
    run = IngestEnvelope.model_validate(env)
    await ingest_envelope(client, run, prefix=prefix)
    kev_fk = build_docs(run)["findings"][0]["finding_key"]
    return kev_fk, seen, await _now(client, prefix)


async def _past_rows(client: AsyncOpenSearch, prefix: str, t: datetime) -> dict[str, Any]:
    page = await READER.findings_page(
        client,
        cluster_id=CLUSTER,
        t=t,
        filters=SearchFilters(present=True),
        sort="severity_rank",
        order="desc",
        size=500,
        cursor=None,
        prefix=prefix,
    )
    return {d["finding_key"]: d for d in page["data"]}


@requires_opensearch
async def test_at_t_just_now_each_row_has_the_live_sla_deadline(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    """Issue 1000: the I11 keystone for the SLA verdict. A read at T just now gives each row the
    same `overdue` and `due_at` as the live read, also a KEV finding whose severity deadline is
    not over yet (before the history kept KEV, that row was not overdue at T)."""
    client, prefix = real_os
    kev_fk, seen, t = await _seed_kev(client, prefix)

    current = await run_search(
        client, cluster_id=CLUSTER, filters=SearchFilters(present=True), size=500, prefix=prefix
    )
    live = compute_overdue(
        current["data"], policy=await read_sla_policy(client, prefix=prefix), now=t
    )
    past = await _past_rows(client, prefix, t)

    assert set(past) == set(live)
    assert live[kev_fk].overdue  # the case under test: overdue only because of KEV
    kev_due = live[kev_fk].due_at
    assert kev_due is not None
    assert datetime.fromisoformat(kev_due) == seen + timedelta(days=1)
    for fk, verdict in live.items():
        row = past[fk]
        assert row["overdue"] == verdict.overdue, fk
        if verdict.due_at is None:
            assert row["due_at"] is None, fk
        else:
            assert datetime.fromisoformat(row["due_at"]) == datetime.fromisoformat(verdict.due_at)


@requires_opensearch
async def test_a_history_row_without_kev_gets_the_deadline_of_its_severity(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    """A history row written before mapping v20 has no `kev`: the past-time read treats the
    finding as not KEV, so it gets the deadline of its severity (Low: 90 days)."""
    client, prefix = real_os
    kev_fk, seen, _ = await _seed_kev(client, prefix)
    await client.update_by_query(
        index=f"{prefix}javv-finding-occurrences-*",
        body={"script": {"source": "ctx._source.remove('kev')"}},
        params={"refresh": "true", "conflicts": "proceed"},
    )
    t = await _now(client, prefix)

    row = (await _past_rows(client, prefix, t))[kev_fk]
    assert row["overdue"] is False
    assert datetime.fromisoformat(row["due_at"]) == seen + timedelta(days=90)
    assert row["kev"] is None  # the row keeps no KEV value at a past time (issue 1000, D2)


@requires_opensearch
async def test_the_timeline_walks_through_the_page_surface(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    seeded = await _seed(client, prefix)
    fks = seeded["fks"]

    at1 = await READER.findings_page(
        client,
        cluster_id=CLUSTER,
        t=seeded["t1"],
        filters=SearchFilters(present=True),
        sort="severity_rank",
        order="desc",
        size=500,
        cursor=None,
        prefix=prefix,
    )
    assert at1["total"] == {"value": 29, "relation": "eq"}  # before the resolving rescan
    by_key = {d["finding_key"]: d for d in at1["data"]}
    assert by_key[fks[0]]["state"] == "acknowledged"  # direct triage visible at T1
    assert by_key[fks[1]]["state"] == "risk_accepted"  # bulk visible at T1
    decided = [d for d in at1["data"] if d["cve_id"] == seeded["decided_cve"]]
    assert decided and all(d["state"] == "risk_accepted" for d in decided)  # projection at T1
    assert all(d["state_decision_id"] for d in decided)

    at2 = await READER.findings_page(
        client,
        cluster_id=CLUSTER,
        t=seeded["t2"],
        filters=SearchFilters(present=True),
        sort="severity_rank",
        order="desc",
        size=500,
        cursor=None,
        prefix=prefix,
    )
    assert at2["total"]["value"] == 24  # the rescan resolved 5 — as-scanned at T2

    # tombstone parity: the 5 resolved findings are the present=false view at T2
    gone = await READER.findings_page(
        client,
        cluster_id=CLUSTER,
        t=seeded["t2"],
        filters=SearchFilters(present=False),
        sort="last_scan_at",
        order="desc",
        size=500,
        cursor=None,
        prefix=prefix,
    )
    assert gone["total"]["value"] == 5
    assert all(d["resolved_at"] is not None for d in gone["data"])


@requires_opensearch
async def test_facets_and_groups_reconstruct_with_scanner_split(
    real_os: tuple[AsyncOpenSearch, str],
) -> None:
    client, prefix = real_os
    seeded = await _seed(client, prefix)
    facets = await READER.findings_facets(
        client,
        cluster_id=CLUSTER,
        t=seeded["t1"],
        filters=SearchFilters(present=True),
        fields=None,
        prefix=prefix,
    )
    states = {b["key"]: b["count"] for b in facets["facets"]["state"]}
    assert states["acknowledged"] == 1 and states["risk_accepted"] >= 3  # 2 bulk + projection
    assert sum(states.values()) == 29
    for b in facets["facets"]["state"]:
        assert b["by_scanner"] == {"trivy": b["count"]}  # per-scanner is sacred
    assert facets["facets"]["kev"] == []  # whitelisted but unrecorded at T — explicit empty
    # issue 363: the overdue facet at T counts the reconstruction's OWN at-T verdict — pin it
    # against the page surface's row verdicts (facet ≡ rows), never a constant: the golden
    # corpus is dated, so the breached share grows with the wall clock
    overdue = {b["key"]: b["count"] for b in facets["facets"]["overdue"]}
    page = await READER.findings_page(
        client,
        cluster_id=CLUSTER,
        t=seeded["t1"],
        filters=SearchFilters(present=True),
        sort="severity_rank",
        order="desc",
        size=500,
        cursor=None,
        prefix=prefix,
    )
    rows_true = sum(1 for r in page["data"] if r["overdue"])
    assert sum(overdue.values()) == 29
    assert overdue.get("true", 0) == rows_true and rows_true > 0  # dated corpus: some breached
    # issue 349 §1: same contract as overdue — the unassigned facet counts the reader's own
    # expression (non-empty assignee), pinned against the page surface's rows, never a constant
    unassigned = {b["key"]: b["count"] for b in facets["facets"]["unassigned"]}
    rows_unowned = sum(1 for r in page["data"] if not r.get("assignee"))
    assert sum(unassigned.values()) == 29
    assert unassigned.get("true", 0) == rows_unowned

    groups = await READER.findings_groups(
        client,
        cluster_id=CLUSTER,
        t=seeded["t1"],
        filters=SearchFilters(present=True),
        by="cve_id",
        size=10,
        cursor=None,
        prefix=prefix,
    )
    assert len(groups["data"]) == 10 and groups["next_cursor"] is not None
    # walk the rest — every bucket reachable, none silently capped
    seen = [b["key"] for b in groups["data"]]
    cursor = groups["next_cursor"]
    while cursor:
        nxt = await READER.findings_groups(
            client,
            cluster_id=CLUSTER,
            t=seeded["t1"],
            filters=SearchFilters(present=True),
            by="cve_id",
            size=10,
            cursor=cursor,
            prefix=prefix,
        )
        seen += [b["key"] for b in nxt["data"]]
        cursor = nxt["next_cursor"]
    assert len(seen) == len(set(seen)) == len({f["vuln_id"] for f in GOLDEN["findings"]})


@requires_opensearch
async def test_delegated_inputs_are_revalidated(real_os: tuple[AsyncOpenSearch, str]) -> None:
    # the raw-forwarding contract: every non-answerable input is a ValueError (→ the route's
    # 422), never an unchecked pass-through
    client, prefix = real_os
    t = datetime.now(UTC)
    base: dict[str, Any] = dict(cluster_id=CLUSTER, t=t, prefix=prefix)
    with pytest.raises(ValueError, match="sort"):
        await READER.findings_page(
            client,
            **base,
            filters=SearchFilters(),
            sort="epss",
            order="desc",
            size=10,
            cursor=None,
        )
    with pytest.raises(ValueError, match="kev"):
        await READER.findings_page(
            client,
            **base,
            filters=SearchFilters(kev=True),
            sort="cvss",
            order="desc",
            size=10,
            cursor=None,
        )
    with pytest.raises(ValueError, match="not facetable"):
        await READER.findings_facets(client, **base, filters=SearchFilters(), fields=["nope; DROP"])
    with pytest.raises(ValueError, match="not groupable"):
        await READER.findings_groups(
            client, **base, filters=SearchFilters(), by="image_repo", size=10, cursor=None
        )
    with pytest.raises(ValueError, match="cursor"):
        await READER.findings_page(
            client,
            **base,
            filters=SearchFilters(),
            sort="cvss",
            order="desc",
            size=10,
            cursor="garbage!!",
        )


@requires_opensearch
async def test_page_walk_is_stateless_and_complete(real_os: tuple[AsyncOpenSearch, str]) -> None:
    client, prefix = real_os
    seeded = await _seed(client, prefix)
    seen: list[str] = []
    cursor = None
    while True:
        page = await READER.findings_page(
            client,
            cluster_id=CLUSTER,
            t=seeded["t1"],
            filters=SearchFilters(present=True),
            sort="severity_rank",
            order="desc",
            size=7,
            cursor=cursor,
            prefix=prefix,
        )
        seen += [d["finding_key"] for d in page["data"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 29 and len(set(seen)) == 29  # every row exactly once


async def test_snapshot_matches_the_page_walk_from_one_reconstruction(
    real_os: tuple[AsyncOpenSearch, str], monkeypatch
) -> None:
    """The export path's source (audit F-09): `findings_snapshot` returns the page walk's
    exact row order — but reconstructs the cluster ONCE, where the old per-page drain paid
    a full reconstruction per 500 rows."""
    client, prefix = real_os
    seeded = await _seed(client, prefix)

    calls = 0
    real_reconstruct = AsOfTQuery._reconstruct

    async def _counted(self, *a, **kw):
        nonlocal calls
        calls += 1
        return await real_reconstruct(self, *a, **kw)

    monkeypatch.setattr(AsOfTQuery, "_reconstruct", _counted)

    snapshot = await READER.findings_snapshot(
        client,
        cluster_id=CLUSTER,
        t=seeded["t1"],
        filters=SearchFilters(present=True),
        sort="severity_rank",
        order="desc",
        prefix=prefix,
    )
    assert calls == 1  # one reconstruction for the whole sweep

    walked: list[str] = []
    cursor = None
    while True:
        page = await READER.findings_page(
            client,
            cluster_id=CLUSTER,
            t=seeded["t1"],
            filters=SearchFilters(present=True),
            sort="severity_rank",
            order="desc",
            size=7,
            cursor=cursor,
            prefix=prefix,
        )
        walked += [d["finding_key"] for d in page["data"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert [r["finding_key"] for r in snapshot] == walked  # byte-for-byte the same walk


def test_every_search_filter_is_handled_or_rejected_at_past_t() -> None:
    """The parity guard the q gap proved missing (M9b slice 4): a NEW SearchFilters field must
    be either applied by `_apply_filters` or explicitly rejected — silently ignoring one returns
    unfiltered rows at a past T with no error. Each field is probed one at a time: acceptable
    outcomes are 'filters rows' (empty in = empty out) or an explicit unrecorded-ValueError;
    anything else means the reader never saw the field."""
    from dataclasses import fields as dc_fields

    from backend.query.as_of_t import AsOfTQuery
    from backend.query.search import SearchFilters

    probe_values: dict[str, Any] = {
        "severity": ["critical"],
        "state": ["open"],
        "scanner": "trivy",
        "assignee": ["someone"],
        "kev": True,
        "fixable": True,
        "disagree": True,
        "cve_id": ["CVE-0000-0000"],
        "image_digest": "sha256:x",
        "image_repo": ["nginx"],
        "namespace": ["ns"],
        "ptype": ["os"],
        "package_name": ["zlib"],
        "q": "krb5",
        "present": False,
        "new_within_days": 30,
        "overdue": True,  # issue 363 — filters the reconstruction's own at-T verdict
        # issue 349 §1 — the row is unowned, so asking for an OWNER must drop it
        "unassigned": False,
        # issue 349 excludes: each probe MATCHES the row below so a handled exclude drops it
        "exclude_severity": ["high"],
        "exclude_state": ["resolved"],
        "exclude_scanner": "grype",
        "exclude_assignee": [
            "someone"
        ],  # row has assignee=None — pure-must_not KEEPS it; see below
        "exclude_image_repo": ["nginx"],
        "exclude_namespace": ["default"],
        "exclude_ptype": ["os"],  # row has ptype=None — same missing-field carve-out
        "exclude_cve_id": ["CVE-1"],  # issue 492 — matches the row, so it drops
        "exclude_package_name": ["zlib"],  # row has package_name=None — carve-out again
    }
    missing = set(probe_values) ^ {f.name for f in dc_fields(SearchFilters)}
    assert not missing, f"probe map drifted from SearchFilters: {missing}"

    # deliberately mismatches every probe value — a handled filter must EXCLUDE this row
    row = {
        "present": True,
        "severity_canonical": "high",
        "state": "resolved",
        "scanner": "grype",
        "assignee": None,
        "fixable": False,
        "cve_id": "CVE-1",
        "image_digest": "sha256:y",
        "ptype": None,
        "package_name": None,
        "namespaces": ["default"],
        "overdue": False,  # the row's at-T verdict (stamped by _decorate_overdue at now=t)
    }
    # the issue-349 semantic pin: pure must_not — a row MISSING the excluded field survives
    # the exclusion, so these probes legitimately keep the row instead of dropping it
    missing_field_excludes = {"exclude_assignee", "exclude_ptype", "exclude_package_name"}
    for name, value in probe_values.items():
        f = SearchFilters(**{name: value})
        try:
            out = AsOfTQuery._apply_filters([dict(row)], f)
        except ValueError:
            continue  # explicit unrecorded rejection
        if name in missing_field_excludes:
            assert len(out) == 1, f"exclude semantics drifted: {name} must keep a field-less row"
            continue
        assert out == [], f"SearchFilters.{name} was silently ignored by the as_of reader"


def test_several_values_at_past_t_are_membership_not_equality() -> None:
    """Issue 949: the six list filters at a past T. The guard above cannot see this bug: an
    equality check against a list drops EVERY row, which still reads as "filtered". So each
    case here lists two values where exactly one matches the row, and the include must KEEP
    the row while the exclude must DROP it. The live query does the same with `terms`."""
    from backend.query.as_of_t import AsOfTQuery
    from backend.query.search import SearchFilters

    row = {
        "present": True,
        "severity_canonical": "high",
        "state": "open",
        "scanner": "trivy",
        "assignee": "ana",
        "fixable": False,
        "cve_id": "CVE-1",
        "image_digest": "sha256:y",
        "ptype": "deb",
        "package_name": "zlib",
        "namespaces": ["default", "prod"],
        "overdue": False,
    }
    hits: dict[str, Any] = {
        "assignee": ["bob", "ana"],
        "cve_id": ["CVE-9", "CVE-1"],
        "ptype": ["npm", "deb"],
        "package_name": ["openssl", "zlib"],
        "namespace": ["staging", "prod"],  # any overlap with the row's namespaces
    }
    for name, values in hits.items():
        keep = AsOfTQuery._apply_filters([dict(row)], SearchFilters(**{name: values}))
        assert len(keep) == 1, f"{name}={values} must keep a row that holds one of the values"
        drop = AsOfTQuery._apply_filters([dict(row)], SearchFilters(**{f"exclude_{name}": values}))
        assert drop == [], f"exclude_{name}={values} must drop a row that holds one value"
        miss = AsOfTQuery._apply_filters(
            [dict(row)], SearchFilters(**dict[str, Any]({name: ["x", "y"]}))
        )
        assert miss == [], f"{name}=['x', 'y'] must drop a row that holds neither value"
    # an empty list is no filter, as in the live query; image_repo too, though it is unrecorded
    for empty in ("namespace", "image_repo", "exclude_image_repo"):
        f = SearchFilters(**dict[str, Any]({empty: []}))
        assert len(AsOfTQuery._apply_filters([dict(row)], f)) == 1, empty
    # image_repo is not in the scan history: a list is refused like one value always was
    with pytest.raises(ValueError, match="image_repo"):
        AsOfTQuery._apply_filters([dict(row)], SearchFilters(image_repo=["a", "b"]))


async def test_past_t_package_type_facet_leaves_out_its_own_filter(monkeypatch) -> None:
    """Issue 949, ruling 2, at a past T: the same rule as the live facet. After a pick of
    `deb`, the Package type facet still counts `npm`; severity still counts under the pick."""
    from backend.query.as_of_t import AsOfTQuery
    from backend.query.search import SearchFilters

    def _row(ptype: str, sev: str) -> dict[str, Any]:
        return {
            "present": True,
            "severity_canonical": sev,
            "state": "open",
            "scanner": "trivy",
            "assignee": None,
            "fixable": False,
            "cve_id": "CVE-1",
            "image_digest": "sha256:y",
            "ptype": ptype,
            "package_name": None,
            "namespaces": ["default"],
            "overdue": False,
        }

    rows = [_row("deb", "high"), _row("deb", "high"), _row("npm", "low")]

    async def _fake(self: Any, *_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    monkeypatch.setattr(AsOfTQuery, "_reconstruct", _fake)
    out = await AsOfTQuery().findings_facets(
        cast(Any, None),
        cluster_id="c",
        t=datetime(2026, 1, 1, tzinfo=UTC),
        filters=SearchFilters(ptype=["deb"]),
        fields=["ptype", "severity"],
    )
    counts = {k: {b["key"]: b["count"] for b in v} for k, v in out["facets"].items()}
    assert counts["ptype"] == {"deb": 2, "npm": 1}
    assert counts["severity"] == {"high": 2}


async def test_past_t_all_filters_counts_the_package_type_under_its_own_filter(
    monkeypatch,
) -> None:
    """Issue 999, decision 4, at a past T: with `all_filters`, the Package type facet counts
    under its own pick too, the same rule as the live facet."""
    from backend.query.as_of_t import AsOfTQuery
    from backend.query.search import SearchFilters

    def _row(ptype: str) -> dict[str, Any]:
        return {
            "present": True,
            "severity_canonical": "high",
            "state": "open",
            "scanner": "trivy",
            "assignee": None,
            "fixable": False,
            "cve_id": "CVE-1",
            "image_digest": "sha256:y",
            "ptype": ptype,
            "package_name": None,
            "namespaces": ["default"],
            "overdue": False,
        }

    rows = [_row("deb"), _row("deb"), _row("npm")]

    async def _fake(self: Any, *_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    monkeypatch.setattr(AsOfTQuery, "_reconstruct", _fake)
    out = await AsOfTQuery().findings_facets(
        cast(Any, None),
        cluster_id="c",
        t=datetime(2026, 1, 1, tzinfo=UTC),
        filters=SearchFilters(exclude_ptype=["npm"]),
        fields=["ptype"],
        all_filters=True,
    )
    assert {b["key"]: b["count"] for b in out["facets"]["ptype"]} == {"deb": 2}


async def test_past_t_unassigned_count_leaves_out_assignee_is(monkeypatch) -> None:
    """Issue 979 at a past T: the same rule as the live facet. With Assignee "is lead", the
    Unassigned count is the rows with no owner (what a click on Unassigned shows), and the
    other facets still count only the rows of `lead`."""
    from backend.query.as_of_t import AsOfTQuery
    from backend.query.search import SearchFilters

    def _row(assignee: str | None, sev: str) -> dict[str, Any]:
        return {
            "present": True,
            "severity_canonical": sev,
            "state": "open",
            "scanner": "trivy",
            "assignee": assignee,
            "fixable": False,
            "cve_id": "CVE-1",
            "image_digest": "sha256:y",
            "ptype": "deb",
            "package_name": None,
            "namespaces": ["default"],
            "overdue": False,
        }

    rows = [_row("lead", "critical"), _row("lead", "critical"), _row(None, "low")]
    rows += [_row(None, "high"), _row("", "high"), _row("bob", "low")]

    async def _fake(self: Any, *_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    monkeypatch.setattr(AsOfTQuery, "_reconstruct", _fake)
    out = await AsOfTQuery().findings_facets(
        cast(Any, None),
        cluster_id="c",
        t=datetime(2026, 1, 1, tzinfo=UTC),
        filters=SearchFilters(assignee=["lead"]),
        fields=["unassigned", "severity"],
    )
    counts = {k: {b["key"]: b["count"] for b in v} for k, v in out["facets"].items()}
    assert counts["unassigned"] == {"true": 3, "false": 3}  # None and "" have no owner
    assert counts["severity"] == {"critical": 2}


async def test_past_t_facets_filter_again_only_for_a_field_with_its_own_filter(
    monkeypatch,
) -> None:
    """The second pass over the rows is only needed when the ptype facet has a filter of its
    own to leave out; without one it would count the same rows again (as build_facets_body)."""
    from backend.query.as_of_t import AsOfTQuery
    from backend.query.search import SearchFilters

    async def _fake(self: Any, *_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        return []

    passes: list[SearchFilters] = []
    real = AsOfTQuery._apply_filters

    def _counting(rows: list[dict[str, Any]], f: SearchFilters) -> list[dict[str, Any]]:
        passes.append(f)
        return real(rows, f)

    monkeypatch.setattr(AsOfTQuery, "_reconstruct", _fake)
    monkeypatch.setattr(AsOfTQuery, "_apply_filters", staticmethod(_counting))
    for filters, expected in (
        (SearchFilters(severity=["high"]), 1),
        (SearchFilters(namespace=["prod"]), 1),  # not the ptype facet's own field
        (SearchFilters(ptype=["deb"]), 2),
        (SearchFilters(exclude_ptype=["npm"]), 2),
    ):
        passes.clear()
        await AsOfTQuery().findings_facets(
            cast(Any, None),
            cluster_id="c",
            t=datetime(2026, 1, 1, tzinfo=UTC),
            filters=filters,
            fields=["ptype", "severity"],  # ptype is the one freed facet recorded at T
        )
        assert len(passes) == expected, filters
