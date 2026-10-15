"""A release only adds to the index mappings (issue 261, item 2).

`bootstrap()` changes an index in place with `put_mapping` and a template by overwriting it. That
works for an added field only: OpenSearch refuses a retyped field, and a removed one stays in the
index. An older release that runs after a rollback also reads the newer indices. So the
definitions in `core/bootstrap.py` are compared twice:

- with the newest release tag: every index, template, field and setting of that release is still
  there and the same. Only new indices, templates and fields may appear. A breaking change passes
  only when `BREAKING_CHANGES` names it, and `docs/engineering/UPGRADES.md` ("A breaking change")
  says what such a release needs.
- with the merge base on main: a change bumps `MAPPING_VERSION`. `bootstrap()` leaves an index
  alone once its version is at or above `MAPPING_VERSION`, so a second change under the same
  number never reaches a store that already has the first.
"""

import copy
import types
from typing import Any

import pytest
import yaml

from backend.core import bootstrap
from release_refs import ROOT, merge_base_with_main, newest_release_tag, show

BOOTSTRAP = "backend/src/backend/core/bootstrap.py"

# The MAPPING_VERSION that makes a breaking change -> the problems it accepts, as
# `_breaking_changes` words them. Empty: every release so far only added.
BREAKING_CHANGES: dict[int, set[str]] = {}


def _definitions(indexes: dict[str, Any], templates: dict[str, Any]) -> dict[str, Any]:
    """Every index and template body by name, without the version marker."""
    out = {f"index {n}": copy.deepcopy(b) for n, b in indexes.items()}
    out |= {f"template {n}": copy.deepcopy(b) for n, b in templates.items()}
    for body in out.values():
        mappings = body["template"]["mappings"] if "template" in body else body["mappings"]
        mappings.pop("_meta", None)
    return out


def _definitions_at(ref: str) -> tuple[int, dict[str, Any]]:
    """MAPPING_VERSION and the definitions of `core/bootstrap.py` as it is at `ref`."""
    module = types.ModuleType(f"bootstrap_at_{ref}")
    exec(compile(show(ref, BOOTSTRAP), f"{ref}:{BOOTSTRAP}", "exec"), module.__dict__)
    return module.MAPPING_VERSION, _definitions(module.MUTABLE_INDEXES, module.INDEX_TEMPLATES)


def _breaking_changes(old: Any, new: Any, path: str = "") -> list[str]:
    """What `new` removed or changed from `old`. A new index or template, and a new key under
    `properties`, are additions, not problems."""
    if not (isinstance(old, dict) and isinstance(new, dict)):
        return [] if old == new else [f"{path}: {old!r} -> {new!r}"]
    problems = []
    for key, value in old.items():
        where = f"{path}.{key}" if path else key
        problems += (
            _breaking_changes(value, new[key], where) if key in new else [f"{where}: removed"]
        )
    if path and path.rsplit(".", 1)[-1] != "properties":
        problems += [f"{path}.{key}: added" for key in new if key not in old]
    return problems


def _version_problem(
    old: tuple[int, dict[str, Any]], new: tuple[int, dict[str, Any]]
) -> str | None:
    (old_version, old_defs), (new_version, new_defs) = old, new
    if new_version < old_version:
        return f"MAPPING_VERSION went down from {old_version} to {new_version}"
    if new_defs != old_defs and new_version == old_version:
        return f"the mappings changed and MAPPING_VERSION is still {new_version}: bump it by 1"
    return None


CURRENT = (
    bootstrap.MAPPING_VERSION,
    _definitions(bootstrap.MUTABLE_INDEXES, bootstrap.INDEX_TEMPLATES),
)


def test_a_release_only_adds_to_the_mappings() -> None:
    tag = newest_release_tag()
    released = _definitions_at(tag)
    accepted = set().union(
        *(BREAKING_CHANGES.get(v, set()) for v in range(released[0] + 1, CURRENT[0] + 1))
    )
    unaccepted = [p for p in _breaking_changes(released[1], CURRENT[1]) if p not in accepted]
    assert not unaccepted, (
        f"not additive since {tag}: {unaccepted}. A breaking change needs an entry in "
        "BREAKING_CHANGES and the steps in docs/engineering/UPGRADES.md, 'A breaking change'"
    )
    assert _version_problem(released, CURRENT) is None, (
        f"since {tag}: {_version_problem(released, CURRENT)}"
    )


def test_a_changed_mapping_bumps_the_version_since_main() -> None:
    base = merge_base_with_main()
    problem = _version_problem(_definitions_at(base), CURRENT)
    assert problem is None, f"since the merge base with main ({base[:8]}): {problem}"


