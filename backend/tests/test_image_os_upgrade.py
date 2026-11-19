"""Each JAVV image upgrades the OS packages of its base image in its final stage (issue 1172).
The base images are pinned by digest, so without the upgrade a security fix waits until Renovate
moves the digest and the next build. The upgrade must run before USER: the image user can't.

The final stage also removes the package managers that the base image brings and the app never
runs (issue 1263): pip in the Python images, and npm, npx, corepack and yarn in the Node image.
Their packages were findings in every scan of JAVV's own images. The removal also needs root, so
it runs before USER.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

DEBIAN = "RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*"
ALPINE = "RUN apk upgrade --no-cache"
IMAGES = {
    "backend/Dockerfile": DEBIAN,
    "frontend/Dockerfile": ALPINE,
    "scanner/Dockerfile.trivy": DEBIAN,
    "scanner/Dockerfile.grype": DEBIAN,
}

NO_PIP = "RUN python -m pip uninstall --yes --no-cache-dir pip"
NO_NPM = (
    "RUN rm -rf /usr/local/lib/node_modules /opt/yarn-v* /usr/local/bin/npm /usr/local/bin/npx"
    " /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg"
)
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
