"""M6 slice 2 — scanner-faceted aggregations (FR-12): the pure DSL builders.

Pins: aggregation fields are WHITELISTED keyword/bool fields (never `text` — NFR-1); every
bucket carries a `by_scanner` sub-agg (per-scanner is sacred: the UI can always split, we never
force a cross-scanner merge); facet vocabularies use capped `terms`; high-cardinality grouping
uses a `composite` source paginating via `after_key` behind the same opaque-cursor contract as
search (no silently-capped buckets — DoD); the current filter context (SearchFilters) applies to
every aggregation body.
"""

import json
import uuid
from typing import Any

import pytest
from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import MUTABLE_INDEXES
from backend.query.aggs import (
    FACET_FIELDS,
    GROUP_FIELDS,
    ONE_PASS_TERMINATE_AFTER,
    SEARCHABLE_FACETS,
    SEVERITY_BUCKETS,
    TOP_COMPONENTS_SIZE,
    TOP_IMAGES_RANK,
    TOP_IMAGES_SIZE,
    TOP_VALUES_FIELDS,
    build_composite_body,
    build_facets_body,
    build_top_components_body,
    build_top_images_body,
    build_top_values_body,
    cap_value_search,
    contains_pattern,
    decode_after,
    encode_after,
    facet_aggregation,
    top_images_rows,
    top_values_rows,
)
from backend.query.search import SearchFilters, unassigned_clause
from os_env import OS_URL, requires_opensearch


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


def test_top_values_body_ranks_by_findings_with_each_scanner_apart() -> None:
    """Issue 1176: the Top CVEs board. The store ranks by findings, ties by the value; the
    severities count under each scanner only, so no count adds the two scanners' severities."""
    body = build_top_values_body(SearchFilters(fixable=True), "cve_id")
    values = body["aggs"]["values"]
    assert values["terms"] == {
        "field": "cve_id",
        "size": TOP_COMPONENTS_SIZE,
        "order": [{"_count": "desc"}, {"_key": "asc"}],
    }
    assert set(values["aggs"]) == {"by_scanner"}  # no severity split across the scanners
    by_scanner = values["aggs"]["by_scanner"]
    assert by_scanner["terms"]["field"] == "scanner"
    assert by_scanner["aggs"]["severity"]["terms"]["field"] == "severity_canonical"
    assert body["size"] == 0
    assert {"term": {"fixable": True}} in body["query"]["bool"]["filter"]
    assert body["terminate_after"] == ONE_PASS_TERMINATE_AFTER
    assert "terminate_after" not in build_top_values_body(SearchFilters(), "cve_id", exact=False)
    assert TOP_VALUES_FIELDS == ("cve_id",)
    with pytest.raises(ValueError):
        build_top_values_body(SearchFilters(), "assignee")


def test_top_values_rows_keep_the_store_order_and_each_scanner() -> None:
    def bucket(key: str, per: dict[str, dict[str, int]]) -> dict[str, Any]:
        scanners = [
            {
                "key": s,
                "doc_count": sum(sev.values()),
                "severity": {"buckets": [{"key": k, "doc_count": n} for k, n in sev.items()]},
            }
            for s, sev in per.items()
        ]
        return {
            "key": key,
            "doc_count": sum(s["doc_count"] for s in scanners),
            "by_scanner": {"buckets": scanners},
        }

    rows = top_values_rows(
        {
            "values": {
                "buckets": [
                    bucket("CVE-2", {"trivy": {"high": 2}, "grype": {"critical": 1}}),
                    bucket("CVE-1", {"grype": {"low": 1}}),
                ]
            }
        }
    )
    assert rows == [
        {
            "value": "CVE-2",
            "count": 3,
            "count_by_scanner": {"trivy": 2, "grype": 1},
            "severity_by_scanner": {"trivy": {"high": 2}, "grype": {"critical": 1}},
        },
        {
            "value": "CVE-1",
            "count": 1,
            "count_by_scanner": {"grype": 1},
            "severity_by_scanner": {"grype": {"low": 1}},
        },
    ]


