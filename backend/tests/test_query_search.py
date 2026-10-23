"""M6 slice 1 — faceted findings search (FR-12): the pure DSL builder + cursor + PIT lifecycle.

Pins: every filter lands as a `filter` term (never scoring `must`); `present=true` is the
DEFAULT "now"-grid filter (D39 — tombstones are opt-in); sort is whitelisted with a stable
`finding_key` tiebreak so paging is deterministic; the cursor is opaque (base64 JSON, never a
raw search_after contract); the PIT is deleted the moment a page is final (finally on error,
last-page short-circuit) — D38.
"""

import base64
import json
from typing import Any

import pytest
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import NotFoundError

from backend.query.search import (
    FILTER_PAIRS,
    CursorExpired,
    SearchFilters,
    build_search_body,
    conflicting_filter_pair,
    decode_cursor,
    encode_cursor,
    has_owner_clause,
    run_search,
    unassigned_clause,
)


def test_default_body_filters_present_true_and_sorts_stably() -> None:
    body = build_search_body(SearchFilters(), size=50)
    assert {"term": {"present": True}} in body["query"]["bool"]["filter"]
    # stable paging: whitelisted sort field + the unique-key tiebreak (api-design standard)
    assert body["sort"] == [
        {"severity_rank": {"order": "desc"}},
        {"finding_key": {"order": "asc"}},
    ]
    assert body["size"] == 50
    assert body["track_total_hits"] is True


def test_every_facet_filter_is_a_filter_clause_never_scoring() -> None:
    f = SearchFilters(
        severity=["critical", "high"],
        state=["open"],
        scanner="trivy",
        assignee=["ana"],
        kev=True,
        fixable=True,
        disagree=False,
        cve_id=["CVE-2024-1"],
        image_digest="sha256:abc123",
        image_repo=["nginx"],
        namespace=["prod"],
    )
    body = build_search_body(f, size=10)
    fl = body["query"]["bool"]["filter"]
    # D46/#274: the filter targets the canonical query key, never the verbatim word
    assert {"terms": {"severity_canonical": ["critical", "high"]}} in fl
    assert {"terms": {"state": ["open"]}} in fl
    assert {"term": {"scanner": "trivy"}} in fl
    assert {"terms": {"assignee": ["ana"]}} in fl
    assert {"term": {"kev": True}} in fl
    assert {"term": {"fixable": True}} in fl
    assert {"term": {"disagree": False}} in fl  # False is a real filter, not "unset"
    assert {"terms": {"cve_id": ["CVE-2024-1"]}} in fl
    assert {"term": {"image_digest": "sha256:abc123"}} in fl
    assert {"terms": {"image_repo": ["nginx"]}} in fl
    assert {"terms": {"namespaces": ["prod"]}} in fl  # keyword[] — array-contains semantics
    assert "must" not in body["query"]["bool"]  # facets never score


def test_new_within_days_is_a_range_filter_on_the_trend_window_start() -> None:
    from backend.query.trends import window_bounds

    body = build_search_body(SearchFilters(new_within_days=30), size=1)
    gte, _upper = window_bounds(30)
    assert {"range": {"first_seen_at": {"gte": gte}}} in body["query"]["bool"]["filter"]
    # absent by default — the flag is opt-in, never an implicit recency cut
    default = build_search_body(SearchFilters(), size=1)
    assert not [c for c in default["query"]["bool"]["filter"] if "range" in c]


def test_present_false_is_expressible_for_the_tombstone_view() -> None:
    body = build_search_body(SearchFilters(present=False), size=10)
    assert {"term": {"present": False}} in body["query"]["bool"]["filter"]


def test_sort_field_is_whitelisted() -> None:
    body = build_search_body(SearchFilters(), size=10, sort="first_seen_at", order="asc")
    assert body["sort"][0] == {"first_seen_at": {"order": "asc"}}
    with pytest.raises(ValueError):
        build_search_body(SearchFilters(), size=10, sort="cluster_id")  # not a sort key


def test_search_after_is_attached_only_when_paging() -> None:
    assert "search_after" not in build_search_body(SearchFilters(), size=10)
    body = build_search_body(SearchFilters(), size=10, search_after=[5, "fk-1"])
    assert body["search_after"] == [5, "fk-1"]


