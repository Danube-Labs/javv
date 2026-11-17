"""M6 slice 6 — VEX serializer units (FR-22).

Pins: the state → status mapping table in `export/vex.py` (golden-locked for both formats);
`not_affected` carries the CISA justification verbatim in OpenVEX and the documented
CycloneDX translation; `risk_accepted` is OpenVEX `affected` + action_statement / CycloneDX
`exploitable` + `will_not_fix` (never silently dropped); purls percent-encode the digest.
"""

import json
import pathlib
from datetime import UTC, datetime

from backend.export.vex import image_purl, package_purl, to_cyclonedx, to_openvex
from backend.triage.state_machine import CISA_JUSTIFICATIONS

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
GENERATED_AT = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def test_package_purl_percent_encodes_slashy_names_and_versions() -> None:
    """A-n (audit #192): a Go module path (or a `+`/`@`/`:` in name or version) must not yield a
    malformed purl — name/version are percent-encoded, mirroring the image_purl digest encoding."""
    purl = package_purl(
        {"package_name": "github.com/x/y", "installed_version": "v1.2.3+incompatible"}
    )
    assert purl == "pkg:generic/github.com%2Fx%2Fy@v1.2.3%2Bincompatible"
    # a plain package is unchanged (nothing to encode)
    assert package_purl({"package_name": "libssl", "installed_version": "3.0.1"}) == (
        "pkg:generic/libssl@3.0.1"
    )


def _findings() -> list[dict]:
    return json.loads((FIXTURES / "vex-findings.json").read_text())


def test_openvex_golden() -> None:
    doc = to_openvex(
        _findings(), cluster_id="c-vex-golden", scanner="trivy", generated_at=GENERATED_AT
    )
    expected = json.loads((FIXTURES / "vex-openvex-golden.json").read_text())
    assert doc == expected


def test_cyclonedx_golden() -> None:
    doc = to_cyclonedx(
        _findings(), cluster_id="c-vex-golden", scanner="trivy", generated_at=GENERATED_AT
    )
    expected = json.loads((FIXTURES / "vex-cyclonedx-golden.json").read_text())
    assert doc == expected


def test_every_cisa_justification_translates_to_cyclonedx() -> None:
    for j in CISA_JUSTIFICATIONS:
        doc = to_cyclonedx(
            [
                {
                    "cve_id": "CVE-2024-1111",
                    "state": "not_affected",
                    "vex_justification": j,
                    "package_name": "p",
                    "installed_version": "1",
                    "image_repo": "r/a",
                    "image_digest": "sha256:x",
                }
            ],
            cluster_id="c-vex-golden",
            scanner="grype",
            generated_at=GENERATED_AT,
        )
        assert "justification" in doc["vulnerabilities"][0]["analysis"]


def test_image_purl_is_percent_encoded() -> None:
    purl = image_purl({"image_repo": "registry.local/team/app", "image_digest": "sha256:abc"})
    assert purl == "pkg:oci/app@sha256%3Aabc?repository_url=registry.local/team/app"


def _with_paths() -> list[dict]:
    docs = _findings()
    docs[0] = dict(
        docs[0], locations=["/usr/lib/libssl.so.3", "/opt/app/libssl.so.3"], locations_total=2
    )
    return docs


def test_cyclonedx_puts_the_paths_in_the_evidence_of_a_component() -> None:
    """Issue 1245, D2 A: CycloneDX 1.5 `component.evidence.occurrences[].location` holds the paths
    of a finding. The vulnerability names that component in `affects`, next to the image."""
    docs = _with_paths()
    bom = to_cyclonedx(docs, cluster_id="c-vex-paths", scanner="trivy", generated_at=GENERATED_AT)
    [component] = bom["components"]
    assert component["bom-ref"] == docs[0]["finding_key"]
    assert component["type"] == "library"
    assert component["purl"] == package_purl(docs[0])
    assert component["evidence"]["occurrences"] == [
        {"location": "/usr/lib/libssl.so.3"},
        {"location": "/opt/app/libssl.so.3"},
    ]
    first = bom["vulnerabilities"][0]
    assert first["affects"] == [{"ref": image_purl(docs[0])}, {"ref": docs[0]["finding_key"]}]
    # a finding with no paths keeps the image as its only reference
    assert all(
        v["affects"] == [{"ref": image_purl(d)}]
        for v, d in zip(bom["vulnerabilities"][1:], docs[1:], strict=True)
    )


def test_cyclonedx_with_no_paths_has_no_components() -> None:
    bom = to_cyclonedx(_findings(), cluster_id="c", scanner="trivy", generated_at=GENERATED_AT)
    assert "components" not in bom


def test_openvex_has_no_field_for_a_path() -> None:
    """OpenVEX 0.2.0 has no field for a file path, so its export does not change (issue 1245)."""
    with_paths = to_openvex(
        _with_paths(), cluster_id="c", scanner="trivy", generated_at=GENERATED_AT
    )
    without = to_openvex(_findings(), cluster_id="c", scanner="trivy", generated_at=GENERATED_AT)
    assert with_paths == without
