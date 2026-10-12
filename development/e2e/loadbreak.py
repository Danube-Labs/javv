"""#249 gate — load / capture / break: robustness of the whole backend under pressure.

A synthetic-envelope rig (no k3d, no real scanners — that's `smoke.sh`'s job) that drives the LIVE
backend + OpenSearch hard, captures every read surface, and then actively tries to break the app.
Complements the two benches (which measure ONE axis each) and the smoke (which proves pipeline
CORRECTNESS on real scanners). This one proves the app stays UP, accurate, and leak-free when abused.

Phases (`--phase load|capture|break|lifecycle|invariants|all`, default `all`):
  LOAD       flood /api/v1/ingest/scan with mixed v3+v4 envelopes across a synthetic fleet. 429/503
             under pressure are EXPECTED (broker-less flow control) — the pass bar is backoff-and-
             succeed, never a dropped push and never a 500.
  CAPTURE    walk every GET endpoint discovered from /openapi.json (+ /metrics + health), once quiet
             and once WHILE load runs, logging each response body. Runs the whole-surface D46 lint:
             a severity VALUE ever reading crit/med/moderate = FAIL (count COLUMN names exempted).
  BREAK      named abuse cases, each with an expected outcome; any 500 or internals-leak = FAIL.
  LIFECYCLE  index create/delete: bootstrap idempotency (no mapping drift) + (--lifecycle) a real
             rollover+retention sweep on a sacrificial cluster the rig seeds and owns.
  INVARIANTS PIT-leak zero · as-of-T determinism · metrics-move · store vitals · secret-leak grep.

Flags: --chaos-store (pause OpenSearch mid-run — off by default) · --lifecycle (destructive sweep on
the sacrificial cluster — off by default) · LOAD_HEAVY=1 (default: ~250k finding rows, big enough to
provoke 429s on this VM; unset for a gentle run).

PREREQUISITES (this does NOT start them — same as smoke.sh / bench_refresh.py):
  1. OpenSearch up at :9200 (a container named `javv-opensearch` if --chaos-store is used).
  2. Backend:  cd backend && JAVV_ENV=dev JAVV_BOOTSTRAP_ADMIN_USERNAME=admin \
                 JAVV_BOOTSTRAP_ADMIN_PASSWORD=smoke-admin-pw \
                 uv run uvicorn backend.main:app --port 8000 \
                   > development/e2e/logs/backend.log 2>&1
     (the secret-leak grep + log-audit read backend.log, so the pipe is REQUIRED.)
Run:  cd backend && uv run python ../development/e2e/loadbreak.py [--phase ...] [--chaos-store]
Residue: everything lands under cluster_ids `c-load-*` (wipe = compose down -v && up -d).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from backend.core.bootstrap import MAPPING_VERSION, MUTABLE_INDEXES

BACKEND = os.environ.get("LB_BACKEND", "http://localhost:8000")
OS_URL = os.environ.get("LB_OPENSEARCH", "http://localhost:9200")
OS_CONTAINER = os.environ.get("LB_OS_CONTAINER", "javv-opensearch")
ADMIN_PW_INIT = "smoke-admin-pw"
ADMIN_PW = "smoke-admin-rotated-pw"

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
CAPTURE_DIR = LOGS / "api-capture"

HEAVY = os.environ.get("LOAD_HEAVY", "1") != "0"
# heavy: 10 clusters × 2 scanners × 50 digests × 5 cycles × 50 findings ≈ 250k rows, > the 120/min
# per-token rate limit → real 429s. Gentle: a tenth of that, no backpressure.
CLUSTERS = int(os.environ.get("LB_CLUSTERS", "10" if HEAVY else "3"))
DIGESTS = int(os.environ.get("LB_DIGESTS", "50" if HEAVY else "10"))
FINDINGS = int(os.environ.get("LB_FINDINGS", "50" if HEAVY else "20"))
CYCLES = int(os.environ.get("LB_CYCLES", "5" if HEAVY else "2"))
CONCURRENCY = int(os.environ.get("LB_CONCURRENCY", "24" if HEAVY else "8"))
SCANNERS = ("trivy", "grype")

CANON = ("critical", "high", "medium", "low", "negligible", "unknown")
# COUNT_COLUMN shim (D46): the count buckets keep the short names; severity VALUES are full words
COUNT_COLUMN = {"critical": "crit", "medium": "med"}
# v3 scanners emit verbatim severities the normalizer must fold — legacy short/alt tokens included
# on purpose so LOAD exercises the exact rollout window (dual v3/v4 acceptance + D31 heal).
VERBATIM_V3 = ("Critical", "High", "moderate", "Low", "Negligible", "Unknown")
VERBATIM_V4 = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "NEGLIGIBLE", "UNKNOWN")
PTYPES = ("os", "python", "golang", "npm", "gomod")

# a severity VALUE reading as a short/legacy token anywhere in a response = D46 regression. The
# count COLUMN keys (crit/med) are a wire constant — matched only as object keys, never here.
BAD_SEV_VALUE = re.compile(
    r'"(?:severity|severity_canonical)"\s*:\s*"(crit|med|moderate)"', re.IGNORECASE
)


def log_line(name: str, obj: dict[str, Any]) -> None:
    (LOGS / name).open("a").write(json.dumps(obj, default=str) + "\n")


# ── envelope generation ─────────────────────────────────────────────────────────────────────────
def _findings(
    digest_i: int, schema: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    verbatim = VERBATIM_V3 if schema == 3 else VERBATIM_V4
    rows: list[dict[str, Any]] = []
    tally: Counter[str] = Counter()
    fixable = 0
    for i in range(FINDINGS):
        sev = i % len(CANON)
        fix = i % 3 == 0
        fixable += fix
        tally[CANON[sev]] += 1
        row: dict[str, Any] = {
            "vuln_id": f"CVE-2024-{20000 + digest_i * FINDINGS + i}",
            "package_name": f"libload{i % 7}",
            "package_version": f"1.{i}.0",
            "severity": verbatim[
                sev
            ],  # verbatim — the server re-derives the canonical (D16)
            "severity_canonical": CANON[
                sev
            ],  # sent, NOT trusted; full words for realism
            "cvss": round(min(9.9, 1.0 + i * 0.3), 1),
            "fixable": fix,
            "fixed_version": f"1.{i}.1" if fix else None,
            "epss": None,
            "kev": i % 17 == 0,
        }
        if (
            schema == 4
        ):  # v4 adds ptype; v3 findings have none (→ null, D31 heals on a v4 sweep)
            row["ptype"] = PTYPES[i % len(PTYPES)]
        rows.append(row)
    counts = {COUNT_COLUMN.get(s, s): tally.get(s, 0) for s in CANON}
    counts |= {"total": FINDINGS, "fixable": fixable}
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


def envelope(
    cid: str, scanner: str, digest_i: int, run: str, order: int, schema: int
) -> dict[str, Any]:
    rows, counts = _findings(digest_i, schema)
    env: dict[str, Any] = {
        "schema_version": schema,
        "cluster_id": cid,
        "scanner": scanner,
        "image_digest": f"sha256:{'%064x' % (0x10AD + digest_i)}",
        "image_ref": f"registry.local/load/app{digest_i}:1.0",
        "namespaces": ["default", f"ns-{digest_i % 3}"],
        "replicas": 1 + digest_i % 3,
        "scan_run_id": run,
        "scan_order": order,
        "last_seen_at": datetime.now(UTC).isoformat(),
        "scanner_version": "load",
        "scanner_db_version": "load",
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
    return env


# ── auth / store helpers ────────────────────────────────────────────────────────────────────────
def _session_header(r: httpx.Response) -> dict[str, str]:
    # the session cookie is Secure; python's cookiejar won't replay it over http://localhost
    return {"cookie": f"javv_session={r.cookies['javv_session']}"}


async def login(http: httpx.AsyncClient) -> dict[str, str]:
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


async def mint_tokens(
    http: httpx.AsyncClient, hdr: dict[str, str], cids: list[str]
) -> dict[tuple[str, str], str]:
    tokens: dict[tuple[str, str], str] = {}
    for cid in cids:
        for scanner in SCANNERS:
            r = await http.post(
                f"{BACKEND}/api/v1/admin/tokens",
                headers=hdr,
                json={"cluster_id": cid, "scanner": scanner},
            )
            r.raise_for_status()
            tokens[(cid, scanner)] = r.json()["token"]
    return tokens


async def scan_order(http: httpx.AsyncClient, token: str) -> int:
    """The scanner's cycle start: ingest refuses an order scan-runs never handed out."""
    r = await http.post(
        f"{BACKEND}/api/v1/scan-runs", headers={"authorization": f"Bearer {token}"}
    )
    r.raise_for_status()
    return int(r.json()["scan_order"])


