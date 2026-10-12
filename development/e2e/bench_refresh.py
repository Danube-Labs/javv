"""#117 measurement — does the per-envelope `findings` refresh storm at fleet scale?

`services/reconcile.py` forces `indices.refresh("findings")` once per ingest envelope (plus
`refresh:true` on the watermark CAS and the tombstone UBQ). Correct but write-amplifying; this
bench measures it BEFORE M6 puts read load on the same index (measure-first, audit m-2).

Method: synthetic schema-v3 envelopes (no real scanners — this isolates the backend+OpenSearch
ingest path) at BENCH_CLUSTERS x 2 scanners x BENCH_DIGESTS, BENCH_FINDINGS findings each,
pushed with BENCH_CONCURRENCY parallel senders (emulating independent fleet scanners). Two
cycles: cycle 1 = create path, cycle 2 = merge + reconcile path (same digests, new scan run).
Around each cycle it samples `findings/_stats/refresh` (external refresh count + cumulative time)
and reports per-envelope latency percentiles + refresh cost.

PREREQUISITES (same as smoke.sh — this does NOT start them):
  1. OpenSearch up at :9200
  2. Backend:  cd backend && JAVV_ENV=dev JAVV_BOOTSTRAP_ADMIN_USERNAME=admin \
                 JAVV_BOOTSTRAP_ADMIN_PASSWORD=smoke-admin-pw \
                 uv run uvicorn backend.main:app --port 8000
Run:  cd backend && uv run python ../development/e2e/bench_refresh.py
Residue: everything lands under cluster_ids `c-bench-*` (wipe = compose down -v && up -d).
"""

import asyncio
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from typing import Any

import httpx

BACKEND = os.environ.get("BENCH_BACKEND", "http://localhost:8000")
OS_URL = os.environ.get("BENCH_OPENSEARCH", "http://localhost:9200")
ADMIN_PW_INIT = "smoke-admin-pw"
ADMIN_PW = "smoke-admin-rotated-pw"

CLUSTERS = int(os.environ.get("BENCH_CLUSTERS", "5"))
DIGESTS = int(os.environ.get("BENCH_DIGESTS", "50"))
FINDINGS = int(os.environ.get("BENCH_FINDINGS", "30"))
CONCURRENCY = int(os.environ.get("BENCH_CONCURRENCY", "8"))
SCANNERS = ("trivy", "grype")

_SEVERITIES = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
_CANON = ("crit", "high", "med", "low", "negligible", "unknown")


