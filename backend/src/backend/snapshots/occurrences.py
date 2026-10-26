"""Per-scan snapshot rows (M8a/FR-5b) — the immutable point-in-time scanner facts.

One row per finding per scan, appended to `javv-finding-occurrences-<cluster_id>-*` BEFORE the
scan-events catalog doc commits (D39 commit-then-cache: a snapshot the catalog never certified is
unreachable, never half-read). `_id = hash(scan_run_id + finding_key)` so an idempotent envelope
replay (D18) writes no duplicates. Rows are built FROM `build_docs` output, never re-derived from
the envelope — `finding_key`/`commit_key` stay identical to the cache path by construction.

No `severity_rank` here (OE-5/D38: as-of-T severity sort uses a fixed order map) and no state —
absence in a later snapshot IS resolution (no close events). A clean scan writes zero rows; the
catalog doc alone certifies it (R-CATALOG reads it as clean, not as the prior snapshot).
"""

import hashlib
from typing import Any

OCCURRENCES_SERIES = "javv-finding-occurrences"

# the INDEX-MAP row shape — kept explicit so drift from the spec fails a test, not a reader
_ROW_FIELDS = (
    "@timestamp",
    "ingested_at",
    "scan_run_id",
    "scan_order",
    "commit_key",
    "cluster_id",
    "scanner",
    "image_digest",
    "namespaces",
    "vuln_id",
    "package_name",
    "package_version",
    "finding_key",
    "severity",
    "severity_canonical",
    "cvss",
    "fixable",
    "fixed_version",
    "ptype",
    "kev",
    "schema_version",
)


def occurrence_id(scan_run_id: str, finding_key: str) -> str:
    """Idempotent row identity (D18): same run + same finding → same `_id`, always."""
    return hashlib.sha256("|".join((scan_run_id, finding_key)).encode()).hexdigest()


def build_occurrence_rows(docs: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(row_id, row) pairs from one envelope's `build_docs` output. Pure — no I/O.

    Sourcing from the built findings docs (not the raw envelope) is deliberate: `finding_key`,
    `commit_key` and the server-stamped `ingested_at` are computed once in `services.ingest` and
    reused verbatim, so the history row and the cache row can never disagree on identity."""
    ingested_at = docs["scan_event"]["ingested_at"]
    rows: list[tuple[str, dict[str, Any]]] = []
    for f in docs["findings"]:
        row = {
            "@timestamp": f["last_seen_at"],  # scan time — display only, never the ordering key
            "ingested_at": ingested_at,  # server-stamped — the retention age basis (task F m-4)
            "scan_run_id": f["last_scan_run_id"],
            "scan_order": f["last_scan_order"],  # the ordering key (D40/C-r3)
            "commit_key": docs["commit_key"],  # exact-tuple membership for the symmetric query
            "cluster_id": f["cluster_id"],
            "scanner": f["scanner"],
            "image_digest": f["image_digest"],
            "namespaces": f["namespaces"],
            "vuln_id": f["cve_id"],  # CVE pivot (= cve_id elsewhere)
            "package_name": f["package_name"],
            "package_version": f["installed_version"],
            "finding_key": f["finding_key"],
            "severity": f["severity"],  # as-of-then, verbatim (D16) — evidence/display
            "severity_canonical": f["severity_canonical"],  # the query key (D46/#274)
            "cvss": f["cvss"],
            "fixable": f["fixable"],
            "fixed_version": f["fixed_version"],
            "ptype": f["ptype"],  # M8d/B-1: as-of-then package type; null on v3-era rows
            # issue 1000: as-of-then — a past-time read gives a KEV finding the KEV deadline
            "kev": f["kev"],
            "schema_version": f["schema_version"],
        }
        assert tuple(row) == _ROW_FIELDS  # spec drift guard — INDEX-MAP is the row contract
        rows.append((occurrence_id(f["last_scan_run_id"], f["finding_key"]), row))
    return rows
