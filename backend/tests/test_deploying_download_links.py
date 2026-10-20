"""The install pages name the JAVV release in their commands. Each block that installs or verifies a
release sets `VERSION=` first, and the compose guide links the three files of that release.
release-please moves each of these lines in the release PR, so each line carries its marker and
each page is in its extra-files. Without that, the docs of a new release would install an old one.
A `<version>` placeholder is not allowed: a command with one fails when the reader pastes it."""

import json
import re
from pathlib import Path

import pytest

from backend.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "DEPLOYING.md"
PAGES = ("docs/DEPLOYING.md",)
LINK = re.compile(
    r"https://raw\.githubusercontent\.com/Danube-Labs/javv-poc/v(?P<version>[^/]+)"
    r"/deploy/compose/(?P<file>[^\")\s]+)"
)
VERSION_LINE = re.compile(r"^\s*VERSION=(?P<version>\S+)\s*$")
FILES = {"compose.yaml", ".env.example", "setup.sh"}


def _versioned_lines(page: Path) -> list[tuple[str, bool]]:
    """Each line with a file link or a `VERSION=` line, and whether release-please updates it."""
    lines: list[tuple[str, bool]] = []
    in_block = False
    for line in page.read_text().splitlines():
        if "x-release-please-start-version" in line:
            in_block = True
        elif "x-release-please-end" in line:
            in_block = False
        elif LINK.search(line) or VERSION_LINE.match(line):
            lines.append((line, in_block or "x-release-please-version" in line))
    return lines


def test_the_guide_links_each_file_of_the_current_release() -> None:
    lines = _versioned_lines(GUIDE)
    linked = {m["file"] for line, _ in lines for m in LINK.finditer(line)}
    assert linked >= FILES
    for line, _ in lines:
        for match in LINK.finditer(line):
            if match["version"] != "$VERSION":
                assert match["version"] == APP_VERSION, line
            if match["file"] != "$f":
                assert (ROOT / "deploy" / "compose" / match["file"]).is_file(), line


@pytest.mark.parametrize("page", PAGES)
def test_each_version_line_names_the_current_release(page: str) -> None:
    lines = [line for line, _ in _versioned_lines(ROOT / page) if VERSION_LINE.match(line)]
    assert lines, f"{page} sets no VERSION"
    for line in lines:
        match = VERSION_LINE.match(line)
        assert match and match["version"] == APP_VERSION, line


@pytest.mark.parametrize("page", PAGES)
def test_no_command_has_a_version_placeholder(page: str) -> None:
    assert "<version>" not in (ROOT / page).read_text()


@pytest.mark.parametrize("page", PAGES)
def test_release_please_moves_each_version(page: str) -> None:
    assert all(updated for _, updated in _versioned_lines(ROOT / page))
    config = json.loads((ROOT / "release-please-config.json").read_text())
    paths = {entry["path"] for entry in config["packages"]["."]["extra-files"]}
    assert page in paths
