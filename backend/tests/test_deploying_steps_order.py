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


SCANNER_README = (ROOT / "deploy" / "helm" / "javv-scanner" / "README.md.gotmpl").read_text()
NOTES = (ROOT / "deploy" / "helm" / "javv-scanner" / "templates" / "NOTES.txt").read_text()


def _scanner_steps() -> str:
    return section(GUIDE, "## Connect the scanners", "### Steps")


def _scanner_install(steps: str) -> str:
    start = steps.index("helm install scanner")
    return steps[start : steps.index("```", start)]


@pytest.mark.parametrize(
    "steps",
    [_scanner_steps(), section(SCANNER_README, "## Install", "### Steps")],
    ids=["DEPLOYING", "javv-scanner chart README"],
)
def test_the_scanner_install_waits_for_its_volumes_and_names_no_port(steps: str) -> None:
    # the install's vuln-DB Jobs bind the cache volumes, which --wait waits for; the port of
    # JAVV is 8080 only on the Service, a NodePort or a load balancer has its own (issue 1126)
    install = _scanner_install(steps)
    assert "--wait" in install
    assert "--set backendUrl=http://<the address and port of JAVV>" in install


def _notes_commands() -> list[str]:
    """The kubectl commands of the NOTES that start a cycle, for the release `scanner` in the
    namespace `javv-scanner`, with `$s` for the scanner."""
    lines = [line.strip() for line in NOTES.splitlines() if line.strip().startswith("kubectl")]
    names = {
        "{{ $.Release.Namespace }}": "javv-scanner",
        "{{ $.Release.Name }}": "scanner",
        "{{ $cj }}": "$cj",
        "{{ $name }}": "$s",
    }
    out = []
    for line in lines:
        for template, value in names.items():
            line = line.replace(template, value)
        out.append(line)
    return out


def test_the_scanner_steps_start_the_first_cycle_with_the_commands_of_the_notes() -> None:
    steps = _scanner_steps()
    cycle = steps[steps.index("helm test scanner") :]
    where = [cycle.index(command) for command in _notes_commands()]
    assert len(where) == 5
    assert where == sorted(where)
    assert "cj=scanner-javv-scanner-$s" in cycle
    # a schedule in the pause starts that cycle at the resume (issue 1126, H7)
    assert "a second cycle" in cycle


def test_the_scanner_steps_verify_the_chart_before_its_install() -> None:
    # a compose install does not do the Helm steps, so this step names the verification itself
    steps = _scanner_steps()
    assert steps.index("First verify the chart") < steps.index("helm install scanner")


def test_the_scanner_steps_tell_where_to_name_the_cluster() -> None:
    assert "**Settings › Cluster**" in _scanner_steps()
