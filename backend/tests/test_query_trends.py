"""M6 slice 3 — trends (FR-5/FR-12): the pure DSL builders.

THE pin (task B, #139): committed scans are counted via `cardinality(commit_key)` — NEVER raw
doc counts or sums over scan-event docs. A retry straddling a rollover leaves byte-identical
sibling docs (same `commit_key`) in two backing indices; raw counts would double them
(accepted-in-storage, deduped-at-read — tests/test_rollover_idempotency.py owns the storage
side, this owns the read side). Series are split by scanner (per-scanner is sacred); the time
axis is the SERVER-stamped `ingested_at` (client `@timestamp` is display-only and gameable);
`size:0` — counts come from aggregations only.
"""

from datetime import UTC, datetime, timedelta

import pytest

from backend.query.search import SearchFilters, build_search_body
from backend.query.trends import (
    build_findings_trend_body,
    build_ingest_failures_trend_body,
    build_new_findings_trend_body,
    build_scans_trend_body,
)


def _gte(days: int) -> str:
    """The absolute window floor — the builders never emit `now`-date-math (the createWeight
    flake, #271/#278 CI); expected == the same day-floored UTC computation the code does."""
    return (datetime.now(UTC).date() - timedelta(days=days)).isoformat()


def test_scans_trend_counts_committed_scans_by_cardinality_never_docs() -> None:
    body = build_scans_trend_body(days=30)
    assert body["size"] == 0
    by_scanner = body["aggs"]["by_scanner"]
    assert by_scanner["terms"]["field"] == "scanner"  # per-scanner is sacred
    timeline = by_scanner["aggs"]["timeline"]
    dh = timeline["date_histogram"]
    assert dh["field"] == "ingested_at"  # server-stamped — never the client's @timestamp
    assert dh["calendar_interval"] == "day"
    assert dh["min_doc_count"] == 0  # continuous axis — quiet days are real data points
    # THE dedup rule (task B, #139): cardinality(commit_key), never a raw doc count
    assert timeline["aggs"]["scans"] == {"cardinality": {"field": "commit_key"}}
    # the window is a query filter, not a client-side trim
    assert body["query"]["bool"]["filter"] == [{"range": {"ingested_at": {"gte": _gte(30)}}}]


def test_scans_trend_days_is_bounded() -> None:
    with pytest.raises(ValueError):
        build_scans_trend_body(days=0)
    with pytest.raises(ValueError):
        build_scans_trend_body(days=366)


def test_scans_trend_hourly_interval_for_short_ranges() -> None:
    """Sub-day scanner cadences (every 4h) are invisible in daily bars — the lens asks for
    hourly buckets on short ranges (audit 343). The vocabulary is closed."""
    body = build_scans_trend_body(days=1, interval="hour")
    dh = body["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"]
    assert dh["calendar_interval"] == "hour"
    with pytest.raises(ValueError):
        build_scans_trend_body(days=1, interval="minute")


def test_findings_trend_builds_new_and_resolved_series_per_scanner() -> None:
    body = build_findings_trend_body(days=30)
    assert body["size"] == 0
    assert "query" not in body or body.get("query") is None or "bool" in body["query"]

    new = body["aggs"]["new"]
    assert new["filter"] == {"range": {"first_seen_at": {"gte": _gte(30)}}}
    new_tl = new["aggs"]["by_key"]["aggs"]["timeline"]["date_histogram"]
    assert new_tl["field"] == "first_seen_at"

    resolved = body["aggs"]["resolved"]
    assert resolved["filter"] == {"range": {"resolved_at": {"gte": _gte(30)}}}
    res_tl = resolved["aggs"]["by_key"]["aggs"]["timeline"]["date_histogram"]
    assert res_tl["field"] == "resolved_at"

    # "new" must count finding ROWS regardless of current presence — a finding that appeared
    # and was tombstoned inside the window still counts as new that day (no present filter)
    import json

    assert '"present"' not in json.dumps(body)


def test_findings_trend_severity_split_buckets_on_the_server_derived_canonical() -> None:
    # M9c 1b: the severity lens — terms on severity_canonical (the D16 server-derived key,
    # never the verbatim scanner word), six buckets, same timeline shape
    body = build_findings_trend_body(days=30, split="severity")
    for series in ("new", "resolved"):
        terms = body["aggs"][series]["aggs"]["by_key"]["terms"]
        assert terms["field"] == "severity_canonical"
        assert terms["size"] == 6
    # default split stays per-scanner and keeps the by_key agg name (one response shaper)
    default = build_findings_trend_body(days=30)
    assert default["aggs"]["new"]["aggs"]["by_key"]["terms"]["field"] == "scanner"


def test_findings_trend_scanner_scope_is_a_query_filter() -> None:
    # scoping the severity split to one scanner filters at the query — never client math
    body = build_findings_trend_body(days=30, split="severity", scanner="trivy")
    assert {"term": {"scanner": "trivy"}} in body["query"]["bool"]["filter"]
    unscoped = build_findings_trend_body(days=30)
    assert "query" not in unscoped or not any(
        "scanner" in str(f) for f in unscoped.get("query", {}).get("bool", {}).get("filter", [])
    )


def test_ingest_failures_trend_counts_refused_pushes_per_scanner_per_day() -> None:
    """Issue 575: the strip under Scan ingest. Every refused push is one doc written once under
    its own id, so the doc count IS the refusal count — and it matches the failed-ingests
    table's total for the same window."""
    body = build_ingest_failures_trend_body(days=30)
    assert body["size"] == 0
    by_scanner = body["aggs"]["by_scanner"]
    assert by_scanner["terms"]["field"] == "scanner"  # one series per scanner, never merged
    timeline = by_scanner["aggs"]["timeline"]
    assert timeline["date_histogram"]["field"] == "@timestamp"  # stamped by the server here
    assert timeline["date_histogram"]["min_doc_count"] == 0
    assert "aggs" not in timeline  # a plain doc count, no sub-aggregation
    assert body["query"]["bool"]["filter"] == [{"range": {"@timestamp": {"gte": _gte(30)}}}]


