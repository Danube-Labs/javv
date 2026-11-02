"""development/scripts/check-ingest-roundtrip.sh checks a pushed run in the store (issue 631). A
scanner report lists a finding once for each file that holds the package, and JAVV stores and
counts findings (issue 1076). Thus the script compares the stored history rows with the counts of
the stored scan event, and the entries that the scanner sent with `report_entries`."""

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from opensearchpy import AsyncOpenSearch

from backend.core.bootstrap import bootstrap
from backend.models.envelope import IngestEnvelope
from backend.services.ingest import ingest_envelope
from os_env import OS_URL, requires_opensearch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "development" / "scripts" / "check-ingest-roundtrip.sh"
GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())


async def _push_a_run_with_a_repeated_entry(client: AsyncOpenSearch) -> dict[str, Any]:
    """Store one run as the cycle does, and give back the summary that `scanner.compat` writes."""
    cluster, run = f"c-rt-{uuid.uuid4().hex[:8]}", f"rt-{uuid.uuid4().hex[:8]}"
    first, second = GOLDEN["findings"][:2]  # both LOW, not fixable
    counts = dict.fromkeys(("crit", "high", "med", "low", "negligible", "unknown", "fixable"), 0)
    counts |= {"low": 4, "total": 4}
    env = IngestEnvelope.model_validate(
        {
            **GOLDEN,
            "cluster_id": cluster,
            "scan_run_id": run,
            "findings": [first, second, first, first],  # 4 entries, 2 findings
            "counts": counts,
        }
    )
    await bootstrap(client)
    await ingest_envelope(client, env)
    await client.index(
        index=f"javv-inventory-runs-{cluster}-000001",
        body={"inventory_run_id": run, "cluster_id": cluster, "status": "committed"},
        params={"refresh": "true"},
    )
    return {
        "scanner": env.scanner,
        "scanner_version": env.scanner_version,
        "cluster_id": cluster,
        "scan_run_id": run,
        "image_digest": env.image_digest,
        "counts": counts,
        "delivered": True,
        "inventory_committed": True,
    }


def _check(summary: dict[str, Any], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary))
    return subprocess.run(
        ["bash", str(SCRIPT), str(path), OS_URL], capture_output=True, text=True, check=False
    )


@requires_opensearch
async def test_a_run_with_a_repeated_entry_passes_and_names_both_numbers(tmp_path: Path) -> None:
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        summary = await _push_a_run_with_a_repeated_entry(client)
        result = _check(summary, tmp_path)
    finally:
        await client.indices.delete(
            index=f"javv-*-{summary['cluster_id']}-*", params={"ignore_unavailable": "true"}
        )
        await client.close()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 entries" in result.stdout and "2 findings" in result.stdout


@requires_opensearch
async def test_a_lost_entry_fails_the_check(tmp_path: Path) -> None:
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        summary = await _push_a_run_with_a_repeated_entry(client)
        # the scanner sent one entry more than the store recorded
        sent = {**summary, "counts": {**summary["counts"], "low": 5, "total": 5}}
        result = _check(sent, tmp_path)
    finally:
        await client.indices.delete(
            index=f"javv-*-{summary['cluster_id']}-*", params={"ignore_unavailable": "true"}
        )
        await client.close()
    assert result.returncode == 1
    assert "entries: sent 5, stored 4" in result.stdout
