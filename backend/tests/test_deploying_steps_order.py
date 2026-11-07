"""The install steps of docs/DEPLOYING.md run in a safe sequence (issues 1125 and 1126): a reader
verifies an image or a chart before it runs. A reader who pastes the steps one by one does what the
page says, so the order of the commands on the page is the order of the install."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs" / "DEPLOYING.md").read_text()
JAVV_README = (ROOT / "deploy" / "helm" / "javv" / "README.md.gotmpl").read_text()
CHARTS = {"javv-opensearch", "javv", "javv-scanner"}


def section(text: str, *headings: str) -> str:
    """The text under the last heading, found after each heading before it, up to the next heading
    of the same or a higher level."""
    start = 0
    lines = text.splitlines()
    for heading in headings:
        start = lines.index(heading, start) + 1
    level = len(headings[-1]) - len(headings[-1].lstrip("#"))
    end = next(
        (
            i
            for i in range(start, len(lines))
            if lines[i].startswith("#") and len(lines[i]) - len(lines[i].lstrip("#")) <= level
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_section_stops_at_the_next_heading_of_its_level() -> None:
    page = "## A\n### Steps\none\n#### Sub\ntwo\n### Next\nthree\n## B\n### Steps\nfour\n"
    assert section(page, "## A", "### Steps") == "one\n#### Sub\ntwo"
    assert section(page, "## B", "### Steps") == "four"


def test_the_compose_steps_verify_the_pulled_images_before_they_start() -> None:
    steps = section(GUIDE, "## Install with docker compose", "### Steps")
    pull, verify, up = (
        steps.index(command)
        for command in ("docker compose pull", "cosign verify", "docker compose up -d")
    )
    assert pull < verify < up
    # the signature is for a digest, and compose.yaml names a tag: verify what the pull got
    assert "{{index .RepoDigests 0}}" in steps[pull:verify]


def test_a_checkout_does_not_pull_over_the_images_that_it_made() -> None:
    # the images of a checkout have no signature, and the tag of the compose file is the tag of
    # the last release: a pull would put the images of that release in their place
    checkout = section(GUIDE, "## Install with docker compose", "### Install from a checkout")
    assert "not `docker compose pull`" in checkout


def _helm_steps() -> str:
    return section(GUIDE, "## Install on Kubernetes with Helm", "### Steps")


def test_the_helm_steps_verify_the_three_charts_before_any_install() -> None:
    steps = _helm_steps()
    loop = re.search(r"for chart in (?P<charts>[^;]+); do", steps)
    assert loop and set(loop["charts"].split()) == CHARTS
    assert loop.start() < steps.index("cosign verify") < steps.index("helm install store")


def _store_install(steps: str) -> str:
    start = steps.index("helm install store")
    return steps[start : steps.index("```", start)]


@pytest.mark.parametrize(
    "steps",
    [_helm_steps(), section(JAVV_README, "## Install", "### Steps")],
    ids=["DEPLOYING", "javv chart README"],
)
def test_the_store_install_requests_the_memory_of_its_heap_then_tests_it(steps: str) -> None:
    # the heap is 1 GB and the official chart requests 100Mi; the test waits for a ready store
    install = _store_install(steps)
    assert "--set opensearch.resources.requests.memory=2Gi" in install
    assert "--wait" in install
    assert "helm test store" in install


def test_the_helm_page_tells_how_scanners_in_other_clusters_reach_javv() -> None:
    part = section(GUIDE, "## Install on Kubernetes with Helm", "### Scanners in other clusters")
    assert "--set frontend.service.type=LoadBalancer" in part
    assert "kubectl get svc javv" in part
    assert "kubectl get nodes -o wide" in part