def test_the_definitions_at_a_ref_are_read_from_that_ref() -> None:
    assert _definitions_at("HEAD")[0] == bootstrap.MAPPING_VERSION
    assert _definitions_at("v0.3.4")[0] == 13  # 0.3.4 shipped schema 13


def test_every_job_that_runs_the_backend_tests_checks_out_the_history() -> None:
    runs = 0
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        for name, job in (yaml.safe_load(workflow.read_text())["jobs"] or {}).items():
            steps = job.get("steps", [])
            if not any(
                "uv run pytest" in s.get("run", "") and s.get("working-directory") == "backend"
                for s in steps
            ):
                continue
            runs += 1
            checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
            assert checkout.get("with", {}).get("fetch-depth") == 0, (
                f"{workflow.name} job {name}: the upgrade checks need the tags and origin/main"
            )
    assert runs >= 2  # ci.yml's Backend and clock-drift.yml's backend at +90 days


# --- the comparison itself --------------------------------------------------------------------

_OLD = {
    "index findings": {
        "settings": {"index": {"number_of_shards": 1}},
        "mappings": {"dynamic": False, "properties": {"cve_id": {"type": "keyword"}}},
    },
    "template javv-images": {
        "index_patterns": ["javv-images-*"],
        "template": {"mappings": {"properties": {"repo": {"type": "keyword"}}}},
    },
}


def _changed(edit: Any) -> dict[str, Any]:
    new = copy.deepcopy(_OLD)
    edit(new)
    return new


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        pytest.param(
            lambda d: d["index findings"]["mappings"]["properties"].update(cve_id={"type": "text"}),
            ["index findings.mappings.properties.cve_id.type: 'keyword' -> 'text'"],
            id="retyped field",
        ),
        pytest.param(
            lambda d: d["index findings"]["mappings"]["properties"].pop("cve_id"),
            ["index findings.mappings.properties.cve_id: removed"],
            id="removed field",
        ),
        pytest.param(
            lambda d: d.pop("template javv-images"),
            ["template javv-images: removed"],
            id="removed template",
        ),
        pytest.param(
            lambda d: d["index findings"]["mappings"]["properties"]["cve_id"].update(index=False),
            ["index findings.mappings.properties.cve_id.index: added"],
            id="a field no longer indexed",
        ),
        pytest.param(
            lambda d: d["index findings"]["mappings"].update(dynamic=True),
            ["index findings.mappings.dynamic: False -> True"],
            id="dynamic changed",
        ),
        pytest.param(
            lambda d: d["index findings"]["settings"]["index"].update(number_of_shards=2),
            ["index findings.settings.index.number_of_shards: 1 -> 2"],
            id="shard count changed",
        ),
        pytest.param(
            lambda d: d["template javv-images"].update(index_patterns=["javv-image-*"]),
            ["template javv-images.index_patterns: ['javv-images-*'] -> ['javv-image-*']"],
            id="template pattern changed",
        ),
    ],
)
def test_a_change_that_is_not_an_addition_is_a_problem(edit: Any, expected: list[str]) -> None:
    assert _breaking_changes(_OLD, _changed(edit)) == expected


def test_new_fields_indices_and_templates_are_additions() -> None:
    def add(d: dict[str, Any]) -> None:
        d["index findings"]["mappings"]["properties"]["epss"] = {"type": "float"}
        d["index findings"]["mappings"]["properties"]["fix"] = {
            "properties": {"state": {"type": "keyword"}}
        }
        d["template javv-images"]["template"]["mappings"]["properties"]["arch"] = {
            "type": "keyword"
        }
        d["index system-views"] = {"mappings": {"properties": {}}}

    assert _breaking_changes(_OLD, _changed(add)) == []


def test_a_change_without_a_bump_is_a_problem() -> None:
    added = _changed(
        lambda d: d["index findings"]["mappings"]["properties"].update(x={"type": "keyword"})
    )
    assert _version_problem((18, _OLD), (18, added)) == (
        "the mappings changed and MAPPING_VERSION is still 18: bump it by 1"
    )
    assert _version_problem((18, _OLD), (19, added)) is None
    assert _version_problem((18, _OLD), (18, copy.deepcopy(_OLD))) is None
    assert _version_problem((18, _OLD), (17, _OLD)) == "MAPPING_VERSION went down from 18 to 17"


def test_the_definitions_drop_only_the_version_marker() -> None:
    defs = CURRENT[1]
    assert set(defs) == {f"index {n}" for n in bootstrap.MUTABLE_INDEXES} | {
        f"template {n}" for n in bootstrap.INDEX_TEMPLATES
    }
    assert "_meta" not in defs["index findings"]["mappings"]
    assert "_meta" in bootstrap.MUTABLE_INDEXES["findings"]["mappings"]  # the source is not changed
