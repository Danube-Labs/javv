"""Scanner-faceted aggregations (M6 slice 2, FR-12) — pure DSL builders.

Two shapes, both `size:0` (counts come from aggregations, raw findings never ship to the
client — server-side-everything):

- **Facets** — capped `terms` over WHITELISTED bounded-vocabulary keyword/bool fields
  (severity/state/scanner/…). Whitelisting is the "never aggregate on `text`" guard (NFR-1)
  made structural.
- **Groups** — one `composite` source over a whitelisted high-cardinality keyword dim
  (image_repo/namespaces/cve_id/…), paginating via `after_key` behind the same opaque-cursor
  contract as search — every bucket is reachable, none silently capped (DoD).

Every bucket carries a `by_scanner` sub-agg: per-scanner is sacred (the UI can always split;
a cross-scanner merge is never forced). The caller's SearchFilters context applies to every
body, and `tenant_query` (the tenant read path) forces the cluster filter on top at execution.
"""

import base64
import binascii
import json
from dataclasses import replace
from typing import Any

from backend.query.search import (
    SearchFilters,
    build_search_body,
    overdue_clause,
    unassigned_clause,
)

# bounded-vocabulary fields — capped terms cannot truncate these (NFR-1: keyword/bool only) —
# plus two capped-WITH-INTENT rail dims (M9b slice 4): `namespaces`/`assignee` show the top-N
# by count (that is what a facet rail is); their COMPLETE enumeration stays groups territory.
FACET_FIELDS = (
    "severity",
    "state",
    "scanner",
    "fixable",
    "kev",
    "disagree",
    "present",
    "ptype",
    "namespaces",
    "assignee",
    "overdue",  # issue 363: a filter agg over the overdue clause, not a terms agg
    "unassigned",  # issue 349 §1: likewise an expression (absence), not a term
)
_FACET_TERMS_SIZE = 32  # ≥ the largest bounded vocabulary; the top-N cap for the rail dims

# pre-M8d findings carry ptype: null until a v4 sweep re-observes them (D30) — the facet shows
# them as an explicit "unknown" bucket rather than silently dropping the rows (the B-1 caveat)
_FACET_MISSING = {"ptype": "unknown"}

# D46/#274: the API keeps `severity` as the facet NAME, but the agg targets the full-word
# canonical query key — bucket keys are `critical`/`medium`/…, never the verbatim scanner word
_FACET_FIELD_ALIAS = {"severity": "severity_canonical"}

# high-cardinality keyword dims — composite/after_key territory, never a capped terms
GROUP_FIELDS = ("image_repo", "image_digest", "namespaces", "cve_id", "assignee", "app", "ptype")

_BY_SCANNER = {"by_scanner": {"terms": {"field": "scanner", "size": 4}}}


def _base(filters: SearchFilters, sla_cutoffs: dict[str, str] | None = None) -> dict[str, Any]:
    """The filter context, agg-shaped: same facets as the grid, no hits, no sort."""
    body = build_search_body(filters, size=0, sla_cutoffs=sla_cutoffs)
    del body["sort"], body["track_total_hits"]
    return body


# facet name -> the SearchFilters field whose filter that facet leaves out (issue 949, ruling
# 2). These facets list the values a user picks several of, so a pick must not hide the other
# values. Only these three: the saved-view card count sums the severity facet under the view's
# own filters, so severity, state and scanner keep the full filter context.
OWN_FILTER_FREE_FACETS = {"namespaces": "namespace", "ptype": "ptype", "assignee": "assignee"}


def without_own_filter(filters: SearchFilters, facet: str) -> SearchFilters:
    """The filters a facet in OWN_FILTER_FREE_FACETS counts under: all but its own field's
    include and exclude."""
    field = OWN_FILTER_FREE_FACETS[facet]
    return replace(filters, **{field: None, f"exclude_{field}": None})


def counting_filters(filters: SearchFilters, facet: str) -> SearchFilters:
    """The filters one facet counts under. A list facet leaves out its own field (issue 949).
    The Unassigned count leaves out the Assignee "is" values (issue 979): a click on Unassigned
    clears them (issue 975), so the count is what the click shows. Assignee "is not" stays,
    because the click keeps it."""
    own = OWN_FILTER_FREE_FACETS.get(facet)
    if own is not None and (getattr(filters, own) or getattr(filters, f"exclude_{own}")):
        return without_own_filter(filters, facet)
    if facet == "unassigned" and filters.assignee:
        return replace(filters, assignee=None)
    return filters


def facet_aggregation(agg: dict[str, Any]) -> dict[str, Any]:
    """One facet's aggregation from the response, whether or not the body wrapped it in its
    own filter context (see build_facets_body)."""
    return agg.get("values", agg)


