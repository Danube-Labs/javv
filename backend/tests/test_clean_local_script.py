"""development/scripts/clean-local.sh deletes local clutter (issue 660): test and build output,
end-to-end logs, dead-letter files and tool caches. It deletes a path only when git ignores it and
the path is in one of those categories. It never deletes `tmp/` (screenshots, trailer and demo
work; operator rulings 2026-10-03 and 2026-10-16) or the other ignored files a developer keeps.

The script runs here in a scratch git repository that has this repository's `.gitignore` files, so
a change to the ignore rules shows here too."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "development" / "scripts" / "clean-local.sh"

# what one --apply run must delete, as the script lists it (git shows an ignored folder once)
DELETED = {
    "frontend/coverage/",
    "frontend/dist/",
    "frontend/test-results/",
    "docs-site/site/",
    "docs-site/.cache/",
    "backend/.coverage",
    "development/e2e/logs/",
    "scanner/trivy.dead-letter.jsonl",
    "backend/src/backend/__pycache__/",
    "backend/.pytest_cache/",
    ".ruff_cache/",
    "frontend/.eslintcache",
}
FILES_DELETED = (
    "frontend/coverage/index.html",
    "frontend/dist/assets/app.js",
    "frontend/test-results/run/trace.zip",
    "docs-site/site/index.html",
    "docs-site/.cache/x.json",
    "backend/.coverage",
    "development/e2e/logs/smoke.log",
    "scanner/trivy.dead-letter.jsonl",
    "backend/src/backend/__pycache__/main.cpython-312.pyc",
    "backend/.pytest_cache/v/cache/lastfailed",
    ".ruff_cache/0.17.1/x",
    "frontend/.eslintcache",
)
# ignored too, but never in a category: these must stay
FILES_KEPT = (
    "tmp/screenshots/881/ab-881.png",
    "tmp/trailer/cut.webp",
    "tmp/demo/demo.webm",
    "tmp/__pycache__/x.cpython-312.pyc",
    "tmp/old.dead-letter.jsonl",
    ".claude/sessions/2026-10-16-handoff.md",
    ".claude/settings.local.json",
    ".codex/config.toml",
    ".serena/cache/x",
    ".impeccable/critique/x.md",
    "AGENTS.md",
    "backend/cookies.txt",
    "frontend/node_modules/pkg/__pycache__/x.pyc",
    "backend/.venv/lib/__pycache__/x.pyc",
)
# git tracks these, so they stay although their names are in a category
FILES_TRACKED = (
    "README.md",
    "frontend/src/main.ts",
    "scanner/tests/fixtures/sample.dead-letter.jsonl",
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    tracked = subprocess.run(
        ["git", "ls-files", "*.gitignore"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    for name in tracked:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, tmp_path / name)
    for name in FILES_DELETED + FILES_KEPT + FILES_TRACKED:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(name)
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-f", *tracked, *FILES_TRACKED], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "t"], check=True)
    return tmp_path


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def _listed(out: str, prefix: str) -> set[str]:
    return {line.split("\t")[-1] for line in out.splitlines() if line.startswith(prefix)}


def test_the_dry_run_lists_the_four_categories_and_deletes_nothing(repo: Path) -> None:
    result = _run(repo)
    assert result.returncode == 0, result.stderr
    assert _listed(result.stdout, "  ") == DELETED
    assert "Nothing deleted" in result.stdout
    assert all((repo / name).exists() for name in FILES_DELETED + FILES_KEPT + FILES_TRACKED)


def test_apply_deletes_the_listed_paths_and_nothing_else(repo: Path) -> None:
    result = _run(repo, "--apply")
    assert result.returncode == 0, result.stderr
    assert _listed(result.stdout, "deleted\t") == DELETED
    assert [name for name in FILES_DELETED if (repo / name).exists()] == []
    assert [name for name in FILES_KEPT + FILES_TRACKED if not (repo / name).exists()] == []
    again = _run(repo)
    assert _listed(again.stdout, "  ") == set() and "Nothing to delete" in again.stdout


def test_tmp_stays_when_the_ignore_rules_no_longer_fold_it(repo: Path) -> None:
    # without the `tmp/` rule, git lists the dead-letter file and the cache in tmp/ one by one
    ignore = repo / ".gitignore"
    rules = ignore.read_text().splitlines()
    assert "tmp/" in rules
    ignore.write_text("\n".join(line for line in rules if line != "tmp/") + "\n")
    result = _run(repo, "--apply")
    assert result.returncode == 0, result.stderr
    assert _listed(result.stdout, "deleted\t") == DELETED
    assert [name for name in FILES_KEPT if not (repo / name).exists()] == []


def test_it_works_from_a_folder_inside_the_repository(repo: Path) -> None:
    result = _run(repo / "frontend" / "src")
    assert result.returncode == 0, result.stderr
    assert _listed(result.stdout, "  ") == DELETED


def test_an_unknown_argument_stops_it_before_it_deletes(repo: Path) -> None:
    result = _run(repo, "--aply")
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert all((repo / name).exists() for name in FILES_DELETED)


def test_it_stops_outside_a_git_repository(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "git repository" in result.stderr