async def store_vitals(http: httpx.AsyncClient, phase: str) -> dict[str, Any]:
    """heap %, index count, findings docs, open PITs — the trend line that made the 839-index /
    heap-80% incident invisible until the suite went red. Logged before/after every phase."""
    try:
        heap = (
            await http.get(f"{OS_URL}/_cat/nodes", params={"h": "heap.percent"})
        ).text.split()
        idx = (
            (await http.get(f"{OS_URL}/_cat/indices", params={"h": "index"}))
            .text.strip()
            .splitlines()
        )
        docs = (await http.get(f"{OS_URL}/findings/_count")).json().get("count", -1)
        pits = len(
            (await http.get(f"{OS_URL}/_search/point_in_time/_all"))
            .json()
            .get("pits", [])
        )
    except Exception as exc:  # noqa: BLE001 - vitals are best-effort telemetry, never a hard failure
        return {"phase": phase, "error": str(exc)}
    v = {
        "phase": phase,
        "heap_pct": [int(h) for h in heap if h.isdigit()],
        "index_count": len(idx),
        "findings_docs": docs,
        "open_pits": pits,
        "at": datetime.now(UTC).isoformat(),
    }
    log_line("loadbreak-vitals.jsonl", v)
    return v


# ── phase: LOAD ─────────────────────────────────────────────────────────────────────────────────
async def phase_load(
    http: httpx.AsyncClient, tokens: dict[tuple[str, str], str]
) -> dict[str, Any]:
    """CYCLES of concurrent pushes across the fleet. Mixed v3/v4 (alternating cycles). 429/503 are
    backpressure, not failure; a 5xx other than 503, or any non-2xx/429/503, IS a failure."""
    sem = asyncio.Semaphore(CONCURRENCY)
    status_tally: Counter[int] = Counter()
    latencies: list[float] = []
    failures: list[
        dict[str, Any]
    ] = []  # real errors: 5xx (non-503), connection drops, odd codes
    shed: list[
        dict[str, Any]
    ] = []  # persistent 429/503 after backoff — correct load-shedding

    async def push(
        cid: str, scanner: str, digest_i: int, order: int, schema: int
    ) -> None:
        body = envelope(
            cid, scanner, digest_i, f"load-{cid}-{scanner}-{order}", order, schema
        )
        token = tokens[(cid, scanner)]
        for attempt in range(
            6
        ):  # backoff on backpressure — the only broker-less flow control
            async with sem:
                t0 = time.perf_counter()
                r = await http.post(
                    f"{BACKEND}/api/v1/ingest/scan",
                    json=body,
                    headers={"authorization": f"Bearer {token}"},
                )
                latencies.append(time.perf_counter() - t0)
            status_tally[r.status_code] += 1
            if r.status_code == 202:
                return
            if r.status_code in (
                429,
                503,
            ):  # expected under pressure — back off and retry
                await asyncio.sleep(0.25 * (attempt + 1))
                continue
            failures.append(
                {
                    "cid": cid,
                    "scanner": scanner,
                    "status": r.status_code,
                    "body": r.text[:300],
                }
            )
            return
        # persistent 429/503 after all retries — the rate limiter shedding excess. Under a
        # DELIBERATE overload (250 pushes/token in ~100s vs a 120/min limit) shedding is CORRECT
        # backpressure, not failure: a real scanner CronJob retries next cycle. Reported, not fatal.
        shed.append({"cid": cid, "scanner": scanner, "digest": digest_i})

    # every cycle's order up front, so the flood's 429s never land on an allocation
    orders = {
        cs: [await scan_order(http, tok) for _ in range(CYCLES)]
        for cs, tok in tokens.items()
    }
    t0 = time.perf_counter()
    for c in range(CYCLES):
        schema = 3 if c % 2 == 0 else 4  # interleave the vocabulary/rollout window
        jobs = [
            push(cid, scanner, d, orders[(cid, scanner)][c], schema)
            for (cid, scanner) in tokens
            for d in range(DIGESTS)
        ]
        await asyncio.gather(*jobs)
    wall = time.perf_counter() - t0

    lat = sorted(latencies) or [0.0]
    # the real robustness bar: NO 5xx and NO hard failures under overload. The system must shed
    # (429), never break (500) — and at least some pushes must land (it kept serving, didn't wedge).
    server_errors = sum(
        n for code, n in status_tally.items() if 500 <= code < 600 and code != 503
    )
    accepted = status_tally[202]
    result = {
        "cycles": CYCLES,
        # envelopes_sent = unique envelopes (each terminates exactly one way: accepted / shed /
        # hard-failure). http_attempts includes retries, so status_tally is ATTEMPT-level: a 429
        # there may belong to an envelope that was later accepted — only shed_after_backoff counts
        # envelopes that never landed.
        "envelopes_sent": accepted + len(shed) + len(failures),
        "http_attempts": sum(status_tally.values()),
        "wall_s": round(wall, 1),
        "status_tally": dict(status_tally),
        "accepted_202": accepted,
        "backpressure_429_503": status_tally[429] + status_tally[503],
        "shed_after_backoff": len(shed),
        "server_errors_5xx": server_errors,
        "lat_p50_ms": round(statistics.median(lat) * 1000, 1),
        "lat_p95_ms": round(lat[int(len(lat) * 0.95)] * 1000, 1),
        "lat_max_ms": round(lat[-1] * 1000, 1),
        "hard_failures": failures,
        "verdict": "PASS"
        if (not failures and server_errors == 0 and accepted > 0)
        else "FAIL",
    }
    log_line("loadbreak-load.jsonl", result)
    return result


