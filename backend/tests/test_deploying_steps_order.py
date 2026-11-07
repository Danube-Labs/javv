"""The install steps of docs/DEPLOYING.md run in a safe sequence (issues 1125 and 1126): a reader
verifies an image or a chart before it runs. A reader who pastes the steps one by one does what the
page says, so the order of the commands on the page is the order of the install."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs" / "DEPLOYING.md").read_text()


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
