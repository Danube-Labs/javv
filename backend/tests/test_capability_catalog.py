"""The permission list (issue 990): the Roles card shows each permission by name and what it
allows, so the list must name every permission a route checks, and agree with docs/API.md."""

import re
from pathlib import Path

from backend.auth.capabilities import PERMISSIONS, ROLE_BUNDLES

SRC = Path(__file__).resolve().parents[1] / "src" / "backend"
API_MD = Path(__file__).resolve().parents[2] / "docs" / "API.md"
CAP_LITERAL = re.compile(r"[\"'](can_[a-z_]+)[\"']")


def _ids() -> list[str]:
    return [p.id for p in PERMISSIONS]


def test_each_permission_is_listed_once_with_a_name_and_what_it_allows() -> None:
    assert len(_ids()) == len(set(_ids()))
    for p in PERMISSIONS:
        assert p.name.strip() and p.description.strip(), p.id
        assert not p.name.startswith("can_"), p.id


def test_the_list_has_each_permission_the_code_checks() -> None:
    checked = {
        m.group(1)
        for path in SRC.rglob("*.py")
        if path.name != "capabilities.py"
        for m in CAP_LITERAL.finditer(path.read_text())
    }
    assert checked, "the scan found no permission names; check the pattern"
    assert checked <= set(_ids()), sorted(checked - set(_ids()))


def test_the_list_has_each_permission_of_a_default_role() -> None:
    granted = {cap for caps in ROLE_BUNDLES.values() for cap in caps if cap != "*"}
    assert granted <= set(_ids()), sorted(granted - set(_ids()))


def test_the_list_agrees_with_the_permission_table_in_api_md() -> None:
    rows = re.findall(r"^\| `(can_[a-z_]+)` \|", API_MD.read_text(), flags=re.MULTILINE)
    assert rows == _ids()