# ── phase: CAPTURE ──────────────────────────────────────────────────────────────────────────────
def _slug(method: str, path: str) -> str:
    return f"{method.lower()}-{re.sub(r'[^a-zA-Z0-9]+', '_', path).strip('_')}.jsonl"


async def _discover_gets(http: httpx.AsyncClient) -> list[str]:
    """Every GET path from /openapi.json that takes NO required path param — the read surface. By
    deriving from the spec, capture can never drift when M9+ adds routes."""
    spec = (await http.get(f"{BACKEND}/openapi.json")).json()
    paths = []
    for path, ops in spec.get("paths", {}).items():
        if "get" not in ops:
            continue
        if (
            "{" in path
        ):  # skip templated paths — we capture the id-less list/read surface
            continue
        paths.append(path)
    return sorted(paths)


async def phase_capture(
    http: httpx.AsyncClient, hdr: dict[str, str], cid: str, label: str
) -> dict[str, Any]:
    """Walk the read surface, log every response, lint every body for D46 severity leakage."""
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    gets = await _discover_gets(http)
    # params good enough to get a real answer out of the tenant-scoped reads
    q = {"cluster_id": cid, "scanner": "trivy", "size": 20, "days": 30}
    lint_hits: list[dict[str, Any]] = []
    captured = 0
    for path in gets:
        url = f"{BACKEND}{path}"
        try:
            r = await http.get(url, headers=hdr, params=q)
        except Exception as exc:  # noqa: BLE001 - a transport error under load is worth recording
            log_line(
                _slug("get", path), {"label": label, "path": path, "error": str(exc)}
            )
            continue
        body_text = r.text
        rec = {
            "label": label,
            "path": path,
            "status": r.status_code,
            "elapsed_ms": round(r.elapsed.total_seconds() * 1000, 1),
            "bytes": len(body_text),
            "body": body_text[:20000],
        }
        (CAPTURE_DIR / _slug("get", path)).open("a").write(json.dumps(rec) + "\n")
        captured += 1
        if r.status_code == 200 and (m := BAD_SEV_VALUE.findall(body_text)):
            lint_hits.append({"path": path, "tokens": sorted({t.lower() for t in m})})
    # /metrics is text (prometheus), not JSON — captured separately
    metrics = (await http.get(f"{BACKEND}/metrics")).text
    (LOGS / "metrics-capture.txt").open("a").write(
        f"\n##### {label} @ {datetime.now(UTC).isoformat()} #####\n{metrics}"
    )
    result = {
        "label": label,
        "endpoints_captured": captured,
        "d46_lint_hits": lint_hits,
        "verdict": "PASS" if not lint_hits else "FAIL",
    }
    log_line("loadbreak-capture.jsonl", result)
    return result


