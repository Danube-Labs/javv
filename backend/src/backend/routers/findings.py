"""The findings read surface (M6 slices 1–2, FR-12): grid, facets, groups.

Read = any authenticated principal (MVP tenant model, D38/H9); `cluster_id` is REQUIRED and
forced into every query by the tenant read path — never a UI-only filter (SEC-4). One shared
filter-context dependency drives all three endpoints, so the facet counts always describe the
grid the user is looking at.

- `GET /api/v1/findings` — the grid: opaque-cursor PIT paging (`query/search.py`), rows
  decorated with the M5d overdue verdict. The D21 group clock needs the EARLIEST
  `first_seen_at` across each row's `(cve_id, image_digest)` group, so sibling rows are fetched
  (tenant-filtered) and fed to `compute_overdue` alongside the page — a page filter (e.g. one
  scanner) must never hide the clock-setting sibling.
- `GET /api/v1/findings/facets` — bounded-vocabulary counts (`query/aggs.py`), every bucket
  split `by_scanner` (per-scanner is sacred).
- `GET /api/v1/findings/groups` — high-cardinality grouping via composite `after_key` behind
  the same opaque-cursor contract; every bucket reachable, none silently capped.

`as_of`: absent/`now`/future reads materialized current-state — NEVER the reconstruction
path; a past T dispatches through `query/as_of.py` to M8b's registered `as_of_t` reader
(501 at the seam until M8b lands — D28, these routes never reconstruct).
"""

from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import ConnectionTimeout

from backend.auth.principal import Principal, get_current_principal
from backend.core.identifiers import ClusterId
from backend.core.metrics import OS_REQUEST_ERRORS, SLA_CLOCK_MISSING
from backend.query import pit_guard
from backend.query.aggs import (
    build_composite_body,
    build_facets_body,
    build_top_components_body,
    cap_value_search,
    decode_after,
    encode_after,
    facet_aggregation,
)
from backend.query.as_of import AsOfTReader, AsOfTUnavailable, as_of_t_reader, parse_as_of
from backend.query.search import (
    MAX_FILTER_VALUES,
    CursorExpired,
    FilterValue64,
    FilterValue128,
    FilterValue256,
    FilterValue512,
    SearchFilters,
    conflicting_filter_pair,
    cursor_pit_id,
    run_search,
)
from backend.sla.overdue import compute_overdue, overdue_cutoffs
from backend.sla.policy import read_sla_policy
from backend.tenancy.read_path import tenant_search

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

# several values for one filter (issue 949): `?namespace=a&namespace=b`. `Query(max_length)` on a
# list caps the NUMBER of values; each value keeps its own length cap on the item type.
_Values64 = Annotated[list[FilterValue64] | None, Query(max_length=MAX_FILTER_VALUES)]
_Values128 = Annotated[list[FilterValue128] | None, Query(max_length=MAX_FILTER_VALUES)]
_Values256 = Annotated[list[FilterValue256] | None, Query(max_length=MAX_FILTER_VALUES)]
_Values512 = Annotated[list[FilterValue512] | None, Query(max_length=MAX_FILTER_VALUES)]

_GROUP_CLOCK_PAGE = 1_000  # composite agg page for the exact min(first_seen_at) per (cve, digest)


def _resolve_as_of(
    as_of: Annotated[str | None, Query(max_length=64)] = None,
) -> datetime | None:
    """The D28 seam, uniform on every read: None = current state; a datetime = the route
    delegates to M8b's registered reader (`_reader_or_501`) — never reconstructs itself."""
    try:
        return parse_as_of(as_of)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _reader_or_501() -> AsOfTReader:
    try:
        return as_of_t_reader()
    except AsOfTUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc


