#!/usr/bin/env python3
"""Scan the running Docker images of a Nomad cluster with Trivy or Grype, and push them to JAVV.

It reads the running allocations from the Nomad API, scans each image, takes the digest from the
scanner output and pushes one scan cycle (INGEST-CONTRACT page). It needs no Docker access.

  JAVV_BACKEND_URL=https://javv.example JAVV_TOKEN=… JAVV_CLUSTER_ID=nomad-prod-01 \\
  JAVV_SCANNER=trivy NOMAD_ADDR=http://127.0.0.1:4646 NOMAD_TOKEN=… python3 javv_nomad_push.py

The settings: README.md in this folder.

The place of an image (the `namespaces` field) is the Nomad job ID for a job in the namespace
`default`, else `<namespace>/<job ID>`. A periodic or dispatched job counts as its parent job.
The job that runs this script skips itself. Python 3.11 or later, standard library only.
"""

import datetime as dt
import fnmatch
import gzip
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

log = logging.getLogger("javv-nomad")

SEV = {
    "critical": "crit",
    "crit": "crit",
    "high": "high",
    "medium": "med",
    "med": "med",
    "moderate": "med",
    "low": "low",
    "negligible": "negligible",
}
TRUE = {"1", "true", "yes", "on"}
TRIVY_SCANNERS = ("vuln", "misconfig", "secret", "license")
TRIVY_SEVERITIES = ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL")
TRIVY_PKG_TYPES = ("os", "library")
GRYPE_SCOPES = ("squashed", "all-layers", "deep-squashed")
GO_DURATION = re.compile(r"^([0-9]+(\.[0-9]+)?(ns|us|µs|ms|s|m|h))+$")


class SettingError(Exception):
    pass


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or default


def required(name: str) -> str:
    value = env(name)
    if not value:
        raise SettingError(f"{name} is required")
    return value


def flag(name: str) -> bool:
    return (env(name) or "").lower() in TRUE


def csv(name: str) -> list[str]:
    return [p.strip() for p in (env(name) or "").split(",") if p.strip()]


def choices(name: str, allowed: tuple[str, ...], upper: bool = False) -> str | None:
    raw = env(name)
    if raw is None:
        return None
    parts = [
        p.strip().upper() if upper else p.strip().lower()
        for p in raw.split(",")
        if p.strip()
    ]
    bad = [p for p in parts if p not in allowed]
    if bad or not parts:
        raise SettingError(
            f"{name}={raw!r}: use values from {list(allowed)}, separated by commas"
        )
    return ",".join(parts)


def positive_int(name: str, default: int) -> int:
    raw = env(name)
    if raw is None:
        return default
    if not raw.isdigit() or int(raw) <= 0:
        raise SettingError(f"{name}={raw!r}: use whole seconds, more than 0")
    return int(raw)


class Settings:
    def __init__(self) -> None:
        self.javv = required("JAVV_BACKEND_URL").rstrip("/")
        self.token = required("JAVV_TOKEN")
        self.cluster = required("JAVV_CLUSTER_ID")
        self.scanner = required("JAVV_SCANNER")
        if self.scanner not in ("trivy", "grype"):
            raise SettingError(f"JAVV_SCANNER={self.scanner!r}: use trivy or grype")
        self.nomad = env("NOMAD_ADDR", "http://127.0.0.1:4646").rstrip("/")
        self.nomad_token = env("NOMAD_TOKEN", "")
        self.namespaces = csv("JAVV_NOMAD_NAMESPACES") or ["*"]
        self.skip_jobs = csv("JAVV_NOMAD_SKIP_JOBS")
        # the job that runs this script: a periodic run has its own ID, the parent is the job
        self.self_job = env("NOMAD_JOB_PARENT_ID") or env("NOMAD_JOB_ID")
        self.dry_run = flag("JAVV_DRY_RUN")
        self.retry_budget = positive_int("JAVV_PUSH_RETRY_BUDGET_SECONDS", 360)
        if self.scanner == "trivy":
            timeout = env("JAVV_TRIVY_TIMEOUT")
            if timeout and not GO_DURATION.match(timeout):
                raise SettingError(
                    f"JAVV_TRIVY_TIMEOUT={timeout!r}: use a duration, for example 10m"
                )
            self.tuning = {
                "scanners": choices("JAVV_TRIVY_SCANNERS", TRIVY_SCANNERS) or "vuln",
                "ignore_unfixed": flag("JAVV_TRIVY_IGNORE_UNFIXED"),
                "severities": choices(
                    "JAVV_TRIVY_SEVERITIES", TRIVY_SEVERITIES, upper=True
                ),
                "pkg_types": choices("JAVV_TRIVY_PKG_TYPES", TRIVY_PKG_TYPES),
                "timeout": timeout,
            }
        else:
            self.tuning = {
                "only_fixed": flag("JAVV_GRYPE_ONLY_FIXED"),
                "scope": choices("JAVV_GRYPE_SCOPE", GRYPE_SCOPES),
                "scan_timeout": positive_int("JAVV_GRYPE_SCAN_TIMEOUT", 600),
            }


