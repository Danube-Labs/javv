"""The approvals-queue DSL (M9d slice 4b) — pure builders for `GET /decisions/approvals`.

The rail returned by operator re-ruling (§8.5, on the built 4a specimen): the prototype's
Status/Approver dims + a CVE search, served HERE because client-filtering a paged fetch is
banned (server-side everything). `status` derives from `expiry` against a caller-supplied
`now` + warn window (the sla_clock cutoff discipline: derive at query time, never store a
verdict); `scanner` filters the COLUMN's value — `both` = apply_both_scanners, else the D22
scanner-specific subject. Facet counts are `filters`/`terms` aggs under the SAME lens, so the
rail always describes the queue below it (the findings-rail contract).
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.query.aggs import facet_aggregation

STATUS_VALUES = ("active", "expiring", "expired", "open-ended")
SCANNER_VALUES = ("both", "trivy", "grype")
_APPROVER_TERMS_SIZE = 32  # top-N rail dim, the audit-actor precedent


@dataclass(frozen=True)
class ApprovalFilters:
    """The 4b lens. `None` or an empty list = unset; vocabulary is validated at the route edge.

    `status` and `created_by` take several values (issue 952): an approval matches any of them,
    and an exclusion leaves out an approval with any of them. `scanner` stays one value. The
    `exclude_*` twins are the negation side (issue 349): a field is included OR excluded,
    never both. `status` and `scanner` are derived rather than stored, so their exclusions are
    the complement of a computed clause — well defined because each vocabulary partitions the
    queue exactly: an approval has one status (open-ended | expired | expiring | active) and
    one scanner value (both | trivy | grype). Excluding `expiring` therefore yields the other
    three, open-ended included, because a doc with no `expiry` never matches the range.
    """

    q: str | None = None  # CVE contains-search
    status: list[str] | None = None
    created_by: list[str] | None = None
    scanner: str | None = None  # both | trivy | grype — the column's value
    exclude_status: list[str] | None = None
    exclude_created_by: list[str] | None = None
    exclude_scanner: str | None = None


def _status_clause(status: str, *, now: datetime, warn_days: int) -> dict[str, Any]:
    """One status bucket as a filter clause. Boundaries mirror ExpiryChip exactly
    (chip ≡ filter ≡ facet): expired = `expiry ≤ now`; expiring = within the warn window."""
    iso = now.isoformat()
    warn_iso = (now + timedelta(days=warn_days)).isoformat()
    if status == "open-ended":
        return {"bool": {"must_not": [{"exists": {"field": "expiry"}}]}}
    if status == "expired":
        return {"range": {"expiry": {"lte": iso}}}
    if status == "expiring":
        return {"range": {"expiry": {"gt": iso, "lte": warn_iso}}}
    return {"range": {"expiry": {"gt": warn_iso}}}  # active


def _scanner_clause(scanner: str) -> dict[str, Any]:
    if scanner == "both":
        return {"term": {"apply_both_scanners": True}}
    return {
        "bool": {
            "filter": [{"term": {"apply_both_scanners": False}}, {"term": {"scanner": scanner}}]
        }
    }


def derive_status(expiry: str | None, *, now: datetime, warn_days: int) -> str:
    """One row's status, by the SAME boundaries `_status_clause` filters on — so the CSV export
    (issue 359) can stamp a status per row without a second reading of the rule.

    The FE chip derives this too (`approvals/viewModel.ts` `expiryStatus`); all three agree by
    construction: no expiry = open-ended, `expiry <= now` = expired, inside the warn window =
    expiring, beyond it = active. An unparseable date reads open-ended, matching the chip.
    """
    if not expiry:
        return "open-ended"
    try:
        when = datetime.fromisoformat(expiry)
    except ValueError:
        return "open-ended"
    if when.tzinfo is None:
        # a stored expiry is routinely DATE-ONLY ("2026-07-15") — the UI's picker submits a day,
        # and the mapping is a `date`. Parsed, that is naive, and OpenSearch reads it as midnight
        # UTC when the range clause compares it. Attaching UTC here is what keeps this function
        # agreeing with `_status_clause` on exactly those rows.
        when = when.replace(tzinfo=UTC)
    if when <= now:
        return "expired"
    return "expiring" if when <= now + timedelta(days=warn_days) else "active"


def _any_of(clauses: list[dict[str, Any]]) -> dict[str, Any]:
    """One clause that matches when any of `clauses` does; a single clause stays as it is."""
    if len(clauses) == 1:
        return clauses[0]
    return {"bool": {"should": clauses, "minimum_should_match": 1}}


def _approver_clause(filters: ApprovalFilters) -> dict[str, Any] | None:
    """The approver filter alone, or None when it is unset (see `build_approvals_body`)."""
    clauses: dict[str, Any] = {}
    if filters.created_by:
        clauses["filter"] = [{"terms": {"created_by": filters.created_by}}]
    if filters.exclude_created_by:
        clauses["must_not"] = [{"terms": {"created_by": filters.exclude_created_by}}]
    return {"bool": clauses} if clauses else None


def build_approvals_query(
    filters: ApprovalFilters, *, cluster_id: str, now: datetime, warn_days: int
) -> dict[str, Any]:
    """The lens itself — the bool query the queue page, its facets, and the CSV export all run.

    One definition so an export can never describe a different set of rows from the screen it
    was exported from (issue 359).
    """
    fl: list[dict[str, Any]] = [
        {"term": {"cluster_id": cluster_id}},
        {"term": {"type": "risk_accepted"}},
    ]
    if filters.q is not None:
        escaped = filters.q.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")
        # structured wildcard, never query_string (the findings-q discipline, DSL injection)
        fl.append({"wildcard": {"cve_id": {"value": f"*{escaped}*", "case_insensitive": True}}})
    if filters.status:
        fl.append(
            _any_of([_status_clause(s, now=now, warn_days=warn_days) for s in filters.status])
        )
    if filters.created_by:
        fl.append({"terms": {"created_by": filters.created_by}})
    if filters.scanner is not None:
        fl.append(_scanner_clause(filters.scanner))

    # the revoked guard is the queue's definition, not a user filter — exclusions APPEND to it,
    # because replacing it would put revoked acceptances back in the review queue
    must_not: list[dict[str, Any]] = [{"exists": {"field": "revoked_at"}}]
    for status in filters.exclude_status or ():
        must_not.append(_status_clause(status, now=now, warn_days=warn_days))
    if filters.exclude_created_by:
        must_not.append({"terms": {"created_by": filters.exclude_created_by}})
    if filters.exclude_scanner is not None:
        must_not.append(_scanner_clause(filters.exclude_scanner))

    return {"bool": {"filter": fl, "must_not": must_not}}


def build_approvals_body(
    filters: ApprovalFilters,
    *,
    cluster_id: str,
    size: int,
    offset: int,
    now: datetime,
    warn_days: int,
) -> dict[str, Any]:
    """Page + facets in ONE query (the queue is fleet-bounded — one round trip beats two).
    Sort stays the review contract: soonest expiry first, open-ended last.

    The approver count leaves out the approver filter (issue 952, ruling 2), so a picked
    approver does not hide the others. The query thus holds every filter but that one, and
    `post_filter` applies it to the rows and the total only. The status and scanner counts
    put it back, so they still count the whole lens. The cluster filter stays in the query."""
    aggs: dict[str, Any] = {
        "status": {
            "filters": {
                "filters": {
                    s: _status_clause(s, now=now, warn_days=warn_days) for s in STATUS_VALUES
                }
            }
        },
        "created_by": {"terms": {"field": "created_by", "size": _APPROVER_TERMS_SIZE}},
        "scanner": {"filters": {"filters": {s: _scanner_clause(s) for s in SCANNER_VALUES}}},
    }
    approver = _approver_clause(filters)
    body: dict[str, Any] = {
        "size": size,
        "from": offset,
        "track_total_hits": True,
        "query": build_approvals_query(
            replace(filters, created_by=None, exclude_created_by=None) if approver else filters,
            cluster_id=cluster_id,
            now=now,
            warn_days=warn_days,
        ),
        "sort": [{"expiry": {"order": "asc", "missing": "_last"}}],
        "aggs": aggs,
    }
    if approver is not None:
        body["post_filter"] = approver
        for field in ("status", "scanner"):
            aggs[field] = {"filter": approver, "aggs": {"values": aggs[field]}}
    return body


def shape_facets(aggregations: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Agg response → the rail's wire shape ({key, count} lists, the findings-facet look).
    Zero-count buckets are kept — a rail dim with a stable vocabulary lists quiet values."""
    out: dict[str, list[dict[str, Any]]] = {}
    for field in ("status", "scanner"):
        buckets = facet_aggregation(aggregations[field])["buckets"]
        out[field] = [{"key": k, "count": buckets[k]["doc_count"]} for k in buckets]
    out["created_by"] = [
        {"key": b["key"], "count": b["doc_count"]} for b in aggregations["created_by"]["buckets"]
    ]
    return out