# ── phase: BREAK ────────────────────────────────────────────────────────────────────────────────
async def phase_break(
    http: httpx.AsyncClient,
    hdr: dict[str, str],
    tokens: dict[tuple[str, str], str],
    cid: str,
) -> dict[str, Any]:
    """Named abuse cases. Each records (name, expected, actual, PASS/FAIL). A 500 anywhere, or an
    internals leak in an error body, is a FAIL."""
    results: list[dict[str, Any]] = []
    # a FRESH cluster+token, not the load-phase fleet: its rate-limit bucket is empty, so setup
    # pushes (esp. the ordering keystone) land as 202 instead of 429'd by leftover load pressure
    bcid = "c-load-break"
    r = await http.post(
        f"{BACKEND}/api/v1/admin/tokens",
        headers=hdr,
        json={"cluster_id": bcid, "scanner": "trivy"},
    )
    r.raise_for_status()
    btoken = r.json()["token"]
    auth = {"authorization": f"Bearer {btoken}"}

    def record(name: str, ok: bool, detail: str) -> None:
        results.append({"name": name, "pass": ok, "detail": detail})

    async def ingest(
        body: Any, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        # headers=None → the valid break token; headers={} → send NO auth header (the no-auth case).
        # (NOT `headers or auth`: an empty dict is falsy, so that would wrongly re-send the token.)
        h = auth if headers is None else headers
        return await http.post(f"{BACKEND}/api/v1/ingest/scan", json=body, headers=h)

    good_order = await scan_order(http, btoken)
    good = envelope(bcid, "trivy", 0, "break-good", good_order, 4)

    # 1. malformed: extra field (extra=forbid), bad type, illegal ptype pattern, bad schema_version
    for name, mutate in [
        ("extra_field", lambda e: {**e, "surprise": 1}),
        ("bad_type_scan_order", lambda e: {**e, "scan_order": "not-an-int"}),
        (
            "illegal_ptype",
            lambda e: {**e, "findings": [{**e["findings"][0], "ptype": "Bad Ptype!"}]},
        ),
        ("bad_schema_version", lambda e: {**e, "schema_version": 2}),
        (
            "missing_required",
            lambda e: {k: v for k, v in e.items() if k != "cluster_id"},
        ),
    ]:
        r = await ingest(mutate(good))
        record(
            f"malformed:{name}",
            r.status_code in (400, 422),
            f"{r.status_code} (expect 422)",
        )

    # 2. oversized: a body past the read cap → 413 (bounded memory, never a 500). The stream is
    # capped at ingest_max_compressed_bytes (10 MiB) BEFORE parse, so ~11 MiB is already over.
    huge = {**good, "image_ref": "x" * (11 * 1024 * 1024)}
    try:
        r = await ingest(huge)
        record("oversized_body", r.status_code == 413, f"{r.status_code} (expect 413)")
    except (
        httpx.HTTPError
    ) as exc:  # server may cut the connection at the cap — fine, not a 500
        record(
            "oversized_body", True, f"connection closed at cap: {type(exc).__name__}"
        )

    # 3. auth: garbage bearer, oversized bearer, no auth → 401 (generic, no existence oracle)
    for name, h in [
        ("garbage_bearer", {"authorization": "Bearer deadbeef"}),
        ("oversized_bearer", {"authorization": "Bearer " + "z" * 600}),
        ("no_auth", {}),
    ]:
        r = await ingest(good, h)
        leak = any(
            k in r.text.lower() for k in ("traceback", "opensearch", "token_hash")
        )
        record(
            f"auth:{name}",
            r.status_code == 401 and not leak,
            f"{r.status_code} (expect 401){' LEAK' if leak else ''}",
        )

    # 4. tenant / scope binding (SEC-3): the break token is scoped to (bcid, trivy). Push VALID
    # envelopes for a different cluster / scanner — they must 403 on the scope check. Inputs
    # must be otherwise-valid or they'd 422 on validation BEFORE reaching authz (a valid-shape cid,
    # and a real grype envelope — not a trivy body with scanner flipped (fails tuning validation).
    other = envelope("c-load-other", "trivy", 0, "break-tenant", good_order, 4)
    r = await ingest(other)
    record("scope:wrong_cluster", r.status_code == 403, f"{r.status_code} (expect 403)")
    r = await ingest(envelope(bcid, "grype", 0, "break-scanner", good_order, 4))
    record("scope:wrong_scanner", r.status_code == 403, f"{r.status_code} (expect 403)")

    # 5. cursor tampering on the read surface: garbage cursor → 422, never a 500
    r = await http.get(
        f"{BACKEND}/api/v1/findings",
        headers=hdr,
        params={"cluster_id": cid, "cursor": "not-a-real-cursor"},
    )
    record(
        "cursor:garbage_findings",
        r.status_code in (400, 422),
        f"{r.status_code} (expect 422)",
    )
    r = await http.get(
        f"{BACKEND}/api/v1/audit",
        headers=hdr,
        params={"cluster_id": cid, "cursor": "@@@tampered@@@"},
    )
    record(
        "cursor:garbage_audit",
        r.status_code in (400, 422),
        f"{r.status_code} (expect 422)",
    )

    # 6. ordering replay (D40 keystone): commit a high scan_order that RETIRES all-but-one finding,
    # then replay a LOWER order re-including them. The stale scan must NOT resurrect — per-digest
    # state can't guard a create, so the watermark does. On the FRESH break token (no load noise),
    # so the setup pushes land; assert each committed (202) before trusting the observable present=.
    d_digest = 7
    # three orders in a row; the first is the stale one, as a delayed cycle's would be
    stale_order, hi, hi2 = [await scan_order(http, btoken) for _ in range(3)]
    full = envelope(bcid, "trivy", d_digest, f"replay-hi-{hi}", hi, 4)
    # keep ONE finding — and rebuild counts to match it (the envelope validates counts vs findings,
    # so a total=1 with the old per-severity tallies would 422 before ever reaching the watermark)
    kept = full["findings"][:1]
    kept_counts = {
        c: 0 for c in ("crit", "high", "med", "low", "negligible", "unknown")
    }
    for f in kept:
        kept_counts[
            COUNT_COLUMN.get(f["severity_canonical"], f["severity_canonical"])
        ] += 1
    kept_counts |= {"total": len(kept), "fixable": sum(1 for f in kept if f["fixable"])}
    shrunk = {
        **full,
        "scan_run_id": f"replay-hi2-{hi2}",
        "scan_order": hi2,
        "findings": kept,
        "counts": kept_counts,
    }
    stale = {
        **full,
        "scan_run_id": f"replay-stale-{stale_order}",
        "scan_order": stale_order,
    }  # old order
    setup = [(await ingest(full)).status_code, (await ingest(shrunk)).status_code]
    r = await ingest(stale)
    await http.post(f"{OS_URL}/findings/_refresh")
    count_body = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"cluster_id": bcid}},
                    {"term": {"scanner": "trivy"}},
                    {"term": {"image_digest": full["image_digest"]}},
                    {"term": {"present": True}},
                ]
            }
        }
    }
    present_after = (
        (await http.post(f"{OS_URL}/findings/_count", json=count_body))
        .json()
        .get("count")
    )
    # only meaningful if the setup actually committed (202,202); else it's an inconclusive test, not
    # a product failure. The watermark must keep present==1 despite the stale replay of all rows.
    setup_ok = setup == [202, 202] and r.status_code == 202
    record(
        "ordering:stale_replay_no_resurrect",
        setup_ok and present_after == 1,
        f"present={present_after} (expect 1 — watermark held); setup={setup} stale={r.status_code}"
        + ("" if setup_ok else " [INCONCLUSIVE: a setup push did not commit]"),
    )

    # 7. CAS hammer: N concurrent renames of ONE cluster → all resolve (200/409/503), final
    # consistent, and a journal row exists. No lost-update, no 500.
    async def rename(n: int) -> int:
        rr = await http.put(
            f"{BACKEND}/api/v1/clusters/{cid}/name",
            headers=hdr,
            json={"cluster_name": f"hammer-{n}"},
        )
        return rr.status_code

    codes = await asyncio.gather(*(rename(n) for n in range(12)))
    clean = all(c in (200, 409, 503) for c in codes)
    record(
        "cas:rename_hammer",
        clean,
        f"codes={sorted(set(codes))} (expect ⊆ {{200,409,503}})",
    )

    verdict = "PASS" if all(x["pass"] for x in results) else "FAIL"
    out = {
        "verdict": verdict,
        "cases": results,
        "failed": [x["name"] for x in results if not x["pass"]],
    }
    log_line("loadbreak-break.jsonl", out)
    return out


