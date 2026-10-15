"""A removed route stays for one release (issue 261, item 2).

During an upgrade the frontend and the backend change at different times, and a rollback runs an
older frontend against a newer backend. So a route that the newest release has must still be in
the API contract (`frontend/openapi.json`), unless that release marked it `deprecated`: a route is
deprecated in one release, and the next release can remove it.
"""

import json
from typing import Any

from release_refs import ROOT, newest_release_tag, show

CONTRACT = "frontend/openapi.json"
_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


def _removed_routes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """The routes of `old` that `new` does not have and that `old` did not mark deprecated."""
    problems = []
    for path, operations in old["paths"].items():
        for method, operation in operations.items():
            if method not in _METHODS or method in new["paths"].get(path, {}):
                continue
            if not operation.get("deprecated", False):
                problems.append(f"{method.upper()} {path}")
    return problems


def test_a_route_of_the_last_release_is_kept_or_was_deprecated() -> None:
    tag = newest_release_tag()
    removed = _removed_routes(
        json.loads(show(tag, CONTRACT)), json.loads((ROOT / CONTRACT).read_text())
    )
    assert not removed, (
        f"removed without a release that marked them deprecated ({tag} did not): {removed}. "
        "Mark a route deprecated=True in one release, and remove it in the next"
    )


# --- the comparison itself --------------------------------------------------------------------

_OLD = {
    "paths": {
        "/api/v1/meta": {"get": {}},
        "/api/v1/views/{view_id}": {"get": {}, "delete": {"deprecated": True}},
        "/api/v1/old": {"parameters": [], "post": {"deprecated": False}},
    }
}


def test_a_removed_route_that_was_not_deprecated_is_a_problem() -> None:
    new = {"paths": {"/api/v1/meta": {"get": {}}, "/api/v1/views/{view_id}": {"get": {}}}}
    assert _removed_routes(_OLD, new) == ["POST /api/v1/old"]


def test_a_removed_route_that_was_deprecated_is_not_a_problem() -> None:
    new = {"paths": {"/api/v1/meta": {"get": {}}, "/api/v1/old": {"post": {}}}}
    assert _removed_routes(_OLD, new) == ["GET /api/v1/views/{view_id}"]


def test_a_new_route_and_a_kept_route_are_not_problems() -> None:
    new = {"paths": {**_OLD["paths"], "/api/v1/new": {"get": {}}}}
    assert _removed_routes(_OLD, new) == []
