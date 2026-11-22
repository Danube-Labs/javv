"""Each JAVV image upgrades the OS packages of its base image in its final stage (issue 1172).
The base images are pinned by digest, so without the upgrade a security fix waits until Renovate
moves the digest and the next build. The upgrade must run before USER: the image user can't.

The final stage also removes the package managers that the base image brings and the app never
runs (issue 1263): pip in the Python images, and npm and npx in the Node image. The Node 26 base
has no corepack or yarn (issue 1283).
Their packages were findings in every scan of JAVV's own images. The removal also needs root, so
it runs before USER.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ALPINE = "RUN apk upgrade --no-cache"
IMAGES = {
    "backend/Dockerfile": ALPINE,
    "frontend/Dockerfile": ALPINE,
    "scanner/Dockerfile.trivy": ALPINE,
    "scanner/Dockerfile.grype": ALPINE,
}

NO_PIP = (
    "RUN rm -rf /usr/local/lib/python3*/site-packages/pip"
    " /usr/local/lib/python3*/site-packages/pip-*.dist-info /usr/local/bin/pip*"
)
NO_NPM = "RUN rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx"
REMOVALS = {
    "backend/Dockerfile": NO_PIP,
    "frontend/Dockerfile": NO_NPM,
    "scanner/Dockerfile.trivy": NO_PIP,
    "scanner/Dockerfile.grype": NO_PIP,
}


def test_every_dockerfile_of_the_repository_is_listed() -> None:
    found = {
        str(p.relative_to(ROOT))
        for pattern in ("*/Dockerfile", "*/Dockerfile.*")
        for p in ROOT.glob(pattern)
    }
    assert found == set(IMAGES)


def final_stage(path: str) -> list[str]:
    """The instructions of the last stage, with each continued line joined to its instruction."""
    lines: list[str] = []
    for raw in (ROOT / path).read_text().splitlines():
        if lines and lines[-1].endswith("\\"):
            lines[-1] = lines[-1][:-1].rstrip() + " " + raw.strip()
        else:
            lines.append(raw)
    final = max(i for i, line in enumerate(lines) if line.startswith("FROM "))
    return lines[final:]


@pytest.mark.parametrize("path", sorted(IMAGES))
def test_the_final_stage_upgrades_its_os_packages_before_user(path: str) -> None:
    stage = final_stage(path)
    assert IMAGES[path] in stage, f"{path}: the final stage has no `{IMAGES[path]}`"
    user = [i for i, line in enumerate(stage) if re.match(r"USER\b", line)]
    assert user, f"{path}: the final stage sets no USER"
    assert stage.index(IMAGES[path]) < user[0], f"{path}: the upgrade runs after USER"


def test_every_image_removes_a_package_manager() -> None:
    assert set(REMOVALS) == set(IMAGES)


@pytest.mark.parametrize("path", sorted(REMOVALS))
def test_the_final_stage_removes_the_package_manager_of_its_base_before_user(path: str) -> None:
    stage = final_stage(path)
    assert REMOVALS[path] in stage, f"{path}: the final stage has no `{REMOVALS[path]}`"
    user = [i for i, line in enumerate(stage) if re.match(r"USER\b", line)]
    assert user, f"{path}: the final stage sets no USER"
    assert stage.index(REMOVALS[path]) < user[0], f"{path}: the removal runs after USER"


PYTHON_IMAGES = ("backend/Dockerfile", "scanner/Dockerfile.trivy", "scanner/Dockerfile.grype")


@pytest.mark.parametrize("path", PYTHON_IMAGES)
def test_every_python_stage_uses_the_one_alpine_base(path: str) -> None:
    """The Python images are on Alpine (issue 1263): its musl wheels in the venv of a build stage
    only run on a final stage with the same base, so every stage names the same image."""
    bases = {
        line.split()[1]
        for line in (ROOT / path).read_text().splitlines()
        if line.startswith("FROM python:")
    }
    assert len(bases) == 1, f"{path}: the stages use other bases {sorted(bases)}"
    assert re.match(r"python:[0-9.]+-alpine@sha256:[0-9a-f]{64}$", bases.pop())