# ── phase: LIFECYCLE (index create/delete) ──────────────────────────────────────────────────────
async def phase_lifecycle(
    http: httpx.AsyncClient, hdr: dict[str, str], run_sweep: bool
) -> dict[str, Any]:
    """Bootstrap idempotency (no mapping drift) + optionally a real rollover/retention sweep."""
    # bootstrap converged: every managed index + template reports _meta.version == MAPPING_VERSION,
    # so a re-run is a no-op (bootstrap only touches version < MAPPING_VERSION). Non-mutating proof.
    drift: list[dict[str, Any]] = []
    for name in MUTABLE_INDEXES:
        r = await http.get(f"{OS_URL}/{name}/_mapping")
        if r.status_code != 200:
            drift.append({"index": name, "issue": f"mapping GET {r.status_code}"})
            continue
        body = r.json()
        ver = body.get(name, {}).get("mappings", {}).get("_meta", {}).get("version")
        if ver != MAPPING_VERSION:
            drift.append({"index": name, "version": ver, "expected": MAPPING_VERSION})
    result: dict[str, Any] = {
        "expected_mapping_version": MAPPING_VERSION,
        "bootstrap_idempotent": not drift,
        "drift": drift,
    }

    if run_sweep:
        # a real retention drop on a sacrificial cluster the rig owns. Seed one scan-events index,
        # roll it, then sweep with a zero-day retention: the rolled-off backing index is DROPPED
        # (whole-index, never delete_by_query) while the write index survives. Destructive → gated.
        life_cid = "c-load-life"
        before = (
            (
                await http.get(
                    f"{OS_URL}/_cat/indices/javv-scan-events-{life_cid}-*",
                    params={"h": "index"},
                )
            )
            .text.strip()
            .splitlines()
        )
        # the lifecycle phase runs alone, so blocking the loop holds up nothing
        proc = subprocess.run(  # noqa: ASYNC221
            [sys.executable, "-m", "backend.jobs.lifecycle"],
            env={
                **os.environ,
                "JAVV_OPENSEARCH_URL": OS_URL,
                "JAVV_LIFECYCLE_RETENTION_DAYS": "0",
                "JAVV_LIFECYCLE_CLUSTER": life_cid,
            },
            capture_output=True,
            text=True,
            cwd=str(HERE.parent.parent / "backend"),
            check=False,
        )
        after = (
            (
                await http.get(
                    f"{OS_URL}/_cat/indices/javv-scan-events-{life_cid}-*",
                    params={"h": "index"},
                )
            )
            .text.strip()
            .splitlines()
        )
        result["retention_sweep"] = {
            "cluster": life_cid,
            "indices_before": len(before),
            "indices_after": len(after),
            "job_rc": proc.returncode,
            "job_tail": proc.stderr[-400:],
        }
    result["verdict"] = "PASS" if result["bootstrap_idempotent"] else "FAIL"
    log_line("loadbreak-lifecycle.jsonl", result)
    return result


