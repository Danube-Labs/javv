"""Shared scanner data shapes.

`Finding` is one vulnerability occurrence as a single scanner reports it — scanner-intrinsic
facts only. Tenant/run identity (`cluster_id`, `scan_run_id`, `scan_order`, `commit_key`, …) is
stamped later by the envelope; per-scanner findings are never merged across scanners.
"""

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from scanner.normalize import canonical_severity


class Provenance(BaseModel):
    """Which scanner build + vuln-DB produced a scan (D41). Self-reported by the binary at run
    time; ingested for the read-only "scanner status / version" view and audit version matrix.
    DB fields are nullable/best-effort: Grype reports them in the scan JSON; Trivy's comes from a
    per-cycle `trivy version --format json` call (#96) — nulls if that fails, never a dead scan."""

    model_config = ConfigDict(frozen=True)

    scanner_version: str | None = None  # Trivy `Trivy.Version` / Grype `descriptor.version`
    db_version: str | None = None  # Grype `db.status.schemaVersion` / Trivy `VulnerabilityDB` ver
    db_built: datetime | None = None  # Grype `db.status.built` / Trivy `VulnerabilityDB.UpdatedAt`


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    vuln_id: str
    package_name: str
    package_version: str
    severity: str  # verbatim scanner word, preserved for evidence/display (D16)
    cvss: float | None = None
    fixable: bool = False
    fixed_version: str | None = None
    epss: float | None = None  # Grype-only; None when the scanner doesn't provide it
    kev: bool = False  # Grype-only (Known Exploited Vulnerabilities)
    # package type (M8d/B-1): "os" (Trivy os-pkgs) or the scanner's verbatim-lowercase ecosystem
    # string (Trivy Type / Grype artifact.type) — per-scanner vocabulary, never folded across
    # scanners (per-scanner is sacred; facet buckets never merge)
    ptype: str | None = None
    # the files in the image where the scanner found the package (issue 1077): each starts with
    # `/`, no repeats, the first 64 sorted (normalize.clean_paths). One report row, never merged.
    locations: tuple[str, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def severity_canonical(self) -> str:
        """Canonical bucket (D16); always consistent with the verbatim `severity`."""
        return canonical_severity(self.severity)


@dataclass(frozen=True)
class ScanResult:
    """One scanner's output for one image: the findings plus its self-reported provenance."""

    findings: list[Finding] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)
    paths_dropped: int = 0  # paths that the backend would refuse (normalize.clean_paths)
    paths_over_cap: int = 0  # valid paths past the first 64 of an entry
