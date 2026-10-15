"""The operator docs site (issue 639), read from `docs-site/` and its two workflows.

`docs-site/src/` holds a symlink to each published file, laid out as in the repository; that tree
is the list of what is published. Zensical's strict build checks links between pages, but not
links to other files, nor that the tree publishes only operator files. These tests hold the rest:
- src/ is exactly the operator files, each a symlink to the same path in the repository, plus
  the site's own stylesheet, which the config loads;
- every published page is in the nav and every nav entry is published;
- every relative link in a published page reaches a published file;
- the supported-versions page includes README's table, which check-versions.sh keeps in step;
- CI builds the site strict and checks the theme's files were written, blocks render and no list
  rendered as a paragraph;
- a release publishes its docs as its `major.minor` version and as `latest`;
- no published page carries an em dash;
- the pages carry no engineering references (milestones, decisions, audit ids, issue
  numbers), except links to issues that track a limit an operator meets today;
- every `page.md#heading` link reaches a heading on that page;
- the publish workflow runs for every published file.
"""

import fnmatch
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "docs-site"
SRC = SITE / "src"
CONFIG: dict[str, Any] = yaml.safe_load((SITE / "mkdocs.yml").read_text())

# What the site is for (issue 639, "Scope"): the operator pages, rendered where they live.
PAGES = {
    "docs/index.md",
    "docs/supported-versions.md",
    "docs/DEPLOYING.md",
    "docs/CONFIGURATION.md",
    "docs/UPGRADING.md",
    "docs/API.md",
    "docs/INGEST-CONTRACT.md",
    "docs/runbooks/opensearch-sizing.md",
    "docs/runbooks/multi-pod.md",
    "docs/runbooks/indices-and-data.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "deploy/helm/javv/README.md",
    "deploy/helm/javv-opensearch/README.md",
    "deploy/helm/javv-scanner/README.md",
}
# Files the pages link to, published as they are.
FILES = {"docs/ingest-envelope.schema.json", "versions.yaml", "deploy/compose/compose.yaml"}
PUBLISHED = PAGES | FILES
# The site's own files: real files in src/, not copies of anything in the repository.
SITE_FILES = {"stylesheets/javv.css"}

_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _src_entries() -> set[str]:
    """Every file under src/ by its path there, plus any symlinked folder (which would hide its
    contents: Zensical does not follow folder symlinks)."""
    entries: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(SRC):
        folder_links = [d for d in dirnames if (Path(dirpath) / d).is_symlink()]
        for name in filenames + folder_links:
            entries.add((Path(dirpath) / name).relative_to(SRC).as_posix())
    return entries


def _nav_files(nav: list[Any]) -> list[str]:
    files: list[str] = []
    for entry in nav:
        value = next(iter(entry.values())) if isinstance(entry, dict) else entry
        files.extend(_nav_files(value) if isinstance(value, list) else [value])
    return files


def _normalize(path: str) -> str:
    """`docs/../deploy/x.md` -> `deploy/x.md`, without touching the filesystem."""
    parts: list[str] = []
    for part in path.split("/"):
        if part == "..":
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def _workflow(name: str) -> dict[Any, Any]:
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())


def test_src_is_exactly_the_operator_files() -> None:
    assert _src_entries() == PUBLISHED | SITE_FILES


def test_the_sites_own_files_are_real_files_the_config_loads() -> None:
    for name in SITE_FILES:
        assert (SRC / name).is_file() and not (SRC / name).is_symlink()
    assert set(CONFIG["extra_css"]) == {n for n in SITE_FILES if n.endswith(".css")}


@pytest.mark.parametrize("published", sorted(PUBLISHED))
def test_each_entry_links_to_the_same_path_in_the_repository(published: str) -> None:
    entry = SRC / published
    assert entry.is_symlink(), f"{published} in src/ is a copy, not a symlink"
    assert entry.resolve() == (ROOT / published).resolve()
    assert entry.resolve().is_file()


def test_the_nav_is_every_published_page() -> None:
    assert sorted(_nav_files(CONFIG["nav"])) == sorted(PAGES)


