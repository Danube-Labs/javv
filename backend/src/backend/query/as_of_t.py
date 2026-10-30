"""The M8b `AsOfTReader` (D28/FR-23) — findings surfaces reconstructed at a past T.

Composition per row (the D28 recipe): the scanner facts come from the digest's occurrence
history (last committed appearance ≤ T, catalog-ordered — `query/pit.py` rules); the human
fields from the audit replay (`query/human_at.py`); decisions active at T project through
M5c's OWN precedence engine (`decisions/projection.project` — single source, never a copy).
Ownership at T mirrors `_target_for`: a direct human state ≠ open owns the finding; otherwise
the winning active decision projects.

Return shapes MATCH the current-state responses (FR-23: time-travel changes WHEN, never the
wire contract). Two deliberate deviations, both spec-rooted:
- fields the history does not record (`epss`, `disagree`, `image_repo`, `tag`, `app`) come back
  `null`; a FILTER or SORT or GROUP on them at past T is a 422 (`ValueError` at the seam) —
  silently mis-filtering would be worse; whitelisted FACETS on them return empty buckets. `kev`
  is recorded only from mapping v20 on (issue 1000): it decides the SLA deadline, and otherwise
  is treated like the fields above, because the older history has no value.
- paging is stateless (an opaque `search_after`-style cursor, no PIT): history is immutable, so
  a walk is consistent by construction.

Input re-validation (the protocol's contract): the routes forward `filters`/`sort`/`order`/
`by`/facet `fields` RAW past the seam — everything is re-checked here; `ValueError` → the
route's 422, never an unchecked aggregation (a 500).

Scale note: reconstruction is per-call and cluster-wide (bounded by per-digest row caps) —
the MVP read path; measure before optimizing (#134 bench).
"""

import base64
import json
from datetime import date, datetime, timedelta
from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.decisions.projection import project
from backend.models.envelope import SEVERITY_RANK, canonical_severity
from backend.query.aggs import counting_filters
from backend.query.human_at import decisions_active_at, finding_states_at
from backend.query.pit import latest_committed_runs
from backend.query.search import SearchFilters
from backend.sla.overdue import compute_overdue
from backend.sla.policy import read_sla_policy

_PAGE = 1_000
# whitelists at past T — the reconstructable subset of the current-state vocabularies
_SORT_FIELDS = ("severity_rank", "first_seen_at", "last_scan_at", "cvss")  # epss: not recorded
_FACET_FIELDS = (
    "severity",
    "state",
    "scanner",
    "fixable",
    "kev",
    "disagree",
    "present",
    "ptype",
    "overdue",  # issue 363: counts the reconstruction's own at-T verdict (rows carry the bool)
    "unassigned",  # issue 349 §1: an expression over the row's assignee, mirrored below
)
# whitelisted, but no history values → empty buckets (kev: none before mapping v20, issue 1000)
_EMPTY_FACETS = ("kev", "disagree")
_GROUP_FIELDS = ("image_digest", "namespaces", "cve_id", "assignee", "ptype")  # no image_repo/app


def _unrecorded(name: str) -> ValueError:
    return ValueError(
        f"{name} is not recorded in per-scan history — not available for a past as_of"
    )


