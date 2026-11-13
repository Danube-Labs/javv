"""Trivy adapter — parse `trivy image -f json` output into `Finding`s.

Trivy reports CVSS as a dict keyed by source (`nvd`, `redhat`, …); we prefer a V3 base score
over V2 and take the highest available. A vuln is fixable when Trivy gives a `FixedVersion`.
Trivy provides no EPSS/KEV. Input is untrusted: malformed entries are skipped, never fatal.
"""

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any, NamedTuple

from scanner.config import TrivyConfig
from scanner.models import Finding, Provenance, ScanResult
from scanner.normalize import clean_paths

# Hard cap per image so a hung scanner can't block the cycle forever (TimeoutExpired is then
# isolated per-image in run.scan_all). The k8s activeDeadlineSeconds belt-and-braces lands in M10.
SCAN_TIMEOUT_SECONDS = 600

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def trivy_command(image_ref: str, config: TrivyConfig) -> list[str]:
    """Build the trivy invocation from config. `--format json` is fixed (the parser depends on it);
    the default config reproduces the previously-pinned command exactly (#91). Optional flags are
    appended in a deterministic order so the command is stable/testable."""
    cmd = ["trivy", "image", "--quiet", "--scanners", config.scanners, "--format", "json"]
    if config.ignore_unfixed:
        cmd.append("--ignore-unfixed")
    if config.severities:
        cmd += ["--severity", config.severities]
    if config.pkg_types:
        cmd += ["--pkg-types", config.pkg_types]
    if config.timeout:
        cmd += ["--timeout", config.timeout]
    cmd.append(image_ref)
    return cmd


def _cvss(cvss: Any) -> float | None:
    if not isinstance(cvss, Mapping):
        return None
    for key in ("V3Score", "V2Score"):  # prefer V3
        scores = [
            s[key]
            for s in cvss.values()
            if isinstance(s, Mapping) and isinstance(s.get(key), int | float)
        ]
        if scores:
            return float(max(scores))
    return None


def _ptype(result: Mapping[str, Any]) -> str | None:
    """Package type (M8d/B-1): `Class == "os-pkgs"` → `"os"`; otherwise the ecosystem string
    (`Type`, lowercased — e.g. `python-pkg`, `node-pkg`). Missing/garbage → None, never fatal."""
    if result.get("Class") == "os-pkgs":
        return "os"
    ptype = result.get("Type")
    return ptype.lower() if isinstance(ptype, str) and ptype else None


# Trivy puts these labels in `Target` when the packages of a type come from many files, and the
# file of each package in `PkgPath` (v0.76.2, pkg/scan/langpkg/scan.go, `targetName`)
_LABEL_TYPES = frozenset({"python-pkg", "conda-pkg", "gemspec", "node-pkg", "jar", "kubernetes"})


def _raw_paths(result: Mapping[str, Any], vuln: Mapping[str, Any]) -> list[object]:
    """`PkgPath`, else the `Target` of a language result that names a file (a Go binary, a lock
    file). An OS package has none: its `Target` is the name of the image."""
    if vuln.get("PkgPath"):
        return [vuln["PkgPath"]]
    if result.get("Class") == "lang-pkgs" and result.get("Type") not in _LABEL_TYPES:
        target = result.get("Target")
        return [target] if target else []
    return []


def read_trivy(data: Mapping[str, Any]) -> ScanResult:
    """The findings, the provenance and the count of paths left out, from one Trivy report."""
    findings: list[Finding] = []
    dropped = over_cap = 0
    for result in data.get("Results") or []:
        if not isinstance(result, Mapping):
            continue
        ptype = _ptype(result)
        for v in result.get("Vulnerabilities") or []:
            if not isinstance(v, Mapping):
                continue
            vuln_id = v.get("VulnerabilityID")
            package_name = v.get("PkgName")
            if not vuln_id or not package_name:
                continue
            fixed_version = v.get("FixedVersion") or None
            paths = clean_paths(_raw_paths(result, v))
            dropped += paths.dropped
            over_cap += paths.over_cap
            findings.append(
                Finding(
                    vuln_id=vuln_id,
                    package_name=package_name,
                    package_version=v.get("InstalledVersion") or "",
                    severity=v.get("Severity") or "Unknown",
                    cvss=_cvss(v.get("CVSS")),
                    fixable=bool(fixed_version),
                    fixed_version=fixed_version,
                    ptype=ptype,
                    locations=paths.paths,
                )
            )
    return ScanResult(
        findings=findings,
        provenance=parse_trivy_provenance(data),
        paths_dropped=dropped,
        paths_over_cap=over_cap,
    )


def parse_trivy(data: Mapping[str, Any]) -> list[Finding]:
    return read_trivy(data).findings


def parse_trivy_provenance(data: Mapping[str, Any]) -> Provenance:
    """Scanner version from `Trivy.Version`. Trivy's standalone JSON carries no vuln-DB info."""
    trivy = data.get("Trivy")
    version = trivy.get("Version") if isinstance(trivy, Mapping) else None
    return Provenance(scanner_version=version or None)


class TrivyDbInfo(NamedTuple):
    version: str | None
    built: datetime | None


def _coerce_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)  # handles trailing Z + nanosecond fractions (3.11+)
    except ValueError:
        return None


def trivy_db_info(*, runner: Runner = subprocess.run) -> TrivyDbInfo:
    """Best-effort vuln-DB provenance via `trivy version --format json`, once per cycle (#96).

    Trivy's scan report deliberately omits DB metadata (upstream discussions 6264/9400); the
    supported source is the version command, which reads the same local cache the scan uses.
    `VulnerabilityDB.Version` = DB schema, `UpdatedAt` = when the DB content was built. Any
    failure (no cache, bad JSON, subprocess error) → nulls — never fatal to the cycle.
    """
    try:
        proc = runner(
            ["trivy", "version", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        db = json.loads(proc.stdout).get("VulnerabilityDB")
        if not isinstance(db, Mapping):
            return TrivyDbInfo(None, None)
        version = db.get("Version")
        return TrivyDbInfo(
            version=str(version) if version is not None else None,
            built=_coerce_dt(db.get("UpdatedAt")),
        )
    except Exception:
        return TrivyDbInfo(None, None)


def scan_trivy(
    image_ref: str,
    *,
    runner: Runner = subprocess.run,
    config: TrivyConfig | None = None,
    db: TrivyDbInfo | None = None,
) -> ScanResult:
    """Drive the trivy binary against an image ref and parse its JSON output + provenance.
    `db` is the cycle-level `trivy_db_info()` result, merged into the provenance (#96)."""
    proc = runner(
        trivy_command(image_ref, config or TrivyConfig()),
        capture_output=True,
        text=True,
        check=True,
        timeout=SCAN_TIMEOUT_SECONDS,
    )
    result = read_trivy(json.loads(proc.stdout))
    if db is not None:
        result = replace(
            result,
            provenance=result.provenance.model_copy(
                update={"db_version": db.version, "db_built": db.built}
            ),
        )
    return result