async def _reconstructed(coro: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    """Past-T delegation seam: the reader re-validates inputs and rejects unrecorded filters
    with ValueError — that must cost the caller a 422, never a 500 (audit 343: every past-T
    route call rides through here)."""
    try:
        return await coro
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _filters(
    severity: Annotated[list[str] | None, Query()] = None,
    state: Annotated[list[str] | None, Query()] = None,
    scanner: Annotated[str | None, Query(max_length=32)] = None,
    assignee: _Values128 = None,
    kev: bool | None = None,
    fixable: bool | None = None,
    disagree: bool | None = None,
    cve_id: _Values128 = None,
    image_digest: Annotated[str | None, Query(max_length=128)] = None,
    image_repo: _Values512 = None,
    namespace: _Values256 = None,
    ptype: _Values64 = None,
    package_name: _Values512 = None,
    q: Annotated[str | None, Query(min_length=2, max_length=128)] = None,
    present: bool = True,
    new_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    overdue: bool | None = None,
    unassigned: bool | None = None,
    exclude_severity: Annotated[list[str] | None, Query()] = None,
    exclude_state: Annotated[list[str] | None, Query()] = None,
    exclude_scanner: Annotated[str | None, Query(max_length=32)] = None,
    exclude_assignee: _Values128 = None,
    exclude_image_repo: _Values512 = None,
    exclude_namespace: _Values256 = None,
    exclude_ptype: _Values64 = None,
    exclude_cve_id: _Values128 = None,
    exclude_package_name: _Values512 = None,
) -> SearchFilters:
    filters = SearchFilters(
        severity=severity,
        state=state,
        scanner=scanner,
        assignee=assignee,
        kev=kev,
        fixable=fixable,
        disagree=disagree,
        cve_id=cve_id,
        image_digest=image_digest,
        image_repo=image_repo,
        namespace=namespace,
        ptype=ptype,
        package_name=package_name,
        q=q,
        present=present,
        new_within_days=new_within_days,
        overdue=overdue,
        unassigned=unassigned,
        exclude_severity=exclude_severity,
        exclude_state=exclude_state,
        exclude_scanner=exclude_scanner,
        exclude_assignee=exclude_assignee,
        exclude_image_repo=exclude_image_repo,
        exclude_namespace=exclude_namespace,
        exclude_ptype=exclude_ptype,
        exclude_cve_id=exclude_cve_id,
        exclude_package_name=exclude_package_name,
    )
    # a refused pair is a 422 here, so the builder's ValueError (kept as defense for direct
    # constructors like report_drain) never costs a 500
    if (message := conflicting_filter_pair(vars(filters))) is not None:
        raise HTTPException(422, message)
    return filters


Filters = Annotated[SearchFilters, Depends(_filters)]
AsOf = Annotated[datetime | None, Depends(_resolve_as_of)]


async def _sla_cutoffs(
    client: Any, filters: SearchFilters, *, facet: bool = False
) -> dict[str, str] | None:
    """LIVE-policy cutoffs for an `overdue` lens (issue 363) — None when nothing needs them.
    facets/groups resolve here (facets also when the overdue FACET is requested — the rail
    count needs the clause even with the filter off); the grid's `run_search` resolves (and
    cursor-freezes) its own."""
    if filters.overdue is None and not facet:
        return None
    return overdue_cutoffs(await read_sla_policy(client), now=datetime.now(UTC))


async def _decorate_overdue(client: Any, cluster_id: str, page: list[dict[str, Any]]) -> None:
    if not page:
        return
    # The D21 group clock = the EARLIEST first_seen_at across each row's (cve_id, image_digest)
    # group, including siblings OFF this page (a scanner the page filter hid). Since issue 363 it
    # is MATERIALIZED on every doc (`sla_clock_at`, owned by services.sla_clock), so the page
    # already carries it — no sibling fetch. Rows missing it (pre-backfill store, or a recompute
    # the commit crashed out of) fall back to the exact per-pair aggregation and are surfaced
    # loudly: silent under-reporting of overdue is the exact bug this field exists to kill.
    clocks: dict[tuple[str, str], str] = {}
    missing: set[tuple[str, str]] = set()
    for d in page:
        pair = (d["cve_id"], d["image_digest"])
        clk = d.get("sla_clock_at")
        if clk is None:
            missing.add(pair)
        elif pair not in clocks or clk < clocks[pair]:
            clocks[pair] = clk
    if missing:
        SLA_CLOCK_MISSING.inc()
        log.warning(
            "findings rows missing sla_clock_at — agg fallback (rebuild-state backfills)",
            cluster_id=cluster_id,
            pairs=len(missing),
        )
        clocks |= await _agg_group_clocks(client, cluster_id, sorted(missing))

    # feed the true per-group min as a synthetic clock row (compute_overdue derives `earliest`
    # across the rows it's given; page rows stay authoritative for their own fields — D21)
    clock_rows: list[dict[str, Any]] = [
        {
            "finding_key": f"__clock__:{c}:{d}",
            "cve_id": c,
            "image_digest": d,
            "first_seen_at": seen,
            "severity": "critical",  # ignored — a synthetic row's own verdict is never read
            "state": "open",
            "kev": False,
        }
        for (c, d), seen in clocks.items()
    ]
    verdicts = compute_overdue(
        clock_rows + page, policy=await read_sla_policy(client), now=datetime.now(UTC)
    )
    for doc in page:
        v = verdicts[doc["finding_key"]]
        doc["overdue"] = v.overdue
        doc["due_at"] = v.due_at


async def _agg_group_clocks(
    client: Any, cluster_id: str, pairs: list[tuple[str, str]]
) -> dict[tuple[str, str], str]:
    """The pre-363 clock fetch, kept as the missing-field fallback: an EXACT min per pair via a
    bounded composite aggregation over just the given pairs — never a truncatable doc fetch of
    the cve×digest cross-product, which at scale could drop the earliest holder and silently
    under-report overdue (audit A-M4)."""
    should = [
        {"bool": {"filter": [{"term": {"cve_id": c}}, {"term": {"image_digest": d}}]}}
        for c, d in pairs
    ]
    clocks: dict[tuple[str, str], str] = {}
    after: dict[str, str] | None = None
    while True:  # composite paging is bounded and never silently caps (unlike a terms agg)
        composite: dict[str, Any] = {
            "size": _GROUP_CLOCK_PAGE,
            "sources": [
                {"cve_id": {"terms": {"field": "cve_id"}}},
                {"image_digest": {"terms": {"field": "image_digest"}}},
            ],
        }
        if after is not None:
            composite["after"] = after
        resp = await tenant_search(
            client,
            index="findings",
            cluster_id=cluster_id,
            body={
                "size": 0,
                "query": {
                    "bool": {
                        "filter": [{"term": {"present": True}}],
                        "should": should,
                        "minimum_should_match": 1,
                    }
                },
                "aggs": {
                    "groups": {
                        "composite": composite,
                        "aggregations": {
                            "clock": {
                                "min": {
                                    "field": "first_seen_at",
                                    "format": "strict_date_optional_time",
                                }
                            }
                        },
                    }
                },
            },
        )
        groups = resp["aggregations"]["groups"]
        buckets = groups["buckets"]
        for b in buckets:
            seen = b["clock"].get("value_as_string")
            if seen is not None:
                clocks[(b["key"]["cve_id"], b["key"]["image_digest"])] = seen
        after = groups.get("after_key")
        if after is None or not buckets:
            break
    return clocks


async def _decorate_images_affected(
    client: Any, cluster_id: str, page: list[dict[str, Any]]
) -> None:
    """Stamp `images_affected` (distinct image_digest count per CVE, cluster+present-scoped) on
    each page row — the B-4 grid column. One bounded terms-filtered agg over just the page's
    CVEs (≤ page size, exact via a matching terms size + per-bucket cardinality); server-side
    everything, never a client count."""
    if not page:
        return
    cves = sorted({d["cve_id"] for d in page})
    resp = await tenant_search(
        client,
        index="findings",
        cluster_id=cluster_id,
        body={
            "size": 0,
            "query": {
                "bool": {"filter": [{"term": {"present": True}}, {"terms": {"cve_id": cves}}]}
            },
            "aggs": {
                "per_cve": {
                    "terms": {"field": "cve_id", "size": len(cves)},
                    "aggregations": {"images": {"cardinality": {"field": "image_digest"}}},
                }
            },
        },
    )
    counts = {b["key"]: b["images"]["value"] for b in resp["aggregations"]["per_cve"]["buckets"]}
    for doc in page:
        doc["images_affected"] = counts.get(doc["cve_id"], 0)


def _bucket(b: dict[str, Any]) -> dict[str, Any]:
    """One agg bucket → the wire shape. Bool keys keep their readable form ("true"/"false")."""
    return {
        "key": b.get("key_as_string", b["key"]),
        "count": b["doc_count"],
        "by_scanner": {s["key"]: s["doc_count"] for s in b["by_scanner"]["buckets"]},
    }


@router.get("")
async def search_findings(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
    sort: Annotated[str, Query(max_length=32)] = "severity_rank",
    order: Annotated[str, Query(max_length=4)] = "desc",
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    keep_open: bool = False,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:  # past T → M8b's reconstruction, never this route's query (D28)
        return await _reconstructed(
            _reader_or_501().findings_page(
                client,
                cluster_id=cluster_id,
                t=as_of_t,
                filters=filters,
                sort=sort,
                order=order,
                size=size,
                cursor=cursor,
            )
        )
    # no read-side refresh (audit A-m2/#191): reads observe what's committed; triage writes with
    # refresh=wait_for and ingest refreshes post-merge, so a forced per-read Lucene refresh on the
    # hottest index was belt-and-suspenders that any cheap poll could turn into cluster work.
    slot: pit_guard.Slot | None = None  # a cursor-less page opens a fresh PIT and takes a slot
    if cursor is None:
        try:
            slot = pit_guard.acquire(principal.user_id)  # A-m12/#189: bound concurrent PITs
        except pit_guard.PitCapExceeded as exc:
            log.warning("PIT cap reached for principal", format="findings_page")
            raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc
    try:
        out = await run_search(
            client,
            cluster_id=cluster_id,
            filters=filters,
            size=size,
            sort=sort,
            order=order,
            cursor=cursor,
            keep_open=keep_open,
        )
    except CursorExpired as exc:  # A-m1: idled past keep_alive → 410 Gone, restart the walk
        pit_guard.release(principal.user_id, slot)
        if cursor is not None:  # the walk's PIT is gone, so its slot is too
            pit_guard.release_pit(principal.user_id, cursor_pit_id(cursor))
        raise HTTPException(410, str(exc)) from exc
    except ValueError as exc:  # tampered/undecodable cursor or bad sort/order — 422, not a 500
        pit_guard.release(principal.user_id, slot)  # nothing usable to page — free the slot
        raise HTTPException(422, str(exc)) from exc
    except (OSConnectionError, ConnectionTimeout) as exc:  # A-m1: cluster down/slow → 503, not 500
        pit_guard.release(principal.user_id, slot)
        kind = "timeout" if isinstance(exc, ConnectionTimeout) else "conn"
        OS_REQUEST_ERRORS.labels(kind).inc()  # M-2 (#220)
        raise HTTPException(503, "search backend unavailable — retry") from exc
    except BaseException:
        pit_guard.release(principal.user_id, slot)
        raise
    walk = out["next_cursor"] or cursor
    pit_guard.settle(
        principal.user_id,
        slot,
        cursor_pit_id(walk) if walk else None,
        # the final page closed its PIT (D38), unless a continuation asked to keep it
        ended=out["next_cursor"] is None and not (keep_open and cursor is not None),
    )
    await _decorate_overdue(client, cluster_id, out["data"])
    await _decorate_images_affected(client, cluster_id, out["data"])
    return out


@router.get("/facets")
async def facet_findings(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
    fields: Annotated[list[str] | None, Query()] = None,
    all_filters: Annotated[bool, Query()] = False,
    # the same limits as `q`: a search starts at 2 letters
    contains: Annotated[str | None, Query(min_length=2, max_length=128)] = None,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:
        return await _reconstructed(
            _reader_or_501().findings_facets(
                client,
                cluster_id=cluster_id,
                t=as_of_t,
                filters=filters,
                fields=fields,
                all_filters=all_filters,
                contains=contains,
            )
        )
    # no read-side refresh (audit A-m2/#191) — see search_findings
    wants_overdue = fields is None or "overdue" in fields
    try:
        body = build_facets_body(
            filters,
            fields=fields,
            sla_cutoffs=await _sla_cutoffs(client, filters, facet=wants_overdue),
            all_filters=all_filters,
            contains=contains,
        )
    except ValueError as exc:  # non-whitelisted facet field, or contains on a wrong field
        raise HTTPException(422, str(exc)) from exc
    resp = await tenant_search(client, index="findings", cluster_id=cluster_id, body=body)
    if contains is not None:
        (field, raw), *_ = resp["aggregations"].items()
        shown, more = cap_value_search(facet_aggregation(raw)["buckets"])
        return {"facets": {field: [_bucket(b) for b in shown]}, "more": more}
    return {
        "facets": {
            # `overdue` is a filter agg (one count, no buckets) — shaped as a true-bucket so
            # the wire looks exactly like the boolean terms facets the rail already reads
            field: (
                [_bucket(b) for b in agg["buckets"]]
                if "buckets" in agg
                else [_bucket({"key": "true", "doc_count": agg["doc_count"], **agg})]
            )
            for field, agg in (
                (name, facet_aggregation(raw)) for name, raw in resp["aggregations"].items()
            )
        }
    }


@router.get("/top-components")
async def top_components_findings(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
) -> dict[str, Any]:
    """The Overview Top-components card: top packages by finding rows, each with a per-scanner
    unique-CVE count. A now-only read (same rule as the severity-trend split — the card gates at
    a rewound T); "all scanners" is the SUM of per-scanner uniques, never a cross-scanner
    distinct count."""
    if as_of_t is not None:
        raise HTTPException(422, "top-components is a now-only read")
    client = cast(Any, request.app.state.opensearch)
    resp = await tenant_search(
        client, index="findings", cluster_id=cluster_id, body=build_top_components_body(filters)
    )
    return {
        "components": [
            {
                "package_name": b["key"],
                "count": b["doc_count"],
                "unique_cves_by_scanner": {
                    s["key"]: s["unique_cves"]["value"] for s in b["by_scanner"]["buckets"]
                },
            }
            for b in resp["aggregations"]["components"]["buckets"]
        ]
    }


@router.get("/groups")
async def group_findings(
    request: Request,
    principal: Authenticated,
    cluster_id: ClusterId,
    filters: Filters,
    as_of_t: AsOf,
    by: Annotated[str, Query(max_length=32)],
    size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    if as_of_t is not None:
        return await _reconstructed(
            _reader_or_501().findings_groups(
                client,
                cluster_id=cluster_id,
                t=as_of_t,
                filters=filters,
                by=by,
                size=size,
                cursor=cursor,
            )
        )
    # no read-side refresh (audit A-m2/#191) — see search_findings
    try:
        after = decode_after(cursor) if cursor else None
        body = build_composite_body(
            filters,
            by=by,
            size=size,
            after=after,
            sla_cutoffs=await _sla_cutoffs(client, filters),
        )
    except ValueError as exc:  # non-whitelisted dim / unreadable-or-tampered cursor
        raise HTTPException(422, str(exc)) from exc
    resp = await tenant_search(client, index="findings", cluster_id=cluster_id, body=body)
    groups = resp["aggregations"]["groups"]
    data = [
        {
            "key": b["key"]["key"],
            "count": b["doc_count"],
            "by_scanner": {s["key"]: s["doc_count"] for s in b["by_scanner"]["buckets"]},
        }
        for b in groups["buckets"]
    ]
    after_key = groups.get("after_key")
    # a full page + an after_key = more buckets may exist; a short page is definitively the end
    next_cursor = encode_after(after_key) if after_key and len(data) == size else None
    return {"data": data, "next_cursor": next_cursor}
