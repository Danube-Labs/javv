"""Each name that the frontend server or the scanner reads has a row in `docs/CONFIGURATION.md`
(issue 1023). `development/scripts/check-docs-drift.sh` checks the backend's settings against the
page, and the page against the code; it does not start from the names these two read, so a new one
could ship with no row. The row must be in the section of its component. No store needed."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "CONFIGURATION.md"
FRONTEND_SERVER = ROOT / "frontend" / "server"
SCANNER = ROOT / "scanner" / "src" / "scanner"


def _section(heading: str) -> str:
    """The text under `heading`, up to the next heading of the same level or higher."""
    level = heading.split(" ", 1)[0]
    lines = PAGE.read_text().splitlines()
    start = lines.index(heading)
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if re.match(r"#+ ", lines[i]) and len(lines[i].split(" ", 1)[0]) <= len(level)
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _rows(*headings: str) -> set[str]:
    return {
        name
        for heading in headings
        for name in re.findall(r"^\| `(JAVV_[A-Z0-9_]+)` \|", _section(heading), re.M)
    }


def _read_by_the_frontend_server() -> set[str]:
    return {
        name
        for path in FRONTEND_SERVER.glob("*.mjs")
        for name in re.findall(r"process\.env\.(JAVV_[A-Z0-9_]+)", path.read_text())
    }


def _read_by_the_scanner() -> set[str]:
    # the rule of scanner/tests/test_helm_config.py: a name the code reads is a quoted literal
    return {
        name
        for path in SCANNER.rglob("*.py")
        for name in re.findall(r'"(JAVV_[A-Z_]+)"', path.read_text())
    }


def test_every_name_the_frontend_server_reads_has_a_row() -> None:
    names = _read_by_the_frontend_server()
    assert names, f"found no process.env.JAVV_ name in {FRONTEND_SERVER.relative_to(ROOT)}"
    missing = sorted(names - _rows("### Frontend server settings"))
    assert not missing, f"no row in 'Frontend server settings' of {PAGE.name}: {missing}"


def test_every_name_the_scanner_reads_has_a_row() -> None:
    names = _read_by_the_scanner()
    assert names, f"found no JAVV_ name in {SCANNER.relative_to(ROOT)}"
    rows = _rows("## Scanner settings", "## Trivy settings", "## Grype settings")
    missing = sorted(names - rows)
    assert not missing, f"no row in the scanner sections of {PAGE.name}: {missing}"
