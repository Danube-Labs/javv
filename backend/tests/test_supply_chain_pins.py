"""The tools the publish jobs run while they can sign (issue 833, B3): syft, and the self-scan grype
of scanner-images.yml, come from their official images by digest, never by a tag that can move.

Pins: each is `v<version>@sha256:<64 hex>` in versions.yaml; each workflow step that installs one
creates it from exactly that value; Renovate's versions.yaml manager extracts every annotated line
once, and captures the digest of a `tag@sha256:` line so it moves with the tag; the self-scan
grype's tag is the scanner's `current` grype, and the two move in one Renovate PR.
"""

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "versions.yaml"
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED = re.compile(r"v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}")


def _versions() -> dict[str, Any]:
    return yaml.safe_load(VERSIONS.read_text())


def _renovate() -> dict[str, Any]:
    return json.loads((ROOT / "renovate.json").read_text())


def _patterns() -> list[re.Pattern[str]]:
    """Renovate's versions.yaml patterns, its JS named groups written the Python way."""
    manager = _renovate()["customManagers"][0]
    return [re.compile(m.replace("(?<", "(?P<")) for m in manager["matchStrings"]]


def _run_lines(workflow: str) -> str:
    """The run lines of the jobs that can get a signing identity: the ones B3 is about. The
    compat matrix takes each supported scanner version by tag and signs nothing."""
    jobs = yaml.safe_load((WORKFLOWS / workflow).read_text())["jobs"]
    signers = [j for j in jobs.values() if (j.get("permissions") or {}).get("id-token") == "write"]
    assert signers
    return "\n".join(s.get("run", "") for job in signers for s in job.get("steps", []))


def test_syft_and_the_self_scan_grype_are_pinned_by_digest() -> None:
    chain = _versions()["supply_chain"]
    assert PINNED.fullmatch(chain["syft"]), chain["syft"]
    assert PINNED.fullmatch(chain["grype"]), chain["grype"]


def test_each_install_step_creates_the_tool_from_its_digest_pin() -> None:
    release, scanner = _run_lines("release-please.yml"), _run_lines("scanner-images.yml")
    assert "syft=$(yq -r '.supply_chain.syft' versions.yaml)" in release
    assert 'docker create "anchore/syft:$syft"' in release
    assert "grype=$(yq -r '.supply_chain.grype' versions.yaml)" in scanner
    assert '"syft:anchore/syft:$syft" "grype:anchore/grype:$grype"' in scanner
    for text in (release, scanner):
        # a tag built from a version, the way they were taken before
        assert not re.search(r"anchore/(syft|grype):v\$", text)


def test_renovate_extracts_every_annotated_line_once() -> None:
    text = VERSIONS.read_text()
    annotated = len(re.findall(r"^\s*# renovate:", text, re.M))
    found = [m for p in _patterns() for m in p.finditer(text)]
    assert len(found) == annotated
    assert len({m.start() for m in found}) == annotated  # no line taken by two patterns


def test_renovate_moves_a_digest_with_its_tag() -> None:
    text = VERSIONS.read_text()
    digests = {
        m["depName"]: (m["currentValue"], m["currentDigest"])
        for p in _patterns()
        for m in p.finditer(text)
        if "currentDigest" in m.groupdict() and m["currentDigest"]
    }
    chain = _versions()["supply_chain"]
    assert digests == {
        "anchore/syft": tuple(chain["syft"].split("@")),
        "anchore/grype": tuple(chain["grype"].split("@")),
    }


def test_the_self_scan_grype_is_the_scanners_grype_and_moves_with_it() -> None:
    versions = _versions()
    assert (
        versions["supply_chain"]["grype"].split("@")[0]
        == "v" + (versions["scanners"]["grype"]["current"])
    )
    rules = _renovate()["packageRules"]
    group = [
        r
        for r in rules
        if r.get("groupName") == "grype" and r.get("matchPackageNames") == ["anchore/grype"]
    ]
    assert group and group[0]["matchManagers"] == ["custom.regex"]