def test_cursor_round_trips_and_rejects_garbage() -> None:
    cur = encode_cursor(
        pit_id="pit-abc", search_after=[5, "fk-1"], sort="severity_rank", order="desc"
    )
    pit_id, search_after, sort, order, sla_cutoffs = decode_cursor(cur)
    assert (pit_id, search_after, sort, order) == ("pit-abc", [5, "fk-1"], "severity_rank", "desc")
    assert sla_cutoffs is None  # absent unless the walk carries an overdue lens
    with pytest.raises(ValueError):
        decode_cursor("not-base64-json!!")


_CUTOFFS = {
    "kev": "2026-07-11T00:00:00+00:00",
    "critical": "2026-07-10T00:00:00+00:00",
    "high": "2026-07-05T00:00:00+00:00",
    "medium": "2026-06-12T00:00:00+00:00",
    "low": "2026-04-13T00:00:00+00:00",
}


def test_cursor_freezes_overdue_cutoffs_for_the_whole_walk() -> None:
    """Issue 363: the PIT freezes the docs, so the query must freeze too — cutoffs ride the
    cursor and round-trip exactly; a wall-clock cutoff drifting between pages could flip a
    row's match mid-walk. Tampered cutoff shapes are a 422 at decode, never a 500."""
    cur = encode_cursor(
        pit_id="p", search_after=[1], sort="severity_rank", order="desc", sla_cutoffs=_CUTOFFS
    )
    *_, sla_cutoffs = decode_cursor(cur)
    assert sla_cutoffs == _CUTOFFS
    for bad in (
        {"kev": "x"},  # missing severity keys
        {**_CUTOFFS, "critical": 5},  # non-string cutoff
        {**_CUTOFFS, "extra": "x"},  # unknown key
    ):
        tampered = base64.urlsafe_b64encode(
            json.dumps({"p": "p", "a": [1], "s": "severity_rank", "o": "desc", "sc": bad}).encode()
        ).decode()
        with pytest.raises(ValueError):
            decode_cursor(tampered)


def test_overdue_filter_mirrors_compute_overdue_and_requires_cutoffs() -> None:
    """Issue 363: the DSL clause is the exact mirror of the read-time verdict — KEV fast-lane
    wins (severity branches exclude kev rows), negligible/unknown carry no SLA branch, handled
    states are excluded via the SHARED constant (chip ≡ filter), strict `lt` (due == now is
    due, not past-due). Without cutoffs the builder refuses — no consumer can silently drop
    the lens."""
    from backend.sla.overdue import HANDLED_STATES

    body = build_search_body(SearchFilters(overdue=True), size=10, sla_cutoffs=_CUTOFFS)
    clause = next(c for c in body["query"]["bool"]["filter"] if "bool" in c)["bool"]
    assert clause["minimum_should_match"] == 1
    assert clause["must_not"] == [{"terms": {"state": sorted(HANDLED_STATES)}}]
    kev_branch, *sev_branches = clause["should"]
    assert kev_branch["bool"]["filter"] == [
        {"term": {"kev": True}},
        {"range": {"sla_clock_at": {"lt": _CUTOFFS["kev"]}}},
    ]
    assert [b["bool"]["filter"][0] for b in sev_branches] == [
        {"term": {"severity_canonical": s}} for s in ("critical", "high", "medium", "low")
    ]  # negligible/unknown have NO branch — they carry no SLA (FR-10 ruling)
    for branch, sev in zip(sev_branches, ("critical", "high", "medium", "low"), strict=True):
        assert branch["bool"]["filter"][1] == {"range": {"sla_clock_at": {"lt": _CUTOFFS[sev]}}}
        assert branch["bool"]["must_not"] == [{"term": {"kev": True}}]  # the fast-lane owns kev

    # overdue=False is the clause negated — NOT-overdue includes handled and no-SLA rows
    body_f = build_search_body(SearchFilters(overdue=False), size=10, sla_cutoffs=_CUTOFFS)
    assert body_f["query"]["bool"]["must_not"] == [
        next(c for c in body["query"]["bool"]["filter"] if "bool" in c)
    ]

    with pytest.raises(ValueError):  # the lens without cutoffs is unbuildable, never ignored
        build_search_body(SearchFilters(overdue=True), size=10)


