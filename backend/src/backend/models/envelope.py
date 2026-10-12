"""The ingest wire contract — the scanner's schema-v3 envelope, mirrored field-for-field with
`extra="forbid"` (D41 coupling: any drift on either side is a 422, caught by the golden fixture).
v3 adds `effective_config` (D44/FR-25): the tuning flags + scope the cycle actually ran with —
read-only display/audit, persisted on scan-events only, and the tuning shape must match `scanner`.

Security posture (untrusted input): `cluster_id` is shape-validated strictly because it flows into
OpenSearch index names (index-name injection); the counts invariant (total == bucket sum) is an
integrity check; the server RE-derives the canonical severity + rank from the verbatim `severity`
(D16) — the client's `severity_canonical` is accepted on the wire but never trusted.
"""

from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from backend.core.identifiers import CLUSTER_ID_RE as _CLUSTER_ID

# canonical buckets (D16) + the fixed rank order (OE-5). D46 (#274): the canonical vocabulary
# is the FULL words — for every standard scanner word canonical == verbatim-lc, and no released
# artifact ever speaks the historical crit/med shorthand as a VALUE (the short names survive
# only as count COLUMN names on the envelope/scan-events/images, documented physical names).
SEVERITY_RANK: dict[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "negligible": 1,
    "unknown": 0,
}

_CANONICAL = {
    "critical": "critical",
    "crit": "critical",
    "high": "high",
    "medium": "medium",
    "med": "medium",
    "moderate": "medium",
    "low": "low",
    "negligible": "negligible",
    "unknown": "unknown",
}

# cluster_id shape: the ONE shared rule lives in core/identifiers.py (task E / audit M2)


def canonical_severity(raw: str) -> str:
    """Defensive normalizer (D16): anything unrecognized is `unknown`, never `crit`."""
    return _CANONICAL.get(raw.strip().lower(), "unknown")


class IngestFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vuln_id: str = Field(min_length=1, max_length=128)
    package_name: str = Field(min_length=1, max_length=512)
    package_version: str = Field(max_length=256)
    severity: str = Field(max_length=64)  # verbatim scanner word, preserved (D16)
    cvss: float | None = Field(default=None, ge=0, le=10)
    fixable: bool = False
    fixed_version: str | None = Field(default=None, max_length=256)
    epss: float | None = Field(default=None, ge=0, le=1)  # grype only
    kev: bool = False  # grype only
    # package type (M8d/B-1, #241): "os" or the scanner's verbatim-lowercase ecosystem string.
    # Absent in v3 envelopes → None (aggregates as "unknown" until the next sweep re-observes,
    # D30). Untrusted input, lands in a keyword facet field — shape-constrained at the edge.
    ptype: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9][a-z0-9+._-]*$")
    severity_canonical: str  # sent by the scanner; NOT trusted — see severity_server

    @property
    def severity_server(self) -> str:
        """Server-derived canonical bucket — the only one ever written to an index."""
        return canonical_severity(self.severity)

    @property
    def severity_rank(self) -> int:
        return SEVERITY_RANK[self.severity_server]


class IngestCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    crit: int = Field(ge=0)
    high: int = Field(ge=0)
    med: int = Field(ge=0)
    low: int = Field(ge=0)
    negligible: int = Field(ge=0)
    unknown: int = Field(ge=0)
    total: int = Field(ge=0)
    fixable: int = Field(ge=0)


class TrivyTuning(BaseModel):
    """Mirror of the scanner's `TrivyConfig` — disjoint from `GrypeTuning`, so the union below
    is unambiguous and a mismatched shape fails validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scanners: str = Field(max_length=128)
    ignore_unfixed: bool
    severities: str | None = Field(default=None, max_length=128)
    pkg_types: str | None = Field(default=None, max_length=128)
    timeout: str | None = Field(default=None, max_length=64)


class GrypeTuning(BaseModel):
    """Mirror of the scanner's `GrypeConfig`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    only_fixed: bool
    scope: str | None = Field(default=None, max_length=64)
    scan_timeout: int = Field(ge=1)


class IngestScope(BaseModel):
    """Mirror of the D43 `ScanScope` the scanner applied this cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    include_namespaces: list[str] = Field(default=[], max_length=1024)
    ignore_namespaces: list[str] = Field(default=[], max_length=1024)
    exclude_images: list[str] = Field(default=[], max_length=1024)
    ignore_kinds: list[str] = Field(default=[], max_length=64)


class IngestEffectiveConfig(BaseModel):
    """What the cycle ran with (D44/FR-25) — display/audit only, never a control surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tuning: TrivyTuning | GrypeTuning
    scope: IngestScope


class IngestEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # v3 + v4 dual acceptance (M8d/B-1, #241) — the ONE deliberate departure from the
    # current-envelope-only rule (D25/D35; v3 itself was a flag day, D44): scanner images are
    # operator-swapped (D41), so the ptype rollout must not brick un-swapped scanners. v3
    # findings simply have no ptype (→ null). Drop back to a single Literal when v3 retires.
    schema_version: Literal[3, 4]
    cluster_id: str
    scanner: Literal["trivy", "grype"]  # per-scanner is sacred — no other value exists
    image_digest: str = Field(pattern=r"^sha256:[a-fA-F0-9]{6,64}$", max_length=128)
    image_ref: str = Field(max_length=512)
    namespaces: list[str] = Field(max_length=1024)
    replicas: int = Field(ge=0)
    scan_run_id: str = Field(min_length=1, max_length=128)
    scan_order: int = Field(ge=0)
    last_seen_at: AwareDatetime  # the contract: every time carries a zone
    scanner_version: str | None = Field(default=None, max_length=128)
    scanner_db_version: str | None = Field(default=None, max_length=128)
    scanner_db_built: AwareDatetime | None = None
    effective_config: IngestEffectiveConfig  # required in v3 (D44) — no silent omission
    counts: IngestCounts
    findings: list[IngestFinding] = Field(max_length=100_000)

    @field_validator("cluster_id")
    @classmethod
    def _cluster_id_shape(cls, v: str) -> str:
        if not _CLUSTER_ID.fullmatch(v):
            raise ValueError("cluster_id must be lowercase alnum/hyphen, 8-64 chars")
        return v

    @model_validator(mode="after")
    def _counts_invariant(self) -> "IngestEnvelope":
        c = self.counts
        buckets = c.crit + c.high + c.med + c.low + c.negligible + c.unknown
        if c.total != buckets or c.total != len(self.findings):
            raise ValueError("counts invariant violated: total != bucket sum != len(findings)")
        return self

    @model_validator(mode="after")
    def _tuning_matches_scanner(self) -> "IngestEnvelope":
        # a trivy envelope carrying grype tuning (or vice versa) is a lying client (D44)
        expected = TrivyTuning if self.scanner == "trivy" else GrypeTuning
        if not isinstance(self.effective_config.tuning, expected):
            raise ValueError(f"effective_config.tuning shape does not match scanner {self.scanner}")
        return self
