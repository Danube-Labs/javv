"""Trend series (M6 slice 3, FR-5/FR-12) — pure DSL builders over the append logs.

- **Scans** (`javv-scan-events-<cluster_id>-*`): committed scans per day per scanner. THE
  dedup rule (task B, #139): a retry straddling a rollover leaves byte-identical sibling docs
  (same `commit_key`) in two backing indices — accepted in storage, deduped at read via
  `cardinality(commit_key)`. NEVER raw doc counts or sums over scan-event docs.
- **Findings** (`findings`): the FR-5 "new in Nd" series plus its burn-down twin — new
  (`first_seen_at`) vs resolved (`resolved_at`) per day per scanner. No `present` filter: a
  finding that appeared and was tombstoned inside the window still counts as new that day.
- **Ingest failures** (`javv-ingest-failures-<cluster_id>-*`, issue 575): pushes refused after
  the token check, per bucket per scanner, on the scans series' exact axis.
- **New findings** (`findings`, issue 1292): the findings first seen in each bucket, by severity,
  under the filters of the grid, on the scans series' exact axis.

All are `size:0` (server-side everything). The scans, findings and failures series split
`by_scanner` (per-scanner is sacred); the new-findings series splits by severity and counts the
row of each scanner. `ingested_at`, `resolved_at` and a failure record's `@timestamp` are
stamped by the server. `first_seen_at` is not: the ingest copies it from the scan's
`last_seen_at` (`services/ingest.py`), the scanner's clock, so a live window that must not see
the future ends at now. A scan event's `@timestamp` is the client's too: display-only and
gameable (D40: never an ordering key). True
historical severity totals (state at T) are NOT derivable from these logs at read cost — that's
the v1.1 `javv-metrics` rollup; these series are the MVP trend surface.

The tenant filter is forced by the tenant read path at execution; scan-events routing additionally
pins the per-cluster index pattern.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.query.search import SearchFilters

_MAX_DAYS = 365
_BY_SCANNER_TERMS = {"field": "scanner", "size": 4}


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


def build_scans_trend_body(
    *, days: int, anchor: datetime | None = None, interval: str = "day"
) -> dict[str, Any]:
    # hourly buckets answer "does the scanner run every N hours?" on short ranges — daily
    # bars over a 1-day window collapse any cadence into one bar (operator, audit 343)
    gte, upper = window_bounds(days, anchor)
    timeline = _timeline("ingested_at", gte, upper, interval)
    # THE dedup rule (task B, #139): committed scans = cardinality(commit_key), never doc counts
    timeline["aggs"] = {"scans": {"cardinality": {"field": "commit_key"}}}
    window: dict[str, Any] = {"gte": gte}
    if anchor is not None:  # the ≤ T cut — an anchored window must not see later appends
        window["lte"] = anchor.isoformat()
    return {
        "size": 0,
        "query": {"bool": {"filter": [{"range": {"ingested_at": window}}]}},
        "aggs": {"by_scanner": {"terms": dict(_BY_SCANNER_TERMS), "aggs": {"timeline": timeline}}},
    }


def build_ingest_failures_trend_body(
    *, days: int, anchor: datetime | None = None, interval: str = "day"
) -> dict[str, Any]:
    """Refused pushes per bucket per scanner (issue 575), on the scans trend's exact axis so the
    two strips line up. A plain doc count: each refusal is written once under its own id, never
    retried, so no sibling duplicates exist for a cardinality to fold."""
    gte, upper = window_bounds(days, anchor)
    window: dict[str, Any] = {"gte": gte}
    if anchor is not None:
        window["lte"] = anchor.isoformat()
    return {
        "size": 0,
        "query": {"bool": {"filter": [{"range": {"@timestamp": window}}]}},
        "aggs": {
            "by_scanner": {
                "terms": dict(_BY_SCANNER_TERMS),
                "aggs": {"timeline": _timeline("@timestamp", gte, upper, interval)},
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
    *, days: int, split: str = "scanner", scanner: str | None = None
) -> dict[str, Any]:
    gte, upper = window_bounds(days)
    terms = _SPLIT_TERMS[split]

    def series(date_field: str) -> dict[str, Any]:
        return {
            "filter": {"range": {date_field: {"gte": gte}}},
            "aggs": {
                "by_key": {
                    "terms": dict(terms),
                    "aggs": {"timeline": _timeline(date_field, gte, upper)},
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
    days: int,
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
    gte, upper = window_bounds(days, end)
    body = _base(filters, sla_cutoffs)
    body["query"]["bool"]["filter"].append(
        {"range": {"first_seen_at": {"gte": gte, "lte": end.isoformat()}}}
    )
    body["aggs"] = {
        "by_severity": {
            "terms": dict(_SPLIT_TERMS["severity"]),
            "aggs": {"timeline": _timeline("first_seen_at", gte, upper, interval)},
        }
    }
    return body