@pytest.mark.parametrize("page", sorted(PAGES))
def test_relative_links_reach_published_files(page: str) -> None:
    for target in _LINK.findall((ROOT / page).read_text()):
        if re.match(r"[a-z]+:|#", target):
            continue
        resolved = _normalize(f"{Path(page).parent.as_posix()}/{target.split('#')[0]}")
        assert resolved in PUBLISHED, f"{page} links to {target}, which the site does not publish"


def test_the_versions_page_includes_readmes_marked_table() -> None:
    page = (ROOT / "docs" / "supported-versions.md").read_text()
    assert '--8<-- "README.md:supported-versions"' in page
    start = "<!-- --8<-- [start:supported-versions] -->"
    end = "<!-- --8<-- [end:supported-versions] -->"
    readme = (ROOT / "README.md").read_text()
    section = re.search(rf"{re.escape(start)}\n(.*?){re.escape(end)}", readme, re.S)
    assert section, "README.md has no supported-versions section markers"
    rows = [line.split("|")[1].strip() for line in section.group(1).splitlines()[2:]]
    # the rows check-versions.sh rewrites from versions.yaml
    assert rows == ["Trivy", "Grype", "OpenSearch"]


def test_ci_builds_the_site_strict_with_the_themes_files() -> None:
    steps = _workflow("ci.yml")["jobs"]["docs-site"]["steps"]
    runs = "\n".join(s.get("run", "") for s in steps)
    assert "zensical build -f docs-site/mkdocs.yml --strict" in runs
    # the strict build passes when the theme's stylesheets are missing (pages with no styling), or
    # when fenced code renders as inline code
    assert "docs-site/site/assets/stylesheets/" in runs
    assert "grep -q '<pre' docs-site/site/docs/DEPLOYING/index.html" in runs
    # a mermaid block with no mermaid fence renders as code, and the strict build passes
    assert "grep -q '<pre class=\"mermaid\">' docs-site/site/docs/DEPLOYING/index.html" in runs
    # a list GitHub nests with 3 spaces, or one with no blank line before it, renders as text
    assert "python3 development/scripts/check-docs-site-lists.py docs-site/site" in runs


def test_fenced_code_blocks_are_enabled() -> None:
    # listing markdown_extensions replaces the defaults; without superfences no ``` block renders
    names = {e if isinstance(e, str) else next(iter(e)) for e in CONFIG["markdown_extensions"]}
    assert "pymdownx.superfences" in names


def test_the_site_follows_the_readers_light_or_dark_setting() -> None:
    palette = CONFIG["theme"]["palette"]
    assert {p["media"]: p["scheme"] for p in palette} == {
        "(prefers-color-scheme: light)": "default",
        "(prefers-color-scheme: dark)": "slate",
    }
    assert all("toggle" in p for p in palette)


def _superfences() -> dict[str, Any]:
    for entry in CONFIG["markdown_extensions"]:
        if isinstance(entry, dict) and "pymdownx.superfences" in entry:
            return entry["pymdownx.superfences"]
    return {}


@pytest.mark.parametrize("page", sorted(p for p in PAGES if "```mermaid" in (ROOT / p).read_text()))
def test_mermaid_blocks_render_as_diagrams(page: str) -> None:
    fences = {f["name"]: f for f in _superfences().get("custom_fences", [])}
    assert "mermaid" in fences, f"{page} has a mermaid block, and the site renders it as code"
    assert fences["mermaid"]["class"] == "mermaid"
    assert fences["mermaid"]["format"] == "pymdownx.superfences.fence_code_format"


# Issue 796: the operator pages carry no engineering references. A link to an issue stays only
# where it tracks a limit an operator meets today, and it is listed here. The release notes keep
# their links: each entry is a change and its pull request.
OPEN_LIMIT_ISSUES = {664, 719, 739, 865}
_REFERENCE = re.compile(
    r"\bissues? \d+|#\d{2,4}\b|\bM\d{1,2}[a-f]?\b|\b(?:D|FR-|NFR-|SEC-)\d+\b"
    r"|\b[A-Z]-[0-9A-Za-z]{1,3}\b|\baudit (?:[A-Z]-|#)|\bslice \d|\bbolt\b",
    re.IGNORECASE,
)
_ISSUE_LINK = re.compile(
    r"\[issue (\d+)\]\(https://github\.com/Danube-Labs/javv-poc/issues/(\d+)\)"
)