def _encode(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode(cursor: str) -> dict[str, Any]:
    try:
        out = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(out, dict):
        raise ValueError("invalid cursor")
    return out


async def _last_rows_per_key(
    client: AsyncOpenSearch,
    cluster_id: str,
    scanner: str,
    digest: str,
    committed: list[dict[str, Any]],
    prefix: str,
) -> list[dict[str, Any]]:
    """One digest's reconstructed scanner rows at T: the LAST committed occurrence per
    finding_key (top_hits by `scan_order` — exact), plus the first-appearance clock. Present ⟺
    that last appearance IS the digest's latest run; otherwise the row is a tombstone whose
    `resolved_at` is the first committed run after it (the rebuild arm's derivation, §9)."""
    orders = [r["scan_order"] for r in committed]
    latest = committed[-1]
    rows: list[dict[str, Any]] = []
    after: dict[str, Any] | None = None
    while True:
        composite: dict[str, Any] = {
            "size": _PAGE,
            "sources": [{"key": {"terms": {"field": "finding_key"}}}],
        }
        if after is not None:
            composite["after"] = after
        try:
            resp = await client.search(
                index=f"{prefix}javv-finding-occurrences-{cluster_id}-*",
                body={
                    "size": 0,
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"scanner": scanner}},
                                {"term": {"image_digest": digest}},
                                {"terms": {"scan_order": orders}},  # committed runs only
                            ]
                        }
                    },
                    "aggs": {
                        "k": {
                            "composite": composite,
                            "aggs": {
                                "last": {"top_hits": {"size": 1, "sort": [{"scan_order": "desc"}]}},
                                # dates are epoch-ms (< 2^53) — a min agg is exact here
                                "first": {
                                    "min": {
                                        "field": "@timestamp",
                                        "format": "strict_date_optional_time",
                                    }
                                },
                            },
                        }
                    },
                },
            )
        except NotFoundError:
            return rows
        agg = resp["aggregations"]["k"]
        for b in agg["buckets"]:
            src = b["last"]["hits"]["hits"][0]["_source"]
            present = src["scan_order"] == latest["scan_order"]
            resolved_at = None
            if not present:
                resolved_at = next(
                    r["@timestamp"] for r in committed if r["scan_order"] > src["scan_order"]
                )
            rows.append(
                {
                    "occurrence": src,
                    "present": present,
                    "resolved_at": resolved_at,
                    "first_seen_at": b["first"].get("value_as_string"),
                }
            )
        after = agg.get("after_key")
        if after is None or not agg["buckets"]:
            return rows


def _finding_row(raw: dict[str, Any], human: dict[str, Any]) -> dict[str, Any]:
    """One wire row in the findings-grid vocabulary. Fields the history does not record are
    explicit nulls; `kev` too, since the history before mapping v20 has none (issue 1000)."""
    occ = raw["occurrence"]
    return {
        "finding_key": occ["finding_key"],
        "cluster_id": occ["cluster_id"],
        "scanner": occ["scanner"],
        "image_digest": occ["image_digest"],
        "image_repo": None,
        "tag": None,
        "namespaces": occ.get("namespaces") or [],
        "app": None,
        "cve_id": occ["vuln_id"],
        "package_name": occ["package_name"],
        "installed_version": occ["package_version"],
        "severity": occ["severity"],  # verbatim, as-of-then (D16) — display
        # D46/#274: derived, not read from the row — pre-D46 occurrence rows never stored it,
        # and deriving keeps the whole history uniform (canonical_severity is deterministic)
        "severity_canonical": canonical_severity(occ["severity"] or ""),
        "severity_rank": SEVERITY_RANK[canonical_severity(occ["severity"] or "")],
        "cvss": occ.get("cvss"),
        "fixable": occ.get("fixable"),
        "fixed_version": occ.get("fixed_version"),
        "ptype": occ.get("ptype"),  # recorded from M8d on; explicit null on v3-era rows
        "epss": None,
        "kev": None,
        "disagree": None,
        "first_seen_at": raw["first_seen_at"],
        "last_seen_at": occ["@timestamp"],
        "last_scan_run_id": occ["scan_run_id"],
        "last_scan_order": occ["scan_order"],
        "last_scan_at": occ["@timestamp"],
        "present": raw["present"],
        "resolved_at": raw["resolved_at"],
        "state": human["state"],
        "vex_justification": human["vex_justification"],
        "assignee": human["assignee"],
        "notes": human["notes"],
        "pre_stale_status": None,
        "state_decision_id": human.get("state_decision_id"),
        "schema_version": occ.get("schema_version"),
    }


