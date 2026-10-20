"""M6 slice 2 — scanner-faceted aggregations (FR-12): the pure DSL builders.

Pins: aggregation fields are WHITELISTED keyword/bool fields (never `text` — NFR-1); every
bucket carries a `by_scanner` sub-agg (per-scanner is sacred: the UI can always split, we never
force a cross-scanner merge); facet vocabularies use capped `terms`; high-cardinality grouping
uses a `composite` source paginating via `after_key` behind the same opaque-cursor contract as
search (no silently-capped buckets — DoD); the current filter context (SearchFilters) applies to
every aggregation body.
"""

import json
from typing import Any

import pytest

from backend.query.aggs import (
    FACET_FIELDS,
    GROUP_FIELDS,
    TOP_COMPONENTS_SIZE,
    build_composite_body,
    build_facets_body,
    build_top_components_body,
    decode_after,
    encode_after,
    facet_aggregation,
)
from backend.query.search import SearchFilters


def test_facets_body_aggregates_each_whitelisted_field_by_scanner() -> None:
    body = build_facets_body(SearchFilters(), fields=["severity", "state"])
    assert body["size"] == 0  # aggregation-only — raw findings never ship to the client
    sev = body["aggs"]["severity"]
    # D46/#274: the facet NAME stays `severity`, but the agg targets the canonical query key
    assert sev["terms"] == {"field": "severity_canonical", "size": 32}
    assert sev["aggs"]["by_scanner"]["terms"]["field"] == "scanner"
    assert set(body["aggs"]) == {"severity", "state"}
    # the filter context applies — facet counts reflect the current grid view
    assert {"term": {"present": True}} in body["query"]["bool"]["filter"]


def test_facets_reject_non_whitelisted_fields() -> None:
    with pytest.raises(ValueError):
        build_facets_body(SearchFilters(), fields=["package_name"])  # unbounded cardinality
    with pytest.raises(ValueError):
        build_facets_body(SearchFilters(), fields=["title"])  # never aggregate on text (NFR-1)
    assert "severity" in FACET_FIELDS and "image_repo" not in FACET_FIELDS


_CUTOFFS = {
    "kev": "2026-07-11T00:00:00+00:00",
    "critical": "2026-07-10T00:00:00+00:00",
    "high": "2026-07-05T00:00:00+00:00",
    "medium": "2026-06-12T00:00:00+00:00",
    "low": "2026-04-13T00:00:00+00:00",
}


def test_facets_default_to_the_full_whitelist() -> None:
    body = build_facets_body(SearchFilters(), sla_cutoffs=_CUTOFFS)
    assert set(body["aggs"]) == set(FACET_FIELDS)


def test_overdue_facet_is_a_filter_agg_on_the_shared_clause() -> None:
    """Issue 363: the rail chip's count — a `filter` agg over the SAME clause the grid filter
    uses (count ≡ filtered rows by construction), never a terms agg (overdue is an expression,
    not a field value). Requesting it without cutoffs is refused, same rule as the search body."""
    from backend.query.search import overdue_clause

    body = build_facets_body(SearchFilters(), fields=["overdue"], sla_cutoffs=_CUTOFFS)
    agg = body["aggs"]["overdue"]
    assert agg["filter"] == overdue_clause(_CUTOFFS)
    assert agg["aggs"]["by_scanner"]["terms"]["field"] == "scanner"  # per-scanner is sacred
    with pytest.raises(ValueError):
        build_facets_body(SearchFilters(), fields=["overdue"])


def test_composite_body_pages_via_after_key() -> None:
    body = build_composite_body(SearchFilters(scanner="trivy"), by="image_repo", size=100)
    comp = body["aggs"]["groups"]["composite"]
    assert comp["sources"] == [{"key": {"terms": {"field": "image_repo"}}}]
    assert comp["size"] == 100
    assert "after" not in comp
    assert body["aggs"]["groups"]["aggs"]["by_scanner"]["terms"]["field"] == "scanner"
    assert {"term": {"scanner": "trivy"}} in body["query"]["bool"]["filter"]

    paged = build_composite_body(SearchFilters(), by="image_repo", size=100, after={"key": "nginx"})
    assert paged["aggs"]["groups"]["composite"]["after"] == {"key": "nginx"}


def test_composite_by_is_whitelisted() -> None:
    with pytest.raises(ValueError):
        build_composite_body(SearchFilters(), by="severity", size=10)  # facet, not a group
    with pytest.raises(ValueError):
        build_composite_body(SearchFilters(), by="cluster_id", size=10)  # tenant, never a dim
    assert {"image_repo", "namespaces", "cve_id", "assignee", "image_digest"} <= set(GROUP_FIELDS)


def test_after_cursor_round_trips_and_rejects_garbage() -> None:
    after: dict[str, Any] = {"key": "registry/app"}
    assert decode_after(encode_after(after)) == after
    with pytest.raises(ValueError):
        decode_after("!!not-a-cursor!!")


def test_rail_dims_are_facetable_top_n() -> None:
    # M9b slice 4: namespaces/assignee are capped-with-intent rail dims — top-N by count for
    # the facet rail; their complete enumeration stays on the groups (composite) path.
    body = build_facets_body(SearchFilters(), fields=["namespaces", "assignee"])
    assert body["aggs"]["namespaces"]["terms"]["field"] == "namespaces"
    assert body["aggs"]["assignee"]["terms"]["field"] == "assignee"
    assert body["aggs"]["namespaces"]["terms"]["size"] == 32