# ── phase: INVARIANTS ───────────────────────────────────────────────────────────────────────────
async def phase_invariants(
    http: httpx.AsyncClient,
    hdr: dict[str, str],
    cid: str,
    tokens: dict[tuple[str, str], str],
    metrics_before: str,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "pass": ok, "detail": detail})

    # 1. PIT-leak on COMPLETED reads — a read that RUNS TO COMPLETION deletes its PIT in `finally`.
    # NOT a raw "0 PITs" check: a cursor read abandoned mid-walk (the capture opens first-page
    # cursors) legitimately holds its PIT until keep_alive — inherent to pagination, not a leak.
    # Snapshot, drive two completing reads (contributors = a full PIT walk; facets), assert +0.
    async def pit_count() -> int:
        r = await http.get(f"{OS_URL}/_search/point_in_time/_all")
        return len(r.json().get("pits", []))

    before = await pit_count()
    await http.get(
        f"{BACKEND}/api/v1/contributors",
        headers=hdr,
        params={"cluster_id": cid, "days": 30},
    )
    await http.get(
        f"{BACKEND}/api/v1/findings/facets", headers=hdr, params={"cluster_id": cid}
    )
    after = await pit_count()
    add(
        "pit_leak_completed_reads",
        after <= before,
        f"completed reads added {after - before} PIT(s) (before={before} after={after}; "
        f"abandoned-cursor PITs drain at keep_alive)",
    )

    # 2. as-of-T determinism (D28 stability) — the same past T re-read is byte-identical, even after
    # more data lands (httpx encodes the as_of param itself)
    t = datetime.now(UTC).isoformat()
    a = await http.get(
        f"{BACKEND}/api/v1/findings",
        headers=hdr,
        params={"cluster_id": cid, "scanner": "trivy", "size": 50, "as_of": t},
    )
    await http.post(f"{OS_URL}/findings/_refresh")
    b = await http.get(
        f"{BACKEND}/api/v1/findings",
        headers=hdr,
        params={"cluster_id": cid, "scanner": "trivy", "size": 50, "as_of": t},
    )
    a_ids = [d.get("finding_key") for d in a.json().get("data", [])]
    b_ids = [d.get("finding_key") for d in b.json().get("data", [])]
    add(
        "as_of_t_deterministic",
        a.status_code == 200 and a_ids == b_ids,
        f"status={a.status_code} rows={len(a_ids)} identical={a_ids == b_ids}",
    )

    # 3. metrics-move — the ingest counter actually advanced across the run, not just /metrics 200
    def accepted(txt: str) -> float:
        total = 0.0
        for line in txt.splitlines():
            if line.startswith("javv_ingest_accepted_total"):
                total += float(line.rsplit(" ", 1)[-1])
        return total

    after = accepted((await http.get(f"{BACKEND}/metrics")).text)
    before = accepted(metrics_before)
    add("metrics_moved", after > before, f"ingest_accepted {before} -> {after}")

    # 4. secret-leak grep — no token/password material anywhere in backend.log (error paths leak)
    backend_log = LOGS / "backend.log"
    if not backend_log.exists():
        add(
            "secret_leak_grep",
            False,
            "backend.log not found — was the backend piped to it?",
        )
    else:
        text = backend_log.read_text(errors="replace")
        needles = [ADMIN_PW, ADMIN_PW_INIT, *tokens.values()]
        leaks = [n[:8] + "…" for n in needles if n and n in text]
        # a printed password-field value is a hard leak regardless of which secret
        if re.search(r'"password"\s*:\s*"[^"]+"', text):
            leaks.append("password-field-in-log")
        add("secret_leak_grep", not leaks, f"leaks={leaks or 'none'}")

    verdict = "PASS" if all(c["pass"] for c in checks) else "FAIL"
    out = {"verdict": verdict, "checks": checks}
    log_line("loadbreak-invariants.jsonl", out)
    return out


