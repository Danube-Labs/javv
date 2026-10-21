"""Faceted findings search (M6 slice 1, FR-12) — pure DSL builder + PIT-paged executor.

Every facet is a `filter` clause (cached, never scored); `present=true` is the DEFAULT grid
filter (D39 — presence ⟂ state; the tombstone view opts in with `present=false`). Sort is
whitelisted and always tiebroken on the unique `finding_key`, so paging is deterministic
(api-design standard). Deep paging is PIT + `search_after` behind an OPAQUE cursor
(`{data, next_cursor}` — raw `search_after` arrays are never a client contract); the PIT is
deleted the moment a page is final: last page, or any error on a page we opened it for (D38).
An abandoned cursor's PIT dies at `keep_alive` — the client never has to clean up.

Tenancy: bodies are built through `tenant_query`, so the `cluster_id` term filter is
structurally present on the PIT path too (SEC-4 — PIT searches carry no index name, so the
body filter is the only guard).
"""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import NotFoundError, RequestError
from pydantic import StringConstraints

from backend.core.settings import get_settings
from backend.query.trends import window_bounds
from backend.sla.overdue import HANDLED_STATES, overdue_cutoffs
from backend.sla.policy import read_sla_policy
from backend.tenancy.read_path import tenant_query

log = structlog.get_logger()

_SORT_FIELDS = ("severity_rank", "first_seen_at", "last_scan_at", "cvss", "epss")
# the most values one list filter takes (issue 949). It matches the facet list, which shows at
# most 32 values of a field (docs/API.md, `/findings/facets`), so every value a facet offers fits.
# Typed values (image, CVE, package) have no facet list and share the same cap.
MAX_FILTER_VALUES = 32
# one value of a list filter, with the length cap the field had as one string. The findings
# route, saved views and export settings all use these, so the three cannot drift apart.
FilterValue64 = Annotated[str, StringConstraints(max_length=64)]
FilterValue128 = Annotated[str, StringConstraints(max_length=128)]
FilterValue256 = Annotated[str, StringConstraints(max_length=256)]
FilterValue512 = Annotated[str, StringConstraints(max_length=512)]
# the six filters that take a list, each with its exclude_ pair
LIST_FILTER_FIELDS = tuple(
    f"{prefix}{name}"
    for prefix in ("", "exclude_")
    for name in ("assignee", "cve_id", "image_repo", "namespace", "ptype", "package_name")
)


def one_value_as_list(value: Any) -> Any:
    """A saved view or export written as one string reads as a list of that one value, so a
    client that still sends one string and a stored blob from before issue 949 keep working."""
    return [value] if isinstance(value, str) else value


_SCALAR = (str, int, float, bool)


class CursorExpired(Exception):
    """A decodable cursor whose PIT OpenSearch no longer holds — the client idled past
    `JAVV_SEARCH_PIT_KEEP_ALIVE`. The route maps this to 410 Gone ("restart the search"), never a
    500. Distinct from a structurally-invalid cursor (ValueError → 422) and a cluster outage
    (transport error → 503)."""


@dataclass(frozen=True)
class SearchFilters:
    """The FR-12 facet set. `None` = facet unset; `False` is a real filter."""

    # list fields take several values (issue 949): ORed inside the field, ANDed across fields.
    # `scanner` stays one value: it has two, and both together are no filter at all.
    severity: list[str] | None = None
    state: list[str] | None = None
    scanner: str | None = None
    assignee: list[str] | None = None
    kev: bool | None = None
    fixable: bool | None = None
    disagree: bool | None = None
    cve_id: list[str] | None = None
    image_digest: str | None = None
    image_repo: list[str] | None = None
    namespace: list[str] | None = None
    ptype: list[str] | None = None  # package type (M8d/B-1): "os" | ecosystem string
    # the package a finding sits in (issue 492) — an EXACT keyword term, not the fuzzy reading
    # `q` offers. `ptype` is the package's TYPE and answers a different question.
    package_name: list[str] | None = None
    q: str | None = None  # contains-search across cve/image/namespace/assignee/package (slice 4)
    present: bool = True  # the "now" grid; tombstones are opt-in
    # "new in range": first_seen_at ≥ the trend window's day-floored start — the SAME bounds
    # the trend charts use, so the lens bars and the filtered rows always agree
    new_within_days: int | None = None
    # SLA breached (issue 363): ranges on the materialized D21 group clock `sla_clock_at`
    # against LIVE-policy cutoffs — the body needs `sla_cutoffs` (see overdue_cutoffs)
    overdue: bool | None = None
    # "unassigned" (issue 349 §1): ABSENCE, not negation, and the two cannot substitute for
    # each other — `exclude_assignee=bob` keeps rows with no assignee at all (see the note
    # below), so no combination of excludes can ask "nobody owns this". True = the untriaged
    # backlog; False = has an owner.
    unassigned: bool | None = None
    # negation (issue 349): each excludable facet mirrors its include twin into `must_not`.
    # A field is include OR exclude, never both (ValueError). Semantics are PURE must_not —
    # a row missing the field survives the exclusion ("is not bob" keeps unassigned rows).
    exclude_severity: list[str] | None = None
    exclude_state: list[str] | None = None
    exclude_scanner: str | None = None
    exclude_assignee: list[str] | None = None
    exclude_image_repo: list[str] | None = None
    exclude_namespace: list[str] | None = None
    exclude_ptype: list[str] | None = None
    exclude_cve_id: list[str] | None = None
    exclude_package_name: list[str] | None = None