def test_overdue_cutoffs_derive_from_the_live_policy() -> None:
    """A policy edit moves every cutoff instantly (the whole point of storing the clock,
    never the verdict) — and strict-`lt` semantics match compute_overdue's `now > due`."""
    from datetime import UTC, datetime, timedelta

    from backend.sla.overdue import overdue_cutoffs
    from backend.sla.policy import SlaPolicy

    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    cut = overdue_cutoffs(SlaPolicy(), now=now)
    assert cut["kev"] == (now - timedelta(days=1)).isoformat()
    assert cut["critical"] == (now - timedelta(days=2)).isoformat()
    assert cut["low"] == (now - timedelta(days=90)).isoformat()
    edited = overdue_cutoffs(SlaPolicy(critical_days=10), now=now)
    assert edited["critical"] == (now - timedelta(days=10)).isoformat()


def test_decode_cursor_rejects_decodable_but_tampered_fields() -> None:
    """A-m1 (audit #191): a base64/JSON-valid cursor with tampered fields must be a 422 at decode,
    not sail through and blow up (500) inside client.search."""

    def cur(**over: Any) -> str:
        d = {"p": "pit", "a": [5, "fk"], "s": "severity_rank", "o": "desc", **over}
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode()

    decode_cursor(cur())  # the baseline shape is fine
    for bad in (
        cur(a="notalist"),  # search_after must be a list
        cur(a=[{"nested": 1}]),  # …of scalars, never nested objects
        cur(p=123),  # pit_id must be a string
        cur(s=["severity_rank"]),  # sort must be a string
    ):
        with pytest.raises(ValueError):
            decode_cursor(bad)


class _PitOS:
    """Stub client: canned pages, records PIT create/delete + every search body."""

    def __init__(self, pages: list[list[dict[str, Any]]]):
        self._pages = pages
        self.created: int = 0
        self.deleted: list[str] = []
        self.bodies: list[dict[str, Any]] = []

    async def create_pit(self, *a: Any, **kw: Any) -> dict[str, Any]:
        self.created += 1
        return {"pit_id": f"pit-{self.created}"}

    async def delete_pit(self, body: dict[str, Any]) -> dict[str, Any]:
        self.deleted += body["pit_id"]  # the API takes {"pit_id": [ids]}
        return {}

    async def search(self, **kw: Any) -> dict[str, Any]:
        self.bodies.append(kw["body"])
        page = self._pages.pop(0)
        return {
            "hits": {
                "total": {"value": 3, "relation": "eq"},
                "hits": [
                    {"_source": doc, "sort": [doc["severity_rank"], doc["finding_key"]]}
                    for doc in page
                ],
            }
        }


def _doc(i: int) -> dict[str, Any]:
    return {"finding_key": f"fk-{i}", "severity_rank": 5 - i, "cluster_id": "c-unit-search"}


async def test_run_search_full_page_returns_cursor_and_keeps_pit() -> None:
    fake = _PitOS(pages=[[_doc(0), _doc(1)]])
    out = await run_search(fake, cluster_id="c-unit-search", filters=SearchFilters(), size=2)  # type: ignore[arg-type]
    assert [d["finding_key"] for d in out["data"]] == ["fk-0", "fk-1"]
    assert out["next_cursor"] is not None
    assert out["total"] == {"value": 3, "relation": "eq"}
    assert fake.created == 1 and fake.deleted == []  # a live cursor keeps its PIT
    # the tenant filter is structurally present even on the PIT path (SEC-4)
    assert {"term": {"cluster_id": "c-unit-search"}} in fake.bodies[0]["query"]["bool"]["filter"]
    assert "pit" in fake.bodies[0]


async def test_run_search_short_page_deletes_pit_and_ends_cursor() -> None:
    fake = _PitOS(pages=[[_doc(0)]])
    out = await run_search(fake, cluster_id="c-unit-search", filters=SearchFilters(), size=2)  # type: ignore[arg-type]
    assert out["next_cursor"] is None
    assert fake.deleted == ["pit-1"]  # last page → the PIT dies with it (D38)


