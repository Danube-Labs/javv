"""`development/scripts/release-app-images.sh`, the release's app images (issue 833, B4).

A re-run after a failed signature must sign what the first run published: a published tag is
pulled, not built, and not pushed again. The script runs as the release runs it, with a stand-in
`docker` on PATH that keeps a registry in a file: a tag it holds answers `imagetools inspect` with
its digest, a missing one answers "not found", and one listed in BROKEN answers another error.
`git` and `jq` are the real ones. The proof against a real registry is in the PR.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "development" / "scripts" / "release-app-images.sh"
VERSION = json.loads((ROOT / ".release-please-manifest.json").read_text())["."]
REGISTRY = "registry.test/danube-labs"
FIRST = {"backend": "sha256:" + "1" * 64, "frontend": "sha256:" + "2" * 64}

# the registry is a file of "<ref> <digest>" lines; every call is logged as one line
_FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "$*" >> "$DOCKER_LOG"
if [ "$1 $2 $3" = "buildx imagetools inspect" ]; then
  ref=$4
  for broken in $BROKEN; do
    case $ref in *"/javv-$broken:"*) echo "ERROR: $ref: unauthorized" >&2; exit 1 ;; esac
  done
  digest=$(awk -v r="$ref" '$1 == r {print $2}' "$REGISTRY_FILE")
  [ -n "$digest" ] || { echo "ERROR: $ref: not found" >&2; exit 1; }
  if [ "${5:-}" = "--format" ]; then echo "{\"digest\": \"$digest\"}"; else echo "Name: $ref"; fi
  exit 0
fi
case $1 in
  push)  # a new build: a digest no earlier push had; the tag moves to it
    n=$(cat "$REGISTRY_FILE" "$DOCKER_LOG" | wc -l)
    grep -v "^$3 " "$REGISTRY_FILE" > "$REGISTRY_FILE.new" || true
    echo "$3 sha256:$(printf '%064d' "$n" | tr 0 9)" >> "$REGISTRY_FILE.new"
    mv "$REGISTRY_FILE.new" "$REGISTRY_FILE" ;;
  pull | build) ;;
  *) exit 9 ;;
esac
"""


def _ref(app: str) -> str:
    return f"{REGISTRY}/javv-{app}:{VERSION}"


def _run(
    tmp_path: Path, mode: str, *, published: tuple[str, ...] = (), broken: str = ""
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "docker").write_text(_FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    registry = tmp_path / "registry.txt"
    if not registry.exists():
        registry.write_text("".join(f"{_ref(a)} {FIRST[a]}\n" for a in published))
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "REGISTRY": REGISTRY,
        "DOCKER_LOG": str(tmp_path / "docker.log"),
        "REGISTRY_FILE": str(registry),
        "BROKEN": broken,
    }
    return subprocess.run(
        ["bash", str(SCRIPT), mode, str(tmp_path / "state")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _calls(tmp_path: Path, verb: str) -> list[str]:
    log = (tmp_path / "docker.log").read_text().splitlines()
    return [line for line in log if line.split()[0] == verb]


def _digests(run: subprocess.CompletedProcess[str]) -> dict[str, str]:
    return dict(line.split("=", 1) for line in run.stdout.splitlines())


def test_a_first_run_builds_and_pushes_both(tmp_path: Path) -> None:
    assert _run(tmp_path, "prepare").returncode == 0
    run = _run(tmp_path, "push")
    assert run.returncode == 0, run.stderr
    assert [c.split()[-1] for c in _calls(tmp_path, "build")] == [".", "."]
    assert sorted(c.split()[-1] for c in _calls(tmp_path, "push")) == sorted(
        [_ref("backend"), _ref("frontend")]
    )
    digests = _digests(run)
    assert list(digests) == ["backend", "frontend"]
    for app, ref in digests.items():
        assert ref.startswith(f"{REGISTRY}/javv-{app}@sha256:")
        assert ref.split("@")[1] != FIRST[app]


def test_a_rerun_signs_what_is_published_and_builds_nothing(tmp_path: Path) -> None:
    published = ("backend", "frontend")
    assert _run(tmp_path, "prepare", published=published).returncode == 0
    run = _run(tmp_path, "push", published=published)
    assert run.returncode == 0, run.stderr
    assert _calls(tmp_path, "build") == []
    assert _calls(tmp_path, "push") == []
    assert sorted(c.split()[-1] for c in _calls(tmp_path, "pull")) == sorted(
        [_ref("backend"), _ref("frontend")]
    )
    assert _digests(run) == {app: f"{REGISTRY}/javv-{app}@{FIRST[app]}" for app in published}


def test_a_rerun_after_one_push_builds_and_pushes_only_the_other(tmp_path: Path) -> None:
    assert _run(tmp_path, "prepare", published=("backend",)).returncode == 0
    run = _run(tmp_path, "push", published=("backend",))
    assert run.returncode == 0, run.stderr
    assert [c.split()[-1] for c in _calls(tmp_path, "pull")] == [_ref("backend")]
    assert len(_calls(tmp_path, "build")) == 1
    assert [c.split()[-1] for c in _calls(tmp_path, "push")] == [_ref("frontend")]
    digests = _digests(run)
    assert digests["backend"] == f"{REGISTRY}/javv-backend@{FIRST['backend']}"
    assert digests["frontend"].split("@")[1].startswith("sha256:")


@pytest.mark.parametrize("broken", ["backend", "frontend"])
def test_a_registry_answer_that_is_not_not_found_stops_it(tmp_path: Path, broken: str) -> None:
    run = _run(tmp_path, "prepare", broken=broken)
    assert run.returncode == 1
    assert f"cannot tell whether {_ref(broken)} is published" in run.stderr
    assert _calls(tmp_path, "build") == []  # nothing built that could be pushed over it


def test_push_without_a_prepare_stops_it(tmp_path: Path) -> None:
    run = _run(tmp_path, "push")
    assert run.returncode == 1
    assert "no prepare state for backend" in run.stderr
    assert run.stdout == ""