def has_owner_clause() -> dict[str, Any]:
    """Rows that HAVE an owner. An owner is a NON-EMPTY assignee: `TriagePatch` reads `None` as
    "not provided", so the only way to clear one is to write "", and OpenSearch counts an empty
    string as existing — `exists` alone would call those rows owned while the grid shows them
    blank. Shared with the facet so the rail count and the filtered grid cannot disagree."""
    return {
        "bool": {
            "filter": [{"exists": {"field": "assignee"}}],
            "must_not": [{"term": {"assignee": ""}}],
        }
    }


def unassigned_clause() -> dict[str, Any]:
    """The complement — the untriaged backlog (issue 349 §1)."""
    return {"bool": {"must_not": [has_owner_clause()]}}


_SLA_SEVERITIES = ("critical", "high", "medium", "low")  # the FR-10 buckets that carry an SLA


def overdue_clause(cutoffs: dict[str, str]) -> dict[str, Any]:
    """The DSL mirror of compute_overdue over the materialized `sla_clock_at` (issue 363):
    KEV rows judge against the kev cutoff regardless of severity (the FR-10 fast-lane —
    severity branches exclude them); negligible/unknown carry no SLA, so no branch matches;
    handled states are never overdue (shared HANDLED_STATES — chip ≡ filter by construction).
    Rows missing `sla_clock_at` (pre-backfill) match nothing — rebuild-state backfills."""
    should: list[dict[str, Any]] = [
        {
            "bool": {
                "filter": [
                    {"term": {"kev": True}},
                    {"range": {"sla_clock_at": {"lt": cutoffs["kev"]}}},
                ]
            }
        }
    ]
    for sev in _SLA_SEVERITIES:
        should.append(
            {
                "bool": {
                    "filter": [
                        {"term": {"severity_canonical": sev}},
                        {"range": {"sla_clock_at": {"lt": cutoffs[sev]}}},
                    ],
                    "must_not": [{"term": {"kev": True}}],
                }
            }
        )
    return {
        "bool": {
            "should": should,
            "minimum_should_match": 1,
            "must_not": [{"terms": {"state": sorted(HANDLED_STATES)}}],
        }
    }


