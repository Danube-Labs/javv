"""Grype adapter — parse `grype <image> -o json` output into `Finding`s.

Package identity comes from `artifact`; the vuln (id/severity/fix/cvss/epss) from `vulnerability`.
Grype additionally provides EPSS (`vulnerability.epss[].epss`) and KEV
(`vulnerability.knownExploited`), which we capture. A vuln is fixable when the fix state is
`fixed` or a fixed version is listed. Input is untrusted: malformed entries are skipped.
"""

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from scanner.config import GrypeConfig
from scanner.models import Finding, Provenance, ScanResult
from scanner.normalize import clean_paths

Runner = Callable[..., "subprocess.CompletedProcess[str]"]

# Default hard cap per image (overridable via config.scan_timeout) so a hung scanner can't block the
# cycle forever (TimeoutExpired is isolated per-image in run.scan_all). k8s activeDeadlineSeconds
# belt-and-braces lands in M10.
SCAN_TIMEOUT_SECONDS = 600


def grype_command(image_ref: str, config: GrypeConfig) -> list[str]:
    """Build the grype invocation from config. `-o json` is fixed (the parser depends on it); the
    default config reproduces the previously-pinned command exactly (#91)."""
    cmd = ["grype", image_ref, "-o", "json"]
    if config.only_fixed:
        cmd.append("--only-fixed")
    if config.scope:
        cmd += ["--scope", config.scope]
    return cmd


def _coerce_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)  # handles the trailing Z (3.11+)
    except ValueError:
        return None


def _cvss(cvss: Any) -> float | None:
    if not isinstance(cvss, Sequence):
        return None
    scores = [
        c["metrics"]["baseScore"]
        for c in cvss
        if isinstance(c, Mapping)
        and isinstance(c.get("metrics"), Mapping)
        and isinstance(c["metrics"].get("baseScore"), int | float)
    ]
    return float(max(scores)) if scores else None


def _epss(epss: Any) -> float | None:
    if isinstance(epss, Sequence) and epss:
        first = epss[0]
        if isinstance(first, Mapping) and isinstance(first.get("epss"), int | float):
            return float(first["epss"])
    return None


def _raw_paths(artifact: Mapping[str, Any]) -> list[object]:
    """Each `artifact.locations[].path`. Operator ruling (issue 1077): all of them, also the
    package database files of an OS package."""
    locations = artifact.get("locations")
    if not isinstance(locations, Sequence) or isinstance(locations, str):
        return []
    return [loc.get("path") for loc in locations if isinstance(loc, Mapping)]


def read_grype(data: Mapping[str, Any]) -> ScanResult:
    """The findings, the provenance and the count of paths left out, from one Grype report."""
    findings: list[Finding] = []
    dropped = over_cap = 0
    for m in data.get("matches") or []:
        if not isinstance(m, Mapping):
            continue
        vuln = m.get("vulnerability") or {}
        artifact = m.get("artifact") or {}
        vuln_id = vuln.get("id")
        package_name = artifact.get("name")
        if not vuln_id or not package_name:
            continue
        fix = vuln.get("fix") or {}
        versions = fix.get("versions") or []
        # package type (M8d/B-1): Grype's artifact.type, verbatim-lowercase (apk/deb/rpm/python/…)
        raw_ptype = artifact.get("type")
        ptype = raw_ptype.lower() if isinstance(raw_ptype, str) and raw_ptype else None
        paths = clean_paths(_raw_paths(artifact))
        dropped += paths.dropped
        over_cap += paths.over_cap
        findings.append(
            Finding(
                vuln_id=vuln_id,
                package_name=package_name,
                package_version=artifact.get("version") or "",
                severity=vuln.get("severity") or "Unknown",
                cvss=_cvss(vuln.get("cvss")),
                fixable=fix.get("state") == "fixed" or bool(versions),
                fixed_version=versions[0] if versions else None,
                epss=_epss(vuln.get("epss")),
                kev=bool(vuln.get("knownExploited")),
                ptype=ptype,
                locations=paths.paths,
            )
        )
    return ScanResult(
        findings=findings,
        provenance=parse_grype_provenance(data),
        paths_dropped=dropped,
        paths_over_cap=over_cap,
    )


def parse_grype(data: Mapping[str, Any]) -> list[Finding]:
    return read_grype(data).findings


def parse_grype_provenance(data: Mapping[str, Any]) -> Provenance:
    """Scanner version from `descriptor.version`; vuln-DB info from `descriptor.db.status`."""
    desc = data.get("descriptor")
    if not isinstance(desc, Mapping):
        return Provenance()
    db = desc.get("db")
    status = db.get("status") if isinstance(db, Mapping) else None
    status = status if isinstance(status, Mapping) else {}
    return Provenance(
        scanner_version=desc.get("version") or None,
        db_version=status.get("schemaVersion") or None,
        db_built=_coerce_dt(status.get("built")),
    )


def scan_grype(
    image_ref: str, *, runner: Runner = subprocess.run, config: GrypeConfig | None = None
) -> ScanResult:
    """Drive the grype binary against an image ref and parse its JSON output + provenance."""
    cfg = config or GrypeConfig()
    proc = runner(
        grype_command(image_ref, cfg),
        capture_output=True,
        text=True,
        check=True,
        timeout=cfg.scan_timeout,
    )
    return read_grype(json.loads(proc.stdout))