def _findings(digest_i: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows, buckets = [], dict.fromkeys(_CANON, 0)
    fixable = 0
    for i in range(FINDINGS):
        sev = i % len(_SEVERITIES)
        fix = i % 3 == 0
        fixable += fix
        buckets[_CANON[sev]] += 1
        rows.append(
            {
                "vuln_id": f"CVE-2024-{10000 + digest_i * FINDINGS + i}",
                "package_name": f"libbench{i % 7}",
                "package_version": f"1.{i}.0",
                "severity": _SEVERITIES[sev],
                "severity_canonical": _CANON[sev],
                "cvss": round(min(9.9, 1.0 + i * 0.3), 1),
                "fixable": fix,
                "fixed_version": f"1.{i}.1" if fix else None,
                "epss": None,
                "kev": False,
            }
        )
    counts = {**buckets, "total": FINDINGS, "fixable": fixable}
    return rows, counts


def _tuning(scanner: str) -> dict[str, Any]:
    if scanner == "trivy":
        return {
            "scanners": "vuln",
            "ignore_unfixed": False,
            "severities": None,
            "pkg_types": None,
            "timeout": None,
        }
    return {"only_fixed": False, "scope": "squashed", "scan_timeout": 300}


def _envelope(
    cid: str, scanner: str, digest_i: int, run: str, order: int
) -> dict[str, Any]:
    rows, counts = _findings(digest_i)
    return {
        "schema_version": 3,
        "cluster_id": cid,
        "scanner": scanner,
        "image_digest": f"sha256:{'%064x' % (0xBE0C + digest_i)}",
        "image_ref": f"registry.local/bench/app{digest_i}:1.0",
        "namespaces": ["default"],
        "replicas": 1,
        "scan_run_id": run,
        "scan_order": order,
        "last_seen_at": datetime.now(UTC).isoformat(),
        "scanner_version": "bench",
        "scanner_db_version": "bench",
        "scanner_db_built": None,
        "effective_config": {
            "tuning": _tuning(scanner),
            "scope": {
                "include_namespaces": [],
                "ignore_namespaces": [],
                "exclude_images": [],
                "ignore_kinds": [],
            },
        },
        "counts": counts,
        "findings": rows,
    }


async def _refresh_stats(http: httpx.AsyncClient) -> tuple[int, int]:
    r = (await http.get(f"{OS_URL}/findings/_stats/refresh")).json()
    ref = r["indices"]["findings"]["primaries"]["refresh"]
    return ref["external_total"], ref["external_total_time_in_millis"]


def _session_header(r: httpx.Response) -> dict[str, str]:
    # the session cookie is Secure; python's cookiejar won't replay it over http://localhost
    # (curl would) — so carry it explicitly
    return {"cookie": f"javv_session={r.cookies['javv_session']}"}


async def _login(http: httpx.AsyncClient) -> dict[str, str]:
    r = await http.post(
        f"{BACKEND}/auth/login", json={"username": "admin", "password": ADMIN_PW}
    )
    if r.status_code == 200:
        return _session_header(r)
    r = await http.post(
        f"{BACKEND}/auth/login", json={"username": "admin", "password": ADMIN_PW_INIT}
    )
    r.raise_for_status()
    hdr = _session_header(r)
    r = await http.post(
        f"{BACKEND}/auth/password",
        headers=hdr,
        json={"current_password": ADMIN_PW_INIT, "new_password": ADMIN_PW},
    )
    r.raise_for_status()
    # the change revoked the session above; the reply carries its replacement
    return _session_header(r)


async def _scan_order(http: httpx.AsyncClient, token: str) -> int:
    # the scanner's cycle start: ingest refuses an order scan-runs never handed out
    r = await http.post(
        f"{BACKEND}/api/v1/scan-runs", headers={"authorization": f"Bearer {token}"}
    )
    r.raise_for_status()
    return int(r.json()["scan_order"])


async def _cycle(
    http: httpx.AsyncClient, tokens: dict[tuple[str, str], str], run: str
) -> dict[str, Any]:
    jobs = [(cid_scanner, d) for cid_scanner in tokens for d in range(DIGESTS)]
    latencies: list[float] = []
    sem = asyncio.Semaphore(CONCURRENCY)
    orders = {cs: await _scan_order(http, tok) for cs, tok in tokens.items()}

    async def push(cid_scanner: tuple[str, str], digest_i: int) -> None:
        cid, scanner = cid_scanner
        body = _envelope(
            cid, scanner, digest_i, f"{run}-{cid}-{scanner}", orders[cid_scanner]
        )
        async with sem:
            t0 = time.perf_counter()
            r = await http.post(
                f"{BACKEND}/api/v1/ingest/scan",
                json=body,
                headers={"authorization": f"Bearer {tokens[cid_scanner]}"},
            )
            latencies.append(time.perf_counter() - t0)
        if r.status_code != 202:  # ingest ACKs with 202 accepted
            raise RuntimeError(f"ingest failed {r.status_code}: {r.text[:300]}")

    ref0, reft0 = await _refresh_stats(http)
    t0 = time.perf_counter()
    await asyncio.gather(*(push(cs, d) for cs, d in jobs))
    wall = time.perf_counter() - t0
    ref1, reft1 = await _refresh_stats(http)

    lat = sorted(latencies)
    return {
        "envelopes": len(jobs),
        "wall_s": round(wall, 2),
        "envelopes_per_s": round(len(jobs) / wall, 1),
        "lat_p50_ms": round(statistics.median(lat) * 1000, 1),
        "lat_p95_ms": round(lat[int(len(lat) * 0.95)] * 1000, 1),
        "lat_max_ms": round(lat[-1] * 1000, 1),
        "refreshes": ref1 - ref0,
        "refresh_ms_total": reft1 - reft0,
        "refresh_ms_per_envelope": round((reft1 - reft0) / len(jobs), 2),
    }


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as http:
        assert (await http.get(f"{OS_URL}")).status_code == 200, "OpenSearch not up"
        assert (await http.get(f"{BACKEND}/readyz")).status_code == 200, (
            "backend not up"
        )
        hdr = await _login(http)

        tokens: dict[tuple[str, str], str] = {}
        for c in range(CLUSTERS):
            cid = f"c-bench-{c:02d}"
            for scanner in SCANNERS:
                r = await http.post(
                    f"{BACKEND}/api/v1/admin/tokens",
                    headers=hdr,
                    json={"cluster_id": cid, "scanner": scanner},
                )
                r.raise_for_status()
                tokens[(cid, scanner)] = r.json()["token"]

        run = f"bench-{int(time.time())}"
        print(
            f"scale: {CLUSTERS} clusters x {len(SCANNERS)} scanners x {DIGESTS} digests "
            f"x {FINDINGS} findings, concurrency {CONCURRENCY}",
            file=sys.stderr,
        )
        c1 = await _cycle(http, tokens, f"{run}-c1")
        c2 = await _cycle(http, tokens, f"{run}-c2")
        docs = (await http.get(f"{OS_URL}/findings/_count")).json()["count"]
        print(
            json.dumps(
                {
                    "cycle1_create": c1,
                    "cycle2_merge_reconcile": c2,
                    "findings_docs_total": docs,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