async def test_run_search_resumes_from_cursor() -> None:
    fake = _PitOS(pages=[[_doc(2)]])
    cur = encode_cursor(
        pit_id="pit-live", search_after=[4, "fk-1"], sort="severity_rank", order="desc"
    )
    out = await run_search(
        fake,  # type: ignore[arg-type]
        cluster_id="c-unit-search",
        filters=SearchFilters(),
        size=2,
        cursor=cur,
    )
    assert fake.created == 0  # resumed, not reopened
    assert fake.bodies[0]["search_after"] == [4, "fk-1"]
    assert fake.bodies[0]["pit"]["id"] == "pit-live"
    assert out["next_cursor"] is None and fake.deleted == ["pit-live"]


async def test_keep_open_keeps_a_continuations_pit_past_its_final_page() -> None:
    """Issue 832: a client that may page back keeps the walk's PIT and closes it itself. A first
    page that is also its last still closes it: the client has no cursor to close it by."""
    cur = encode_cursor(
        pit_id="pit-live", search_after=[4, "fk-1"], sort="severity_rank", order="desc"
    )
    kept = _PitOS(pages=[[_doc(2)]])
    out = await run_search(
        kept,  # type: ignore[arg-type]
        cluster_id="c-unit-search",
        filters=SearchFilters(),
        size=2,
        cursor=cur,
        keep_open=True,
    )
    assert out["next_cursor"] is None and kept.deleted == []

    first = _PitOS(pages=[[_doc(0)]])
    out = await run_search(
        first,  # type: ignore[arg-type]
        cluster_id="c-unit-search",
        filters=SearchFilters(),
        size=2,
        keep_open=True,
    )
    assert out["next_cursor"] is None and first.deleted == ["pit-1"]


async def test_run_search_deletes_a_fresh_pit_on_error(monkeypatch) -> None:
    class _Boom(_PitOS):
        async def search(self, **kw: Any) -> dict[str, Any]:
            raise RuntimeError("shard exploded")

    # capture_logs can't see a proxy already bound under the cached prod config — swap fresh
    import structlog

    from backend.query import search as search_module

    monkeypatch.setattr(search_module, "log", structlog.get_logger())

    fake = _Boom(pages=[])
    with structlog.testing.capture_logs() as logs, pytest.raises(RuntimeError):
        await run_search(fake, cluster_id="c-unit-search", filters=SearchFilters(), size=2)  # type: ignore[arg-type]
    assert fake.deleted == ["pit-1"]  # no orphaned PIT on the error path (D38)
    # the reclaim is observable — a blown-up page is an operational event, not a silent retry
    assert any(
        e["event"] == "search page failed — PIT reclaimed" and e["log_level"] == "warning"
        for e in logs
    )


def _cursor_for(pit_id: str) -> str:
    return encode_cursor(
        pit_id=pit_id, search_after=[4, "fk-1"], sort="severity_rank", order="desc"
    )


async def test_run_search_maps_expired_cursor_pit_to_cursor_expired() -> None:
    """A-m1 (audit #191): a cursor whose PIT OpenSearch no longer holds (idled past keep_alive)
    raises CursorExpired (→ 410), never a 500 — and the already-gone PIT is not re-reclaimed."""

    class _Gone(_PitOS):
        async def search(self, **kw: Any) -> dict[str, Any]:
            raise NotFoundError(404, "search_context_missing_exception", {})

    fake = _Gone(pages=[])
    with pytest.raises(CursorExpired):
        await run_search(
            fake,  # type: ignore[arg-type]
            cluster_id="c-unit-search",
            filters=SearchFilters(),
            size=2,
            cursor=_cursor_for("pit-dead"),
        )
    assert fake.deleted == []  # a gone PIT is never reclaimed; a fresh walk is unaffected


async def test_run_search_keeps_a_cursor_pit_on_a_transient_page_error() -> None:
    """A-m1 (audit #191): a transient transport hiccup on a cursor page must NOT reclaim the
    client-owned PIT — the walk can retry. Only a PIT this call opened is reclaimed on error."""

    class _Hiccup(_PitOS):
        async def search(self, **kw: Any) -> dict[str, Any]:
            raise OSConnectionError("N/A", "connection refused", None)

    fake = _Hiccup(pages=[])
    with pytest.raises(OSConnectionError):
        await run_search(
            fake,  # type: ignore[arg-type]
            cluster_id="c-unit-search",
            filters=SearchFilters(),
            size=2,
            cursor=_cursor_for("pit-live"),
        )
    assert fake.deleted == []  # the client's PIT survives to keep_alive for a retry