def build_facets_body(
    filters: SearchFilters,
    fields: list[str] | None = None,
    *,
    sla_cutoffs: dict[str, str] | None = None,
    all_filters: bool = False,
) -> dict[str, Any]:
    """`all_filters`: every facet counts under every filter, its own field's too. A dashboard
    panel that lists namespaces with "Namespace is not kube-system" must leave that row out
    (issue 999, decision 4); the Findings filter list keeps the default."""
    chosen = fields if fields is not None else list(FACET_FIELDS)
    bad = [f for f in chosen if f not in FACET_FIELDS]
    if bad:
        raise ValueError(f"not facetable (whitelist {FACET_FIELDS}): {bad}")
    body = _base(filters, sla_cutoffs)
    body["aggs"] = {
        f: {
            "terms": {
                "field": _FACET_FIELD_ALIAS.get(f, f),
                "size": _FACET_TERMS_SIZE,
                **({"missing": _FACET_MISSING[f]} if f in _FACET_MISSING else {}),
            },
            "aggs": dict(_BY_SCANNER),
        }
        for f in chosen
        if f not in ("overdue", "unassigned")
    }
    if "overdue" in chosen:
        # the rail chip's count (issue 363): overdue is an EXPRESSION over the materialized
        # clock, so its facet is a `filter` agg on the same clause the grid filter uses —
        # count ≡ filtered rows by construction. Cutoffs required, same rule as the search body.
        if sla_cutoffs is None:
            raise ValueError("the overdue facet requires sla_cutoffs (from the live SLA policy)")
        body["aggs"]["overdue"] = {"filter": overdue_clause(sla_cutoffs), "aggs": dict(_BY_SCANNER)}
    if "unassigned" in chosen:
        # the rail flag's count: absence is an expression, so the facet reuses the grid's own
        # clause — count ≡ filtered rows by construction, same contract as overdue
        body["aggs"]["unassigned"] = {"filter": unassigned_clause(), "aggs": dict(_BY_SCANNER)}
    freed = [] if all_filters else [f for f in chosen if counting_filters(filters, f) != filters]
    if not freed:
        return body
    # disjunctive facets: the top-level query drops the filters that the freed facets leave
    # out, and each facet counts inside a `filter` agg that puts back every filter it counts
    # under. Other facets get the full query back, so their counts do not change.
    top = filters
    for f in freed:
        top = counting_filters(top, f)
    full = body["query"]
    wrapped = _base(top, sla_cutoffs)
    wrapped["aggs"] = {
        name: {
            "filter": (
                _base(counting_filters(filters, name), sla_cutoffs)["query"]
                if name in freed
                else full
            ),
            "aggs": {"values": agg},
        }
        for name, agg in body["aggs"].items()
    }
    return wrapped


# the Overview Top-components board cap — the contributors-leaderboard model (a ≤100-row
# server board the card pages as display slices), not a tunable
TOP_COMPONENTS_SIZE = 100


def build_top_components_body(filters: SearchFilters) -> dict[str, Any]:
    """Top components (Overview card): capped `terms` over `package_name` ordered by finding
    rows, each bucket carrying a PER-SCANNER unique-CVE cardinality. There is deliberately no
    cross-scanner cardinality — distinct CVEs across scanners would be a merge (per-scanner is
    sacred); the "all scanners" display adds the per-scanner uniques, same additive grammar as
    every facet."""
    body = _base(filters)
    body["aggs"] = {
        "components": {
            "terms": {"field": "package_name", "size": TOP_COMPONENTS_SIZE},
            "aggs": {
                "by_scanner": {
                    "terms": {"field": "scanner", "size": 4},
                    "aggs": {"unique_cves": {"cardinality": {"field": "cve_id"}}},
                }
            },
        }
    }
    return body


def build_composite_body(
    filters: SearchFilters,
    *,
    by: str,
    size: int,
    after: dict[str, Any] | None = None,
    sla_cutoffs: dict[str, str] | None = None,
) -> dict[str, Any]:
    if by not in GROUP_FIELDS:
        raise ValueError(f"not groupable (whitelist {GROUP_FIELDS}): {by!r}")
    composite: dict[str, Any] = {
        "sources": [{"key": {"terms": {"field": by}}}],
        "size": size,
    }
    if after is not None:
        composite["after"] = after
    body = _base(filters, sla_cutoffs)
    body["aggs"] = {"groups": {"composite": composite, "aggs": dict(_BY_SCANNER)}}
    return body


def encode_after(after: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(after).encode()).decode()


def decode_after(cursor: str) -> dict[str, Any]:
    try:
        after = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(after, dict):
            raise ValueError("after cursor must decode to an object")
        # a composite `after_key` is {source: scalar}; a nested/non-scalar value would sail past
        # decode and blow up inside the aggregation (500) — reject the tampered shape here (A-m1)
        if not all(v is None or isinstance(v, (str, int, float, bool)) for v in after.values()):
            raise ValueError("after cursor values must be scalars")
        return after
    except (binascii.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("invalid cursor") from exc
