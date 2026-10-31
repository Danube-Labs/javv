"""The audit-log read (M8c slice 1, #240) — cursor-paged walk over `system-audit-log-*`.

Feeds the M9d Audit screen + the Contributors activity feed. Ordering is the replay contract's
`(@timestamp, event_id)` pair (D32/D40) with BOTH keys in the requested direction, so a page walk
is deterministic and gap-free over the append-only log (default `desc` — a feed reads newest
first; replay itself lives in `query/human_at.py` and stays `asc` + revision-collapsed).

Deep paging is the A-m1 machinery shared with the findings grid: PIT + `search_after` behind the
same opaque cursor contract (`encode_cursor`/`decode_cursor` reused verbatim) — an expired PIT is
410, a tampered cursor is 422, never a 500. Tenancy: the body goes through `tenant_query`
(SEC-4 — a PIT search carries no index name, so the body filter is the only guard)."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import NotFoundError, RequestError

from backend.core.settings import get_settings
from backend.query.aggs import _FACET_TERMS_SIZE, contains_pattern
from backend.query.search import CursorExpired, decode_cursor, encode_cursor
from backend.tenancy.read_path import tenant_query

log = structlog.get_logger()

_PATTERN = "system-audit-log-*"
_SORT_KEY = "@timestamp"  # fixed — the cursor's `s` field must round-trip exactly this
# The account events: sign-ins and sign-outs, password, user and role changes (`user`), and the
# ingest tokens (`token`). Only `can_manage_users` reads them (issue 892 ruling 3).
ACCOUNT_ENTITY_TYPES = ("token", "user")
# A dashboard row carries the whole dashboard, a private one too. Only `can_manage_settings`, who
# sees every dashboard, reads them (issue 440, ruling of 2026-10-25).
DASHBOARD_ENTITY_TYPES = ("dashboard",)
# The Entity and Action lists are fixed lists, and the Action list has 45 values. Each value gets
# a count only when the size is larger than the list (issue 983). The frontend mirrors this size
# (`AUDIT_LIST_CAP` in `audit/fields.config.ts`), and a spec keeps them equal. The User list has no
# fixed values and keeps the top `_FACET_TERMS_SIZE`.
_AUDIT_LIST_TERMS_SIZE = 64
# Fleet-wide settings rows written before issue 559 carry this literal instead of no cluster_id.
# The log is append-only, so they keep it; no real cluster can match, since ids are 8-64 chars.
_LEGACY_FLEET_CLUSTER_ID = "fleet"


@dataclass(frozen=True)
class AuditFilters:
    """The M8c filter set (bolt #240): keyword filters; `None` or an empty list = unset.

    `entity_type`, `action` and `actor` take several values (issue 952): a row matches any of
    them, and an exclusion leaves out a row with any of them. The `exclude_*` twins are the
    negation side (issue 349): a field is included OR excluded, never both, so the pair is set
    by the caller from one UI mode. A row missing the field entirely survives its exclusion —
    `must_not terms` only drops rows that actually match, so
    "actor is not alice" keeps system rows that have no actor. That is the reading the client
    matcher uses for images too, and it is what the pill claims.
    """

    entity_type: list[str] | None = None
    action: list[str] | None = None
    actor: list[str] | None = None
    finding_key: str | None = None  # per-finding activity (M9b slice 4 — the detail screen)
    until: datetime | None = None  # D28: a rewound picker must not see post-T events (M9d)
    exclude_entity_type: list[str] | None = None
    exclude_action: list[str] | None = None
    exclude_actor: list[str] | None = None


def audit_tenant_query(
    cluster_id: str, body: dict[str, Any], *, account_events: bool, dashboard_events: bool
) -> dict[str, Any]:
    """SEC-4 for the JOURNAL specifically (operator catch, 2026-07-18): the log holds two row
    classes — cluster-scoped (triage, decisions) and FLEET-scoped (auth, user admin, store
    inspect, job triggers — no cluster to belong to). The plain term guard silently hid the
    whole fleet class from the audit screen. Still a structural, server-built guard: a row is
    visible iff it is the selected tenant's, carries no cluster_id at all, or carries the legacy
    fleet literal (MVP tenancy is all-clusters-visible, D38 — nothing here a session holder
    can't already see). Without `account_events` the account rows (`ACCOUNT_ENTITY_TYPES`) are
    left out, and without `dashboard_events` the dashboard rows (`DASHBOARD_ENTITY_TYPES`). The
    arguments have no default, so every reader of the log decides."""
    guarded = tenant_query(cluster_id, body)
    term = guarded["query"]["bool"]["filter"][0]
    guarded["query"]["bool"]["filter"][0] = {
        "bool": {
            "should": [
                term,
                {"bool": {"must_not": [{"exists": {"field": "cluster_id"}}]}},
                {"term": {"cluster_id": _LEGACY_FLEET_CLUSTER_ID}},
            ],
            "minimum_should_match": 1,
        }
    }
    if not account_events:
        guarded["query"]["bool"].setdefault("must_not", []).append(
            {"terms": {"entity_type": list(ACCOUNT_ENTITY_TYPES)}}
        )
    if not dashboard_events:
        guarded["query"]["bool"].setdefault("must_not", []).append(
            {"terms": {"entity_type": list(DASHBOARD_ENTITY_TYPES)}}
        )
    return guarded


def build_audit_body(
    filters: AuditFilters,
    *,
    size: int,
    order: str = "desc",
    search_after: list[Any] | None = None,
) -> dict[str, Any]:
    """Pure builder (the unit-tested contract). No tenant filter (tenant_query forces that in)
    and no PIT (the executor owns its lifecycle). Sort is the FIXED `(@timestamp, event_id)`
    pair — one direction for both, so `search_after` pages without gaps or duplicates."""
    if order not in ("asc", "desc"):
        raise ValueError("order must be asc or desc")
    fl: list[dict[str, Any]] = [
        {"terms": {field: values}}
        for field, values in (
            ("entity_type", filters.entity_type),
            ("action", filters.action),
            ("actor", filters.actor),
        )
        if values
    ]
    if filters.finding_key is not None:
        # a bulk change names its findings in `target_ids`, never in `finding_key` (issue 912)
        fl.append(
            {
                "bool": {
                    "should": [
                        {"term": {"finding_key": filters.finding_key}},
                        {"term": {"target_ids": filters.finding_key}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if filters.until is not None:
        fl.append({"range": {_SORT_KEY: {"lte": filters.until.isoformat()}}})
    must_not: list[dict[str, Any]] = [
        {"terms": {field: values}}
        for field, values in (
            ("entity_type", filters.exclude_entity_type),
            ("action", filters.exclude_action),
            ("actor", filters.exclude_actor),
        )
        if values
    ]
    body: dict[str, Any] = {
        "size": size,
        "track_total_hits": True,
        "sort": [{_SORT_KEY: {"order": order}}, {"event_id": {"order": order}}],
    }
    if fl or must_not:
        clauses: dict[str, Any] = {}
        if fl:
            clauses["filter"] = fl
        if must_not:
            clauses["must_not"] = must_not
        body["query"] = {"bool": clauses}
    if search_after is not None:
        body["search_after"] = search_after
    return body


async def run_audit_search(
    client: AsyncOpenSearch,
    *,
    cluster_id: str,
    filters: AuditFilters,
    size: int,
    order: str = "desc",
    cursor: str | None = None,
    account_events: bool,
    dashboard_events: bool,
    prefix: str = "",
    keep_open: bool = False,
) -> dict[str, Any]:
    """One page — `{data, next_cursor, total}`; `next_cursor=None` ends the walk. Same PIT
    lifecycle discipline as `run_search` (D38): the PIT dies with the final page, and any error
    on a page we opened it for reclaims it; a client-owned cursor PIT lives to `keep_alive`.
    `keep_open` keeps a continuation's PIT past its final page, as in `run_search`."""
    keep_alive = get_settings().search_pit_keep_alive
    search_after: list[Any] | None = None
    if cursor is not None:
        pit_id, search_after, sort, order, _ = decode_cursor(cursor)
        if sort != _SORT_KEY:  # a findings-grid (or hand-rolled) cursor is not an audit cursor
            raise ValueError("invalid cursor")
    else:
        try:
            pit_id = (
                await client.create_pit(
                    index=f"{prefix}{_PATTERN}", params={"keep_alive": keep_alive}
                )
            )["pit_id"]
        except NotFoundError:  # nothing journaled yet anywhere — a real, empty answer
            return {"data": [], "next_cursor": None, "total": {"value": 0, "relation": "eq"}}

    opened_here = cursor is None
    body = build_audit_body(filters, size=size, order=order, search_after=search_after)
    # SEC-4 + the fleet-row seam (see the builder)
    body = audit_tenant_query(
        cluster_id, body, account_events=account_events, dashboard_events=dashboard_events
    )
    body["pit"] = {"id": pit_id, "keep_alive": keep_alive}
    try:
        resp = await client.search(body=body)
    except NotFoundError as exc:  # the PIT is gone — expired past keep_alive, or a tampered id
        if opened_here:
            await client.delete_pit(body={"pit_id": [pit_id]})
            raise
        log.info("audit cursor PIT expired — client should restart", cluster_id=cluster_id)
        raise CursorExpired(
            f"cursor expired — restart the walk (PIT keep-alive is {keep_alive})"
        ) from exc
    except RequestError as exc:  # a decodable cursor OpenSearch rejects (tampered pit_id/fields)
        if opened_here:
            await client.delete_pit(body={"pit_id": [pit_id]})
            raise
        raise ValueError("invalid cursor") from exc
    except BaseException:
        if opened_here:  # reclaim ONLY the PIT we opened — a cursor PIT may still serve a retry
            await client.delete_pit(body={"pit_id": [pit_id]})
            log.warning("audit page failed — PIT reclaimed", cluster_id=cluster_id)
        raise

    hits = resp["hits"]["hits"]
    if len(hits) < size:  # final page — the PIT dies with it (D38), unless the client keeps it
        if opened_here or not keep_open:  # a first page gave the client no cursor to close it by
            await client.delete_pit(body={"pit_id": [pit_id]})
        next_cursor = None
    else:
        next_cursor = encode_cursor(
            pit_id=pit_id, search_after=hits[-1]["sort"], sort=_SORT_KEY, order=order
        )
    rows = [h["_source"] for h in hits]
    try:
        await decorate_rows(client, cluster_id=cluster_id, rows=rows, prefix=prefix)
    except BaseException:
        # non-final page: the walk dies with this exception, so reclaim the PIT this call
        # opened (a final page already deleted it; a cursor PIT is the client's walk)
        if opened_here and next_cursor is not None:
            await client.delete_pit(body={"pit_id": [pit_id]})
            log.warning("audit decorate failed — PIT reclaimed", cluster_id=cluster_id)
        raise
    return {
        "data": rows,
        "next_cursor": next_cursor,
        "total": resp["hits"]["total"],
    }


_FINDING_DECOR = (
    "cve_id",
    "image_repo",
    "image_digest",
    "scanner",
    "package_name",
    "severity_canonical",
)
_DECISION_DECOR = ("cve_id", "type", "scanner", "apply_both_scanners")


async def decorate_rows(
    client: AsyncOpenSearch, *, cluster_id: str, rows: list[dict[str, Any]], prefix: str = ""
) -> None:
    """Attach the touched entity's human identity to each page row (M9d, operator ruling: an
    opaque `finding_key` answers nothing) — `finding`/`decision` sub-objects from one mget per
    index, display-only. `None` when the doc is gone (history outlives current state by design)
    or belongs to another tenant: mget bypasses `tenant_query`, so the cluster check happens
    HERE, per doc (SEC-4)."""

    async def resolve(
        index: str, ids: list[str], fields: tuple[str, ...]
    ) -> dict[str, dict[str, Any]]:
        resp = await client.mget(index=f"{prefix}{index}", body={"ids": ids})
        out: dict[str, dict[str, Any]] = {}
        for doc in resp["docs"]:
            src = doc.get("_source")
            if not doc.get("found") or not src or src.get("cluster_id") != cluster_id:
                continue
            out[doc["_id"]] = {k: src.get(k) for k in fields}
        return out

    finding_ids = sorted({r["entity_id"] for r in rows if r.get("entity_type") == "finding"})
    decision_ids = sorted({r["entity_id"] for r in rows if r.get("entity_type") == "decision"})
    findings = await resolve("findings", finding_ids, _FINDING_DECOR) if finding_ids else {}
    decisions = (
        await resolve("system-decisions", decision_ids, _DECISION_DECOR) if decision_ids else {}
    )
    for row in rows:
        if row.get("entity_type") == "finding":
            row["finding"] = findings.get(row["entity_id"])
        elif row.get("entity_type") == "decision":
            row["decision"] = decisions.get(row["entity_id"])


def build_actor_search_body(filters: AuditFilters, contains: str) -> dict[str, Any]:
    """A value search on the User list (issue 1064): the users that contain `contains`, in any
    case, from all users and not only the top 32. It counts under the filters of the list, so it
    leaves out the user filter too. It asks for one value more than the cap: the caller sends the
    cap and reads the extra one as "more values match" (`aggs.cap_value_search`)."""
    body = build_audit_body(replace(filters, actor=None, exclude_actor=None), size=0)
    body.pop("sort")
    body.pop("track_total_hits")
    body["aggs"] = {
        "actor": {
            "terms": {
                "field": "actor",
                "size": _FACET_TERMS_SIZE + 1,
                "include": contains_pattern(contains),
            }
        }
    }
    return body


def build_audit_facets_body(
    filters: AuditFilters,
    *,
    interval: str | None = None,
    window_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Terms counts for the rail dims (entity_type/action/actor) under the SAME filters as the
    walk — pure builder, tenant filter forced in by the executor's `tenant_query`. With
    `interval` (day|hour), adds the `activity` date_histogram over the picker window ending at
    the D28 bound (the audit lens): `extended_bounds` renders quiet buckets as zeros, and the
    window's `gte` scopes ONLY the histogram — the rail counts stay whole-lens, except the one
    below.

    The `actor` count leaves out the user filter (issue 952), so a picked user does
    not hide the others from the list. Entity and action keep their own filter, as severity
    and state do on Findings: their values are a fixed list, so each stays offered."""
    body = build_audit_body(filters, size=0)
    body.pop("sort")
    body.pop("track_total_hits")
    body["aggs"] = {
        "entity_type": {"terms": {"field": "entity_type", "size": _AUDIT_LIST_TERMS_SIZE}},
        "action": {"terms": {"field": "action", "size": _AUDIT_LIST_TERMS_SIZE}},
        "actor": {"terms": {"field": "actor", "size": _FACET_TERMS_SIZE}},  # the findings rail cap
    }
    window: dict[str, Any] | None = None
    if interval is not None:
        if interval not in ("day", "hour"):
            raise ValueError("interval must be day or hour")
        end = filters.until or now or datetime.now(UTC)
        start = end - timedelta(days=window_days)
        window = {"range": {_SORT_KEY: {"gte": start.isoformat(), "lte": end.isoformat()}}}
        body["aggs"]["activity"] = {
            "filter": window,
            "aggs": {
                "buckets": {
                    "date_histogram": {
                        "field": _SORT_KEY,
                        "calendar_interval": interval,
                        "min_doc_count": 0,
                        "extended_bounds": {
                            "min": start.isoformat(),
                            "max": end.isoformat(),
                        },
                    }
                }
            },
        }
    if not (filters.actor or filters.exclude_actor):
        return body
    # the main query drops the user filter, so the actor count sees every user; each other
    # aggregation puts every filter back, so its counts do not change
    full = body["query"]
    wrapped = build_audit_body(replace(filters, actor=None, exclude_actor=None), size=0)
    wrapped.pop("sort")
    wrapped.pop("track_total_hits")
    aggs = body["aggs"]
    wrapped["aggs"] = {
        "actor": aggs["actor"],
        **{
            field: {"filter": full, "aggs": {"values": aggs[field]}}
            for field in ("entity_type", "action")
        },
    }
    if window is not None:
        wrapped["aggs"]["activity"] = {
            **aggs["activity"],
            "filter": {"bool": {"filter": [full, window]}},
        }
    return wrapped
