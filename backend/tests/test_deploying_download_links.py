"""The compose install guide links the three files of the release it documents. release-please
moves the tag in each link, so every link line carries its marker and the guide is in its
extra-files. Without that, the guide of a new release would hand out the files of an old one."""

import json
import re
from pathlib import Path

from backend.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "DEPLOYING.md"
LINK = re.compile(
    r"https://raw\.githubusercontent\.com/Danube-Labs/javv-poc/v(?P<version>[^/]+)"
    r"/deploy/compose/(?P<file>[^\")\s]+)"
)
FILES = {"compose.yaml", ".env.example", "setup.sh"}


def _link_lines() -> list[tuple[str, bool]]:
    """Each line with a file link, and whether release-please updates that line."""
    lines: list[tuple[str, bool]] = []
    in_block = False
    for line in GUIDE.read_text().splitlines():
        if "x-release-please-start-version" in line:
            in_block = True
        elif "x-release-please-end" in line:
            in_block = False
        elif LINK.search(line):
            lines.append((line, in_block or "x-release-please-version" in line))
    return lines


def test_the_guide_links_each_file_of_the_current_release() -> None:
    lines = _link_lines()
    linked = {m["file"] for line, _ in lines for m in LINK.finditer(line)}
    assert linked >= FILES
    for line, _ in lines:
        for match in LINK.finditer(line):
            assert match["version"] == APP_VERSION, line
            if match["file"] != "$f":
                assert (ROOT / "deploy" / "compose" / match["file"]).is_file(), line


def test_release_please_moves_the_tag_in_each_link() -> None:
    assert all(updated for _, updated in _link_lines())
    config = json.loads((ROOT / "release-please-config.json").read_text())
    paths = {entry["path"] for entry in config["packages"]["."]["extra-files"]}
    assert "docs/DEPLOYING.md" in paths
