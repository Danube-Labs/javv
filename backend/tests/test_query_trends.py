"""M6 slice 3 — trends (FR-5/FR-12): the pure DSL builders.

THE pin (task B, #139): committed scans are counted via `cardinality(commit_key)` — NEVER raw
doc counts or sums over scan-event docs. A retry straddling a rollover leaves byte-identical
sibling docs (same `commit_key`) in two backing indices; raw counts would double them
(accepted-in-storage, deduped-at-read — tests/test_rollover_idempotency.py owns the storage
side, this owns the read side). Series are split by scanner (per-scanner is sacred); the time
axis is the SERVER-stamped `ingested_at` (client `@timestamp` is display-only and gameable);
`size:0` — counts come from aggregations only.
"""

from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from backend.query.search import SearchFilters, build_search_body, has_tag_clause
from backend.query.trends import (
    EXACT_MAX_SECONDS,
    EXACT_MIN_SECONDS,
    ScanFilters,
    build_findings_trend_body,
    build_ingest_failures_trend_body,
    build_new_findings_trend_body,
    build_scans_trend_body,
    range_bounds,
)


def _gte(days: int) -> str:
    """The absolute window floor — the builders never emit `now`-date-math (the createWeight
    flake, #271/#278 CI); expected == the same day-floored UTC computation the code does."""
    return (datetime.now(UTC).date() - timedelta(days=days)).isoformat()


# a fixed end for a window of 30 whole days: the day floor 30 days back, up to the end itself
END = datetime(2026, 11, 20, 11, 30, tzinfo=UTC)
DAYS_30 = {"gte": "2026-10-21", "lte": "2026-11-20T11:30:00.000+00:00"}


def _ms(t: datetime) -> str:
    """A bound as the builders write it: always with milliseconds (see trends._ms)."""
    return t.isoformat(timespec="milliseconds")


def _assert_now(lte: str) -> None:
    """A live read stops at now (issue 1291, ruling 3): the server's clock at the build."""
    assert abs(datetime.fromisoformat(lte) - datetime.now(UTC)) < timedelta(seconds=30)


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
    # the window is a query filter, not a client-side trim; it stops at now (issue 1291)
    [window] = body["query"]["bool"]["filter"]
    assert window["range"]["ingested_at"]["gte"] == _gte(30)
    _assert_now(window["range"]["ingested_at"]["lte"])


def test_scans_trend_puts_each_filter_on_the_field_of_the_scan_record() -> None:
    """Issue 1293: the filters of /findings that a scan record holds, on its fields. The names
    of the fields are those of a finding: `namespace` reads the array `namespaces`."""
    body = build_scans_trend_body(
        days=30,
        anchor=END,
        filters=ScanFilters(
            namespace=["shop"],
            exclude_image_repo=["ops/tool"],
            tag=["1.4.2"],
            image_digest="sha256:d1",
            scanner="grype",
        ),
    )
    q = body["query"]["bool"]
    assert q["filter"] == [
        {"range": {"ingested_at": DAYS_30}},
        {"terms": {"namespaces": ["shop"]}},
        {"terms": {"tag": ["1.4.2"]}},
        {"term": {"image_digest": "sha256:d1"}},
        {"term": {"scanner": "grype"}},
    ]
    assert q["must_not"] == [{"terms": {"image_repo": ["ops/tool"]}}]


def test_scans_trend_exclude_sides_and_no_tag() -> None:
    q = build_scans_trend_body(
        days=7,
        filters=ScanFilters(
            exclude_namespace=["kube-system"],
            image_repo=["shop/app"],
            exclude_tag=["latest"],
            exclude_scanner="trivy",
            untagged=True,
        ),
    )["query"]["bool"]
    assert q["filter"][1:] == [{"terms": {"image_repo": ["shop/app"]}}]
    assert q["must_not"] == [
        {"terms": {"namespaces": ["kube-system"]}},
        {"terms": {"tag": ["latest"]}},
        {"term": {"scanner": "trivy"}},
        has_tag_clause(),  # "no tag" is a missing tag or "", as for the findings
    ]
    has_tag = build_scans_trend_body(days=7, filters=ScanFilters(untagged=False))["query"]["bool"]
    assert has_tag["filter"][1:] == [has_tag_clause()] and "must_not" not in has_tag


