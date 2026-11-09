"""GET /api/v1/findings/top-values (issue 1176, step 2): the Top CVEs board, against real
OpenSearch.

Pins: the store ranks the CVEs by their findings, ties by the CVE; each row keeps the findings
and the severities of each scanner apart; a `scanner` filter ranks by that scanner; the filters
of /findings apply, with the open grid's default of present findings; another cluster's rows
never count; `by` takes only `cve_id`; a past `as_of` is 422 (a now-only read). Seeds keep the
scanners' own severity casing, so the canonical key is the server's, not the test's."""

import uuid
from typing import Any

from os_env import requires_opensearch
from test_findings_route import _seed
from test_findings_route import env as env  # the fixture

pytestmark = requires_opensearch


def _finding(cve: str, scanner: str, severity: str, **over: Any) -> dict[str, Any]:
    return {
        "finding_key": f"fk-{uuid.uuid4().hex[:12]}",
        "cve_id": cve,
        "scanner": scanner,
        "severity": severity,
        "image_digest": f"sha256:{uuid.uuid4().hex[:8]}",
        **over,
    }


def _many(n: int, cve: str, scanner: str, severity: str, **over: Any) -> list[dict[str, Any]]:
    return [_finding(cve, scanner, severity, **over) for _ in range(n)]


async def _top(http: Any, cid: str, **params: Any) -> list[dict[str, Any]]:
    r = await http.get(
        "/api/v1/findings/top-values", params={"cluster_id": cid, "by": "cve_id", **params}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["by"] == "cve_id"
    return body["values"]


async def test_the_store_ranks_the_cves_and_keeps_each_scanner_apart(env) -> None:
    login, client = env
    cid, other = f"c-topv-{uuid.uuid4().hex[:8]}", f"c-topv-{uuid.uuid4().hex[:8]}"
    await _seed(
        client,
        cid,
        _many(3, "CVE-2024-0003", "trivy", "CRITICAL")
        + _many(2, "CVE-2024-0003", "grype", "High")
        + _many(4, "CVE-2024-0001", "grype", "Medium")
        # a tie with CVE-2024-0001 on 4 findings: the CVE breaks it
        + _many(4, "CVE-2024-0002", "trivy", "LOW")
        # findings the scanner no longer reports are not in the board
        + _many(9, "CVE-2024-0009", "trivy", "CRITICAL", present=False),
    )
    await _seed(client, other, _many(50, "CVE-2024-0666", "trivy", "CRITICAL"))
    http = await login()

    rows = await _top(http, cid)
    assert [(r["value"], r["count"]) for r in rows] == [
        ("CVE-2024-0003", 5),
        ("CVE-2024-0001", 4),
        ("CVE-2024-0002", 4),
    ]
    assert rows[0]["count_by_scanner"] == {"trivy": 3, "grype": 2}
    assert rows[0]["severity_by_scanner"] == {"trivy": {"critical": 3}, "grype": {"high": 2}}
    assert rows[1]["severity_by_scanner"] == {"grype": {"medium": 4}}


async def test_a_scanner_filter_ranks_by_that_scanner(env) -> None:
    login, client = env
    cid = f"c-topv-{uuid.uuid4().hex[:8]}"
    await _seed(
        client,
        cid,
        _many(1, "CVE-2024-0100", "trivy", "HIGH")
        + _many(5, "CVE-2024-0100", "grype", "High")
        + _many(3, "CVE-2024-0200", "trivy", "HIGH"),
    )
    http = await login()

    assert [r["value"] for r in await _top(http, cid)] == ["CVE-2024-0100", "CVE-2024-0200"]
    trivy = await _top(http, cid, scanner="trivy")
    assert [(r["value"], r["count"]) for r in trivy] == [("CVE-2024-0200", 3), ("CVE-2024-0100", 1)]
    assert trivy[1]["count_by_scanner"] == {"trivy": 1}  # the grype findings are not in the read


async def test_the_filters_of_findings_apply(env) -> None:
    login, client = env
    cid = f"c-topv-{uuid.uuid4().hex[:8]}"
    await _seed(
        client,
        cid,
        _many(4, "CVE-2024-0300", "trivy", "HIGH", fixable=False)
        + _many(2, "CVE-2024-0400", "trivy", "HIGH", fixable=True, namespaces=["payments"]),
    )
    http = await login()

    assert [r["value"] for r in await _top(http, cid, fixable="true")] == ["CVE-2024-0400"]
    assert [r["value"] for r in await _top(http, cid, exclude_namespace="payments")] == [
        "CVE-2024-0300"
    ]
    # the overdue filter needs the SLA cutoffs of the store, as on /findings/top-images
    r = await http.get(
        "/api/v1/findings/top-values", params={"cluster_id": cid, "by": "cve_id", "overdue": "true"}
    )
    assert r.status_code == 200, r.text


async def test_refusals(env) -> None:
    login, client = env
    cid = f"c-topv-{uuid.uuid4().hex[:8]}"
    await _seed(client, cid, _many(1, "CVE-2024-0500", "trivy", "HIGH"))
    http = await login()
    path = "/api/v1/findings/top-values"

    for params in (
        {"cluster_id": cid},  # no `by`
        {"cluster_id": cid, "by": "assignee"},  # ruled to `cve_id` only (decision D5)
        {"cluster_id": cid, "by": "cve_id", "as_of": "2026-01-01T00:00:00Z"},  # now-only
    ):
        r = await http.get(path, params=params)
        assert r.status_code == 422, (params, r.text)
    assert (await http.get(path, params={"by": "cve_id"})).status_code == 422  # no cluster