def test_top_images_body_ranks_the_running_images_on_the_store() -> None:
    """Issue 1063: the filtered Riskiest images board. The store ranks the images by critical,
    then high, medium and low findings, and the body counts only the running digests."""
    body = build_top_images_body(SearchFilters(fixable=True), ["sha256:a", "sha256:b"])
    assert body["size"] == 0
    fl = body["query"]["bool"]["filter"]
    assert {"terms": {"image_digest": ["sha256:a", "sha256:b"]}} in fl
    assert {"term": {"fixable": True}} in fl  # the panel's filters apply
    images = body["aggs"]["images"]
    assert images["terms"]["field"] == "image_digest"
    assert images["terms"]["size"] == TOP_IMAGES_SIZE == 100
    assert images["terms"]["order"] == [
        {"crit": "desc"},
        {"high": "desc"},
        {"med": "desc"},
        {"low": "desc"},
        {"_key": "asc"},  # a tie keeps one order from read to read
    ]
    # one pass per shard, never segment slices, unless JAVV_EXACT_RANKING is off (issue 1063)
    assert body["terminate_after"] == ONE_PASS_TERMINATE_AFTER == 2**31 - 1
    assert "terminate_after" not in build_top_images_body(
        SearchFilters(), ["sha256:a"], exact=False
    )
    # each rank key counts the canonical severity, never the scanner's own word (D46)
    assert TOP_IMAGES_RANK == ("crit", "high", "med", "low")
    assert images["aggs"]["crit"] == {"filter": {"term": {"severity_canonical": "critical"}}}
    assert images["aggs"]["med"] == {"filter": {"term": {"severity_canonical": "medium"}}}


def test_top_images_body_counts_each_severity_per_scanner_only() -> None:
    images = build_top_images_body(SearchFilters(), ["sha256:a"])["aggs"]["images"]
    by_scanner = images["aggs"]["by_scanner"]
    assert by_scanner["terms"]["field"] == "scanner"
    assert by_scanner["aggs"]["severity"]["terms"] == {
        "field": "severity_canonical",
        "size": len(SEVERITY_BUCKETS),
    }
    # the severity counts exist only under the scanner split: two scanners are never one count
    assert set(images["aggs"]) == {*TOP_IMAGES_RANK, "by_scanner"}
    assert set(SEVERITY_BUCKETS.values()) == {"crit", "high", "med", "low", "negligible", "unknown"}


@requires_opensearch
async def test_top_images_body_ranks_an_image_spread_over_segments_first() -> None:
    """Issue 1063: the true top image has one critical finding in each of 6 segments; 1,200
    others have 3 in one segment. The index searches in 3 segment slices on any machine, as
    OpenSearch's default does on 7 CPUs or more: each slice keeps only its own top images."""
    client = AsyncOpenSearch(hosts=[OS_URL])
    index = f"t-topimg-{uuid.uuid4().hex[:8]}"
    findings = MUTABLE_INDEXES["findings"]
    settings = {
        **findings["settings"]["index"],
        "refresh_interval": -1,
        "search.concurrent_segment_search.mode": "auto",
        "search.concurrent.max_slice_count": 3,
    }
    await client.indices.create(
        index=index, body={"settings": {"index": settings}, "mappings": findings["mappings"]}
    )
    try:
        digests = ["sha256:x"] + [f"sha256:s{s}-{i:03d}" for s in range(6) for i in range(200)]
        doc = {
            "cluster_id": "c",
            "scanner": "trivy",
            "severity_canonical": "critical",
            "present": True,
        }
        for s in range(6):  # one refresh per batch: one segment per batch
            batch = ["sha256:x"] + [f"sha256:s{s}-{i:03d}" for i in range(200) for _ in range(3)]
            lines = [x for d in batch for x in ({"index": {}}, {**doc, "image_digest": d})]
            assert not (await client.bulk(index=index, body=lines))["errors"]
            await client.indices.refresh(index=index)

        async def first(body: dict[str, Any]) -> dict[str, Any]:
            resp = await client.search(index=index, body=body)
            return top_images_rows(resp["aggregations"])[0]

        exact = build_top_images_body(SearchFilters(), digests)
        row = await first(exact)
        assert row["image_digest"] == "sha256:x"
        assert row["severity_by_scanner"]["trivy"]["crit"] == 6

        # the control: the same index searched in slices loses the image
        sliced = build_top_images_body(SearchFilters(), digests, exact=False)
        assert (await first(sliced))["image_digest"] != "sha256:x"
    finally:
        await client.indices.delete(index=index)
        await client.close()


def test_top_images_body_needs_the_cutoffs_for_an_overdue_filter() -> None:
    with pytest.raises(ValueError):
        build_top_images_body(SearchFilters(overdue=True), ["sha256:a"])
    body = build_top_images_body(SearchFilters(overdue=True), ["sha256:a"], sla_cutoffs=_CUTOFFS)
    assert {"terms": {"image_digest": ["sha256:a"]}} in body["query"]["bool"]["filter"]