def test_top_components_body_is_per_scanner_cardinality_only() -> None:
    # the Overview Top-components card: unique-CVE counts exist ONLY under the by_scanner
    # split — a top-level cardinality would dedupe CVEs across scanners (forbidden)
    body = build_top_components_body(SearchFilters(fixable=True))
    comp = body["aggs"]["components"]
    assert comp["terms"] == {"field": "package_name", "size": TOP_COMPONENTS_SIZE}
    by_scanner = comp["aggs"]["by_scanner"]
    assert by_scanner["terms"]["field"] == "scanner"
    assert by_scanner["aggs"]["unique_cves"] == {"cardinality": {"field": "cve_id"}}
    assert set(comp["aggs"]) == {"by_scanner"}  # no cross-scanner unique count, ever
    assert body["size"] == 0
    # the caller's filter context applies to the body like every other agg
    assert {"term": {"fixable": True}} in body["query"]["bool"]["filter"]


# issue 949, ruling 2: the namespace, package type and assignee facets leave out the filter
# of their OWN field, so a picked value does not hide the others from the list. Every other
# facet keeps the full filter context: the saved-view card count sums the severity facet
# under the view's filters, so severity must stay exactly as it is.
_OWN_FILTER_FREE = (("namespaces", "namespace"), ("ptype", "ptype"), ("assignee", "assignee"))


def _query_of(agg: dict[str, Any]) -> str:
    """The filter context an agg counts under, as text, for clause lookups."""
    return json.dumps(agg.get("filter", {}))


def test_no_own_field_filter_keeps_the_body_unchanged() -> None:
    """Zero cost when it does not apply: no wrapper, the same body as before issue 949."""
    f = SearchFilters(severity=["high"], scanner="trivy")
    body = build_facets_body(f, fields=["severity", "namespaces", "ptype", "assignee"])
    for name in ("severity", "namespaces", "ptype", "assignee"):
        assert "terms" in body["aggs"][name], name


@pytest.mark.parametrize(("facet", "param"), _OWN_FILTER_FREE)
@pytest.mark.parametrize("mode", ["", "exclude_"])
def test_a_list_facet_leaves_out_its_own_filter_only(facet: str, param: str, mode: str) -> None:
    f = SearchFilters(**dict[str, Any]({f"{mode}{param}": ["a"]}), severity=["high"])
    body = build_facets_body(f, fields=["severity", facet])
    field = "namespaces" if param == "namespace" else param
    own_clause = json.dumps({"terms": {field: ["a"]}})
    # the top-level query no longer carries the field's filter...
    assert own_clause not in json.dumps(body["query"])
    # ...the facet of that field counts without it, but with every other filter...
    own = body["aggs"][facet]
    assert own_clause not in _query_of(own)
    assert json.dumps({"terms": {"severity_canonical": ["high"]}}) in _query_of(own)
    assert own["aggs"]["values"]["terms"]["field"] == facet
    # ...and every other facet still counts under the field's filter
    assert own_clause in _query_of(body["aggs"]["severity"])
    assert body["aggs"]["severity"]["aggs"]["values"]["terms"]["field"] == "severity_canonical"


def test_two_list_facets_each_leave_out_only_their_own_filter() -> None:
    f = SearchFilters(namespace=["a", "b"], ptype=["deb"])
    body = build_facets_body(f, fields=["namespaces", "ptype"])
    ns, pt = body["aggs"]["namespaces"], body["aggs"]["ptype"]
    assert '"namespaces": ["a", "b"]' not in _query_of(ns)
    assert '"ptype": ["deb"]' in _query_of(ns)
    assert '"ptype": ["deb"]' not in _query_of(pt)
    assert '"namespaces": ["a", "b"]' in _query_of(pt)


def test_flag_facets_keep_the_full_filter_context_when_wrapped() -> None:
    """`overdue` and `unassigned` are filter aggs: with a list facet active they must still
    count under the namespace filter that the top-level query no longer carries."""
    f = SearchFilters(namespace=["a"])
    body = build_facets_body(
        f, fields=["namespaces", "unassigned", "overdue"], sla_cutoffs=_CUTOFFS
    )
    for name in ("unassigned", "overdue"):
        agg = body["aggs"][name]
        assert '"namespaces": ["a"]' in _query_of(agg), name
        assert "by_scanner" in agg["aggs"]["values"]["aggs"], name


def test_facet_buckets_unwraps_both_shapes() -> None:
    """The route reads one shape whether or not the body wrapped an agg."""
    plain = {"buckets": [{"key": "a", "doc_count": 1}]}
    wrapped = {"doc_count": 9, "values": plain}
    flag = {"doc_count": 3, "by_scanner": {"buckets": []}}
    wrapped_flag = {"doc_count": 9, "values": flag}
    assert facet_aggregation(plain) is plain
    assert facet_aggregation(wrapped) is plain
    assert facet_aggregation(flag) is flag
    assert facet_aggregation(wrapped_flag) is flag
