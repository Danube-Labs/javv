"""VEX export (M6 slice 6, FR-22 export-only; import → v1.1).

Pure serializers: a list of finding docs (ONE scanner — per-scanner is sacred, the route
enforces it) → an OpenVEX document or a CycloneDX VEX BOM: a standard record of the triage
decisions. Trivy and grype do not apply it today: both refuse the CycloneDX form, and the
OpenVEX form names the package `pkg:generic/...`, which neither matches (trivy also expects a
Docker Hub image as `index.docker.io/...`). Issue 791 holds the fix. The two-field triage model
maps as follows (ruling recorded here):

| JAVV state                  | OpenVEX status        | CycloneDX analysis.state       |
|-----------------------------|-----------------------|--------------------------------|
| `not_affected`              | `not_affected`        | `not_affected`                 |
| `risk_accepted`             | `affected`¹           | `exploitable` + `will_not_fix` |
| `resolved`                  | `fixed`               | `resolved`                     |
| `open`/`acknowledged`/`stale` | `under_investigation` | `in_triage`                    |

¹ OpenVEX has no "accepted" status — `affected` + an action_statement naming the journaled
risk-accept is the faithful encoding (the vuln IS present; we've decided to carry it).

The CISA five ARE the OpenVEX justification vocabulary (verbatim). CycloneDX has its own
labels; the mapping below is the module's ruling (documented, golden-pinned):
`component_not_present`/`vulnerable_code_not_present` → `code_not_present`;
`vulnerable_code_not_in_execute_path` → `code_not_reachable`;
`vulnerable_code_cannot_be_controlled_by_adversary`/`inline_mitigations_already_exist`
→ `protected_by_mitigating_control`.

Products are purl-identified: the image as `pkg:oci/<name>@<digest>?repository_url=<repo>`
(digest `:` percent-encoded per purl spec), the package best-effort as `pkg:generic/...`
(the envelope doesn't carry the ecosystem — v1.1 purl passthrough would tighten this).
"""

from datetime import datetime
from typing import Any
from urllib.parse import quote

_OPENVEX_CONTEXT = "https://openvex.dev/ns/v0.2.0"

_OPENVEX_STATUS = {
    "not_affected": "not_affected",
    "risk_accepted": "affected",
    "resolved": "fixed",
    "open": "under_investigation",
    "acknowledged": "under_investigation",
    "stale": "under_investigation",
}

_CDX_STATE = {
    "not_affected": "not_affected",
    "risk_accepted": "exploitable",
    "resolved": "resolved",
    "open": "in_triage",
    "acknowledged": "in_triage",
    "stale": "in_triage",
}

_CDX_JUSTIFICATION = {
    "component_not_present": "code_not_present",
    "vulnerable_code_not_present": "code_not_present",
    "vulnerable_code_not_in_execute_path": "code_not_reachable",
    "vulnerable_code_cannot_be_controlled_by_adversary": "protected_by_mitigating_control",
    "inline_mitigations_already_exist": "protected_by_mitigating_control",
}

_RISK_ACCEPT_NOTE = "risk accepted in JAVV (decision journaled in system-audit-log)"


def image_purl(doc: dict[str, Any]) -> str:
    repo = doc.get("image_repo") or "unknown"
    name = repo.rsplit("/", 1)[-1]
    digest = str(doc.get("image_digest") or "").replace(":", "%3A")
    return f"pkg:oci/{name}@{digest}?repository_url={repo}"


def package_purl(doc: dict[str, Any]) -> str:
    # percent-encode name/version (audit A-n): a slashy package (a Go module path
    # `github.com/x/y`) or a `@`/`:` in either component would otherwise yield a malformed purl —
    # mirror the image_purl digest encoding. Ecosystem stays best-effort `generic` (v1.1 tightens).
    name = quote(str(doc.get("package_name") or ""), safe="")
    version = quote(str(doc.get("installed_version") or ""), safe="")
    return f"pkg:generic/{name}@{version}"


def to_openvex(
    findings: list[dict[str, Any]], *, cluster_id: str, scanner: str, generated_at: datetime
) -> dict[str, Any]:
    ts = generated_at.isoformat()
    statements = []
    for doc in findings:
        state = doc.get("state", "open")
        stmt: dict[str, Any] = {
            "vulnerability": {"name": doc["cve_id"]},
            "products": [{"@id": image_purl(doc), "subcomponents": [{"@id": package_purl(doc)}]}],
            "status": _OPENVEX_STATUS[state],
        }
        if state == "not_affected":
            stmt["justification"] = doc["vex_justification"]  # the CISA five, verbatim
        if state == "risk_accepted":
            stmt["action_statement"] = _RISK_ACCEPT_NOTE
        statements.append(stmt)
    return {
        "@context": _OPENVEX_CONTEXT,
        "@id": f"urn:javv:vex:{cluster_id}:{scanner}:{ts}",
        "author": "JAVV",
        "role": "vulnerability management system",
        "timestamp": ts,
        "version": 1,
        "statements": statements,
    }


def to_cyclonedx(
    findings: list[dict[str, Any]], *, cluster_id: str, scanner: str, generated_at: datetime
) -> dict[str, Any]:
    ts = generated_at.isoformat()
    vulnerabilities = []
    components = []
    for doc in findings:
        state = doc.get("state", "open")
        affects = [{"ref": image_purl(doc)}]
        if paths := doc.get("locations"):
            # the paths of a finding are the evidence of where its package is (issue 1245)
            components.append(
                {
                    "bom-ref": doc["finding_key"],
                    "type": "library",
                    "name": str(doc.get("package_name") or ""),
                    "version": str(doc.get("installed_version") or ""),
                    "purl": package_purl(doc),
                    "evidence": {"occurrences": [{"location": p} for p in paths]},
                }
            )
            affects.append({"ref": doc["finding_key"]})
        analysis: dict[str, Any] = {"state": _CDX_STATE[state]}
        if state == "not_affected":
            analysis["justification"] = _CDX_JUSTIFICATION[doc["vex_justification"]]
        if state == "risk_accepted":
            analysis["response"] = ["will_not_fix"]
            analysis["detail"] = _RISK_ACCEPT_NOTE
        vulnerabilities.append(
            {
                "id": doc["cve_id"],
                "source": {"name": scanner},
                "analysis": analysis,
                "affects": affects,
            }
        )
    bom: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": ts,
            "tools": [{"vendor": "JAVV", "name": "javv"}],
            "properties": [
                {"name": "javv:cluster_id", "value": cluster_id},
                {"name": "javv:scanner", "value": scanner},
            ],
        },
        "vulnerabilities": vulnerabilities,
    }
    if components:
        bom["components"] = components
    return bom
