"""Each JAVV image upgrades the OS packages of its base image in its final stage (issue 1172).
The base images are pinned by digest, so without the upgrade a security fix waits until Renovate
moves the digest and the next build. The upgrade must run before USER: the image user can't.
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


def test_every_dockerfile_of_the_repository_is_listed() -> None:
    found = {
        str(p.relative_to(ROOT))
        for pattern in ("*/Dockerfile", "*/Dockerfile.*")
        for p in ROOT.glob(pattern)
    }
    assert found == set(IMAGES)


@pytest.mark.parametrize("path", sorted(IMAGES))
def test_the_final_stage_upgrades_its_os_packages_before_user(path: str) -> None:
    lines = (ROOT / path).read_text().splitlines()
    final = max(i for i, line in enumerate(lines) if line.startswith("FROM "))
    stage = lines[final:]
    assert IMAGES[path] in stage, f"{path}: the final stage has no `{IMAGES[path]}`"
    user = [i for i, line in enumerate(stage) if re.match(r"USER\b", line)]
    assert user, f"{path}: the final stage sets no USER"
    assert stage.index(IMAGES[path]) < user[0], f"{path}: the upgrade runs after USER"
