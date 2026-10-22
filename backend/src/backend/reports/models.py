"""M7 scheduled-export queue (#32) — shared constants + the enqueue request contract.

Report results are stored IN OpenSearch (chunked, `system-report-chunks`), NOT an object store — the
#32 storage decision, which supersedes SEC-10's object-store + presigned-URL model. The enqueue
endpoint writes a `pending` `system-reports` doc; the off-peak drain (a later slice) claims it via
optimistic concurrency, streams the export through M6's engine, stores the result chunked, and rings
the bell. This module is pure — the doc builder does no I/O, so it unit-tests without OpenSearch."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.core.identifiers import ClusterId
from backend.query.search import (
    LIST_FILTER_FIELDS,
    MAX_FILTER_VALUES,
    FilterValue64,
    FilterValue128,
    FilterValue256,
    FilterValue512,
    one_value_as_list,
)

REPORTS_INDEX = "system-reports"
REPORT_CHUNKS_INDEX = "system-report-chunks"
NOTIFICATIONS_INDEX = "system-notifications"

REPORT_SCHEMA_VERSION = 1

# job statuses (system-reports.status)
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


class ExportParams(BaseModel):
    """The export lens — mirrors the M6 `SearchFilters` facets + the output format. Stored opaquely
    as the report doc's `params`; the drain rebuilds a `SearchFilters` from it (a later slice)."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["csv", "openvex", "cyclonedx"] = "csv"
    severity: list[str] | None = Field(default=None, max_length=16)
    state: list[str] | None = Field(default=None, max_length=16)
    scanner: str | None = Field(default=None, max_length=32)
    assignee: list[FilterValue128] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    kev: bool | None = None
    fixable: bool | None = None
    disagree: bool | None = None
    cve_id: list[FilterValue128] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    image_digest: str | None = Field(default=None, max_length=128)
    image_repo: list[FilterValue512] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    namespace: list[FilterValue256] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    ptype: list[FilterValue64] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    package_name: list[FilterValue512] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    q: str | None = Field(default=None, min_length=2, max_length=128)
    present: bool = True
    new_within_days: int | None = Field(default=None, ge=1, le=365)
    overdue: bool | None = None
    unassigned: bool | None = None
    exclude_severity: list[str] | None = Field(default=None, max_length=16)
    exclude_state: list[str] | None = Field(default=None, max_length=16)
    exclude_scanner: str | None = Field(default=None, max_length=32)
    exclude_assignee: list[FilterValue128] | None = Field(
        default=None, max_length=MAX_FILTER_VALUES
    )
    exclude_image_repo: list[FilterValue512] | None = Field(
        default=None, max_length=MAX_FILTER_VALUES
    )
    exclude_namespace: list[FilterValue256] | None = Field(
        default=None, max_length=MAX_FILTER_VALUES
    )
    exclude_ptype: list[FilterValue64] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    exclude_cve_id: list[FilterValue128] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    exclude_package_name: list[FilterValue512] | None = Field(
        default=None, max_length=MAX_FILTER_VALUES
    )

    @field_validator(*LIST_FILTER_FIELDS, mode="before")
    @classmethod
    def _one_value_as_list(cls, v: Any) -> Any:
        return one_value_as_list(v)

    @model_validator(mode="after")
    def _vex_needs_scanner(self) -> "ExportParams":
        # per-scanner is sacred: a VEX document speaks for ONE scanner (mirrors the M6 inline rule)
        if self.format in ("openvex", "cyclonedx") and self.scanner is None:
            raise ValueError("VEX export requires a scanner filter (per-scanner is sacred)")
        return self

    @model_validator(mode="after")
    def _no_conflicting_filters(self) -> "ExportParams":
        # the pairs Findings refuses with a 422: the search raises on them, so a queued job that
        # held one would fail only when it ran (issue 962)
        for name in type(self).model_fields:
            if not name.startswith("exclude_"):
                continue
            include = name.removeprefix("exclude_")
            if getattr(self, include) is not None and getattr(self, name) is not None:
                raise ValueError(f"{include} and {name} are mutually exclusive")
        if self.assignee is not None and self.unassigned is not None:
            raise ValueError("assignee and unassigned are mutually exclusive")
        return self


class BulkTriageParams(BaseModel):
    """The scheduled-bulk request (slice 5, audit A-Mc): selector + patch, exactly the inline
    bulk-triage shapes. The selector freezes to `target_ids` AT ENQUEUE (never a live selector
    in a queue — D38/H8); the drain applies the frozen set."""

    model_config = ConfigDict(extra="forbid")

    selector: dict[str, Any]  # validated by the route via the inline BulkSelector model
    patch: dict[str, Any]  # validated by the route via BulkPatch, then validate_bulk_patch


class EnqueueReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["export", "bulk_triage"] = "export"
    cluster_id: ClusterId
    run_mode: Literal["now", "offpeak"] = "offpeak"
    params: ExportParams = Field(default_factory=ExportParams)
    bulk_params: BulkTriageParams | None = None  # required iff kind=bulk_triage
    scheduled_for: datetime | None = None
    as_of_t: datetime | None = None  # export at a past T (M8b); the drain reads it via AsOfTQuery

    @model_validator(mode="after")
    def _kind_shapes(self) -> "EnqueueReport":
        if self.kind == "bulk_triage":
            if self.bulk_params is None:
                raise ValueError("bulk_triage requires bulk_params (selector + patch)")
            if self.as_of_t is not None:
                raise ValueError("bulk_triage acts on current state — as_of_t is not applicable")
        elif self.bulk_params is not None:
            raise ValueError("bulk_params is only valid with kind=bulk_triage")
        return self


def new_report_doc(body: EnqueueReport, *, requested_by: str) -> tuple[str, dict[str, Any]]:
    """Build the initial `pending` `system-reports` doc + its id. Pure — no I/O. `expires_at` is
    stamped by the drain at completion (not now — a pending job has no result to expire).
    For `bulk_triage` the route freezes the selector and adds `params["target_ids"]` before
    indexing (frozen at enqueue — the queue never carries a live selector, D38/H8)."""
    report_id = uuid4().hex
    if body.kind == "bulk_triage":
        assert body.bulk_params is not None  # the model validator guarantees the pairing
        params = body.bulk_params.model_dump()
    else:
        params = body.params.model_dump()
    doc: dict[str, Any] = {
        "report_id": report_id,
        "kind": body.kind,
        "status": PENDING,
        "cluster_id": body.cluster_id,
        "requested_by": requested_by,
        "run_mode": body.run_mode,
        "params": params,
        "scheduled_for": body.scheduled_for.isoformat() if body.scheduled_for else None,
        "as_of_t": body.as_of_t.isoformat() if body.as_of_t else None,
        "created_at": datetime.now(UTC).isoformat(),
        "retry_count": 0,
        "schema_version": REPORT_SCHEMA_VERSION,
    }
    return report_id, doc


_PUBLIC_FIELDS = (
    "report_id",
    "kind",
    "status",
    "cluster_id",
    "requested_by",
    "run_mode",
    "created_at",
    "scheduled_for",
    "bytes",
    "chunk_count",
    "expires_at",
    "error",
)


def public_report(doc: dict[str, Any]) -> dict[str, Any]:
    """The status view — never the raw `params` blob, attempt/lease internals, or chunk data."""
    return {k: doc.get(k) for k in _PUBLIC_FIELDS}
