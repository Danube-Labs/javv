"""M9d slice 4b — the approvals-queue DSL builder. Pins: status boundaries MIRROR the FE
ExpiryChip exactly (chip ≡ filter ≡ facet — expired is `expiry ≤ now`, expiring sits inside
the warn window); the CVE search is a structured wildcard with escaped metacharacters (never
query_string); `scanner` filters the column's VALUE (both = apply_both, else the D22 subject);
revoked rows stay excluded whatever the lens; facets ride the same filtered query."""

from datetime import UTC, datetime, timedelta

from backend.export.approvals_csv import APPROVALS_SORT
from backend.query.approvals import (
    ApprovalFilters,
    build_approvals_body,
    build_approvals_query,
    derive_status,
    shape_facets,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
KW = {"cluster_id": "c-1", "size": 25, "offset": 0, "now": NOW, "warn_days": 7}


def _filters(body: dict) -> list[dict]:
    return body["query"]["bool"]["filter"]


def test_base_body_keeps_the_review_contract() -> None:
    body = build_approvals_body(ApprovalFilters(), **KW)
    assert {"term": {"cluster_id": "c-1"}} in _filters(body)
    assert {"term": {"type": "risk_accepted"}} in _filters(body)
    assert body["query"]["bool"]["must_not"] == [{"exists": {"field": "revoked_at"}}]
    assert body["sort"] == [{"expiry": {"order": "asc", "missing": "_last"}}]
    assert body["from"] == 0 and body["size"] == 25


def test_status_boundaries_mirror_the_expiry_chip() -> None:
    iso = NOW.isoformat()
    warn = (NOW + timedelta(days=7)).isoformat()
    expired = build_approvals_body(ApprovalFilters(status=["expired"]), **KW)
    assert {"range": {"expiry": {"lte": iso}}} in _filters(expired)  # AT now = expired
    expiring = build_approvals_body(ApprovalFilters(status=["expiring"]), **KW)
    assert {"range": {"expiry": {"gt": iso, "lte": warn}}} in _filters(expiring)
    active = build_approvals_body(ApprovalFilters(status=["active"]), **KW)
    assert {"range": {"expiry": {"gt": warn}}} in _filters(active)
    open_ended = build_approvals_body(ApprovalFilters(status=["open-ended"]), **KW)
    assert {"bool": {"must_not": [{"exists": {"field": "expiry"}}]}} in _filters(open_ended)


def test_warn_days_moves_the_expiring_window() -> None:
    body = build_approvals_body(ApprovalFilters(status=["expiring"]), **{**KW, "warn_days": 30})
    warn = (NOW + timedelta(days=30)).isoformat()
    assert {"range": {"expiry": {"gt": NOW.isoformat(), "lte": warn}}} in _filters(body)


def test_cve_search_is_an_escaped_wildcard_never_query_string() -> None:
    body = build_approvals_body(ApprovalFilters(q="cve-2024*?"), **KW)
    (clause,) = [c for c in _filters(body) if "wildcard" in c]
    assert clause["wildcard"]["cve_id"] == {
        "value": "*cve-2024\\*\\?*",
        "case_insensitive": True,
    }
    assert "query_string" not in str(body)


def test_scanner_filters_the_column_value() -> None:
    both = build_approvals_body(ApprovalFilters(scanner="both"), **KW)
    assert {"term": {"apply_both_scanners": True}} in _filters(both)
    trivy = build_approvals_body(ApprovalFilters(scanner="trivy"), **KW)
    assert {
        "bool": {
            "filter": [
                {"term": {"apply_both_scanners": False}},
                {"term": {"scanner": "trivy"}},
            ]
        }
    } in _filters(trivy)


def test_facets_ride_the_same_lens_and_shape_to_the_rail_wire() -> None:
    body = build_approvals_body(ApprovalFilters(status=["active"]), **KW)
    assert _status_clause_present(body, "active")  # the facets share this query
    assert "post_filter" not in body  # no approver filter, nothing moves out of the query
    assert set(body["aggs"]) == {"status", "created_by", "scanner"}
    assert set(body["aggs"]["status"]["filters"]["filters"]) == {
        "active",
        "expiring",
        "expired",
        "open-ended",
    }

    shaped = shape_facets(
        {
            "status": {
                "buckets": {
                    "active": {"doc_count": 2},
                    "expiring": {"doc_count": 1},
                    "expired": {"doc_count": 0},
                    "open-ended": {"doc_count": 3},
                }
            },
            "scanner": {
                "buckets": {
                    "both": {"doc_count": 4},
                    "trivy": {"doc_count": 1},
                    "grype": {"doc_count": 1},
                }
            },
            "created_by": {"buckets": [{"key": "lead", "doc_count": 6}]},
        }
    )
    assert {"key": "expired", "count": 0} in shaped["status"]  # quiet values still list
    assert shaped["created_by"] == [{"key": "lead", "count": 6}]
    assert {"key": "both", "count": 4} in shaped["scanner"]


def _must_not(body: dict) -> list[dict]:
    return body["query"]["bool"]["must_not"]


def test_exclusions_append_to_the_revoked_guard_never_replace_it() -> None:
    """issue 349: the revoked guard defines the queue. An exclusion that overwrote it would
    put revoked acceptances back in front of the reviewer."""
    body = build_approvals_body(ApprovalFilters(exclude_status=["expired"]), **KW)
    assert {"exists": {"field": "revoked_at"}} in _must_not(body)
    assert len(_must_not(body)) == 2
    query = build_approvals_query(
        ApprovalFilters(exclude_created_by=["lead"]),
        cluster_id="c-1",
        now=NOW,
        warn_days=7,
    )
    assert query["bool"]["must_not"] == [
        {"exists": {"field": "revoked_at"}},
        {"terms": {"created_by": ["lead"]}},
    ]


def test_excluding_a_status_is_the_complement_of_its_own_clause() -> None:
    # the four buckets partition the queue, so "not expiring" is the other three — and a doc
    # with no expiry never matches the range, so open-ended survives the exclusion
    body = build_approvals_body(ApprovalFilters(exclude_status=["expiring"]), **KW)
    included = build_approvals_body(ApprovalFilters(status=["expiring"]), **KW)
    clause = _filters(included)[-1]
    assert clause in _must_not(body)
    assert clause not in _filters(body)


def test_excluding_open_ended_keeps_only_the_dated_ones() -> None:
    body = build_approvals_body(ApprovalFilters(exclude_status=["open-ended"]), **KW)
    assert {"bool": {"must_not": [{"exists": {"field": "expiry"}}]}} in _must_not(body)


def test_exclude_scanner_negates_the_composite_column_clause() -> None:
    # `trivy` is (apply_both=false AND scanner=trivy), so excluding it keeps `both` rows too
    body = build_approvals_body(ApprovalFilters(exclude_scanner="trivy"), **KW)
    assert {
        "bool": {
            "filter": [{"term": {"apply_both_scanners": False}}, {"term": {"scanner": "trivy"}}]
        }
    } in _must_not(body)


def test_include_and_exclude_ride_the_same_query_so_facets_follow_the_lens() -> None:
    body = build_approvals_body(
        ApprovalFilters(status=["active"], exclude_created_by=["lead"]), **KW
    )
    assert _status_clause_present(body, "active")
    # the approver exclusion filters the rows through post_filter, see the test below
    assert body["post_filter"] == {"bool": {"must_not": [{"terms": {"created_by": ["lead"]}}]}}
    assert set(body["aggs"]) == {"status", "created_by", "scanner"}


def _status_clause_present(body: dict, status: str) -> bool:
    expected = build_approvals_body(ApprovalFilters(status=[status]), **KW)
    return _filters(expected)[-1] in _filters(body)


# --- issue 359: the export shares this lens, and stamps a per-row status from it ----------


def test_the_export_lens_is_the_page_lens_not_a_second_definition() -> None:
    """The CSV export runs `build_approvals_query` directly. If the page body stopped being
    built from it, an export could silently describe a different set of rows than the screen
    it came from — so the identity is pinned, not assumed."""
    filters = ApprovalFilters(status=["expiring"], exclude_scanner="trivy")
    page = build_approvals_body(filters, **KW)
    lens = build_approvals_query(
        filters, cluster_id=KW["cluster_id"], now=KW["now"], warn_days=KW["warn_days"]
    )
    assert page["query"] == lens
    # with an approver filter the page splits its filters into its query and its post_filter,
    # and the two together are the export's query: the same clauses, nothing more
    with_approver = ApprovalFilters(status=["expiring"], created_by=["lead", "ops"])
    page = build_approvals_body(with_approver, **KW)
    export = build_approvals_query(
        with_approver, cluster_id=KW["cluster_id"], now=KW["now"], warn_days=KW["warn_days"]
    )
    approver = {"terms": {"created_by": ["lead", "ops"]}}
    assert page["post_filter"] == {"bool": {"filter": [approver]}}
    assert export["bool"]["filter"] == [*page["query"]["bool"]["filter"], approver]
    assert export["bool"]["must_not"] == page["query"]["bool"]["must_not"]


def test_several_statuses_match_any_of_them_and_an_exclusion_leaves_out_each() -> None:
    """issue 952: status is calculated, so two statuses are two clauses joined by OR. One
    status stays its own clause, so the one-value body does not change."""
    two = build_approvals_body(ApprovalFilters(status=["expired", "open-ended"]), **KW)
    expired = _filters(build_approvals_body(ApprovalFilters(status=["expired"]), **KW))[-1]
    open_ended = _filters(build_approvals_body(ApprovalFilters(status=["open-ended"]), **KW))[-1]
    assert _filters(two)[-1] == {
        "bool": {"should": [expired, open_ended], "minimum_should_match": 1}
    }
    excluded = build_approvals_body(ApprovalFilters(exclude_status=["expired", "active"]), **KW)
    active = _filters(build_approvals_body(ApprovalFilters(status=["active"]), **KW))[-1]
    assert _must_not(excluded)[1:] == [expired, active]
    # an empty list is no filter, never a clause that matches nothing
    assert build_approvals_body(ApprovalFilters(status=[], created_by=[]), **KW) == (
        build_approvals_body(ApprovalFilters(), **KW)
    )


def test_the_approver_count_leaves_out_the_approver_filter_and_nothing_else_does() -> None:
    """issue 952: the rows and the total keep the approver filter (post_filter), the
    approver count does not, and the status and scanner counts put it back."""
    body = build_approvals_body(ApprovalFilters(created_by=["lead"], scanner="trivy"), **KW)
    approver = {"bool": {"filter": [{"terms": {"created_by": ["lead"]}}]}}
    assert body["post_filter"] == approver
    assert not any("created_by" in str(c) for c in _filters(body))
    assert {"term": {"cluster_id": "c-1"}} in _filters(body)  # the tenant stays in the query
    assert body["aggs"]["created_by"] == {"terms": {"field": "created_by", "size": 32}}
    for field in ("status", "scanner"):
        assert body["aggs"][field]["filter"] == approver
        assert "filters" in body["aggs"][field]["aggs"]["values"]
    # the wrapped buckets reach the screen in the same shape as the plain ones
    shaped = shape_facets(
        {
            "status": {"doc_count": 1, "values": {"buckets": {"active": {"doc_count": 1}}}},
            "scanner": {"doc_count": 1, "values": {"buckets": {"trivy": {"doc_count": 1}}}},
            "created_by": {"buckets": [{"key": "lead", "doc_count": 1}]},
        }
    )
    assert shaped["status"] == [{"key": "active", "count": 1}]
    assert shaped["scanner"] == [{"key": "trivy", "count": 1}]


def test_derive_status_agrees_with_the_clause_that_filters_on_it() -> None:
    """chip ≡ filter ≡ facet ≡ export. Every status is checked at the boundary INSTANT its
    clause uses, so an off-by-one between `<=` and `<` on either side fails here."""
    warn = 7
    at_now = NOW  # `expiry <= now` is expired — AT now, not after it
    inside_warn = NOW + timedelta(days=warn)  # the window is inclusive at its far edge
    past_warn = NOW + timedelta(days=warn, seconds=1)
    cases = {
        None: "open-ended",
        "": "open-ended",
        at_now.isoformat(): "expired",
        (NOW - timedelta(days=400)).isoformat(): "expired",
        (NOW + timedelta(seconds=1)).isoformat(): "expiring",
        inside_warn.isoformat(): "expiring",
        past_warn.isoformat(): "active",
    }
    for expiry, expected in cases.items():
        assert derive_status(expiry, now=NOW, warn_days=warn) == expected, expiry


def test_derive_status_follows_warn_days_the_same_way_the_clause_does() -> None:
    twenty_days_out = (NOW + timedelta(days=20)).isoformat()
    assert derive_status(twenty_days_out, now=NOW, warn_days=7) == "active"
    assert derive_status(twenty_days_out, now=NOW, warn_days=30) == "expiring"


def test_a_garbled_expiry_reads_open_ended_rather_than_raising() -> None:
    """The chip does the same with an unparseable date. An export that raised would fail the
    whole download over one bad row."""
    assert derive_status("not-a-date", now=NOW, warn_days=7) == "open-ended"


def test_the_sweep_sort_is_unique_so_search_after_cannot_drop_rows() -> None:
    """The page sorts on `expiry` alone — fine for from/size, NOT unique. Under search_after a
    tie would silently skip or repeat rows, so the sweep appends `decision_id`."""
    assert APPROVALS_SORT[0] == {"expiry": {"order": "asc", "missing": "_last"}}
    assert APPROVALS_SORT[-1] == {"decision_id": {"order": "asc"}}
    assert build_approvals_body(ApprovalFilters(), **KW)["sort"] == [APPROVALS_SORT[0]]


def test_a_date_only_expiry_is_read_as_utc_midnight_like_opensearch_does() -> None:
    """The regression that a self-consistent test hid. The app stores `expiry` as a DATE
    ("2026-07-15") — the picker submits a day and the mapping is a `date` — so
    `fromisoformat` hands back a NAIVE datetime. Comparing that against a tz-aware `now`
    raised TypeError and truncated the export mid-stream (200 + header, zero rows).

    OpenSearch reads a bare date as midnight UTC when the range clause compares it, so that is
    what this must do, or the column and the filter disagree on exactly these rows.
    """
    day_before = (NOW - timedelta(days=2)).date().isoformat()
    day_after = (NOW + timedelta(days=2)).date().isoformat()
    far_off = (NOW + timedelta(days=60)).date().isoformat()
    assert derive_status(day_before, now=NOW, warn_days=7) == "expired"
    assert derive_status(day_after, now=NOW, warn_days=7) == "expiring"
    assert derive_status(far_off, now=NOW, warn_days=7) == "active"
    # the midnight-UTC reading itself: today's date is already past at midday NOW
    assert derive_status(NOW.date().isoformat(), now=NOW, warn_days=7) == "expired"
