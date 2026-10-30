"""The release notes (issue 1061): the What's new section of the release PR, and its STE check.

release-please makes the release page from the body of the release PR. `/release-notes` writes a
What's new section between two markers in that body, and the `Release notes` workflow lints the
section with the STE linter in `development/scripts/`. These tests hold:
- the linter in the repository passes its own self-test;
- the check finds the section between the markers, lints only the section, and fails on a
  finding or when the section is not there;
- the workflow runs the check on each open, edit and reopen of a release PR, with the body passed
  through the environment, never written into the script;
- the release standard names the command, and each path that the command names exists.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "development" / "scripts"
CHECK = SCRIPTS / "check-release-notes.py"
COMMAND = ROOT / ".claude" / "commands" / "release-notes.md"
WORKFLOW = ROOT / ".github" / "workflows" / "release-notes.yml"

GOOD = (
    "### What's new\n\n"
    "- **Windows have one look.** Each window has the dark blue head of the tables.\n"
)
LIST = (
    "### Bug Fixes\n\n* a release-please line that is made from a commit subject, with no"
    " limit on its length or its words; it is not part of the section ([#1](https://x.test))\n"
)


def _body(section: str | None) -> str:
    head = "## [9.9.9](https://example.test) (2026-10-30)\n\n"
    wrapped = f"<!-- whats-new -->\n{section}<!-- /whats-new -->\n\n" if section is not None else ""
    top = ":robot: I have created a release *beep* *boop*\n---\n\n\n"
    return f"{top}{head}{wrapped}{LIST}\n---\nfooter\n"


def _check(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "body.md"
    path.write_text(body)
    return subprocess.run(
        [sys.executable, "-B", str(CHECK), str(path)], capture_output=True, text=True
    )


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("check_release_notes", CHECK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # no __pycache__ next to the script: the docs-drift check lists every file in that folder
    write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    spec.loader.exec_module(module)
    sys.dont_write_bytecode = write_bytecode
    return module


def test_the_linter_passes_its_self_test() -> None:
    run = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "ste-lint.py"), "--selftest"],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_a_section_in_ste_passes(tmp_path: Path) -> None:
    run = _check(tmp_path, _body(GOOD))
    assert run.returncode == 0, run.stdout


def test_only_the_section_is_linted() -> None:
    # the release-please list below the section has a semicolon and a long line: not the check's
    assert _module().section(_body(GOOD)) == GOOD


def test_a_body_edited_in_the_browser_has_crlf_line_ends(tmp_path: Path) -> None:
    run = _check(tmp_path, _body(GOOD).replace("\n", "\r\n"))
    assert run.returncode == 0, run.stdout


@pytest.mark.parametrize(
    ("line", "rule"),
    [
        ("Each window has the dark blue head; it is new.", "semicolon"),
        (" ".join(["word"] * 26) + ".", "long-sentence"),
        ("The windows look seamless.", "marketing-adjective"),
    ],
)
def test_a_finding_in_the_section_fails(tmp_path: Path, line: str, rule: str) -> None:
    run = _check(tmp_path, _body(f"{GOOD}- {line}\n"))
    assert run.returncode == 1
    assert rule in run.stdout


@pytest.mark.parametrize("section", [None, "\n  \n"], ids=["no markers", "empty"])
def test_a_body_without_the_section_fails(tmp_path: Path, section: str | None) -> None:
    run = _check(tmp_path, _body(section))
    assert run.returncode == 1
    assert "no What's new section" in run.stdout


def test_the_workflow_checks_each_edit_of_a_release_pr() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    # PyYAML reads the key `on` as True
    trigger = workflow[True]["pull_request"]
    assert {"opened", "edited", "reopened"} <= set(trigger["types"])
    assert trigger["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["whats-new"]
    assert job["if"] == "startsWith(github.head_ref, 'release-please--')"
    step = next(s for s in job["steps"] if "run" in s)
    # the body is text that people write: it reaches the shell as a variable, never as script
    assert step["env"]["BODY"] == "${{ github.event.pull_request.body }}"
    assert "${{" not in step["run"]
    assert "python3 development/scripts/check-release-notes.py" in step["run"]


def test_the_release_standard_names_the_command() -> None:
    text = (ROOT / "development" / "standards" / "releases.md").read_text()
    assert "`/release-notes`" in text
    assert "`.claude/commands/release-notes.md`" in text


def test_the_command_uses_the_markers_and_the_check() -> None:
    text = COMMAND.read_text()
    assert "<!-- whats-new -->" in text and "<!-- /whats-new -->" in text
    assert "python3 development/scripts/check-release-notes.py" in text


def test_each_path_the_command_names_exists() -> None:
    names = re.findall(
        r"`((?:\.claude|\.github|backend|development|docs|frontend)/[^`\s]+)`", COMMAND.read_text()
    )
    assert names
    missing = [name for name in names if not (ROOT / name).exists()]
    assert not missing, missing