def test_scans_trend_with_no_filter_keeps_its_body_and_refuses_a_pair() -> None:
    q = build_scans_trend_body(days=30, anchor=END, filters=ScanFilters())["query"]["bool"]
    assert q == {"filter": [{"range": {"ingested_at": DAYS_30}}]}  # no must_not
    with pytest.raises(ValueError, match="tag and untagged"):
        build_scans_trend_body(days=30, filters=ScanFilters(tag=["1"], untagged=True))
    with pytest.raises(ValueError, match="namespace and exclude_namespace"):
        build_scans_trend_body(
            days=30, filters=ScanFilters(namespace=["a"], exclude_namespace=["b"])
        )


def test_scan_filters_have_the_names_of_the_findings_filters() -> None:
    """The pair check (`conflicting_filter_pair`) reads the names of SearchFilters: a field of
    ScanFilters with another name would skip it, and a refused pair would filter instead."""
    assert {f.name for f in fields(ScanFilters)} <= set(SearchFilters.__dataclass_fields__)


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
    body = build_findings_trend_body(days=30, now=END)
    assert body["size"] == 0
    assert "query" not in body or body.get("query") is None or "bool" in body["query"]

    new = body["aggs"]["new"]
    assert new["filter"] == {"range": {"first_seen_at": DAYS_30}}
    new_tl = new["aggs"]["by_key"]["aggs"]["timeline"]["date_histogram"]
    assert new_tl["field"] == "first_seen_at"

    resolved = body["aggs"]["resolved"]
    assert resolved["filter"] == {"range": {"resolved_at": DAYS_30}}
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
    [window] = body["query"]["bool"]["filter"]
    assert window["range"]["@timestamp"]["gte"] == _gte(30)
    _assert_now(window["range"]["@timestamp"]["lte"])


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
    assert window == {
        "gte": "2026-09-13",
        "lte": t.isoformat(timespec="milliseconds"),
    }  # later refusals stay out
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
    window = {"range": {"first_seen_at": {"gte": "2026-09-13", "lte": _ms(NOW)}}}
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


# issue 1291: a range of 2 days or less starts at its exact time (ruling 1). The backend takes the
# end from its own clock (ruling 2), and each live read stops at its end (ruling 3). END is above.


@pytest.mark.parametrize(
    ("end", "seconds", "gte"),
    [
        (END, 3600, "2026-11-20T10:30:00.000+00:00"),  # "Last 1 hour"
        (datetime(2026, 11, 20, 11, 1, tzinfo=UTC), 3600, "2026-11-20T10:01:00.000+00:00"),
        (datetime(2026, 12, 1, 0, 30, tzinfo=UTC), 3600, "2026-11-30T23:30:00.000+00:00"),
        (END, EXACT_MAX_SECONDS, "2026-11-18T11:30:00.000+00:00"),  # exactly 2 days
        (END, EXACT_MIN_SECONDS, "2026-11-20T11:29:00.000+00:00"),
    ],
)
def test_range_bounds_is_the_end_minus_the_length(end: datetime, seconds: int, gte: str) -> None:
    """Across midnight and the end of a month too: no day floor."""
    assert range_bounds(seconds, end) == (gte, _ms(end))