def build_search_body(
    filters: SearchFilters,
    *,
    size: int,
    sort: str = "severity_rank",
    order: str = "desc",
    search_after: list[Any] | None = None,
    sla_cutoffs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Pure — the unit-tested contract. Does NOT include the tenant filter (tenant_query
    forces that in) or the PIT (the executor owns its lifecycle). An `overdue` filter REQUIRES
    `sla_cutoffs` (derive via `overdue_cutoffs` from the live policy) — raising instead of
    silently dropping the facet is what keeps every consumer's results correct."""
    if sort not in _SORT_FIELDS:
        raise ValueError(f"sort must be one of {_SORT_FIELDS}")
    if order not in ("asc", "desc"):
        raise ValueError("order must be asc or desc")
    fl: list[dict[str, Any]] = [{"term": {"present": filters.present}}]
    for field, value in (
        # D46/#274: the severity FILTER targets the server-derived full-word canonical key —
        # the verbatim field only lc-folds case, so `critical` used to work while the canonical
        # vocabulary silently matched nothing on real rows
        ("severity_canonical", filters.severity),
        ("state", filters.state),
        ("assignee", filters.assignee),
        ("cve_id", filters.cve_id),
        ("image_repo", filters.image_repo),
        ("namespaces", filters.namespace),  # keyword[]: matches when ANY namespace is listed
        ("ptype", filters.ptype),
        ("package_name", filters.package_name),
    ):
        if value:
            fl.append({"terms": {field: value}})
    for field, term in (
        ("scanner", filters.scanner),
        ("kev", filters.kev),
        ("fixable", filters.fixable),
        ("disagree", filters.disagree),
        ("image_digest", filters.image_digest),
    ):
        if term is not None:
            fl.append({"term": {field: term}})
    if filters.new_within_days is not None:
        gte, _upper = window_bounds(filters.new_within_days)
        fl.append({"range": {"first_seen_at": {"gte": gte}}})
    mn: list[dict[str, Any]] = []
    for name, field, include, exclude in (
        ("severity", "severity_canonical", filters.severity, filters.exclude_severity),
        ("state", "state", filters.state, filters.exclude_state),
        ("assignee", "assignee", filters.assignee, filters.exclude_assignee),
        ("image_repo", "image_repo", filters.image_repo, filters.exclude_image_repo),
        ("namespace", "namespaces", filters.namespace, filters.exclude_namespace),
        ("ptype", "ptype", filters.ptype, filters.exclude_ptype),
        ("cve_id", "cve_id", filters.cve_id, filters.exclude_cve_id),
        ("package_name", "package_name", filters.package_name, filters.exclude_package_name),
    ):
        if exclude:
            if include:
                raise ValueError(f"{name} and exclude_{name} are mutually exclusive")
            mn.append({"terms": {field: exclude}})
    if filters.exclude_scanner is not None:
        if filters.scanner is not None:
            raise ValueError("scanner and exclude_scanner are mutually exclusive")
        mn.append({"term": {"scanner": filters.exclude_scanner}})
    bool_q: dict[str, Any] = {"filter": fl}
    if filters.overdue is not None:
        if sla_cutoffs is None:
            raise ValueError("overdue filter requires sla_cutoffs (from the live SLA policy)")
        clause = overdue_clause(sla_cutoffs)
        if filters.overdue:
            fl.append(clause)
        else:
            mn.append(clause)
    if filters.unassigned is not None:
        if filters.assignee:
            raise ValueError("assignee and unassigned are mutually exclusive")
        if filters.unassigned:
            mn.append(has_owner_clause())
        else:
            fl.append(has_owner_clause())
    if mn:
        bool_q["must_not"] = mn
    if filters.q is not None:
        # contains-match across the identifier fields (M9b slice 4, operator ask). Structured
        # wildcard clauses — NEVER query_string (DSL injection surface). `*`/`?` in user input
        # are escaped so a crafted pattern can't go pathological; `case_insensitive` rides the
        # lc-normalized keywords. COST NOTE: a leading wildcard scans the field's terms — fine
        # at fleet-scaled MVP size; past that the fix is an INDEX-MAP change (wildcard field
        # type / n-grams), not a bigger box.
        escaped = filters.q.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")
        pattern = f"*{escaped}*"
        bool_q["must"] = [
            {
                "bool": {
                    "should": [
                        {"wildcard": {f: {"value": pattern, "case_insensitive": True}}}
                        for f in ("cve_id", "image_repo", "namespaces", "assignee", "package_name")
                    ],
                    "minimum_should_match": 1,
                }
            }
        ]
    body: dict[str, Any] = {
        "size": size,
        "track_total_hits": True,
        "query": {"bool": bool_q},
        "sort": [{sort: {"order": order}}, {"finding_key": {"order": "asc"}}],
    }
    if search_after is not None:
        body["search_after"] = search_after
    return body


def encode_cursor(
    *,
    pit_id: str,
    search_after: list[Any],
    sort: str,
    order: str,
    sla_cutoffs: dict[str, str] | None = None,
) -> str:
    payload: dict[str, Any] = {"p": pit_id, "a": search_after, "s": sort, "o": order}
    if sla_cutoffs is not None:
        # freeze the overdue cutoffs with the walk (issue 363): the PIT freezes the docs, so the
        # query must freeze too — a wall-clock cutoff drifting between pages could flip a row's
        # match mid-walk and skip/duplicate it across a page boundary
        payload["sc"] = sla_cutoffs
    raw = json.dumps(payload)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, list[Any], str, str, dict[str, str] | None]:
    try:
        c = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        pit_id, search_after, sort, order = c["p"], c["a"], c["s"], c["o"]
        sla_cutoffs = c.get("sc")
    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid cursor") from exc
    # a base64/JSON-valid cursor can still carry tampered fields that would sail past decode and
    # blow up inside client.search (500) — type-check them here so a bad shape is a 422 (A-m1).
    # sort/order are re-validated by build_search_body against their whitelists (also → 422).
    if not (isinstance(pit_id, str) and isinstance(sort, str) and isinstance(order, str)):
        raise ValueError("invalid cursor")
    if not isinstance(search_after, list) or not all(
        v is None or isinstance(v, _SCALAR) for v in search_after
    ):
        raise ValueError("invalid cursor")
    if sla_cutoffs is not None and not (
        isinstance(sla_cutoffs, dict)
        and set(sla_cutoffs) == {"kev", *_SLA_SEVERITIES}
        and all(isinstance(v, str) for v in sla_cutoffs.values())
    ):
        raise ValueError("invalid cursor")
    return pit_id, search_after, sort, order, sla_cutoffs