def now() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class Javv:
    """The calls to JAVV. Sends again after 429, 503 or no reply, until the retry budget ends."""

    def __init__(self, s: Settings) -> None:
        self.s = s

    def call(self, method: str, path: str, body=None, gz: bool = False):
        data, headers = None, {"Authorization": f"Bearer {self.s.token}"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
            if gz:  # only the push of an envelope accepts a compressed body
                data = gzip.compress(data)
                headers["Content-Encoding"] = "gzip"
        deadline, wait = time.monotonic() + self.s.retry_budget, 2.0
        while True:
            req = urllib.request.Request(
                self.s.javv + path, data=data, headers=headers, method=method
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.status, json.loads(r.read() or b"null")
            except urllib.error.HTTPError as e:
                if e.code not in (429, 503):
                    return e.code, json.loads(e.read() or b"null")
                reason = f"HTTP {e.code}"
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                reason = str(getattr(e, "reason", e))
            if time.monotonic() + wait > deadline:
                return None, {
                    "error": f"no answer in {self.s.retry_budget} s: {reason}"
                }
            log.warning(
                "JAVV did not accept %s %s (%s); again in %.0f s",
                method,
                path,
                reason,
                wait,
            )
            time.sleep(wait)
            wait = min(wait * 2, 60)


def nomad_get(s: Settings, path: str):
    req = urllib.request.Request(
        s.nomad + path, headers={"X-Nomad-Token": s.nomad_token}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def match(value: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(value, p) for p in patterns)


def running_images(s: Settings, scope: dict):
    """{image ref: {places, replicas}} of the running docker tasks that the settings and the scope
    allow, and what they skipped."""
    out: dict[str, dict] = {}
    skipped = {"job": set(), "namespace": set(), "kind": set(), "image": set()}
    allocs = []
    for ns in s.namespaces:
        allocs += nomad_get(s, f"/v1/allocations?namespace={urllib.parse.quote(ns)}")
    seen = set()
    for a in allocs:
        if a["ClientStatus"] != "running" or a["ID"] in seen:
            continue
        seen.add(a["ID"])
        alloc = nomad_get(
            s,
            f"/v1/allocation/{a['ID']}?namespace={urllib.parse.quote(a['Namespace'])}",
        )
        job = alloc["Job"].get("ParentID") or a["JobID"]
        if job == s.self_job:
            continue
        if match(job, s.skip_jobs):
            skipped["job"].add(job)
            continue
        place = job if a["Namespace"] == "default" else f"{a['Namespace']}/{job}"
        include, ignore = (
            scope.get("include_namespaces") or [],
            scope.get("ignore_namespaces") or [],
        )
        if (include and not match(place, include)) or match(place, ignore):
            skipped["namespace"].add(place)
            continue
        if alloc["Job"]["Type"] in (scope.get("ignore_kinds") or []):
            skipped["kind"].add(place)
            continue
        group = next(
            g for g in alloc["Job"]["TaskGroups"] if g["Name"] == alloc["TaskGroup"]
        )
        for task in group["Tasks"]:
            state = (alloc.get("TaskStates") or {}).get(task["Name"], {})
            if task["Driver"] != "docker" or state.get("State") != "running":
                continue
            ref = task["Config"]["image"]
            if match(ref, scope.get("exclude_images") or []):
                skipped["image"].add(ref)
                continue
            e = out.setdefault(ref, {"places": set(), "replicas": 0})
            e["places"].add(place)
            e["replicas"] += 1
    return out, {k: sorted(v) for k, v in skipped.items() if v}


def repo_digest(ref_digests: list[str]) -> str | None:
    return ref_digests[0].split("@", 1)[1] if ref_digests else None


def run(cmd: list[str], timeout: int | None = None) -> dict:
    return json.loads(
        subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=timeout
        ).stdout
    )


def scan_trivy(s: Settings, ref: str):
    t = s.tuning
    cmd = ["trivy", "image", "--quiet", "--format", "json", "--scanners", t["scanners"]]
    if t["ignore_unfixed"]:
        cmd.append("--ignore-unfixed")
    for opt, key in (
        ("--severity", "severities"),
        ("--pkg-types", "pkg_types"),
        ("--timeout", "timeout"),
    ):
        if t[key]:
            cmd += [opt, t[key]]
    rep = run(cmd + [ref])
    findings = []
    for res in rep.get("Results") or []:
        ptype = (
            "os"
            if res.get("Class") == "os-pkgs"
            else (res.get("Type") or "").lower() or None
        )
        for v in res.get("Vulnerabilities") or []:
            if not v.get("VulnerabilityID") or not v.get("PkgName"):
                continue
            cvss = list((v.get("CVSS") or {}).values())
            scores = [c["V3Score"] for c in cvss if c.get("V3Score")] or [
                c["V2Score"] for c in cvss if c.get("V2Score")
            ]
            findings.append(
                {
                    "vuln_id": v["VulnerabilityID"],
                    "package_name": v["PkgName"],
                    "package_version": v.get("InstalledVersion") or "",
                    "severity": v.get("Severity") or "",
                    "severity_canonical": (v.get("Severity") or "").lower(),
                    "cvss": max(scores) if scores else None,
                    "fixable": bool(v.get("FixedVersion")),
                    "fixed_version": v.get("FixedVersion") or None,
                    "epss": None,
                    "kev": False,
                    "ptype": ptype,
                }
            )
    ver = run(["trivy", "version", "--format", "json"])
    db = ver.get("VulnerabilityDB") or {}
    digest = repo_digest((rep.get("Metadata") or {}).get("RepoDigests") or [])
    return (
        digest,
        findings,
        ver.get("Version"),
        str(db["Version"]) if "Version" in db else None,
        db.get("UpdatedAt"),
    )


def scan_grype(s: Settings, ref: str):
    t = s.tuning
    cmd = ["grype", f"registry:{ref}", "-o", "json"]
    if t["only_fixed"]:
        cmd.append("--only-fixed")
    if t["scope"]:
        cmd += ["--scope", t["scope"]]
    rep = run(cmd, timeout=t["scan_timeout"])
    findings = []
    for m in rep.get("matches") or []:
        vul, art = m["vulnerability"], m["artifact"]
        if not vul.get("id") or not art.get("name"):
            continue
        fix = vul.get("fix") or {}
        scores = [
            c["metrics"]["baseScore"]
            for c in vul.get("cvss") or []
            if (c.get("metrics") or {}).get("baseScore") is not None
        ]
        epss = vul.get("epss") or []
        findings.append(
            {
                "vuln_id": vul["id"],
                "package_name": art["name"],
                "package_version": art.get("version") or "",
                "severity": vul.get("severity") or "",
                "severity_canonical": (vul.get("severity") or "").lower(),
                "cvss": max(scores) if scores else None,
                "fixable": fix.get("state") == "fixed" or bool(fix.get("versions")),
                "fixed_version": (fix.get("versions") or [None])[0],
                "epss": epss[0]["epss"] if epss else None,
                "kev": bool(vul.get("knownExploited")),
                "ptype": (art.get("type") or "").lower() or None,
            }
        )
    d = rep.get("descriptor") or {}
    st = (d.get("db") or {}).get("status") or {}
    target = (rep.get("source") or {}).get("target") or {}
    digest = repo_digest(target.get("repoDigests") or []) or target.get(
        "manifestDigest"
    )
    return (
        digest,
        findings,
        d.get("version"),
        str(st["schemaVersion"]) if "schemaVersion" in st else None,
        st.get("built"),
    )


def expected_count(scanned: int, found: int) -> int:
    """As the JAVV scanners: count each scanned image, also a refused push, so that lost data leaves
    the cycle partial. If no image scanned (no registry, a broken scanner), keep the count of the
    images found: the cycle stays partial and JAVV keeps the last good inventory."""
    return scanned if scanned else found


def counts(findings):
    c = {"crit": 0, "high": 0, "med": 0, "low": 0, "negligible": 0, "unknown": 0}
    for f in findings:
        c[SEV.get(f["severity"].lower(), "unknown")] += 1
    c["total"] = len(findings)
    c["fixable"] = sum(1 for f in findings if f["fixable"])
    return c


def main() -> int:
    logging.basicConfig(
        level=(env("JAVV_LOG_LEVEL", "info") or "info").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        s = Settings()
    except SettingError as e:
        log.error("setting not valid: %s", e)
        return 2
    api = Javv(s)
    started = now()
    # The scope of the cluster in JAVV. Without it, the cycle does not scan (as the JAVV scanners).
    status, scope = api.call("GET", "/api/v1/scan-scope")
    if status != 200:
        log.error(
            "no scan scope from JAVV (%s %s): no scan in this cycle", status, scope
        )
        return 1
    images, skipped = running_images(s, scope)
    log.info(
        "%d images to scan: %s",
        len(images),
        "; ".join(
            f"{r} in {sorted(e['places'])} x{e['replicas']}" for r, e in images.items()
        ),
    )
    if skipped:
        log.info("skipped: %s", skipped)
    if s.dry_run:
        log.info("dry run: no push")
        return 0
    status, body = api.call("POST", "/api/v1/scan-runs")
    if status != 200:
        log.error("scan-runs: %s %s", status, body)
        return 1
    order, run_id = body["scan_order"], str(uuid.uuid4())
    by_digest: dict[str, dict] = {}
    failed = 0
    for ref, e in sorted(images.items()):
        try:
            digest, *result = (scan_trivy if s.scanner == "trivy" else scan_grype)(
                s, ref
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
            log.error(
                "scan of %s failed: %s",
                ref,
                str(getattr(err, "stderr", "") or err)[-500:],
            )
            failed += 1
            continue
        if not digest:
            log.warning("skip %s: the scanner gave no repository digest", ref)
            continue
        d = by_digest.setdefault(
            digest, {"ref": ref, "places": set(), "replicas": 0, "result": result}
        )
        d["places"] |= e["places"]
        d["replicas"] += e["replicas"]
    pushed = 0
    for digest, e in sorted(by_digest.items()):
        findings, ver, dbv, built = e["result"]
        envelope = {
            "schema_version": 4,
            "cluster_id": s.cluster,
            "scanner": s.scanner,
            "image_digest": digest,
            "image_ref": e["ref"],
            "namespaces": sorted(e["places"]),
            "replicas": e["replicas"],
            "scan_run_id": run_id,
            "scan_order": order,
            "last_seen_at": started,
            "scanner_version": ver,
            "scanner_db_version": dbv,
            "scanner_db_built": built,
            "effective_config": {
                "tuning": s.tuning,
                "scope": {
                    k: scope.get(k) or []
                    for k in (
                        "include_namespaces",
                        "ignore_namespaces",
                        "exclude_images",
                        "ignore_kinds",
                    )
                },
            },
            "counts": counts(findings),
            "findings": findings,
        }
        status, body = api.call("POST", "/api/v1/ingest/scan", envelope, gz=True)
        log.info(
            "push %s %s: %d findings, %s", e["ref"], digest[:19], len(findings), status
        )
        if status == 202:
            pushed += 1
        else:
            log.error("push refused: %s %s", status, body)
    expected = expected_count(len(by_digest), len(images))
    status, body = api.call(
        "POST",
        "/api/v1/inventory-runs",
        {"scan_run_id": run_id, "expected_count": expected, "started_at": started},
    )
    log.info(
        "cycle %s: %s of %s images pushed, status %s",
        run_id,
        pushed,
        expected,
        (body or {}).get("status", status),
    )
    return 0 if status == 200 and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