def test_q_contains_search_is_structured_and_escaped() -> None:
    # M9b slice 4: contains across the identifier fields — structured wildcards, never
    # query_string; user wildcards are escaped so a crafted pattern can't go pathological
    body = build_search_body(SearchFilters(q="krb5"), size=10)
    must = body["query"]["bool"]["must"]
    fields = [next(iter(c["wildcard"])) for c in must[0]["bool"]["should"]]
    assert set(fields) == {"cve_id", "image_repo", "namespaces", "assignee", "package_name"}
    for c in must[0]["bool"]["should"]:
        spec = c["wildcard"][next(iter(c["wildcard"]))]
        assert spec == {"value": "*krb5*", "case_insensitive": True}

    hostile = build_search_body(SearchFilters(q="a*b?c"), size=10)
    spec = hostile["query"]["bool"]["must"][0]["bool"]["should"][0]["wildcard"]["cve_id"]
    assert spec["value"] == "*a\\*b\\?c*"  # user wildcards neutralized

    assert "must" not in build_search_body(SearchFilters(), size=10)["query"]["bool"]


def test_exclude_facets_land_as_pure_must_not() -> None:
    """Issue 349: every excludable facet mirrors its include twin into `must_not`. Semantic
    pin: PURE must_not, no exists-guard — a row MISSING the field survives the exclusion
    ("assignee is not bob" keeps unassigned rows; "namespace is not kube-system" keeps rows
    with no namespace data)."""
    body = build_search_body(
        SearchFilters(
            exclude_severity=["low", "negligible"],
            exclude_state=["resolved"],
            exclude_scanner="trivy",
            exclude_assignee=["bob"],
            exclude_image_repo=["docker.io/library/memcached"],
            exclude_namespace=["kube-system"],
            exclude_ptype=["deb"],
            exclude_cve_id=["CVE-2021-3711"],
            exclude_package_name=["zlib"],
        ),
        size=10,
    )
    mn = body["query"]["bool"]["must_not"]
    assert {"terms": {"severity_canonical": ["low", "negligible"]}} in mn
    assert {"terms": {"state": ["resolved"]}} in mn
    assert {"term": {"scanner": "trivy"}} in mn  # scanner stays one value (issue 949)
    for field, term in (
        ("assignee", "bob"),
        ("image_repo", "docker.io/library/memcached"),
        ("namespaces", "kube-system"),
        ("ptype", "deb"),
        # issue 492: the last two facets to grow an exclude side. `package_name` is the one
        # field that is commonly ABSENT on a row (an OS-level finding with no package), which
        # is exactly the case the no-exists-guard assertion below protects
        ("cve_id", "CVE-2021-3711"),
        ("package_name", "zlib"),
    ):
        assert {"terms": {field: [term]}} in mn
    assert not any("exists" in json.dumps(c) for c in mn)
    # the include side stays untouched — excludes never leak into the filter context
    assert body["query"]["bool"]["filter"] == [{"term": {"present": True}}]


def test_include_and_exclude_on_one_field_is_rejected() -> None:
    """No mixing: a field is an include-list OR an exclude-list ("is one of" vs "is none of");
    both at once is ambiguous and refuses to build (the router 422s it first)."""
    with pytest.raises(ValueError, match="severity"):
        build_search_body(SearchFilters(severity=["high"], exclude_severity=["low"]), size=10)
    with pytest.raises(ValueError, match="namespace"):
        build_search_body(
            SearchFilters(namespace=["prod"], exclude_namespace=["kube-system"]), size=10
        )
    with pytest.raises(ValueError, match="cve_id"):
        build_search_body(
            SearchFilters(cve_id=["CVE-2021-3711"], exclude_cve_id=["CVE-2022-0001"]), size=10
        )
    with pytest.raises(ValueError, match="package_name"):
        build_search_body(
            SearchFilters(package_name=["zlib"], exclude_package_name=["openssl"]), size=10
        )
    with pytest.raises(ValueError, match="scanner"):
        build_search_body(SearchFilters(scanner="trivy", exclude_scanner="grype"), size=10)