def cursor_pit_id(cursor: str) -> str:
    """The PIT a findings or audit cursor walks; `ValueError` for a cursor that does not decode."""
    return decode_cursor(cursor)[0]


async def run_search(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: SearchFilters,
    size: int,
    sort: str = "severity_rank",
    order: str = "desc",
    cursor: str | None = None,
    prefix: str = "",
    keep_open: bool = False,
) -> dict[str, Any]:
    """One page. Returns `{data, next_cursor, total}`; `next_cursor=None` ends the walk.
    `keep_open` keeps a continuation's PIT past its final page, for a client that may page back
    and closes the walk itself (`POST /api/v1/cursors/close`, issue 832)."""
    keep_alive = get_settings().search_pit_keep_alive
    search_after: list[Any] | None = None
    sla_cutoffs: dict[str, str] | None = None
    if cursor is not None:
        pit_id, search_after, sort, order, sla_cutoffs = decode_cursor(cursor)
        if filters.overdue is not None and sla_cutoffs is None:
            # a cursor minted by a non-overdue walk carries no frozen cutoffs — resolve live
            policy = await read_sla_policy(client, prefix=prefix)
            sla_cutoffs = overdue_cutoffs(policy, now=datetime.now(UTC))
    else:
        if filters.overdue is not None:
            # first page resolves the LIVE policy once; continuations reuse the cursor-frozen
            # cutoffs. Resolved BEFORE the PIT opens — a failing policy read must not leak a
            # just-created PIT the error paths below never see (issue 509's sweep).
            policy = await read_sla_policy(client, prefix=prefix)
            sla_cutoffs = overdue_cutoffs(policy, now=datetime.now(UTC))
        pit_id = (
            await client.create_pit(index=f"{prefix}findings", params={"keep_alive": keep_alive})
        )["pit_id"]

    opened_here = cursor is None  # this call created the PIT (vs. a client-owned cursor PIT)
    body = build_search_body(
        filters,
        size=size,
        sort=sort,
        order=order,
        search_after=search_after,
        sla_cutoffs=sla_cutoffs,
    )
    body = tenant_query(cluster_id, body)  # SEC-4 — the only guard on the index-less PIT path
    body["pit"] = {"id": pit_id, "keep_alive": keep_alive}
    try:
        resp = await client.search(body=body)
    except NotFoundError as exc:  # the PIT is gone — expired past keep_alive, or a tampered id
        if opened_here:  # our just-created PIT vanished — reclaim (near-impossible) and surface
            await client.delete_pit(body={"pit_id": [pit_id]})
            raise
        # a client-owned cursor PIT expired: 410, not 500 — and never reclaim it (already gone)
        log.info("cursor PIT expired — client should restart", cluster_id=cluster_id)
        raise CursorExpired(
            f"cursor expired — restart the search (PIT keep-alive is {keep_alive})"
        ) from exc
    except RequestError as exc:  # a decodable cursor OpenSearch rejects (tampered pit_id/fields)
        if opened_here:  # a server-built query shouldn't 400 — reclaim our PIT and surface as-is
            await client.delete_pit(body={"pit_id": [pit_id]})
            raise
        raise ValueError("invalid cursor") from exc
    except BaseException:  # transient transport/cluster hiccup (or a cursorless re-raise above)
        if opened_here:  # reclaim ONLY the PIT we opened — a cursor PIT is the client's walk, let
            await client.delete_pit(body={"pit_id": [pit_id]})  # it live to keep_alive for a retry
            log.warning("search page failed — PIT reclaimed", cluster_id=cluster_id, sort=sort)
        raise

    hits = resp["hits"]["hits"]
    if len(hits) < size:  # final page — the PIT dies with it (D38), unless the client keeps it
        if opened_here or not keep_open:  # a first page gave the client no cursor to close it by
            await client.delete_pit(body={"pit_id": [pit_id]})
        next_cursor = None
    else:
        next_cursor = encode_cursor(
            pit_id=pit_id,
            search_after=hits[-1]["sort"],
            sort=sort,
            order=order,
            sla_cutoffs=sla_cutoffs if filters.overdue is not None else None,
        )
    return {
        "data": [h["_source"] for h in hits],
        "next_cursor": next_cursor,
        "total": resp["hits"]["total"],
    }