def _prose(page: str) -> str:
    """The page without its code blocks and inline code: commands and identifiers are not prose."""
    text = re.sub(r"```.*?```", "", (ROOT / page).read_text(), flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


@pytest.mark.parametrize("page", sorted(PAGES - {"CHANGELOG.md"}))
def test_published_pages_carry_no_internal_references(page: str) -> None:
    text = _prose(page)
    for shown, target in _ISSUE_LINK.findall(text):
        assert shown == target and int(target) in OPEN_LIMIT_ISSUES, f"{page}: issue {target}"
    found = _REFERENCE.findall(_ISSUE_LINK.sub("", text))
    assert not found, f"{page} carries {found}"


def _slug(heading: str) -> str:
    """The anchor the site gives a heading (Python-Markdown's toc slug, on the heading's text)."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "").replace("*", "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[-\s]+", "-", re.sub(r"[^\w\s-]", "", text).strip().lower())


def _anchors(page: str) -> set[str]:
    text = re.sub(r"```.*?```", "", (ROOT / page).read_text(), flags=re.S)
    return {_slug(h) for h in re.findall(r"^#{1,6} (.+)$", text, re.M)}


@pytest.mark.parametrize("page", sorted(PAGES))
def test_links_to_a_heading_reach_it(page: str) -> None:
    # the strict build checks that a linked page exists, not that its heading does: a renamed
    # heading breaks every link to it without a word
    for target in _LINK.findall((ROOT / page).read_text()):
        if re.match(r"[a-z]+:", target) or "#" not in target:
            continue
        path, anchor = target.split("#", 1)
        linked = _normalize(f"{Path(page).parent.as_posix()}/{path}") if path else page
        if linked in PAGES:
            assert anchor in _anchors(linked), f"{page} links to {target}: no such heading"


@pytest.mark.parametrize("page", sorted(PAGES))
def test_published_pages_carry_no_em_dash(page: str) -> None:
    lines = (ROOT / page).read_text().splitlines()
    found = [n for n, line in enumerate(lines, 1) if "\u2014" in line]
    assert not found, f"{page} has an em dash on lines {found}"


def test_the_release_publishes_its_docs_as_its_version_and_latest() -> None:
    job = _workflow("release-please.yml")["jobs"]["publish-docs"]
    # only a created release, and only once its charts are out: `latest` names an installable one
    assert job["if"] == "needs.release-please.outputs.release_created == 'true'"
    assert "publish-charts" in job["needs"]
    checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ needs.release-please.outputs.tag_name }}"
    runs = " ".join(" ".join(s.get("run", "").split()) for s in job["steps"]).replace("\\ ", "")
    assert 'minor="${VERSION%.*}"' in runs
    assert (
        "mike deploy --config-file docs-site/mkdocs.yml --push --update-aliases"
        ' --alias-type=redirect --title "$VERSION" "$minor" latest'
    ) in runs
    assert "mike set-default --config-file docs-site/mkdocs.yml --push latest" in runs
    # docs.yml pushes the same branch: one job at a time
    assert job["concurrency"]["group"] == _workflow("docs.yml")["concurrency"]["group"]


def test_the_publish_workflow_runs_for_every_published_file() -> None:
    workflow = _workflow("docs.yml")
    paths: list[str] = workflow[True]["push"]["paths"]  # yaml reads the `on:` key as True
    watched = PUBLISHED | {"README.md", "docs-site/mkdocs.yml", "docs-site/uv.lock"}
    watched |= {f"docs-site/src/{p}" for p in PUBLISHED}
    for f in sorted(watched):
        assert any(fnmatch.fnmatch(f, p) for p in paths), f"docs.yml does not run for {f}"
    runs = "\n".join(s.get("run", "") for s in workflow["jobs"]["dev"]["steps"])
    assert "mike deploy --config-file docs-site/mkdocs.yml --push dev" in runs
