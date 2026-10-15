"""Git refs that the upgrade checks compare against (issue 261): the newest release tag and the
merge base with main. CI checks these out with `fetch-depth: 0`
(`test_mapping_additive.py::test_every_job_that_runs_the_backend_tests_checks_out_the_history`);
a missing ref fails the check, it never skips it."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def newest_release_tag() -> str:
    """The newest `v*` tag that HEAD contains: the release this tree upgrades from."""
    tags = git("tag", "--merged", "HEAD", "--list", "v*", "--sort=-v:refname").split()
    assert tags, "no v* tag reachable from HEAD: check out the history with fetch-depth 0"
    return tags[0]


def merge_base_with_main() -> str:
    try:
        return git("merge-base", "HEAD", "origin/main")
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"no merge base with origin/main ({exc.stderr.strip()}): "
            "check out the history with fetch-depth 0"
        ) from exc


def show(ref: str, path: str) -> str:
    """The file at `path` (from the repository root) as it is at `ref`."""
    return git("show", f"{ref}:{path}")
