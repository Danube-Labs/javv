"""A numbered step of a docs page must not join the bullet list above it on the docs site.

The site's Markdown ends a nested bullet list only at a blank line when the step that holds it
also has a paragraph after a blank line. Without the blank line, the next step and the steps after
it render as bullets of that list, with no numbers. GitHub renders the same source correctly, and
the strict build passes, so this test reads the source of each page in the site navigation."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
STEP = re.compile(r"^\d+\. ")
NESTED_ITEM = re.compile(r"^\s{4,}[-*] ")


def _nav_files(nav: list[Any]) -> list[str]:
    files: list[str] = []
    for entry in nav:
        value = next(iter(entry.values())) if isinstance(entry, dict) else entry
        files.extend(_nav_files(value) if isinstance(value, list) else [value])
    return files


PAGES = _nav_files(yaml.safe_load((ROOT / "docs-site" / "mkdocs.yml").read_text())["nav"])


def steps_joined_to_a_list(text: str) -> list[str]:
    """The steps that follow, with no blank line, a step with a blank line and a nested list."""
    found: list[str] = []
    in_fence = False
    has_blank = has_nested = False
    previous = ""
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if STEP.match(line) and not in_fence:
            if has_blank and has_nested and previous.strip():
                found.append(line)
            has_blank = has_nested = False
        elif not in_fence and line and not line[0].isspace():
            has_blank = has_nested = False
        elif not line.strip():
            has_blank = True
        elif NESTED_ITEM.match(line) and not in_fence:
            has_nested = True
        previous = line
    return found


def test_the_rule_finds_the_step_that_the_site_renders_as_a_bullet() -> None:
    page = "1. One.\n\n    Text.\n\n    - a\n    - b\n2. Two.\n"
    assert steps_joined_to_a_list(page) == ["2. Two."]
    assert steps_joined_to_a_list(page.replace("- b\n2.", "- b\n\n2.")) == []
    assert steps_joined_to_a_list("1. One:\n    - a\n    - b\n2. Two.\n") == []


@pytest.mark.parametrize("page", PAGES)
def test_no_step_joins_the_list_above_it(page: str) -> None:
    assert steps_joined_to_a_list((ROOT / page).read_text()) == []