# issue 949, ruling 2: the namespace, package type and assignee facets leave out the filter
# of their OWN field, so a picked value does not hide the others from the list. Every other
# facet keeps the full filter context: the saved-view card count sums the severity facet
# under the view's filters, so severity must stay exactly as it is.
_OWN_FILTER_FREE = (("namespaces", "namespace"), ("ptype", "ptype"), ("assignee", "assignee"))


def _query_of(agg: dict[str, Any]) -> str:
    """The filter context an agg counts under, as text, for clause lookups."""
    return json.dumps(agg.get("filter", {}))


def test_no_own_field_filter_keeps_the_body_unchanged(monkeypatch) -> None:
    """Zero cost when it does not apply: no wrapper, the same body as before issue 949. The
    body with no freed facets at all is the reference, so the whole body is compared."""
    from backend.query import aggs

    f = SearchFilters(severity=["high"], scanner="trivy", cve_id=["CVE-1"])
    fields = ["severity", "namespaces", "ptype", "assignee"]
    body = build_facets_body(f, fields=fields)
    monkeypatch.setattr(aggs, "OWN_FILTER_FREE_FACETS", {})
    assert body == build_facets_body(f, fields=fields)
    for name in fields:
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


_ASSIGNEE_IS = json.dumps({"terms": {"assignee": ["lead"]}})


def test_the_unassigned_count_leaves_out_assignee_is() -> None:
    """Issue 979: a click on Unassigned clears the Assignee "is" values (issue 975), so the
    Unassigned count is what the grid shows after the click: every other filter, no Assignee."""
    f = SearchFilters(assignee=["lead"], severity=["high"])
    body = build_facets_body(f, fields=["severity", "unassigned"])
    unassigned = body["aggs"]["unassigned"]
    assert _ASSIGNEE_IS not in _query_of(unassigned)
    assert json.dumps({"terms": {"severity_canonical": ["high"]}}) in _query_of(unassigned)
    assert "by_scanner" in unassigned["aggs"]["values"]["aggs"]
    # the other facets still count with the Assignee filter, and the grid query keeps it
    assert _ASSIGNEE_IS in _query_of(body["aggs"]["severity"])
    assert _ASSIGNEE_IS not in json.dumps(body["query"])


@pytest.mark.parametrize("mode", ["", "exclude_"])
def test_all_filters_counts_every_facet_under_every_filter(mode: str) -> None:
    """Issue 999, decision 4: a dashboard panel that lists namespaces with "Namespace is not
    kube-system" must leave that row out. With `all_filters`, no facet is freed: the body is
    the plain one, every facet a direct `terms` or `filter` agg under the whole query."""
    f = SearchFilters(
        **dict[str, Any]({f"{mode}namespace": ["a"], f"{mode}ptype": ["deb"]}),
        assignee=["lead"],
    )
    fields = ["severity", "namespaces", "ptype", "assignee", "unassigned"]
    body = build_facets_body(f, fields=fields, all_filters=True)
    query = json.dumps(body["query"])
    for clause in ({"namespaces": ["a"]}, {"ptype": ["deb"]}, {"assignee": ["lead"]}):
        assert json.dumps({"terms": clause}) in query, clause
    for name in fields:
        assert "values" not in body["aggs"][name].get("aggs", {}), name
    # the default is unchanged: the same filters free the list facets
    assert "values" in build_facets_body(f, fields=fields)["aggs"]["namespaces"]["aggs"]


def test_the_unassigned_count_keeps_assignee_is_not() -> None:
    """The click keeps Assignee "is not" (the API takes that pair), so the count keeps it."""
    f = SearchFilters(exclude_assignee=["lead"])
    body = build_facets_body(f, fields=["severity", "unassigned"])
    assert "values" not in body["aggs"]["unassigned"].get("aggs", {})  # no wrapper needed
    assert json.dumps({"terms": {"assignee": ["lead"]}}) in json.dumps(body["query"])


def test_assignee_and_unassigned_counts_together_with_assignee_is() -> None:
    """The Assignee list leaves out its own include and exclude. The Unassigned count leaves out
    only the include. Both are freed at once, and the rest of the rail keeps the filter."""
    f = SearchFilters(assignee=["lead"], namespace=["shop"])
    body = build_facets_body(f, fields=["assignee", "unassigned", "kev"])
    for name in ("assignee", "unassigned"):
        assert _ASSIGNEE_IS not in _query_of(body["aggs"][name]), name
        assert '"namespaces": ["shop"]' in _query_of(body["aggs"][name]), name
    assert _ASSIGNEE_IS in _query_of(body["aggs"]["kev"])