class AsOfTQuery:
    """The registered reader (slice 3: findings trio; slice 4 adds trends + contributors)."""

    async def _raws(
        self, client: AsyncOpenSearch, cluster_id: str, t: datetime, *, prefix: str = ""
    ) -> list[dict[str, Any]]:
        """The cluster's raw scanner facts at T (occurrence + presence + first/resolved clocks)
        — shared by the findings reconstruction and the findings-trend derivation."""
        runs = await latest_committed_runs(client, cluster_id, t, prefix=prefix)
        by_digest: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in runs:
            by_digest.setdefault((r["scanner"], r["image_digest"]), []).append(r)

        raws: list[dict[str, Any]] = []
        for (scanner, digest), latest_only in sorted(by_digest.items()):
            # committed runs ≤ T for the digest (ascending) — resolved_at needs the successor
            committed = await self._committed_asc(
                client, cluster_id, t, scanner, digest, prefix=prefix
            )
            if not committed:
                committed = latest_only
            raws.extend(
                await _last_rows_per_key(client, cluster_id, scanner, digest, committed, prefix)
            )
        return raws

    async def _reconstruct(
        self, client: AsyncOpenSearch, cluster_id: str, t: datetime, *, prefix: str = ""
    ) -> list[dict[str, Any]]:
        """Every finding row of the cluster as it stood at T (present AND tombstones) —
        filters/facets/groups are applied over this one reconstruction."""
        raws = await self._raws(client, cluster_id, t, prefix=prefix)
        keys = [r["occurrence"]["finding_key"] for r in raws]
        humans = await finding_states_at(client, cluster_id, t, finding_keys=keys, prefix=prefix)
        decisions = await decisions_active_at(client, cluster_id, t, prefix=prefix)
        iso = t.isoformat()

        rows: list[dict[str, Any]] = []
        for raw in raws:
            fk = raw["occurrence"]["finding_key"]
            human = dict(humans[fk])
            human["state_decision_id"] = None
            row = _finding_row(raw, human)
            # ownership at T mirrors reproject._target_for: a direct human state ≠ open owns
            # the finding; an un-owned one takes the winning active decision's projection
            if row["state"] == "open" and decisions:
                won = project(row, decisions, at=iso)
                if won is not None:
                    row["state"] = won.state
                    row["vex_justification"] = won.vex_justification
                    row["state_decision_id"] = won.decision_id
            rows.append(row)

        # the deadline judges KEV as the scan recorded it (issue 1000); a history row written
        # before mapping v20 has no value, so that finding gets the deadline of its severity
        kev = {r["occurrence"]["finding_key"]: bool(r["occurrence"].get("kev")) for r in raws}
        await self._decorate_overdue(client, rows, t, kev=kev, prefix=prefix)
        return rows

    async def _committed_asc(
        self,
        client: AsyncOpenSearch,
        cluster_id: str,
        t: datetime,
        scanner: str,
        digest: str,
        *,
        prefix: str,
    ) -> list[dict[str, Any]]:
        try:
            resp = await client.search(
                index=f"{prefix}javv-scan-events-{cluster_id}-*",
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"scanner": scanner}},
                                {"term": {"image_digest": digest}},
                                {"range": {"@timestamp": {"lte": t.isoformat()}}},
                            ]
                        }
                    },
                    "sort": [{"scan_order": "asc"}],
                    "size": _PAGE,
                    "_source": ["scan_run_id", "scan_order", "@timestamp", "commit_key"],
                },
            )
        except NotFoundError:
            return []
        return [h["_source"] for h in resp["hits"]["hits"]]

    async def _decorate_overdue(
        self,
        client: AsyncOpenSearch,
        rows: list[dict[str, Any]],
        t: datetime,
        *,
        kev: dict[str, bool],
        prefix: str,
    ) -> None:
        if not rows:
            return
        # the D21 group clock across the WHOLE reconstruction (siblings included), judged at T
        # with the recorded KEV value; the row itself keeps `kev: null` (issue 1000, D2)
        judged = [dict(r, kev=kev[r["finding_key"]]) for r in rows]
        verdicts = compute_overdue(
            judged, policy=await read_sla_policy(client, prefix=prefix), now=t
        )
        for row in rows:
            v = verdicts[row["finding_key"]]
            row["overdue"] = v.overdue
            row["due_at"] = v.due_at

    # --- the protocol surface ------------------------------------------------

    @staticmethod
    def _apply_filters(rows: list[dict[str, Any]], f: SearchFilters) -> list[dict[str, Any]]:
        if f.kev is not None:
            raise _unrecorded("kev")
        if f.disagree is not None:
            raise _unrecorded("disagree")
        # an empty list is no filter, as on the live read
        if f.image_repo:
            raise _unrecorded("image_repo")
        if f.exclude_image_repo:
            raise _unrecorded("exclude_image_repo")
        if f.q is not None:
            # contains-search spans image_repo, which occurrences don't record — a partial match
            # at a past T would silently LIE (rows missing for the wrong reason). Reject loudly.
            raise _unrecorded("q")
        if f.new_within_days is not None:
            # first_seen_at is the findings-cache D21 group clock — occurrences don't record it
            raise _unrecorded("new_within_days")
        sev = set(f.severity) if f.severity else None
        out = []
        for r in rows:
            if r["present"] != f.present:
                continue
            # overdue at T filters the reconstruction's OWN read-time verdict (judged at now=t
            # by _decorate_overdue above) — never the live cache's sla_clock_at (issue 363):
            # history has no cache, and the materialized clock describes now, not T
            if f.overdue is not None and r["overdue"] != f.overdue:
                continue
            # unassigned at T (issue 349 §1): answerable from the reconstruction, since
            # occurrences carry the assignee. Mirrors the live clause — an owner is a NON-EMPTY
            # assignee, so a cleared one ("") counts as unowned here too
            if f.unassigned is not None and bool(r.get("assignee")) == f.unassigned:
                continue
            # D46/#274: compare the CANONICAL bucket, mirroring the live filter's target field
            if sev and r["severity_canonical"] not in sev:
                continue
            if f.state and r["state"] not in f.state:
                continue
            # excludes mirror the live PURE-must_not semantics (issue 349): a row MISSING the
            # field survives the exclusion, so `got == want` drops and None/absent passes
            if f.exclude_severity and r["severity_canonical"] in f.exclude_severity:
                continue
            if f.exclude_state and r["state"] in f.exclude_state:
                continue
            checks = (
                (f.scanner, r["scanner"]),
                (f.fixable, r["fixable"]),
                (f.image_digest, r["image_digest"]),
            )
            if any(want is not None and want != got for want, got in checks):
                continue
            # the list filters (issue 949) are MEMBERSHIP, mirroring the live `terms`: an
            # equality test against a list would drop every row and still look like a filter
            in_checks = (
                (f.assignee, r["assignee"]),
                (f.cve_id, r["cve_id"]),
                # ptype IS recorded on occurrences from M8d on — a filter at a past T matches
                # rows as-scanned; v3-era rows carry null and correctly drop out
                (f.ptype, r["ptype"]),
                # package_name likewise rides the occurrence row (issue 492)
                (f.package_name, r["package_name"]),
            )
            if any(want and got not in want for want, got in in_checks):
                continue
            if f.namespace and not set(f.namespace) & set(r["namespaces"] or []):
                continue
            ex_checks = (
                (f.exclude_assignee, r["assignee"]),
                (f.exclude_ptype, r["ptype"]),
                (f.exclude_cve_id, r["cve_id"]),
                (f.exclude_package_name, r["package_name"]),
            )
            if f.exclude_scanner is not None and f.exclude_scanner == r["scanner"]:
                continue
            if any(want and got in want for want, got in ex_checks):
                continue
            if f.exclude_namespace and set(f.exclude_namespace) & set(r["namespaces"] or []):
                continue
            out.append(r)
        return out

    async def findings_snapshot(
        self,
        client: AsyncOpenSearch,
        *,
        cluster_id: str,
        t: datetime,
        filters: SearchFilters,
        sort: str,
        order: str,
        prefix: str = "",
    ) -> list[dict[str, Any]]:
        """Every filtered row at T in walk order, from ONE reconstruction — the export
        path's source (audit F-09: paging findings_page re-reconstructed the whole cluster
        per page; a sweep holds the same list one page already materialized, once)."""
        # re-validate EVERYTHING before reconstructing — a bad input must cost a 422, not a
        # cluster-wide reconstruction (and never reach an evaluation, per the seam contract)
        if sort not in _SORT_FIELDS:
            raise ValueError(f"sort must be one of {_SORT_FIELDS} for a past as_of")
        if order not in ("asc", "desc"):
            raise ValueError("order must be asc or desc")
        self._apply_filters([], filters)  # filter re-validation, before any work
        rows = self._apply_filters(
            await self._reconstruct(client, cluster_id, t, prefix=prefix), filters
        )
        desc = order == "desc"

        def _key(r: dict[str, Any]) -> Any:
            v = r.get(sort)
            return (v is None, v)  # nulls last on asc; stable + comparable

        rows.sort(key=lambda r: r["finding_key"])
        rows.sort(key=_key, reverse=desc)
        return rows

    async def findings_page(
        self,
        client: AsyncOpenSearch,
        *,
        cluster_id: str,
        t: datetime,
        filters: SearchFilters,
        sort: str,
        order: str,
        size: int,
        cursor: str | None,
        prefix: str = "",
    ) -> dict[str, Any]:
        if cursor is not None:
            _decode(cursor)  # shape check before any reconstruction work
        rows = await self.findings_snapshot(
            client,
            cluster_id=cluster_id,
            t=t,
            filters=filters,
            sort=sort,
            order=order,
            prefix=prefix,
        )
        if cursor is not None:
            c = _decode(cursor)
            if c.get("s") != sort or c.get("o") != order:
                raise ValueError("invalid cursor")  # a cursor is bound to its walk's ordering
            last_key = c.get("k")
            idx = next((i for i, r in enumerate(rows) if r["finding_key"] == last_key), None)
            rows_after = rows[idx + 1 :] if idx is not None else rows
        else:
            rows_after = rows
        page = rows_after[:size]
        next_cursor = (
            _encode({"k": page[-1]["finding_key"], "s": sort, "o": order})
            if len(rows_after) > size
            else None
        )
        return {
            "data": page,
            "next_cursor": next_cursor,
            "total": {"value": len(rows), "relation": "eq"},
        }

    async def findings_facets(
        self,
        client: AsyncOpenSearch,
        *,
        cluster_id: str,
        t: datetime,
        filters: SearchFilters,
        fields: list[str] | None,
        prefix: str = "",
        all_filters: bool = False,
    ) -> dict[str, Any]:
        chosen = list(fields) if fields is not None else list(_FACET_FIELDS)
        bad = [f for f in chosen if f not in _FACET_FIELDS]
        if bad:
            raise ValueError(f"not facetable (whitelist {_FACET_FIELDS}): {bad}")
        reconstructed = await self._reconstruct(client, cluster_id, t, prefix=prefix)
        rows = self._apply_filters(reconstructed, filters)
        facets: dict[str, list[dict[str, Any]]] = {}
        for field in chosen:
            if field in _EMPTY_FACETS:  # whitelisted but unrecorded at T — explicit empty
                facets[field] = []
                continue
            # mirrors the live facet: the same filters per facet (issues 949, 979 and 999)
            own_filters = filters if all_filters else counting_filters(filters, field)
            counted = (
                rows if own_filters == filters else self._apply_filters(reconstructed, own_filters)
            )
            counts: dict[Any, dict[str, Any]] = {}
            for r in counted:
                if field == "unassigned":
                    # issue 349 §1: an expression, not a stored key — an owner is a NON-EMPTY
                    # assignee (a cleared one is ""), the same reading as the live filter agg
                    # and this reader's own filter above
                    key: Any = not bool(r.get("assignee"))
                else:
                    # D46/#274: the severity facet counts the canonical bucket (mirrors the
                    # live facet's field alias — keys are critical/medium/…, never verbatim)
                    key = r["severity_canonical" if field == "severity" else field]
                if key is None:
                    if field != "ptype":
                        continue
                    key = "unknown"  # mirrors the live facet's missing-bucket (the B-1 caveat)
                key = str(key).lower() if isinstance(key, bool) else key
                b = counts.setdefault(key, {"key": key, "count": 0, "by_scanner": {}})
                b["count"] += 1
                b["by_scanner"][r["scanner"]] = b["by_scanner"].get(r["scanner"], 0) + 1
            facets[field] = sorted(counts.values(), key=lambda b: (-b["count"], str(b["key"])))
        return {"facets": facets}

    async def findings_groups(
        self,
        client: AsyncOpenSearch,
        *,
        cluster_id: str,
        t: datetime,
        filters: SearchFilters,
        by: str,
        size: int,
        cursor: str | None,
        prefix: str = "",
    ) -> dict[str, Any]:
        if by not in _GROUP_FIELDS:
            raise ValueError(f"not groupable at a past as_of (whitelist {_GROUP_FIELDS}): {by!r}")
        rows = self._apply_filters(
            await self._reconstruct(client, cluster_id, t, prefix=prefix), filters
        )
        buckets: dict[str, dict[str, Any]] = {}
        for r in rows:
            keys = r[by] if by == "namespaces" else [r[by]]
            for key in keys or []:
                if key is None:
                    continue
                b = buckets.setdefault(key, {"key": key, "count": 0, "by_scanner": {}})
                b["count"] += 1
                b["by_scanner"][r["scanner"]] = b["by_scanner"].get(r["scanner"], 0) + 1
        ordered = sorted(buckets.values(), key=lambda b: b["key"])  # composite order: key asc
        if cursor is not None:
            after = _decode(cursor).get("a")
            ordered = [b for b in ordered if b["key"] > after]
        page = ordered[:size]
        next_cursor = _encode({"a": page[-1]["key"]}) if len(ordered) > size else None
        return {"data": page, "next_cursor": next_cursor}

    # --- trends + contributors at T (slice 4) ---------------------------------
    # The scans trend and the contributors board read APPEND logs (scan-events, audit-log) —
    # immutable, so the historical answer IS the same aggregation with the window ending at T
    # (the anchored builders; single source with the current-state routes). The FINDINGS trend
    # buckets on the mutable cache in current-state — at a past T it derives from occurrences
    # instead (a reappearance clears the cache's `resolved_at`, so the cache cannot answer
    # history); same limitation class as the cache, one direction stricter.

    async def trends_scans(
        self,
        client: AsyncOpenSearch,
        *,
        cluster_id: str,
        t: datetime,
        days: int,
        prefix: str = "",
    ) -> dict[str, Any]:
        from backend.query.trends import build_scans_trend_body
        from backend.routers.trends import _series
        from backend.tenancy.read_path import tenant_search

        body = build_scans_trend_body(days=days, anchor=t)  # ValueError on bad days → 422
        resp = await tenant_search(
            client,
            index=f"{prefix}javv-scan-events-{cluster_id}-*",
            cluster_id=cluster_id,
            body=body,
        )
        aggs = resp.get("aggregations")
        series = _series(aggs["by_scanner"], metric="scans") if aggs else {}
        return {"series": series, "days": days}

    async def trends_findings(
        self,
        client: AsyncOpenSearch,
        *,
        cluster_id: str,
        t: datetime,
        days: int,
        prefix: str = "",
    ) -> dict[str, Any]:
        if not 1 <= days <= 365:
            raise ValueError("days must be 1..365")
        raws = await self._raws(client, cluster_id, t, prefix=prefix)
        start = t.date() - timedelta(days=days)
        end = t.date()

        def _day(iso: str | None) -> date | None:
            if iso is None:
                return None
            return datetime.fromisoformat(iso).date()

        new: dict[str, dict[date, int]] = {}
        resolved: dict[str, dict[date, int]] = {}
        for raw in raws:
            scanner = raw["occurrence"]["scanner"]
            first = _day(raw["first_seen_at"])
            if first is not None and start <= first <= end:
                bucket = new.setdefault(scanner, {})
                bucket[first] = bucket.get(first, 0) + 1
            gone = _day(raw["resolved_at"])
            if gone is not None and start <= gone <= end:
                bucket = resolved.setdefault(scanner, {})
                bucket[gone] = bucket.get(gone, 0) + 1

        def _axis(per_scanner: dict[str, dict[date, int]]) -> dict[str, list[dict[str, Any]]]:
            # the continuous zero-filled day axis, matching the date_histogram wire format
            days_axis = [start + timedelta(days=i) for i in range((end - start).days + 1)]
            return {
                scanner: [
                    {"date": f"{d.isoformat()}T00:00:00.000Z", "count": buckets.get(d, 0)}
                    for d in days_axis
                ]
                for scanner, buckets in sorted(per_scanner.items())
            }

        return {
            "new": _axis(new),
            "resolved": _axis(resolved),
            "resolved_semantics": "scan_resolved",  # same A-m9 label as current-state
            "days": days,
        }

    async def contributors(
        self,
        client: AsyncOpenSearch,
        *,
        cluster_id: str,
        t: datetime,
        days: int,
        prefix: str = "",
    ) -> dict[str, Any]:
        from backend.query.contributors import (
            build_actions_body,
            compute_team_totals,
            compute_ttr_sla,
            empty_totals,
        )
        from backend.routers.contributors import _findings_for, _handling_rows
        from backend.sla.policy import read_sla_policy as _policy
        from backend.tenancy.read_path import tenant_search

        body = build_actions_body(days=days, anchor=t)  # ValueError on bad days → 422
        resp = await tenant_search(
            client, index=f"{prefix}system-audit-log-*", cluster_id=cluster_id, body=body
        )
        aggs = resp.get("aggregations")
        if not aggs:
            return {
                "days": days,
                "leaderboard": [],
                "handled_over_time": [],
                "totals": empty_totals(),
            }

        rows = await _handling_rows(client, cluster_id, days, anchor=t, prefix=prefix)
        findings = await _findings_for(
            client,
            cluster_id,
            sorted({r["finding_key"] for r in rows if r.get("finding_key")}),
            prefix=prefix,
        )
        policy = await _policy(client, prefix=prefix)
        verdicts = compute_ttr_sla(rows, findings, policy=policy)
        by_action = {a["key"]: a["doc_count"] for a in aggs["by_action"]["buckets"]}
        totals = {
            "actions": sum(by_action.values()),
            "by_action": by_action,
            **compute_team_totals(rows, findings, policy=policy),
        }
        leaderboard = []
        for bucket in aggs["by_actor"]["buckets"]:
            actor = bucket["key"]
            v = verdicts.get(actor, {})
            leaderboard.append(
                {
                    "actor": actor,
                    "actions": bucket["doc_count"],
                    "by_action": {a["key"]: a["doc_count"] for a in bucket["by_action"]["buckets"]},
                    "handled": v.get("handled", 0),
                    "median_ttr_seconds": v.get("median_ttr_seconds"),
                    "sla_hit_pct": v.get("sla_hit_pct"),
                }
            )
        timeline = [
            {"date": b["key_as_string"], "count": b["doc_count"]}
            for b in aggs["handled_over_time"]["timeline"]["buckets"]
        ]
        return {
            "days": days,
            "leaderboard": leaderboard,
            "handled_over_time": timeline,
            "totals": totals,
        }
