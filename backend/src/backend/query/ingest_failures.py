"""The failed-ingests read (issue 357): one scanner's rejected pushes, newest first, paged.

Paged by `search_after` with NO point-in-time. The series is append-only and read newest-first on
a total order (`@timestamp`, then the unique `failure_id`), so a record written mid-walk lands
AHEAD of the cursor and never shifts a later page — the stability a PIT would buy, without
spending the per-principal PIT budget on a panel that sits on a screen next to others. The one
thing that can move under a walk is retention dropping an old index, which only ends it early.

The window is the shared trend vocabulary (`days` + optional `as_of`, day-floored like every
trend, or an exact `window_seconds` at now, issue 1291), filtered on the server stamp. Each page
takes its window at its own request, as it takes the rows: an exact start moves with the clock,
and a row that left the range is not on a later page. Per-scanner is sacred: `scanner` is
required, so every page and every total belongs to exactly one scanner.
"""

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any

from backend.query.trends import trend_window

SORT: list[dict[str, str]] = [{"@timestamp": "desc"}, {"failure_id": "desc"}]
ROW_FIELDS = [
    "@timestamp",
    "failure_id",
    "scanner",
    "stage",
    "reason",
    "status",
    "error",
    "image_ref",
]


def encode_cursor(sort_values: list[Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps({"a": sort_values}).encode()).decode()


def decode_cursor(cursor: str) -> list[Any]:
    """The last row's sort values, shape-checked so a tampered cursor is a 422, never a 500
    from inside the search."""
    try:
        after = json.loads(base64.urlsafe_b64decode(cursor.encode()))["a"]
    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid cursor") from exc
    if not (
        isinstance(after, list)
        and len(after) == 2
        and isinstance(after[0], int)
        and not isinstance(after[0], bool)
        and isinstance(after[1], str)
    ):
        raise ValueError("invalid cursor")
    return after


def build_ingest_failures_body(
    *,
    scanner: str,
    size: int,
    days: int | None = None,
    window_seconds: int | None = None,
    anchor: datetime | None = None,
    search_after: list[Any] | None = None,
) -> dict[str, Any]:
    """Pure builder. Asks for `size + 1` rows: the extra one only says whether a next page
    exists, so the last page never costs an empty round-trip. The window ends at T or now, the
    end of the strip above the table."""
    w = trend_window(days, window_seconds, anchor or datetime.now(UTC))
    window: dict[str, Any] = {"gte": w.gte, "lte": w.lte}
    body: dict[str, Any] = {
        "size": size + 1,
        "track_total_hits": True,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"scanner": scanner}},
                    {"range": {"@timestamp": window}},
                ]
            }
        },
        "sort": SORT,
        "_source": ROW_FIELDS,
    }
    if search_after is not None:
        body["search_after"] = search_after
    return body


def page_of(resp: dict[str, Any], size: int) -> dict[str, Any]:
    """The list envelope (api-design.md, wrapped total): `data`, `total`, `next_cursor`."""
    hits = resp["hits"]["hits"]
    rows = hits[:size]
    more = len(hits) > size
    return {
        "data": [h["_source"] for h in rows],
        "total": resp["hits"]["total"],
        "next_cursor": encode_cursor(rows[-1]["sort"]) if more and rows else None,
    }
