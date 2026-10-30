"""Fail when a release PR body has no "What's new" section, or the section fails the STE linter.

The section sits between `<!-- whats-new -->` and `<!-- /whats-new -->` in the body of the release
PR, above the list that release-please writes. release-please makes the release page from that
body, so the section is the top of the release notes (issue 1061). The check lints only the
section: the list below it is release-please's, made from commit subjects. Run with the body in a
file:
    python3 development/scripts/check-release-notes.py body.md
"""

import importlib.util
import re
import sys
from pathlib import Path

SECTION = re.compile(r"<!-- whats-new -->\n(.*?)<!-- /whats-new -->", re.DOTALL)

_spec = importlib.util.spec_from_file_location(
    "ste_lint", Path(__file__).with_name("ste-lint.py")
)
assert _spec and _spec.loader
ste_lint = importlib.util.module_from_spec(_spec)
# no __pycache__ next to the script: the docs-drift check lists every file in that folder
sys.dont_write_bytecode = True
_spec.loader.exec_module(ste_lint)


def section(body: str) -> str | None:
    found = SECTION.search(body.replace("\r\n", "\n"))
    return found.group(1) if found else None


def main(path: str) -> int:
    text = section(Path(path).read_text())
    if text is None or not text.strip():
        print(
            "The release PR has no What's new section between <!-- whats-new --> and <!-- /whats-new -->."
        )
        print(
            "Write it with /release-notes before the release (development/standards/releases.md)."
        )
        return 1
    findings, _ = ste_lint.lint(text, filename="What's new")
    hard = [f for f in findings if f["level"] == "advisory-free"]
    for f in findings:
        print(
            f"{f['file']}:{f['line']}:{f['col']} {f['rule']}: {f['message']} [{f['match']}]"
        )
    print(
        f"{len(hard)} STE findings that fail the check, {len(findings) - len(hard)} advisory."
    )
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
