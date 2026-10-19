"""development/scripts/publish-docs-version.sh publishes the docs of one release into a folder of
its own on the docs site (issue 925). It reads the release tags to choose the aliases: the newest
release of a minor also gets the minor (`0.8`), and the newest release of all also gets `latest`.
The run that gives a minor its alias first removes the folder that the old layout kept for that
minor.

These tests run the script's dry run in a scratch repository with release tags and a `gh-pages`
branch on a scratch remote. The dry run prints the plan and builds nothing, so mike is not needed.
"""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "development" / "scripts" / "publish-docs-version.sh"

TAGS = ("v0.7.0", "v0.7.1", "v0.7.2", "v0.8.0", "v0.8.1", "v0.8.2", "v0.8.3", "v0.8.4")
# the site before issue 925: one folder per minor, titled with its newest patch
OLD_SITE = [
    {"version": "dev", "title": "dev", "aliases": []},
    {"version": "0.8", "title": "0.8.4", "aliases": ["latest"]},
    {"version": "0.7", "title": "0.7.2", "aliases": []},
]
# the site after issue 925: one folder per release, the minor and latest are aliases
NEW_SITE = [
    {"version": "dev", "title": "dev", "aliases": []},
    {"version": "0.8.4", "title": "0.8.4", "aliases": ["0.8", "latest"]},
    {"version": "0.8.3", "title": "0.8.3", "aliases": []},
    {"version": "0.7.2", "title": "0.7.2", "aliases": ["0.7"]},
]


def _git(cwd: Path, *args: str) -> str:
    git = ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    return subprocess.run([*git, *args], capture_output=True, text=True, check=True).stdout


def _repo(tmp_path: Path, tags: tuple[str, ...], site: list[dict[str, object]] | None) -> Path:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    if site is not None:
        pages = tmp_path / "pages"
        _git(tmp_path, "init", "-q", "-b", "gh-pages", str(pages))
        (pages / "versions.json").write_text(json.dumps(site))
        _git(pages, "add", "versions.json")
        _git(pages, "commit", "-q", "-m", "site")
        _git(pages, "push", "-q", str(remote), "gh-pages")
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    for tag in tags:
        _git(repo, "commit", "-q", "--allow-empty", "-m", tag)
        _git(repo, "tag", tag)
    _git(repo, "remote", "add", "origin", str(remote))
    return repo


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def _plan(out: str) -> dict[str, str]:
    return dict(line.split(": ", 1) for line in out.splitlines() if ": " in line)


@pytest.mark.parametrize(
    ("version", "aliases", "removes"),
    [
        # an older patch keeps its own folder and takes no alias; the old 0.8 folder stays
        ("0.8.3", "none", None),
        ("0.8.0", "none", None),
        ("0.7.0", "none", None),
        # the newest of an older minor takes the minor and replaces the old folder of that minor
        ("0.7.2", "0.7", "0.7"),
        # the newest of all takes its minor and latest
        ("0.8.4", "0.8 latest", "0.8"),
    ],
)
def test_the_tags_choose_the_aliases_on_the_old_site(
    tmp_path: Path, version: str, aliases: str, removes: str | None
) -> None:
    repo = _repo(tmp_path, TAGS, OLD_SITE)
    result = _run(repo, version, "--dry-run")
    assert result.returncode == 0, result.stderr
    plan = _plan(result.stdout)
    assert plan["release"] == f"{version} (tag v{version})"
    assert plan["aliases"] == aliases
    assert plan.get("remove old folder") == removes
    assert plan.get("default") == ("latest" if "latest" in aliases else None)
    assert "Dry run. Nothing changed." in result.stdout


def test_the_next_release_moves_the_aliases_and_removes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path, (*TAGS, "v0.8.5"), NEW_SITE)
    plan = _plan(_run(repo, "0.8.5", "--dry-run").stdout)
    assert plan["aliases"] == "0.8 latest"
    assert "remove old folder" not in plan
    # 0.8.4 is not the newest any more: a rerun of its docs takes no alias
    assert _plan(_run(repo, "0.8.4", "--dry-run").stdout)["aliases"] == "none"


def test_a_new_minor_leaves_the_older_minor_its_alias(tmp_path: Path) -> None:
    repo = _repo(tmp_path, (*TAGS, "v0.9.0"), NEW_SITE)
    assert _plan(_run(repo, "0.9.0", "--dry-run").stdout)["aliases"] == "0.9 latest"
    assert _plan(_run(repo, "0.8.4", "--dry-run").stdout)["aliases"] == "0.8"


def test_versions_sort_by_number_not_by_text(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ("v0.8.9", "v0.8.10"), NEW_SITE)
    assert _plan(_run(repo, "0.8.10", "--dry-run").stdout)["aliases"] == "0.8 latest"
    assert _plan(_run(repo, "0.8.9", "--dry-run").stdout)["aliases"] == "none"


def test_a_tag_that_is_not_a_release_is_not_the_newest(tmp_path: Path) -> None:
    repo = _repo(tmp_path, (*TAGS, "v0.9.0-rc.1", "v1"), NEW_SITE)
    assert _plan(_run(repo, "0.8.4", "--dry-run").stdout)["aliases"] == "0.8 latest"


def test_the_first_publish_has_no_site_to_change(tmp_path: Path) -> None:
    repo = _repo(tmp_path, TAGS, None)
    result = _run(repo, "0.8.4", "--dry-run")
    assert result.returncode == 0, result.stderr
    plan = _plan(result.stdout)
    assert plan["aliases"] == "0.8 latest"
    assert "remove old folder" not in plan


def test_the_dry_run_changes_no_branch(tmp_path: Path) -> None:
    repo = _repo(tmp_path, TAGS, OLD_SITE)
    remote = tmp_path / "remote.git"
    before = _git(remote, "rev-parse", "gh-pages")
    assert _run(repo, "0.8.4", "--dry-run").returncode == 0
    assert _git(remote, "rev-parse", "gh-pages") == before
    assert _git(repo, "rev-parse", "gh-pages") == before


@pytest.mark.parametrize(
    "args",
    [(), ("0.8",), ("v0.8.4",), ("0.8.4", "--dryrun"), ("0.8.4", "--dry-run", "x")],
)
def test_a_bad_argument_stops_it(tmp_path: Path, args: tuple[str, ...]) -> None:
    result = _run(_repo(tmp_path, TAGS, OLD_SITE), *args)
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_a_version_with_no_tag_stops_it(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, TAGS, OLD_SITE), "0.8.9", "--dry-run")
    assert result.returncode == 2
    assert "no tag v0.8.9" in result.stderr


def test_it_stops_outside_a_git_repository(tmp_path: Path) -> None:
    result = _run(tmp_path, "0.8.4", "--dry-run")
    assert result.returncode == 2
    assert "git repository" in result.stderr