# ── chaos (flag-gated) ──────────────────────────────────────────────────────────────────────────
async def chaos_store(
    http: httpx.AsyncClient,
    tokens: dict[tuple[str, str], str],
    cid: str,
) -> dict[str, Any]:
    """Pause OpenSearch mid-flight → the backend must 503 without internals and /readyz degrade;
    unpause → recovery WITHOUT a backend restart. The #249 'chaos of the real deployment'."""

    def docker(*args: str) -> int:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, check=False
        ).returncode

    result: dict[str, Any] = {}
    order = await scan_order(http, tokens[(cid, "trivy")])  # before the store goes away
    if docker("pause", OS_CONTAINER) != 0:
        return {"verdict": "SKIP", "detail": f"could not pause {OS_CONTAINER}"}
    try:
        await asyncio.sleep(1.0)
        ready = (await http.get(f"{BACKEND}/readyz")).status_code
        ing = await http.post(
            f"{BACKEND}/api/v1/ingest/scan",
            json=envelope(cid, "trivy", 0, "chaos", order, 4),
            headers={"authorization": f"Bearer {tokens[(cid, 'trivy')]}"},
        )
        leak = any(
            k in ing.text.lower()
            for k in ("traceback", "connectionerror", "opensearch")
        )
        result["during_pause"] = {
            "readyz": ready,
            "ingest": ing.status_code,
            "leak": leak,
        }
    finally:
        docker("unpause", OS_CONTAINER)
    # recovery WITHOUT restart — poll readyz back to green
    recovered = False
    for _ in range(30):
        if (await http.get(f"{BACKEND}/readyz")).status_code == 200:
            recovered = True
            break
        await asyncio.sleep(1.0)
    dp = result.get("during_pause", {})
    ok = (
        dp.get("readyz") != 200
        and dp.get("ingest") == 503
        and not dp.get("leak")
        and recovered
    )
    result["recovered_without_restart"] = recovered
    result["verdict"] = "PASS" if ok else "FAIL"
    log_line("loadbreak-chaos.jsonl", result)
    return result