def test_with_no_assignee_the_unassigned_count_is_unchanged() -> None:
    """No Assignee "is": the Unassigned count is the plain filter agg, under the full query."""
    f = SearchFilters(severity=["high"])
    body = build_facets_body(f, fields=["severity", "unassigned"])
    assert body["aggs"]["unassigned"] == {
        "filter": unassigned_clause(),
        "aggs": {"by_scanner": {"terms": {"field": "scanner", "size": 4}}},
    }


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


# issue 1064: a value search. The user types some letters and the server sends the values of
# one list facet that contain them, from all values and not only the top 32.


@pytest.mark.parametrize(
    ("text", "pattern"),
    [
        ("pay", ".*[pP][aA][yY].*"),
        ("PaY", ".*[pP][aA][yY].*"),  # the case of the text does not matter
        ("eu-7", ".*[eE][uU]\\-7.*"),
        # every regex operator is escaped, so the text cannot change the pattern
        (
            'a.b*c?+|{}[]()"\\#@&<>~',
            '.*[aA]\\.[bB]\\*[cC]\\?\\+\\|\\{\\}\\[\\]\\(\\)\\"\\\\\\#\\@\\&\\<\\>\\~.*',
        ),
        ("ns 1", ".*[nN][sS]\\ 1.*"),
        ("Ärzte", ".*[äÄ][rR][zZ][tT][eE].*"),
    ],
)
def test_the_contains_pattern_matches_the_text_in_any_case(text: str, pattern: str) -> None:
    assert contains_pattern(text) == pattern


def test_the_contains_pattern_matches_values_as_the_store_reads_it() -> None:
    """The store reads `include` as a Lucene regex over the whole value. Python's `re` reads the
    same subset the same way, so a full match here is a full match there."""
    import re

    rx = re.compile(contains_pattern("Pay"))
    assert rx.fullmatch("payments-EU-7")
    assert rx.fullmatch("PAYROLL")
    assert rx.fullmatch("team-pay")
    assert not rx.fullmatch("billing")
    dot = re.compile(contains_pattern("a.b"))
    assert dot.fullmatch("xa.by") and not dot.fullmatch("axb")


@pytest.mark.parametrize("field", SEARCHABLE_FACETS)
def test_a_value_search_asks_one_more_bucket_than_the_cap(field: str) -> None:
    body = build_facets_body(SearchFilters(), fields=[field], contains="pay")
    terms = body["aggs"][field]["terms"]
    assert terms["size"] == 33  # 32 to show, and one more that tells "more values match"
    assert terms["include"] == contains_pattern("pay")
    assert terms["field"] == field
    assert body["aggs"][field]["aggs"]["by_scanner"]["terms"]["field"] == "scanner"


def test_a_value_search_keeps_the_filter_rules_of_its_facet() -> None:
    """The counts of a search use the same filters as the list: the facet leaves out its own
    field (issue 949), and with all_filters it keeps it (issue 999)."""
    f = SearchFilters(namespace=["payments"], severity=["high"])
    own_free = build_facets_body(f, fields=["namespaces"], contains="pay")
    counted = own_free["aggs"]["namespaces"]["filter"]
    assert '"payments"' not in json.dumps(counted) and '"high"' in json.dumps(counted)
    assert own_free["aggs"]["namespaces"]["aggs"]["values"]["terms"]["include"]
    every = build_facets_body(f, fields=["namespaces"], contains="pay", all_filters=True)
    assert '"payments"' in json.dumps(every["query"])
    assert every["aggs"]["namespaces"]["terms"]["include"]


@pytest.mark.parametrize(
    "fields",
    [None, [], ["namespaces", "assignee"], ["severity"], ["state"], ["overdue"], ["unassigned"]],
)
def test_a_value_search_takes_exactly_one_list_facet(fields: list[str] | None) -> None:
    with pytest.raises(ValueError):
        build_facets_body(SearchFilters(), fields=fields, contains="pay", sla_cutoffs=_CUTOFFS)


def test_a_value_search_sends_the_cap_and_tells_when_more_match() -> None:
    assert cap_value_search(list(range(33))) == (list(range(32)), True)
    assert cap_value_search(list(range(32))) == (list(range(32)), False)
    assert cap_value_search([]) == ([], False)


def test_no_value_search_keeps_the_body_unchanged() -> None:
    body = build_facets_body(SearchFilters(), fields=["namespaces"])
    assert body["aggs"]["namespaces"]["terms"] == {"field": "namespaces", "size": 32}
