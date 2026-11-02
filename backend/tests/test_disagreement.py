"""Scanner disagreement (M4 slice 3, D5a/D5b, FR-11): per-finding severity `disagree` flags and
the per-image count pair (`trivy_count`/`grype_count`/`count_delta`). Per-scanner is sacred — the
flags mark disagreement, they never merge/sum the scanners; docs stay one-per-scanner. Severity
match key = `(cve_id, package_name)` compared via the D16 canonical buckets (verbatim words with
the same meaning — "HIGH" vs "High" — never disagree). Real OpenSearch for the ingest-path tests."""

import json
from collections import Counter
from pathlib import Path

from backend.models.envelope import IngestEnvelope, canonical_severity
from backend.services.disagreement import severity_flags
from backend.services.ingest import build_docs, ingest_envelope
from os_env import requires_opensearch

GOLDEN = json.loads((Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text())
CLUSTER = GOLDEN["cluster_id"]
GRYPE_TUNING = {"only_fixed": False, "scope": None, "scan_timeout": 300}


def _doc(scanner: str, cve: str, pkg: str, severity: str, key: str) -> dict:
    """A findings-cache doc shape, as severity_flags consumes it."""
    return {
        "finding_key": key,
        "scanner": scanner,
        "cve_id": cve,
        "package_name": pkg,
        "severity": severity,
    }


# --- severity_flags: the pure D5a core --------------------------------------------


def test_cross_scanner_severity_mismatch_flags_both() -> None:
    flags = severity_flags(
        [
            _doc("trivy", "CVE-1", "openssl", "HIGH", "t1"),
            _doc("grype", "CVE-1", "openssl", "Critical", "g1"),
        ]
    )
    assert flags == {"t1": True, "g1": True}


def test_same_canonical_severity_never_disagrees() -> None:
    # verbatim words differ ("HIGH" vs "High") but the D16 canonical bucket is the same
    flags = severity_flags(
        [
            _doc("trivy", "CVE-1", "openssl", "HIGH", "t1"),
            _doc("grype", "CVE-1", "openssl", "High", "g1"),
        ]
    )
    assert flags == {"t1": False, "g1": False}


def test_single_scanner_never_disagrees() -> None:
    flags = severity_flags(
        [
            _doc("trivy", "CVE-1", "openssl", "HIGH", "t1"),
            _doc("trivy", "CVE-2", "zlib", "LOW", "t2"),
        ]
    )
    assert flags == {"t1": False, "t2": False}


def test_different_package_is_not_a_match() -> None:
    # same CVE on different packages = different findings — no comparison (D5a match key)
    flags = severity_flags(
        [
            _doc("trivy", "CVE-1", "openssl", "HIGH", "t1"),
            _doc("grype", "CVE-1", "libssl3", "Critical", "g1"),
        ]
    )
    assert flags == {"t1": False, "g1": False}


# --- ingest path (real OpenSearch) --------------------------------------------------


def _counts(findings: list[dict]) -> dict[str, int]:
    c = Counter(canonical_severity(f["severity"]) for f in findings)
    return {
        "crit": c["critical"],  # D46/#274: full-word canonical keys, short COLUMN names
        "high": c["high"],
        "med": c["medium"],
        "low": c["low"],
        "negligible": c["negligible"],
        "unknown": c["unknown"],
        "total": len(findings),
        "fixable": sum(1 for f in findings if f.get("fixable")),
    }


def _finding(base: dict, *, severity: str) -> dict:
    return {**base, "severity": severity, "severity_canonical": canonical_severity(severity)}


def _env(scanner: str, scan_order: int, run_id: str, findings: list[dict]) -> IngestEnvelope:
    e = {
        **GOLDEN,
        "scanner": scanner,
        "scan_order": scan_order,
        "scan_run_id": run_id,
        "findings": findings,
        "counts": _counts(findings),
    }
    if scanner == "grype":
        e["effective_config"] = {**GOLDEN["effective_config"], "tuning": GRYPE_TUNING}
    return IngestEnvelope.model_validate(e)


def _key(env: IngestEnvelope, position: int) -> str:
    return build_docs(env)["findings"][position]["finding_key"]


async def _row(client, prefix, finding_key) -> dict:
    return (await client.get(index=f"{prefix}findings", id=finding_key))["_source"]


BASE = GOLDEN["findings"][0]  # tar 1.34 — the shared (cve, pkg) both scanners report


@requires_opensearch
async def test_severity_disagreement_flags_both_scanners_docs(real_os) -> None:
    client, prefix = real_os
    trivy = _env("trivy", 1, "t-r1", [_finding(BASE, severity="HIGH"), GOLDEN["findings"][1]])
    grype = _env("grype", 1, "g-r1", [_finding(BASE, severity="Critical")])

    await ingest_envelope(client, trivy, prefix=prefix)
    await ingest_envelope(client, grype, prefix=prefix)

    assert (await _row(client, prefix, _key(trivy, 0)))["disagree"] is True
    assert (await _row(client, prefix, _key(grype, 0)))["disagree"] is True
    # the finding only trivy reports has nothing to disagree with
    assert not (await _row(client, prefix, _key(trivy, 1))).get("disagree")


@requires_opensearch
async def test_flags_clear_when_the_scanners_reconverge(real_os) -> None:
    client, prefix = real_os
    trivy = _env("trivy", 1, "t-r1", [_finding(BASE, severity="HIGH")])
    await ingest_envelope(client, trivy, prefix=prefix)
    await ingest_envelope(
        client, _env("grype", 1, "g-r1", [_finding(BASE, severity="Critical")]), prefix=prefix
    )
    # next grype cycle re-rates it High — agreement restored, both flags must clear
    await ingest_envelope(
        client, grype2 := _env("grype", 2, "g-r2", [_finding(BASE, severity="High")]), prefix=prefix
    )

    assert (await _row(client, prefix, _key(trivy, 0)))["disagree"] is False
    assert (await _row(client, prefix, _key(grype2, 0)))["disagree"] is False


@requires_opensearch
async def test_flag_clears_when_the_other_scanner_drops_the_finding(real_os) -> None:
    client, prefix = real_os
    trivy = _env("trivy", 1, "t-r1", [_finding(BASE, severity="HIGH")])
    await ingest_envelope(client, trivy, prefix=prefix)
    await ingest_envelope(
        client, _env("grype", 1, "g-r1", [_finding(BASE, severity="Critical")]), prefix=prefix
    )
    # grype's next run no longer reports it (fixed per grype) — no counterpart, no disagreement
    await ingest_envelope(client, _env("grype", 2, "g-r2", []), prefix=prefix)

    assert (await _row(client, prefix, _key(trivy, 0)))["disagree"] is False


@requires_opensearch
async def test_image_doc_carries_the_count_pair_once_both_scanners_reported(real_os) -> None:
    client, prefix = real_os
    three, five = GOLDEN["findings"][:3], GOLDEN["findings"][:5]
    await ingest_envelope(client, _env("trivy", 1, "t-r1", three), prefix=prefix)
    await ingest_envelope(client, _env("grype", 1, "g-r1", five), prefix=prefix)
    await client.indices.refresh(index=f"{prefix}javv-images-{CLUSTER}-*")

    hits = (
        await client.search(
            index=f"{prefix}javv-images-{CLUSTER}-*",
            body={"size": 10, "query": {"match_all": {}}},
        )
    )["hits"]["hits"]
    by_run = {h["_source"]["scan_run_id"]: h["_source"] for h in hits}

    # trivy pushed first — no grype data existed yet, so its doc has no pair (single scanner)
    assert "grype_count" not in by_run["t-r1"] and "count_delta" not in by_run["t-r1"]
    # grype's doc compares against trivy's latest committed total (D5b: trivy − grype)
    grype_doc = by_run["g-r1"]
    assert grype_doc["trivy_count"] == 3
    assert grype_doc["grype_count"] == 5
    assert grype_doc["count_delta"] == -2


@requires_opensearch
async def test_the_count_pair_counts_findings_not_report_entries(real_os) -> None:
    # issue 1076: a report lists a finding once for each file that holds the package
    client, prefix = real_os
    three, five = GOLDEN["findings"][:3], GOLDEN["findings"][:5]
    trivy = [*three, three[0], three[0]]  # 5 entries, 3 findings
    grype = [*five, five[1], five[1]]  # 7 entries, 5 findings
    await ingest_envelope(client, _env("trivy", 1, "t-r1", trivy), prefix=prefix)
    await ingest_envelope(client, _env("grype", 1, "g-r1", grype), prefix=prefix)
    await client.indices.refresh(index=f"{prefix}javv-images-{CLUSTER}-*")

    hits = (
        await client.search(
            index=f"{prefix}javv-images-{CLUSTER}-*",
            body={"size": 10, "query": {"term": {"scan_run_id": "g-r1"}}},
        )
    )["hits"]["hits"]
    [grype_doc] = [h["_source"] for h in hits]
    assert grype_doc["trivy_count"] == 3  # the stored total of the trivy run
    assert grype_doc["grype_count"] == 5 and grype_doc["total"] == 5
    assert grype_doc["count_delta"] == -2


@requires_opensearch
async def test_scanners_stay_separate_docs(real_os) -> None:
    # per-scanner sacred: the same (cve, pkg) from two scanners = two findings docs, never one
    client, prefix = real_os
    trivy = _env("trivy", 1, "t-r1", [_finding(BASE, severity="HIGH")])
    grype = _env("grype", 1, "g-r1", [_finding(BASE, severity="Critical")])
    await ingest_envelope(client, trivy, prefix=prefix)
    await ingest_envelope(client, grype, prefix=prefix)

    assert _key(trivy, 0) != _key(grype, 0)
    t_row, g_row = (
        await _row(client, prefix, _key(trivy, 0)),
        await _row(client, prefix, _key(grype, 0)),
    )
    assert t_row["scanner"] == "trivy" and t_row["severity"] == "HIGH"
    assert g_row["scanner"] == "grype" and g_row["severity"] == "Critical"


@requires_opensearch
async def test_recompute_pages_past_the_search_window(real_os, monkeypatch) -> None:
    # task F m-3 (#143): a digest with more findings than one search page must be recomputed
    # completely — page size shrunk to 2 so five findings need three pages
    import backend.services.disagreement as dis

    monkeypatch.setattr(dis, "_SEARCH_PAGE", 2)
    client, prefix = real_os
    extra = [{**BASE, "vuln_id": f"CVE-2026-{9000 + i}", "severity": "Low"} for i in range(3)]
    trivy = _env("trivy", 1, "t-r1", [_finding(BASE, severity="HIGH"), *extra])
    grype = _env("grype", 1, "g-r1", [_finding(BASE, severity="Critical")])

    await ingest_envelope(client, trivy, prefix=prefix)
    await ingest_envelope(client, grype, prefix=prefix)

    # the shared (cve, pkg) disagrees on BOTH sides even though it spans pages
    assert (await _row(client, prefix, _key(trivy, 0)))["disagree"] is True
    assert (await _row(client, prefix, _key(grype, 0)))["disagree"] is True
    for i in range(1, 4):  # the trivy-only rows never disagree
        assert not (await _row(client, prefix, _key(trivy, i))).get("disagree")
