"""The as-of-T dispatcher (M6 slice 7, D28/FR-23) — the M8b seam, typed.

Every read endpoint accepts `as_of`. This module owns the dispatch DECISION and nothing else:

- absent / `"now"` / a future instant → `None`: the route reads materialized current-state
  and NEVER touches the reconstruction path (the T=now short-circuit, DoD-pinned).
- a past instant → the route delegates to the registered `AsOfTReader` — M8b's `as_of_t`
  composition (occurrences ≤ T ⋈ decisions-active-at-T + audit replay ≤ T + images ≤ T,
  catalog-first by `scan_order`, D39/D40). M6 contains NO reconstruction logic; until M8b
  registers an implementation, a past T is `501` (`AsOfTUnavailable` at the seam).

Ruling (recorded on #31): no standalone M8b spike — this protocol + its contract tests ARE
the verified interface M8b lands against. A future T clamps to now rather than erroring: a
UI picker a few seconds ahead of the server clock is asking for "now", not for a 4xx.
"""

from datetime import UTC, datetime
from typing import Any, Protocol

from opensearchpy import AsyncOpenSearch

from backend.query.search import SearchFilters


class AsOfTUnavailable(LookupError):
    """A past-T read arrived before M8b registered its reader — routes answer 501."""


class AsOfTReader(Protocol):
    """The M8b contract: one method per M6 read surface, mirroring the route's own
    parameters plus the parsed T. Return shapes match the current-state responses —
    time-travel changes WHEN, never the wire contract (FR-23).

    Input-validation contract (audit A-n): the current-state routes validate their inputs
    (the facet `fields` whitelist, sort/order, `by` dimension) INSIDE the body builders, but the
    past-T delegation forwards those parameters RAW. The reader MUST re-validate every delegated
    input — especially `findings_facets`'s `fields` — and raise `ValueError` on a non-whitelisted
    value (the route maps it to 422), never pass it unchecked into an aggregation (a 500)."""

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
    ) -> dict[str, Any]: ...

    async def findings_facets(
        self,
        client: AsyncOpenSearch,
        *,
        cluster_id: str,
        t: datetime,
        filters: SearchFilters,
        fields: list[str] | None,
        all_filters: bool = False,
        contains: str | None = None,
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

    async def trends_scans(
        self, client: AsyncOpenSearch, *, cluster_id: str, t: datetime, days: int
    ) -> dict[str, Any]: ...

    async def trends_findings(
        self, client: AsyncOpenSearch, *, cluster_id: str, t: datetime, days: int
    ) -> dict[str, Any]: ...

    async def contributors(
        self, client: AsyncOpenSearch, *, cluster_id: str, t: datetime, days: int
    ) -> dict[str, Any]: ...


_reader: AsOfTReader | None = None


def register_as_of_t(reader: AsOfTReader | None) -> None:
    """M8b calls this once at startup (None unregisters — tests use it to reset)."""
    global _reader
    _reader = reader


def as_of_t_reader() -> AsOfTReader:
    if _reader is None:
        raise AsOfTUnavailable(
            "as_of in the past requires historical reconstruction (M8b's as_of_t)"
        )
    return _reader


def parse_as_of(raw: str | None, *, now: datetime | None = None) -> datetime | None:
    """`None` = read current state; a datetime = delegate to the reader at that T."""
    if raw is None or raw == "now":
        return None
    try:
        t = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            "as_of must be ISO-8601 (e.g. 2026-07-01T00:00:00+00:00) or 'now'"
        ) from exc
    if t.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if t >= (now or datetime.now(UTC)):
        return None  # future/just-now = current state (clock-skewed pickers aren't errors)
    return t
