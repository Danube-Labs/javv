"""POST /api/v1/inventory-runs (M8a slice 2, D39/H4-r2) — the scanner certifies its cycle's
inventory at cycle END: "these `expected_count` scanned images should all have landed."
The backend counts what actually landed (never trusting a client-reported written count),
allocates `inventory_order`, and writes the immutable manifest — `committed` iff complete.

Token-authenticated with the same SEC-3 binding as ingest/scan-runs: the manifest is always for
the token's own `cluster_id`. Best-effort on the scanner side — a failed commit just leaves the
run uncertified (reads fall back to the prior committed run + the staleness banner)."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.core.auth import require_token
from backend.snapshots.inventory_runs import commit_inventory_run

router = APIRouter(prefix="/api/v1", tags=["inventory-runs"])


class CommitInventoryRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_run_id: str = Field(min_length=1, max_length=128)  # = the cycle's inventory_run_id
    expected_count: int = Field(ge=0, le=1_000_000)  # images scanned this cycle
    started_at: AwareDatetime  # the contract: every time carries a zone


@router.post("/inventory-runs")
async def commit_inventory(
    request: Request,
    body: CommitInventoryRun,
    token: Annotated[dict[str, Any], Depends(require_token)],
) -> dict[str, Any]:
    client = cast(Any, request.app.state.opensearch)
    return await commit_inventory_run(
        client,
        token["cluster_id"],  # SEC-3: always the token's own cluster, never a payload value
        body.scan_run_id,
        expected_count=body.expected_count,
        started_at=body.started_at,
    )
