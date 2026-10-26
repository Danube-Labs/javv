"""The memory bank (`development/memory-bank/`, issue 1012) is a summary of the project that a
reader trusts without opening the code. A path that no longer exists makes it lie, so each path it
names must exist. Pure file checks, no store."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
BANK = ROOT / "development" / "memory-bank"
BANK_FILES = sorted(BANK.glob("*.md"))

_LINK = re.compile(r"\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`\s]+)`")
_TOP_LEVEL = {p.name for p in ROOT.iterdir()}
_DECISION = re.compile(r"\bD\d+[a-c]?\b")


def _code_paths(text: str) -> list[str]:
    """Code spans that name a repository path: they start with a top-level entry of the repo."""
    found = []
    for token in _CODE.findall(text):
        if token.split("/")[0] in _TOP_LEVEL:
            found.append(token)
    return found


def test_the_bank_has_its_files():
    names = {p.name for p in BANK_FILES}
    readme = (BANK / "README.md").read_text()
    listed = set(re.findall(r"\(([\w-]+\.md)\)", readme))
    assert listed, "README.md lists no bank files"
    assert listed <= names, f"README.md lists files the bank does not have: {listed - names}"
    assert names - {"README.md"} <= listed, f"bank files README.md does not list: {names - listed}"


@pytest.mark.parametrize("page", BANK_FILES, ids=lambda p: p.name)
def test_each_path_in_the_bank_exists(page: Path):
    text = page.read_text()
    missing = []
    for target in _LINK.findall(text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (page.parent / target.split("#")[0]).exists():
            missing.append(target)
    for token in _code_paths(text):
        if not (ROOT / token.rstrip("/")).exists():
            missing.append(token)
    assert not missing, f"{page.name} names paths that do not exist: {missing}"


def test_each_release_has_a_line_in_the_timeline():
    released = re.findall(r"^##? \[?(\d+\.\d+\.\d+)", (ROOT / "CHANGELOG.md").read_text(), re.M)
    rows = set(re.findall(r"^\| (\d+\.\d+\.\d+) \|", (BANK / "timeline.md").read_text(), re.M))
    assert released, "no release found in CHANGELOG.md"
    missing = [v for v in released if v not in rows]
    assert not missing, f"releases with no row in timeline.md: {missing}"


def test_each_decision_number_exists_in_the_plan():
    plan = set(_DECISION.findall((ROOT / "docs" / "engineering" / "PLAN.md").read_text()))
    named = {d for page in BANK_FILES for d in _DECISION.findall(page.read_text())}
    assert named, "the bank names no decision"
    assert named <= plan, f"decision numbers that PLAN.md does not have: {sorted(named - plan)}"


def test_active_context_says_its_date():
    text = (BANK / "active-context.md").read_text()
    assert re.search(r"^As of: \d{4}-\d\d-\d\d$", text, re.M), (
        "active-context.md has no 'As of' date"
    )
