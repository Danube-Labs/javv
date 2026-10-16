#!/usr/bin/env python3
"""Replay made-up scan data as several scans over time (issue 883).

A fresh store holds one scan at one time, so first seen, new in range and resolved never get a
spread. This script makes a seeded set of images and findings and pushes them as `--waves` scans,
spread over `--span-hours` and ending now. Each wave adds findings, leaves some out (the commit
resolves them), brings one back, and adds images. Trivy and Grype report different sets, each in
its own severity casing.

The plan is pure and seeded: the same seed gives the same data. Only the push talks to a backend.
The push writes only to a cluster ID that does not exist yet, so it never adds to a real cluster.

    cd backend && JAVV_REPLAY_PASSWORD=... uv run python ../development/scripts/replay_waves.py \
        --backend http://localhost:8000 [--cluster replay-0001] [--seed 1] [--waves 4]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import random
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

SCANNERS = ("trivy", "grype")
# ingest refuses a scan older than the cluster's staleness period; 3 days is its default
# (`freshness_days`, backend/src/backend/jobs/staleness.py)
MAX_SPAN_HOURS = 72.0

# canonical severity -> the verbatim word each scanner writes (trivy has no "negligible")
_WORDS = {
    "trivy": {
        "critical": "CRITICAL",
        "high": "HIGH",
        "medium": "MEDIUM",
        "low": "LOW",
        "negligible": "LOW",
        "unknown": "UNKNOWN",
    },
    "grype": {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "negligible": "Negligible",
        "unknown": "Unknown",
    },
}
_SEVERITY_WEIGHTS = (
    ("critical", 1),
    ("high", 4),
    ("medium", 6),
    ("low", 4),
    ("negligible", 2),
    ("unknown", 1),
)
_COUNT_COLUMN = {
    "CRITICAL": "crit",
    "Critical": "crit",
    "HIGH": "high",
    "High": "high",
    "MEDIUM": "med",
    "Medium": "med",
    "LOW": "low",
    "Low": "low",
    "Negligible": "negligible",
    "UNKNOWN": "unknown",
    "Unknown": "unknown",
}
_CVSS = {
    "critical": (9.0, 10.0),
    "high": (7.0, 8.9),
    "medium": (4.0, 6.9),
    "low": (0.1, 3.9),
    "negligible": (0.1, 2.0),
    "unknown": None,
}
_PACKAGES = (
    ("openssl", "debian"),
    ("libc6", "debian"),
    ("zlib1g", "debian"),
    ("curl", "debian"),
    ("libxml2", "debian"),
    ("busybox", "alpine"),
    ("golang.org/x/net", "gomod"),
    ("golang.org/x/crypto", "gomod"),
    ("requests", "python-pkg"),
    ("urllib3", "python-pkg"),
    ("lodash", "node-pkg"),
    ("jackson-databind", "jar"),
)
_SERVICES = ("api", "web", "worker", "billing", "search", "auth", "gateway", "reports")
_NAMESPACES = ("default", "shop", "payments", "monitoring", "edge")


@dataclass(frozen=True)
class Finding:
    vuln_id: str
    package_name: str
    package_version: str
    severity: str  # the scanner's verbatim word
    cvss: float | None
    fixable: bool
    fixed_version: str | None
    ptype: str
    epss: float | None
    kev: bool


@dataclass(frozen=True)
class Image:
    digest: str
    ref: str
    namespaces: tuple[str, ...]
    replicas: int


@dataclass(frozen=True)
class Wave:
    index: int
    at: datetime
    # (scanner, image digest) -> what that scanner reports for that image; an empty tuple is a
    # clean scan, which still resolves what the image had before
    scans: dict[tuple[str, str], tuple[Finding, ...]]


@dataclass(frozen=True)
class Plan:
    images: dict[str, Image]
    waves: tuple[Wave, ...]


def _check_limits(images: int, findings: int, waves: int, span_hours: float) -> None:
    if images < 1:
        raise ValueError("the plan needs at least 1 image")
    if findings < 1:
        raise ValueError("the plan needs at least 1 finding for each image")
    if waves < 2:
        raise ValueError("the plan needs at least 2 waves")
    if span_hours <= 0:
        raise ValueError("the span must be more than 0 hours")
    if span_hours >= MAX_SPAN_HOURS:
        raise ValueError(
            "the span must be shorter than 72 hours, the default staleness period: "
            "ingest refuses an older scan"
        )


@dataclass(frozen=True)
class _Candidate:
    """One finding of one image, with the waves it is present in for each scanner."""

    canonical: str
    base: dict[str, Any]
    born: int
    fixed: int | None  # first wave without it, for good
    gap: int | None  # one wave without it, back in the next
    seen_by: tuple[str, ...]

    def present(self, wave: int) -> bool:
        if wave < self.born or wave == self.gap:
            return False
        return self.fixed is None or wave < self.fixed


def _version(rng: random.Random) -> str:
    return f"{rng.randint(1, 3)}.{rng.randint(0, 20)}.{rng.randint(0, 9)}"


def _candidates(rng: random.Random, count: int, waves: int) -> list[_Candidate]:
    out: list[_Candidate] = []
    ids: set[str] = set()
    for j in range(count):
        vuln_id = f"CVE-{2022 + j % 5}-{rng.randint(10000, 89999)}"
        while vuln_id in ids:
            vuln_id = f"CVE-{2022 + j % 5}-{rng.randint(10000, 89999)}"
        ids.add(vuln_id)
        name, ptype = rng.choice(_PACKAGES)
        version = _version(rng)
        canonical = rng.choices(
            [s for s, _ in _SEVERITY_WEIGHTS], [w for _, w in _SEVERITY_WEIGHTS]
        )[0]
        span = _CVSS[canonical]
        fixable = rng.random() < 0.6
        born = 0 if rng.random() < 0.7 else rng.randint(1, waves - 1)
        fixed = None
        if rng.random() < 0.2 and born + 1 <= waves - 1:
            fixed = rng.randint(born + 1, waves - 1)
        gap = None
        if fixed is None and rng.random() < 0.15 and born + 1 <= waves - 2:
            gap = rng.randint(born + 1, waves - 2)
        seen = tuple(
            s for s, p in (("trivy", 0.9), ("grype", 0.85)) if rng.random() < p
        )
        out.append(
            _Candidate(
                canonical=canonical,
                base={
                    "vuln_id": vuln_id,
                    "package_name": name,
                    "package_version": version,
                    "cvss": round(rng.uniform(*span), 1) if span else None,
                    "fixable": fixable,
                    "fixed_version": f"{version}+fix1" if fixable else None,
                    "ptype": ptype,
                    "epss": round(rng.random() * 0.6, 4),
                    "kev": rng.random() < 0.05,
                },
                born=born,
                fixed=fixed,
                gap=gap,
                seen_by=seen or ("trivy",),
            )
        )
    return out


def _finding(c: _Candidate, scanner: str) -> Finding:
    b = c.base
    grype = scanner == "grype"  # EPSS and KEV come from grype only
    return Finding(
        vuln_id=b["vuln_id"],
        package_name=b["package_name"],
        package_version=b["package_version"],
        severity=_WORDS[scanner][c.canonical],
        cvss=b["cvss"],
        fixable=b["fixable"],
        fixed_version=b["fixed_version"],
        ptype=b["ptype"],
        epss=b["epss"] if grype else None,
        kev=b["kev"] if grype else False,
    )


def plan_waves(
    *,
    seed: int,
    images: int,
    findings: int,
    waves: int,
    span_hours: float,
    now: datetime,
) -> Plan:
    """The images, and for each wave its time and what each scanner reports for each image."""
    _check_limits(images, findings, waves, span_hours)
    rng = random.Random(seed)
    times = [
        now - timedelta(hours=span_hours * (waves - 1 - i) / (waves - 1))
        for i in range(waves)
    ]
    stay = max(1, images - images // 4)  # the rest join in a later wave
    imgs: dict[str, Image] = {}
    joins: dict[str, int] = {}
    pools: dict[str, list[_Candidate]] = {}
    for k in range(images):
        digest = "sha256:" + hashlib.sha256(f"replay-{seed}-{k}".encode()).hexdigest()
        imgs[digest] = Image(
            digest=digest,
            ref=f"registry.example/replay/{_SERVICES[k % len(_SERVICES)]}-{k}:{_version(rng)}",
            namespaces=tuple(sorted(rng.sample(_NAMESPACES, rng.randint(1, 2)))),
            replicas=rng.randint(1, 3),
        )
        joins[digest] = 0 if k < stay else rng.randint(1, waves - 1)
        pools[digest] = _candidates(rng, findings, waves)
    planned: list[Wave] = []
    for w, at in enumerate(times):
        scans: dict[tuple[str, str], tuple[Finding, ...]] = {}
        for digest, pool in pools.items():
            if joins[digest] > w:
                continue
            for scanner in SCANNERS:
                scans[(scanner, digest)] = tuple(
                    _finding(c, scanner)
                    for c in pool
                    if scanner in c.seen_by and c.present(w)
                )
        planned.append(Wave(index=w, at=at, scans=scans))
    return Plan(images=imgs, waves=tuple(planned))


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


def build_envelope(
    cluster_id: str,
    scanner: str,
    image: Image,
    rows: tuple[Finding, ...],
    wave: Wave,
    scan_order: int,
    scan_run_id: str,
) -> dict[str, Any]:
    """One schema-4 envelope: what `scanner` reports for `image` in `wave`."""
    counts = dict.fromkeys(("crit", "high", "med", "low", "negligible", "unknown"), 0)
    for f in rows:
        counts[_COUNT_COLUMN[f.severity]] += 1
    return {
        "schema_version": 4,
        "cluster_id": cluster_id,
        "scanner": scanner,
        "image_digest": image.digest,
        "image_ref": image.ref,
        "namespaces": list(image.namespaces),
        "replicas": image.replicas,
        "scan_run_id": scan_run_id,
        "scan_order": scan_order,
        "last_seen_at": wave.at.isoformat(),
        "scanner_version": "replay",
        "scanner_db_version": "replay",
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
        "counts": counts
        | {"total": len(rows), "fixable": sum(f.fixable for f in rows)},
        "findings": [
            {
                "vuln_id": f.vuln_id,
                "package_name": f.package_name,
                "package_version": f.package_version,
                "severity": f.severity,
                "severity_canonical": f.severity.lower(),
                "cvss": f.cvss,
                "fixable": f.fixable,
                "fixed_version": f.fixed_version,
                "epss": f.epss,
                "kev": f.kev,
                "ptype": f.ptype,
            }
            for f in rows
        ],
    }


# --- the push --------------------------------------------------------------------------------


class ReplayRefused(Exception):
    """The replay stopped before it wrote anything."""


class ReplayFailed(Exception):
    """A call failed after the replay started to write."""


_BUSY = (429, 503)  # the backend's flow control: wait and send again


async def _send(
    http: httpx.AsyncClient, method: str, url: str, **kw: Any
) -> httpx.Response:
    for attempt in range(6):
        r = await http.request(method, url, **kw)
        if r.status_code not in _BUSY:
            return r
        await asyncio.sleep(min(float(r.headers.get("retry-after", 2**attempt)), 30.0))
    return r


def _expect(r: httpx.Response, status: int, step: str) -> dict[str, Any]:
    if r.status_code != status:
        title = (
            r.json().get("title", "")
            if r.headers.get("content-type", "").endswith("json")
            else ""
        )
        raise ReplayFailed(f"{step}: HTTP {r.status_code} {title}".rstrip())
    return r.json() if r.content else {}


async def replay(
    http: httpx.AsyncClient,
    plan: Plan,
    *,
    cluster_id: str,
    username: str,
    password: str,
    say: Callable[[str], None],
) -> dict[str, Any]:
    """Push `plan` into a new cluster `cluster_id`: for each wave and scanner, a scan order, one
    envelope for each image, then the inventory commit."""
    r = await _send(
        http, "POST", "/auth/login", json={"username": username, "password": password}
    )
    if r.status_code != 200:
        raise ReplayRefused(f"sign-in failed for {username} (HTTP {r.status_code})")
    if r.json()["user"]["must_change"]:
        raise ReplayRefused(
            f"{username} must change the password first: sign in once in the UI"
        )
    # the session cookie is Secure, so a client on plain http does not send it back by itself
    session = {"cookie": f"javv_session={r.cookies['javv_session']}"}
    http.cookies.clear()

    r = await _send(
        http,
        "GET",
        "/api/v1/clusters",
        params={"include_retired": "true"},
        headers=session,
    )
    known = {c["cluster_id"] for c in _expect(r, 200, "list clusters")["clusters"]}
    if cluster_id in known:
        raise ReplayRefused(
            f"cluster {cluster_id} already exists: the replay writes only to a new cluster. "
            "Use another --cluster."
        )

    tokens: dict[str, dict[str, str]] = {}
    for scanner in SCANNERS:
        r = await _send(
            http,
            "POST",
            "/api/v1/admin/tokens",
            json={"cluster_id": cluster_id, "scanner": scanner},
            headers=session,
        )
        token = _expect(r, 201, f"mint the {scanner} token")["token"]
        tokens[scanner] = {"authorization": f"Bearer {token}"}

    run_tag = uuid.uuid4().hex[:8]
    pushes = committed = 0
    for wave in plan.waves:
        counts: dict[str, int] = {}
        for scanner in SCANNERS:
            auth = tokens[scanner]
            order = _expect(
                await _send(http, "POST", "/api/v1/scan-runs", headers=auth),
                200,
                "scan order",
            )["scan_order"]
            run_id = f"replay-{run_tag}-w{wave.index}-{scanner}"
            images = [(d, rows) for (s, d), rows in wave.scans.items() if s == scanner]
            for digest, rows in images:
                body = build_envelope(
                    cluster_id, scanner, plan.images[digest], rows, wave, order, run_id
                )
                r = await _send(
                    http, "POST", "/api/v1/ingest/scan", json=body, headers=auth
                )
                _expect(
                    r,
                    202,
                    f"push wave {wave.index + 1} {scanner} {plan.images[digest].ref}",
                )
                pushes += 1
            r = await _send(
                http,
                "POST",
                "/api/v1/inventory-runs",
                json={
                    "scan_run_id": run_id,
                    "expected_count": len(images),
                    "started_at": wave.at.isoformat(),
                },
                headers=auth,
            )
            status = _expect(r, 200, f"commit wave {wave.index + 1} {scanner}")[
                "status"
            ]
            if status != "committed":
                raise ReplayFailed(
                    f"wave {wave.index + 1} {scanner}: the inventory run is {status}"
                )
            committed += 1
            counts[scanner] = sum(len(rows) for _, rows in images)
        say(
            f"wave {wave.index + 1}/{len(plan.waves)} at {wave.at:%Y-%m-%d %H:%M} UTC: "
            f"{len({d for _, d in wave.scans})} images, "
            + ", ".join(f"{s} {n} findings" for s, n in counts.items())
        )
    return {"cluster_id": cluster_id, "pushes": pushes, "committed": committed}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--backend",
        required=True,
        help="the backend URL, for example http://localhost:8000",
    )
    ap.add_argument(
        "--username", default="admin", help="an account with can_manage_tokens"
    )
    ap.add_argument(
        "--cluster", default="replay-0001", help="a cluster ID that does not exist yet"
    )
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--images", type=int, default=8)
    ap.add_argument("--findings", type=int, default=40, help="findings for each image")
    ap.add_argument("--waves", type=int, default=4)
    ap.add_argument("--span-hours", type=float, default=60.0)
    args = ap.parse_args(argv)
    password = os.environ.get("JAVV_REPLAY_PASSWORD")
    if not password:
        sys.stderr.write("set JAVV_REPLAY_PASSWORD to the password of --username\n")
        return 2
    try:
        plan = plan_waves(
            seed=args.seed,
            images=args.images,
            findings=args.findings,
            waves=args.waves,
            span_hours=args.span_hours,
            now=datetime.now(UTC),
        )
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    def say(line: str) -> None:
        sys.stdout.write(line + "\n")

    async def run() -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=args.backend, timeout=60.0) as http:
            return await replay(
                http,
                plan,
                cluster_id=args.cluster,
                username=args.username,
                password=password,
                say=say,
            )

    try:
        summary = asyncio.run(run())
    except (ReplayRefused, ReplayFailed, httpx.HTTPError) as exc:
        sys.stderr.write(f"replay stopped: {exc}\n")
        return 1
    say(
        f"done: cluster {summary['cluster_id']}, {summary['pushes']} scans, "
        f"{summary['committed']} inventory runs committed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