# ── orchestration ───────────────────────────────────────────────────────────────────────────────
def write_summary(sections: dict[str, Any]) -> None:
    lines = [
        f"# loadbreak run — {datetime.now(UTC).isoformat()}",
        (
            f"\nscale: heavy={HEAVY} · {CLUSTERS} clusters × {len(SCANNERS)} scanners × "
            f"{DIGESTS} digests × {CYCLES} cycles × {FINDINGS} findings · "
            f"concurrency {CONCURRENCY}\n"
        ),
    ]
    for name, sec in sections.items():
        verdict = sec.get("verdict", "n/a") if isinstance(sec, dict) else "n/a"
        lines.append(f"## {name}: {verdict}")
        lines.append("```json")
        lines.append(json.dumps(sec, indent=2, default=str)[:4000])
        lines.append("```\n")
    (LOGS / "loadbreak-summary.md").write_text("\n".join(lines))


async def run(args: argparse.Namespace) -> int:
    LOGS.mkdir(exist_ok=True)
    phases = (
        {"load", "capture", "break", "lifecycle", "invariants"}
        if args.phase == "all"
        else {args.phase}
    )
    async with httpx.AsyncClient(timeout=90.0) as http:
        assert (await http.get(f"{OS_URL}")).status_code == 200, "OpenSearch not up"
        assert (await http.get(f"{BACKEND}/readyz")).status_code == 200, (
            "backend not up"
        )
        hdr = await login(http)
        cids = [f"c-load-{i:02d}" for i in range(CLUSTERS)]
        cid0 = cids[0]
        tokens = await mint_tokens(http, hdr, cids)
        metrics_before = (await http.get(f"{BACKEND}/metrics")).text

        sections: dict[str, Any] = {}
        await store_vitals(http, "start")

        if "load" in phases or "capture" in phases:
            # capture-under-load: run a capture pass concurrently with the flood, then a quiet one
            load_task = (
                asyncio.create_task(phase_load(http, tokens))
                if "load" in phases
                else None
            )
            if "capture" in phases and load_task is not None:
                await asyncio.sleep(0.5)  # let the flood ramp
                sections["capture_under_load"] = await phase_capture(
                    http, hdr, cid0, "under_load"
                )
            if load_task is not None:
                sections["load"] = await load_task
                await store_vitals(http, "post_load")
            if "capture" in phases:
                sections["capture_quiet"] = await phase_capture(
                    http, hdr, cid0, "quiet"
                )

        if "break" in phases:
            sections["break"] = await phase_break(http, hdr, tokens, cid0)
            await store_vitals(http, "post_break")

        if "lifecycle" in phases:
            sections["lifecycle"] = await phase_lifecycle(
                http, hdr, run_sweep=args.lifecycle
            )

        if args.chaos_store:
            sections["chaos_store"] = await chaos_store(http, tokens, cid0)

        if "invariants" in phases:
            sections["invariants"] = await phase_invariants(
                http, hdr, cid0, tokens, metrics_before
            )
            await store_vitals(http, "end")

        write_summary(sections)

    failed = [
        n
        for n, s in sections.items()
        if isinstance(s, dict) and s.get("verdict") == "FAIL"
    ]
    print(
        json.dumps(
            {
                "sections": {
                    n: s.get("verdict")
                    for n, s in sections.items()
                    if isinstance(s, dict)
                },
                "failed": failed,
                "summary": str(LOGS / "loadbreak-summary.md"),
            },
            indent=2,
        )
    )
    return 1 if failed else 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="JAVV load / capture / break rig (#249 gate)"
    )
    ap.add_argument(
        "--phase",
        default="all",
        choices=["all", "load", "capture", "break", "lifecycle", "invariants"],
    )
    ap.add_argument(
        "--chaos-store",
        action="store_true",
        help=f"pause/unpause the OpenSearch container ({OS_CONTAINER}) mid-run",
    )
    ap.add_argument(
        "--lifecycle",
        action="store_true",
        help="run the DESTRUCTIVE retention sweep on the sacrificial c-load-life clr",
    )
    sys.exit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()
