"""The contributor and agent guides, and the READMEs of the components, name files of the
repository, and a reader opens them on trust. A path that no longer exists sends the reader
nowhere, so each path that a guide names must exist: each relative link, and each code span that
starts with a top-level folder or file of the repository. The test reads the git tree, not the
disk: a file that a guide names is in the tree, or git ignores it on purpose (a log, a cookie jar or
the test results that a command writes). Pure file checks, no store."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
_TRACKED = set(
    subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
)
_TRACKED_DIRS = {str(Path(f).parent) for f in _TRACKED} | {
    str(parent) for f in _TRACKED for parent in Path(f).parents
}
_TOP_LEVEL = {f.split("/")[0] for f in _TRACKED}
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`\s]+)`")
# a branch name such as docs/1012-memory-bank starts with a top-level folder, but it is no path
_BRANCH = re.compile(r"^(feat|fix|chore|docs|test|refactor)/\d+-")
_PLACEHOLDER = re.compile(r"[*<>{}$…]")

GUIDES = sorted(
    [
        ROOT / "CLAUDE.md",
        ROOT / "REPO-MAP.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / ".github" / "pull_request_template.md",
        ROOT / "development" / "README.md",
        ROOT / "development" / "RUNNING-THE-STACK.md",
        ROOT / "development" / "e2e" / "README.md",
        ROOT / ".claude" / "sessions" / "README.md",
        ROOT / ".claude" / "sessions" / "TEMPLATE.md",
        ROOT / "README.md",
        ROOT / "backend" / "README.md",
        ROOT / "frontend" / "README.md",
        ROOT / "frontend" / "DESIGN.md",
        ROOT / "scanner" / "README.md",
        ROOT / "scanner" / "tests" / "fixtures" / "README.md",
        ROOT / "development" / "video" / "README.md",
        ROOT / "design" / "README.md",
        ROOT / "design" / "brand" / "BRAND.md",
        *(ROOT / ".claude" / "rules").glob("*.md"),
        *(ROOT / ".claude" / "commands").glob("*.md"),
        # the bolt README template links from a bolt folder, and the bolts are history
        *(
            p
            for p in (ROOT / "development" / "standards").glob("*.md")
            if p.name != "bolt-readme-template.md"
        ),
    ]
)


def _in_repo(path: str) -> bool:
    path = os.path.normpath(path)
    if path in _TRACKED or path in _TRACKED_DIRS:
        return True
    ignored = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    return ignored.returncode == 0


def _missing(page: Path) -> list[str]:
    text = page.read_text()
    missing = []
    for target in _LINK.findall(text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        linked = os.path.relpath(page.parent / target.split("#")[0], ROOT)
        if not _in_repo(linked):
            missing.append(target)
    for token in _CODE.findall(text):
        if "/" not in token or token.split("/")[0] not in _TOP_LEVEL:
            continue
        if _BRANCH.match(token) or _PLACEHOLDER.search(token):
            continue
        if not _in_repo(token.split("::")[0].split(":")[0].rstrip("/")):
            missing.append(token)
    return missing


def test_the_guides_are_there() -> None:
    assert all(p.exists() for p in GUIDES)
    assert len(GUIDES) > 20, [p.relative_to(ROOT) for p in GUIDES]


@pytest.mark.parametrize("page", GUIDES, ids=lambda p: str(p.relative_to(ROOT)))
def test_each_path_in_a_guide_exists(page: Path) -> None:
    missing = _missing(page)
    assert not missing, f"{page.relative_to(ROOT)} names paths that do not exist: {missing}"
