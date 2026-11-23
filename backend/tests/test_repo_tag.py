"""How the ingest splits the `image_ref` of a scan into the image name and the tag (issue 1294).

A reference can carry a tag and a digest: `app:1.4.2@sha256:…`. The scanner sends that form when
`status.image` of a pod is a bare `sha256:…` id (EKS), because it then takes the name from
`imageID`. The Docker script sends it from `Config.Image` when the tag of a container moved to
another image. The digest part names no version, so the tag is the part before it."""

import json
from pathlib import Path

import pytest

from backend.models.envelope import IngestEnvelope
from backend.services.ingest import _repo_tag, build_docs

DIGEST = "sha256:05a79c7279f71f86a2a0d05eb72fcb56ea36139150f0a75cd87e80a4272e4e39"
ECR = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/team/app"


@pytest.mark.parametrize(
    ("image_ref", "expected"),
    [
        # the forms that did not change
        ("nginx:1.27", ("nginx", "1.27")),
        ("registry:5000/app:1.2", ("registry:5000/app", "1.2")),
        ("registry:5000/app", ("registry:5000/app", "")),
        ("nginx", ("nginx", "")),
        (f"app@{DIGEST}", ("app", "")),
        (f"registry:5000/app@{DIGEST}", ("registry:5000/app", "")),
        # a tag and a digest: the tag is the part before the digest
        (f"app:1.4.2@{DIGEST}", ("app", "1.4.2")),
        (f"registry:5000/app:1.2@{DIGEST}", ("registry:5000/app", "1.2")),
        (f"docker.io/library/busybox:1.34@{DIGEST}", ("docker.io/library/busybox", "1.34")),
        # the `imageID` of EKS, which the scanner sends when `status.image` is a bare id
        (f"{ECR}:1.4.2@{DIGEST}", (ECR, "1.4.2")),
    ],
)
def test_repo_tag(image_ref: str, expected: tuple[str, str]) -> None:
    assert _repo_tag(image_ref) == expected


def test_each_doc_of_a_scan_gets_the_name_and_the_tag() -> None:
    golden = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
    env = IngestEnvelope.model_validate({**golden, "image_ref": f"{ECR}:1.4.2@{DIGEST}"})
    docs = build_docs(env)
    rows = [*docs["findings"], docs["scan_event"], docs["image"]]
    assert {(d["image_repo"], d["tag"]) for d in rows} == {(ECR, "1.4.2")}