def test_package_name_include_is_an_exact_term() -> None:
    """Issue 492: `package_name` filters the keyword field exactly — the fuzzy reading of a
    package name is `q`'s wildcard, which is a different question and stays include-only."""
    body = build_search_body(SearchFilters(package_name=["zlib"]), size=10)
    assert {"terms": {"package_name": ["zlib"]}} in body["query"]["bool"]["filter"]
    assert "must_not" not in body["query"]["bool"]


def test_exclude_composes_with_overdue_false() -> None:
    """Both write must_not — they must accumulate, never overwrite each other."""
    body = build_search_body(
        SearchFilters(exclude_scanner="grype", overdue=False), size=10, sla_cutoffs=_CUTOFFS
    )
    mn = body["query"]["bool"]["must_not"]
    assert {"term": {"scanner": "grype"}} in mn
    assert any("should" in c.get("bool", {}) for c in mn)  # the negated overdue clause
    assert len(mn) == 2


def test_no_excludes_means_no_must_not_key() -> None:
    assert "must_not" not in build_search_body(SearchFilters(), size=10)["query"]["bool"]


def test_unassigned_is_absence_not_negation() -> None:
    """Issue 349 §1. The distinction is load-bearing: the test above pins that
    `exclude_assignee=bob` KEEPS unassigned rows, so no combination of excludes can ever ask
    "nobody owns this". `unassigned` is its own clause."""
    body = build_search_body(SearchFilters(unassigned=True), size=10)
    mn = body["query"]["bool"]["must_not"]
    assert mn == [
        {
            "bool": {
                "filter": [{"exists": {"field": "assignee"}}],
                "must_not": [{"term": {"assignee": ""}}],
            }
        }
    ]


def test_unassigned_false_asks_for_an_owner() -> None:
    body = build_search_body(SearchFilters(unassigned=False), size=10)
    fl = body["query"]["bool"]["filter"]
    assert has_owner_clause() in fl
    assert "must_not" not in body["query"]["bool"]


def test_an_owner_means_a_NON_EMPTY_assignee() -> None:
    """`TriagePatch` reads `None` as "not provided", so clearing an owner writes "" — and
    OpenSearch counts an empty string as existing. Without the extra term those rows would
    read as owned while the grid shows them blank."""
    clause = has_owner_clause()
    assert {"term": {"assignee": ""}} in clause["bool"]["must_not"]
    assert {"exists": {"field": "assignee"}} in clause["bool"]["filter"]
    # the facet counts the exact complement, so rail count ≡ filtered rows
    assert unassigned_clause() == {"bool": {"must_not": [clause]}}


def test_unassigned_and_a_named_assignee_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="unassigned"):
        build_search_body(SearchFilters(assignee=["bob"], unassigned=True), size=10)


def test_unassigned_composes_with_the_other_must_not_writers() -> None:
    """unassigned, excludes and overdue=False all write must_not — they must accumulate."""
    body = build_search_body(
        SearchFilters(unassigned=True, exclude_scanner="grype", overdue=False),
        size=10,
        sla_cutoffs=_CUTOFFS,
    )
    mn = body["query"]["bool"]["must_not"]
    assert {"term": {"scanner": "grype"}} in mn
    assert has_owner_clause() in mn
    assert len(mn) == 3


async def test_run_search_overdue_policy_failure_opens_no_pit(monkeypatch) -> None:
    """A failing sla-policy read on an overdue first page must not leak a PIT: the read runs
    BEFORE create_pit, so the error paths (which only reclaim what the try block sees) never
    have an orphan to miss (issue 509 sweep)."""
    from backend.query import search as search_module

    async def boom(*a: Any, **kw: Any) -> dict[str, Any]:
        raise RuntimeError("policy read exploded")

    monkeypatch.setattr(search_module, "read_sla_policy", boom)
    fake = _PitOS(pages=[])
    with pytest.raises(RuntimeError, match="policy read exploded"):
        await run_search(
            fake,  # type: ignore[arg-type]
            cluster_id="c-unit-search",
            filters=SearchFilters(overdue=True),
            size=2,
        )
    assert fake.created == 0 and fake.deleted == []  # never opened → nothing to leak


