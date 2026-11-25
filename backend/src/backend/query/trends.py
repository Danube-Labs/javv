"""Trend series (M6 slice 3, FR-5/FR-12) — pure DSL builders over the append logs.

- **Scans** (`javv-scan-events-<cluster_id>-*`): committed scans per day per scanner. THE
  dedup rule (task B, #139): a retry straddling a rollover leaves byte-identical sibling docs
  (same `commit_key`) in two backing indices — accepted in storage, deduped at read via
  `cardinality(commit_key)`. NEVER raw doc counts or sums over scan-event docs. It takes the
  filters of the grid that a scan record also holds (`ScanFilters`, issue 1293).
- **Findings** (`findings`): the FR-5 "new in Nd" series plus its burn-down twin — new
  (`first_seen_at`) vs resolved (`resolved_at`) per day per scanner. No `present` filter: a
  finding that appeared and was tombstoned inside the window still counts as new that day.
- **Ingest failures** (`javv-ingest-failures-<cluster_id>-*`, issue 575): pushes refused after
  the token check, per bucket per scanner, on the scans series' exact axis.
- **New findings** (`findings`, issue 1292): the findings first seen in each bucket, by severity,
  under the filters of the grid, with the bounds and bucket size of the scans series.

A window is whole UTC days (`days`), or exact for a range of 2 days or less (`window_seconds`,
issue 1291): the end minus the length. Each read stops at its end, now or T.

All are `size:0` (server-side everything). The scans, findings and failures series split
`by_scanner` (per-scanner is sacred); the new-findings series splits by severity and counts the
row of each scanner. `ingested_at` and a failure record's `@timestamp` are stamped by the
server. `first_seen_at` and `resolved_at` are not: the ingest and the reconcile copy the scan's
`last_seen_at` (`services/ingest.py`, `services/reconcile.py`), the scanner's clock, so a live
window that must not see the future ends at now. A scan event's `@timestamp` is the client's
too: display-only and gameable (D40: never an ordering key). True
historical severity totals (state at T) are NOT derivable from these logs at read cost — that's
the v1.1 `javv-metrics` rollup; these series are the MVP trend surface.

The tenant filter is forced by the tenant read path at execution; scan-events routing additionally
pins the per-cluster index pattern.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.query.search import SearchFilters

_MAX_DAYS = 365
_BY_SCANNER_TERMS = {"field": "scanner", "size": 4}
# the exact range of issue 1291 (ruling 1): a range of 2 days or less starts at the end minus its
# length; a longer one keeps whole UTC days. Both limits are the API contract (`window_seconds`,
# `new_within_seconds`), not a setting.
EXACT_MIN_SECONDS = 60
EXACT_MAX_SECONDS = 2 * 86_400


def window_bounds(days: int, anchor: datetime | None = None) -> tuple[str, str]:
    """(gte, upper-bound) — ALWAYS absolute ISO dates; unanchored = anchored at now (M8b: a
    trend at T is the SAME aggregation with the window ending at T, D28).

    Never `now`-date-math: OpenSearch intermittently 500s on DateRangeIncludingNowQuery under
    concurrent segment search ("does not implement createWeight" — hit CI on #271 and #278).
    Absolute day-floored UTC bounds are semantically identical to the old `now-{days}d/d` /
    `now/d` pair and never reach the buggy rewrite."""
    if not 1 <= days <= _MAX_DAYS:
        raise ValueError(f"days must be 1..{_MAX_DAYS}")
    day = (anchor or datetime.now(UTC)).date()
    return (day - timedelta(days=days)).isoformat(), day.isoformat()


def range_bounds(window_seconds: int, end: datetime | None = None) -> tuple[str, str]:
    """(gte, lte) for a range of 2 days or less (issue 1291, ruling 1): the end minus the length,
    and the end. The backend takes the end from its own clock (ruling 2), so the start never
    comes after it."""
    if not EXACT_MIN_SECONDS <= window_seconds <= EXACT_MAX_SECONDS:
        raise ValueError(f"window_seconds must be {EXACT_MIN_SECONDS}..{EXACT_MAX_SECONDS}")
    end = end or datetime.now(UTC)
    return iso_ms(end - timedelta(seconds=window_seconds)), iso_ms(end)


def iso_ms(t: datetime) -> str:
    """An exact bound, always with its milliseconds, the precision of a `date` field. OpenSearch
    fills the fields that an `lte` date leaves out with their highest value: `lte 11:30:00`
    counts a document at 11:30:00.999 (a probe on the store, issue 1291)."""
    return t.isoformat(timespec="milliseconds")


DEFAULT_DAYS = 30  # the default window of a trend read, in docs/API.md


def pick_window(
    days: int | None, window_seconds: int | None, *, past: bool, days_name: str = "days"
) -> tuple[int | None, int | None]:
    """(days, window_seconds) of a read, exactly one of them set; `ValueError` for a request
    that names both, or an exact window at a past time, which stays daily (issue 1291, ruling
    5). A route takes `days` with no default, so it can see that a caller named both: the MCP
    tools call the route function, and a default would hide what the caller sent."""
    if window_seconds is None:
        return (DEFAULT_DAYS if days is None else days), None
    if days is not None:
        raise ValueError(f"{days_name} and window_seconds are mutually exclusive")
    if past:
        raise ValueError("window_seconds is not available at a past as_of: a past range is daily")
    return None, window_seconds


@dataclass(frozen=True)
class TrendWindow:
    """The bounds of one trend read: `gte` and `lte` filter the documents, and `gte` to `upper`
    is the axis of the histogram."""

    gte: str
    upper: str
    lte: str


def trend_window(days: int | None, window_seconds: int | None, end: datetime) -> TrendWindow:
    """A whole-day window (`days`) or an exact one (`window_seconds`), never both. Each read stops
    at its end, now or T (issue 1291, ruling 3): a scanner clock that runs ahead stamps times
    after now, and the read must not count them or draw a bar for them."""
    if window_seconds is not None:
        if days is not None:
            raise ValueError("days and window_seconds are mutually exclusive")
        gte, lte = range_bounds(window_seconds, end)
        return TrendWindow(gte=gte, upper=lte, lte=lte)
    if days is None:
        raise ValueError("give days or window_seconds")
    gte, upper = window_bounds(days, end)
    return TrendWindow(gte=gte, upper=upper, lte=iso_ms(end))


def _timeline(date_field: str, gte: str, upper: str, interval: str = "day") -> dict[str, Any]:
    if interval not in ("day", "hour"):  # a scanner cadence lens, not a free-form histogram
        raise ValueError("interval must be day or hour")
    return {
        "date_histogram": {
            "field": date_field,
            "calendar_interval": interval,
            "min_doc_count": 0,  # quiet buckets are real data points — a continuous axis
            "extended_bounds": {"min": gte, "max": upper},
        }
    }


@dataclass(frozen=True)
class ScanFilters:
    """The filters of the findings grid that a scan record also holds (issue 1293): the
    namespaces, the image, its tag and digest, and the scanner, with the names of `/findings`. A
    scan record holds no severity, state or other field of a finding, so the route takes no
    such filter. `scanner` is one value, as on `/findings`."""

    namespace: list[str] | None = None
    exclude_namespace: list[str] | None = None
    image_repo: list[str] | None = None
    exclude_image_repo: list[str] | None = None
    tag: list[str] | None = None
    exclude_tag: list[str] | None = None
    untagged: bool | None = None
    image_digest: str | None = None
    scanner: str | None = None
    exclude_scanner: str | None = None


def _scan_filter_clauses(filters: ScanFilters) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(filter, must_not) on the fields of a scan record, which have the names of the fields of
    a finding: a namespace filter matches a record when ANY of its namespaces is listed."""
    # local: search imports this module for window_bounds
    from backend.query.search import conflicting_filter_pair, has_tag_clause

    if (message := conflicting_filter_pair(vars(filters))) is not None:
        raise ValueError(message)
    fl: list[dict[str, Any]] = []
    mn: list[dict[str, Any]] = []
    for field, include, exclude in (
        ("namespaces", filters.namespace, filters.exclude_namespace),
        ("image_repo", filters.image_repo, filters.exclude_image_repo),
        ("tag", filters.tag, filters.exclude_tag),
    ):
        if include:
            fl.append({"terms": {field: include}})
        if exclude:
            mn.append({"terms": {field: exclude}})
    for field, value in (("image_digest", filters.image_digest), ("scanner", filters.scanner)):
        if value is not None:
            fl.append({"term": {field: value}})
    if filters.exclude_scanner is not None:
        mn.append({"term": {"scanner": filters.exclude_scanner}})
    if filters.untagged is not None:  # "no tag" is a missing tag or "", as for the findings
        (mn if filters.untagged else fl).append(has_tag_clause())
    return fl, mn


def build_scans_trend_body(
    *,
    days: int | None = None,
    window_seconds: int | None = None,
    anchor: datetime | None = None,
    interval: str = "day",
    filters: ScanFilters | None = None,
) -> dict[str, Any]:
    # hourly buckets answer "does the scanner run every N hours?" on short ranges — daily
    # bars over a 1-day window collapse any cadence into one bar (operator, audit 343)
    w = trend_window(days, window_seconds, anchor or datetime.now(UTC))
    timeline = _timeline("ingested_at", w.gte, w.upper, interval)
    # THE dedup rule (task B, #139): committed scans = cardinality(commit_key), never doc counts
    timeline["aggs"] = {"scans": {"cardinality": {"field": "commit_key"}}}
    # the ≤ T cut: an anchored window must not see later appends
    window: dict[str, Any] = {"gte": w.gte, "lte": w.lte}
    fl, mn = _scan_filter_clauses(filters or ScanFilters())
    query: dict[str, Any] = {"filter": [{"range": {"ingested_at": window}}, *fl]}
    if mn:
        query["must_not"] = mn
    return {
        "size": 0,
        "query": {"bool": query},
        "aggs": {"by_scanner": {"terms": dict(_BY_SCANNER_TERMS), "aggs": {"timeline": timeline}}},
    }


def build_ingest_failures_trend_body(
    *,
    days: int | None = None,
    window_seconds: int | None = None,
    anchor: datetime | None = None,
    interval: str = "day",
) -> dict[str, Any]:
    """Refused pushes per bucket per scanner (issue 575), on the scans trend's exact axis so the
    two strips line up. A plain doc count: each refusal is written once under its own id, never
    retried, so no sibling duplicates exist for a cardinality to fold."""
    w = trend_window(days, window_seconds, anchor or datetime.now(UTC))
    return {
        "size": 0,
        "query": {"bool": {"filter": [{"range": {"@timestamp": {"gte": w.gte, "lte": w.lte}}}]}},
        "aggs": {
            "by_scanner": {
                "terms": dict(_BY_SCANNER_TERMS),
                "aggs": {"timeline": _timeline("@timestamp", w.gte, w.upper, interval)},
            }
        },
    }


_SPLIT_TERMS: dict[str, dict[str, Any]] = {
    "scanner": dict(_BY_SCANNER_TERMS),
    # the severity lens (M9c 1b): buckets on the SERVER-derived canonical (D16), never the
    # verbatim scanner word; six D46 buckets
    "severity": {"field": "severity_canonical", "size": 6},
}


def build_findings_trend_body(
    *, days: int, split: str = "scanner", scanner: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    w = trend_window(days, None, now or datetime.now(UTC))
    terms = _SPLIT_TERMS[split]

    def series(date_field: str) -> dict[str, Any]:
        return {
            "filter": {"range": {date_field: {"gte": w.gte, "lte": w.lte}}},
            "aggs": {
                "by_key": {
                    "terms": dict(terms),
                    "aggs": {"timeline": _timeline(date_field, w.gte, w.upper)},
                }
            },
        }

    body: dict[str, Any] = {
        "size": 0,
        "aggs": {"new": series("first_seen_at"), "resolved": series("resolved_at")},
    }
    if scanner is not None:  # scope the split to one scanner AT THE QUERY — never client math
        body["query"] = {"bool": {"filter": [{"term": {"scanner": scanner}}]}}
    return body


def build_new_findings_trend_body(
    filters: "SearchFilters",
    *,
    days: int | None = None,
    window_seconds: int | None = None,
    interval: str = "day",
    sla_cutoffs: dict[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The findings first seen in each bucket, by canonical severity, under the filter context
    of the grid (issue 1292). `present` comes from the filters, so the default counts the
    findings present now. An `overdue` filter needs `sla_cutoffs`, as on the grid."""
    # search.py imports window_bounds from here: a top-level import of aggs would be a cycle
    from backend.query.aggs import _base

    end = now or datetime.now(UTC)
    w = trend_window(days, window_seconds, end)
    body = _base(filters, sla_cutoffs, now=end)  # "new in range" ends where the strip ends
    body["query"]["bool"]["filter"].append(
        {"range": {"first_seen_at": {"gte": w.gte, "lte": w.lte}}}
    )
    body["aggs"] = {
        "by_severity": {
            "terms": dict(_SPLIT_TERMS["severity"]),
            "aggs": {"timeline": _timeline("first_seen_at", w.gte, w.upper, interval)},
        }
    }
    return body