@pytest.mark.parametrize("interval", ["day", "hour"])
def test_ingest_failures_trend_shares_the_scan_ingest_axis(interval: str) -> None:
    """Stacked under Scan ingest, a day must line up vertically across both strips: the same
    bounds and bucket size for the same window, live or rewound."""
    t = datetime(2026, 9, 20, 15, 30, tzinfo=UTC)
    for anchor in (None, t):
        fails = build_ingest_failures_trend_body(days=2, anchor=anchor, interval=interval)
        scans = build_scans_trend_body(days=2, anchor=anchor, interval=interval)
        f_dh = fails["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"]
        s_dh = scans["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"]
        assert {k: v for k, v in f_dh.items() if k != "field"} == {
            k: v for k, v in s_dh.items() if k != "field"
        }


def test_ingest_failures_trend_anchored_window_ends_at_t() -> None:
    t = datetime(2026, 9, 20, 15, 30, tzinfo=UTC)
    body = build_ingest_failures_trend_body(days=7, anchor=t)
    window = body["query"]["bool"]["filter"][0]["range"]["@timestamp"]
    assert window == {"gte": "2026-09-13", "lte": t.isoformat()}  # later refusals stay out
    with pytest.raises(ValueError):
        build_ingest_failures_trend_body(days=0)
    with pytest.raises(ValueError):
        build_ingest_failures_trend_body(days=1, interval="minute")


# issue 1292: the New findings strip under Scan ingest. It counts the findings first seen in each
# bucket, by severity, under the filters of the table.
NOW = datetime(2026, 9, 20, 15, 30, tzinfo=UTC)


def test_new_findings_trend_counts_first_seen_by_canonical_severity() -> None:
    body = build_new_findings_trend_body(SearchFilters(), days=7, now=NOW)
    assert body["size"] == 0
    by_severity = body["aggs"]["by_severity"]
    # the server-derived canonical key (D46), never the verbatim scanner word; six buckets
    assert by_severity["terms"] == {"field": "severity_canonical", "size": 6}
    dh = by_severity["aggs"]["timeline"]["date_histogram"]
    assert dh["field"] == "first_seen_at"
    assert dh["calendar_interval"] == "day"
    assert dh["min_doc_count"] == 0
    assert "aggs" not in by_severity["aggs"]["timeline"]  # a doc count: each scanner's row counts
    # the window starts on the day floor and stops at now: a scanner clock ahead of the server
    # gives a first_seen_at after now, and that finding is not new yet
    window = {"range": {"first_seen_at": {"gte": "2026-09-13", "lte": NOW.isoformat()}}}
    assert window in body["query"]["bool"]["filter"]


@pytest.mark.parametrize("interval", ["day", "hour"])
def test_new_findings_trend_shares_the_scan_ingest_axis(interval: str) -> None:
    """The strip sits under Scan ingest: the same bounds and bucket size for the same window."""
    new = build_new_findings_trend_body(SearchFilters(), days=2, interval=interval, now=NOW)
    scans = build_scans_trend_body(days=2, anchor=NOW, interval=interval)
    n_dh = new["aggs"]["by_severity"]["aggs"]["timeline"]["date_histogram"]
    s_dh = scans["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"]
    assert {k: v for k, v in n_dh.items() if k != "field"} == {
        k: v for k, v in s_dh.items() if k != "field"
    }


def test_new_findings_trend_takes_the_filter_context_of_the_grid() -> None:
    filters = SearchFilters(
        scanner="grype", severity=["critical"], namespace=["shop"], tag=["1.4.1"], q="ssl"
    )
    body = build_new_findings_trend_body(filters, days=7, now=NOW)
    grid = build_search_body(filters, size=0)["query"]["bool"]
    query = body["query"]["bool"]
    assert query["filter"][: len(grid["filter"])] == grid["filter"]  # the grid filters, in order
    assert query["must"] == grid["must"]  # the search
    assert {"term": {"present": True}} in query["filter"]  # D2 A: present from the filters
    gone = build_new_findings_trend_body(SearchFilters(present=False), days=7, now=NOW)
    assert {"term": {"present": False}} in gone["query"]["bool"]["filter"]
    excluded = build_new_findings_trend_body(SearchFilters(exclude_tag=["latest"]), days=7, now=NOW)
    assert excluded["query"]["bool"]["must_not"] == [{"terms": {"tag": ["latest"]}}]


def test_new_findings_trend_overdue_needs_the_sla_cutoffs() -> None:
    with pytest.raises(ValueError, match="sla_cutoffs"):
        build_new_findings_trend_body(SearchFilters(overdue=True), days=7, now=NOW)
    cutoffs: dict[str, str] = {
        k: "2026-09-01T00:00:00+00:00" for k in ("kev", "critical", "high", "medium", "low")
    }
    body = build_new_findings_trend_body(
        SearchFilters(overdue=True), days=7, now=NOW, sla_cutoffs=cutoffs
    )
    grid = build_search_body(SearchFilters(overdue=True), size=0, sla_cutoffs=cutoffs)
    assert grid["query"]["bool"]["filter"][-1] in body["query"]["bool"]["filter"]


def test_new_findings_trend_bounds() -> None:
    with pytest.raises(ValueError):
        build_new_findings_trend_body(SearchFilters(), days=0, now=NOW)
    with pytest.raises(ValueError):
        build_new_findings_trend_body(SearchFilters(), days=1, interval="minute", now=NOW)
