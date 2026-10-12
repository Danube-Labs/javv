"""Inventory commit, scanner side (M8a slice 2, D39/H4-r2). At cycle END the scanner certifies
its run: "I scanned `expected_count` images; every envelope has been pushed." The backend
counts what actually landed and writes the manifest — `committed` only when complete.

Best-effort, unlike the fail-CLOSED cycle-start calls (scope/scan_order): by commit time every
envelope is already pushed, so a failed commit loses nothing — the run just stays uncertified and
inventory reads fall back to the prior committed run (+ the staleness banner). Log and move on. A
transient failure is retried while the cycle's retry budget lasts (issue 832: a store restart
that the pushes outlasted would otherwise still leave the run uncertified)."""

from datetime import datetime

import httpx
import structlog

from scanner.push import RetryBudget, send_with_retries

log = structlog.get_logger()


def commit_inventory(
    http: httpx.Client,
    *,
    token: str | None,
    scan_run_id: str,
    expected_count: int,
    started_at: datetime,
    budget: RetryBudget,
) -> bool:
    """Certify the cycle's inventory. True when the backend answered `status=committed`."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = {
        "scan_run_id": scan_run_id,
        "expected_count": expected_count,
        "started_at": started_at.isoformat(),
    }
    try:
        resp, _ = send_with_retries(
            lambda: http.post("/api/v1/inventory-runs", headers=headers, json=body), budget=budget
        )
        if resp is None:
            raise httpx.TransportError("no answer from the backend")
        resp.raise_for_status()
        manifest = resp.json()
    except Exception:
        log.warning("inventory commit failed — run stays uncertified", exc_info=True)
        return False
    committed = manifest.get("status") == "committed"
    if not committed:
        # expected vs written mismatch: a scanned image never landed (a dead-lettered push)
        log.warning(
            "inventory run partial — not readable as live inventory",
            expected=manifest.get("expected_count"),
            written=manifest.get("written_count"),
        )
    return committed