# issue 949: six filters take several values. Each list is ONE `terms` clause, so the values
# are ORed inside a field and ANDed with the other fields, the way severity and state work.
_LIST_FIELDS = (
    ("namespace", "namespaces"),  # keyword[]: a row matches when ANY of its namespaces is listed
    ("ptype", "ptype"),
    ("assignee", "assignee"),
    ("image_repo", "image_repo"),
    ("cve_id", "cve_id"),
    ("package_name", "package_name"),
)


@pytest.mark.parametrize(("param", "field"), _LIST_FIELDS)
def test_several_values_in_one_field_are_one_terms_clause(param: str, field: str) -> None:
    body = build_search_body(SearchFilters(**dict[str, Any]({param: ["a", "b"]})), size=10)
    q = body["query"]["bool"]
    assert {"terms": {field: ["a", "b"]}} in q["filter"]
    assert "must_not" not in q


@pytest.mark.parametrize(("param", "field"), _LIST_FIELDS)
def test_several_excluded_values_drop_every_listed_value(param: str, field: str) -> None:
    """Ruling 4 on issue 949: "is not A, B" drops the rows in A and the rows in B, the same
    rule as severity. Still PURE must_not: a row without the field survives."""
    body = build_search_body(
        SearchFilters(**dict[str, Any]({f"exclude_{param}": ["a", "b"]})), size=10
    )
    q = body["query"]["bool"]
    assert q["must_not"] == [{"terms": {field: ["a", "b"]}}]
    assert q["filter"] == [{"term": {"present": True}}]


@pytest.mark.parametrize(("param", "_field"), _LIST_FIELDS)
def test_an_empty_list_is_no_filter(param: str, _field: str) -> None:
    """Same reading as severity: an empty list adds no clause and does not trip the
    include-or-exclude rule."""
    body = build_search_body(SearchFilters(**{param: [], f"exclude_{param}": ["x"]}), size=10)
    assert body["query"]["bool"]["filter"] == [{"term": {"present": True}}]


def test_unassigned_and_several_named_assignees_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="unassigned"):
        build_search_body(SearchFilters(assignee=["bob", "ana"], unassigned=True), size=10)


# --- the pairs that cannot be sent together (issue 969) -------------------------------------

_EXCLUDE_FIELDS = [f for f in SearchFilters.__dataclass_fields__ if f.startswith("exclude_")]


def test_every_exclude_filter_is_a_pair_with_its_include_side() -> None:
    assert len(_EXCLUDE_FIELDS) == 9
    assert set(FILTER_PAIRS) == {
        *((f.removeprefix("exclude_"), f) for f in _EXCLUDE_FIELDS),
        ("assignee", "unassigned"),
    }


@pytest.mark.parametrize(("first", "second"), FILTER_PAIRS)
def test_a_pair_gets_its_message(first: str, second: str) -> None:
    values = {first: ["x"], second: ["y"]}
    assert conflicting_filter_pair(values) == f"{first} and {second} are mutually exclusive"


@pytest.mark.parametrize(("first", "second"), FILTER_PAIRS)
def test_one_side_of_a_pair_alone_is_no_conflict(first: str, second: str) -> None:
    assert conflicting_filter_pair({first: ["x"], second: None}) is None
    assert conflicting_filter_pair({first: None, second: ["y"]}) is None
    assert conflicting_filter_pair({second: ["y"]}) is None


def test_a_false_flag_and_an_empty_list_are_set() -> None:
    # set means "not None", as the findings route reads its query: `unassigned=false` is a
    # real filter (rows that have an owner), so it still conflicts with a named assignee
    assert conflicting_filter_pair({"assignee": ["ana"], "unassigned": False}) is not None
    assert conflicting_filter_pair({"cve_id": [], "exclude_cve_id": ["CVE-1"]}) is not None


def test_no_filter_is_no_conflict() -> None:
    assert conflicting_filter_pair(vars(SearchFilters())) is None