def test_range_bounds_cuts_to_the_millisecond_and_never_starts_after_its_end() -> None:
    end = datetime(2026, 11, 20, 10, 59, 59, 999_999, tzinfo=UTC)
    gte, lte = range_bounds(3600, end)
    assert lte == "2026-11-20T10:59:59.999+00:00"  # a date field holds milliseconds
    assert gte == "2026-11-20T09:59:59.999+00:00"
    # an lte with no milliseconds would count up to .999 of its second: always write them
    assert range_bounds(3600, END) == (
        "2026-11-20T10:30:00.000+00:00",
        "2026-11-20T11:30:00.000+00:00",
    )
    live_gte, live_lte = range_bounds(EXACT_MIN_SECONDS)  # unanchored: the server's clock
    assert datetime.fromisoformat(live_gte) < datetime.fromisoformat(live_lte)
    _assert_now(live_lte)


@pytest.mark.parametrize("seconds", [0, -1, EXACT_MIN_SECONDS - 1, EXACT_MAX_SECONDS + 1])
def test_range_bounds_refuses_a_length_outside_its_limits(seconds: int) -> None:
    with pytest.raises(ValueError, match="window_seconds"):
        range_bounds(seconds, END)


def test_scans_trend_with_an_exact_window_filters_and_draws_that_window() -> None:
    """The first bar starts on the hour, before the start: the filter makes it partial."""
    body = build_scans_trend_body(window_seconds=3600, anchor=END, interval="hour")
    [window] = body["query"]["bool"]["filter"]
    exact = {"gte": "2026-11-20T10:30:00.000+00:00", "lte": _ms(END)}
    assert window == {"range": {"ingested_at": exact}}
    dh = body["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"]
    assert dh["calendar_interval"] == "hour"  # the bars stay on the UTC hour (ruling 4)
    assert dh["extended_bounds"] == {"min": exact["gte"], "max": exact["lte"]}


def test_a_trend_window_takes_days_or_window_seconds_never_both() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_scans_trend_body(days=1, window_seconds=3600)
    with pytest.raises(ValueError, match="days or window_seconds"):
        build_ingest_failures_trend_body()
    with pytest.raises(ValueError, match="window_seconds"):
        build_new_findings_trend_body(
            SearchFilters(), window_seconds=EXACT_MAX_SECONDS + 1, now=END
        )


@pytest.mark.parametrize("interval", ["day", "hour"])
def test_the_three_strips_share_an_exact_axis(interval: str) -> None:
    scans = build_scans_trend_body(window_seconds=7200, anchor=END, interval=interval)
    fails = build_ingest_failures_trend_body(window_seconds=7200, anchor=END, interval=interval)
    new = build_new_findings_trend_body(
        SearchFilters(), window_seconds=7200, interval=interval, now=END
    )
    axes = [
        scans["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"],
        fails["aggs"]["by_scanner"]["aggs"]["timeline"]["date_histogram"],
        new["aggs"]["by_severity"]["aggs"]["timeline"]["date_histogram"],
    ]
    assert len({repr({k: v for k, v in a.items() if k != "field"}) for a in axes}) == 1
    window = {"gte": "2026-11-20T09:30:00.000+00:00", "lte": _ms(END)}
    assert {"range": {"first_seen_at": window}} in new["query"]["bool"]["filter"]
    assert fails["query"]["bool"]["filter"] == [{"range": {"@timestamp": window}}]


def test_each_live_trend_read_stops_at_now() -> None:
    """Ruling 3: `first_seen_at` and `resolved_at` carry the scanner's clock. A clock that runs
    ahead must draw no bar after now, on the findings trend too, which has no exact window."""
    findings = build_findings_trend_body(days=30, now=END)
    for series in ("new", "resolved"):
        field = "first_seen_at" if series == "new" else "resolved_at"
        window = findings["aggs"][series]["filter"]["range"][field]
        assert window == DAYS_30
    live = build_findings_trend_body(days=30)["aggs"]["new"]["filter"]["range"]["first_seen_at"]
    _assert_now(live["lte"])
    scans = build_scans_trend_body(days=1, interval="hour")["query"]["bool"]["filter"][0]
    _assert_now(scans["range"]["ingested_at"]["lte"])
