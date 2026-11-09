#!/usr/bin/env python3
"""Scan the images of the running containers of a Docker host with Trivy or Grype, and push them
to JAVV.

It reads the running containers from the Docker API on the socket, scans each image from the
Docker daemon by its image ID, takes the digest from the scanner output and pushes one scan cycle
(INGEST-CONTRACT page).

  JAVV_BACKEND_URL=https://javv.example JAVV_TOKEN=… JAVV_CLUSTER_ID=docker-host-01 \\
  JAVV_SCANNER=trivy python3 javv_docker_push.py

The settings: README.md in this folder.

The place of an image (the `namespaces` field) is the Compose project of the container, else the
container name. A container with the label `javv.scan=true` is not scanned: the scan containers
have it. Python 3.11 or later, standard library only. The parts that scan and push are the same
as in deploy/nomad/javv_nomad_push.py; a test keeps them equal.
"""

import datetime as dt
import fnmatch
import gzip
import http.client
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

log = logging.getLogger("javv-docker")

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
CLUSTER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
GO_DURATION = re.compile(r"^([0-9]+(\.[0-9]+)?(ns|us|µs|ms|s|m|h))+$")
# Grype reads the image from the Docker daemon, by its image ID
GRYPE_SOURCE = "docker"
SCAN_LABEL = "javv.scan"


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
        if not self.javv.startswith(("http://", "https://")):
            raise SettingError(
                f"JAVV_BACKEND_URL={self.javv!r}: start it with http:// or https://"
            )
        self.token = required("JAVV_TOKEN")
        self.cluster = required("JAVV_CLUSTER_ID")
        if not CLUSTER_ID.match(self.cluster):
            raise SettingError(
                f"JAVV_CLUSTER_ID={self.cluster!r}: use 8 to 64 lowercase letters, digits and"
                " hyphens, not a hyphen first"
            )
        self.scanner = required("JAVV_SCANNER")
        if self.scanner not in ("trivy", "grype"):
            raise SettingError(f"JAVV_SCANNER={self.scanner!r}: use trivy or grype")
        # the scanners read DOCKER_HOST too
        docker = env("DOCKER_HOST", "unix:///var/run/docker.sock") or ""
        if not docker.startswith("unix://"):
            raise SettingError(
                f"DOCKER_HOST={docker!r}: use a socket, for example unix:///var/run/docker.sock"
            )
        self.docker_socket = docker.removeprefix("unix://")
        self.skip_projects = csv("JAVV_DOCKER_SKIP_PROJECTS")
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


def body_of(raw: bytes):
    """The JSON of a reply, or its start as text: a proxy in front of JAVV answers with HTML."""
    try:
        return json.loads(raw or b"null")
    except ValueError:
        return {"text": raw[:300].decode("utf-8", "replace")}


class Javv:
    """The calls to JAVV. As the JAVV scanners: send again after 429, a 5xx or no reply, with waits
    of at most 30 s. One retry budget for the whole cycle, charged only for the time that a call
    keeps failing: the scans before the first push do not use it."""

    def __init__(self, s: Settings) -> None:
        self.s = s
        self.spent = 0.0

    def call(self, method: str, path: str, body=None, gz: bool = False):
        data, headers = None, {"Authorization": f"Bearer {self.s.token}"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
            if gz:  # only the push of an envelope accepts a compressed body
                data = gzip.compress(data)
                headers["Content-Encoding"] = "gzip"
        wait, failing_since = 1.0, None
        while True:
            req = urllib.request.Request(
                self.s.javv + path, data=data, headers=headers, method=method
            )
            answer = None
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    answer = r.status, body_of(r.read())
            except urllib.error.HTTPError as e:
                if e.code != 429 and e.code < 500:
                    answer = e.code, body_of(e.read())
                reason = f"HTTP {e.code}"
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                reason = str(getattr(e, "reason", e))
            now = time.monotonic()
            if failing_since is not None:
                self.spent += now - failing_since
            if answer is not None:
                return answer
            failing_since = now
            left = self.s.retry_budget - self.spent
            if left <= 0:
                return None, {
                    "error": f"no answer in the retry budget of {self.s.retry_budget} s: {reason}"
                }
            wait = min(wait, left)
            log.warning(
                "JAVV did not accept %s %s (%s); again in %.0f s",
                method,
                path,
                reason,
                wait,
            )
            time.sleep(wait)
            wait = min(wait * 2, 30)


class DockerError(Exception):
    pass


class SocketConnection(http.client.HTTPConnection):
    def __init__(self, path: str) -> None:
        super().__init__("localhost", timeout=30)
        self.socket_path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(self.socket_path)


def docker_get(s: Settings, path: str):
    conn = SocketConnection(s.docker_socket)
    try:
        conn.request("GET", path)
        r = conn.getresponse()
        body = r.read()
    finally:
        conn.close()
    if r.status != 200:
        raise DockerError(f"GET {path}: HTTP {r.status}")
    return json.loads(body)


def match(value: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(value, p) for p in patterns)


def running_images(s: Settings, scope: dict):
    """{image ID: {refs, places, containers}} of the running containers that the settings and the
    scope allow, and what they skipped."""
    out: dict[str, dict] = {}
    skipped = {
        "project": set(),
        "namespace": set(),
        "image": set(),
        "scan_container": set(),
    }
    for c in docker_get(s, "/containers/json"):
        if c["State"] != "running":
            continue
        labels = c.get("Labels") or {}
        name = (c.get("Names") or ["/" + c["Id"][:12]])[0].lstrip("/")
        # the scan containers: they have the label javv.scan=true
        if labels.get(SCAN_LABEL) == "true":
            skipped["scan_container"].add(name)
            continue
        place = labels.get("com.docker.compose.project") or name
        if match(place, s.skip_projects):
            skipped["project"].add(place)
            continue
        include, ignore = (
            scope.get("include_namespaces") or [],
            scope.get("ignore_namespaces") or [],
        )
        if (include and not match(place, include)) or match(place, ignore):
            skipped["namespace"].add(place)
            continue
        ref = c["Image"]
        # the list gives the image ID when the tag moved to another image after the start
        if ref.startswith("sha256:"):
            try:
                ref = docker_get(s, f"/containers/{c['Id']}/json")["Config"]["Image"]
            except DockerError:
                pass  # the container stopped: keep the image ID as its name
        if match(ref, scope.get("exclude_images") or []):
            skipped["image"].add(ref)
            continue
        e = out.setdefault(
            c["ImageID"], {"refs": set(), "places": set(), "containers": set()}
        )
        e["refs"].add(ref)
        e["places"].add(place)
        e["containers"].add(c["Id"])
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
    cmd = ["grype", f"{GRYPE_SOURCE}:{ref}", "-o", "json"]
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
    # the repository digest only: the manifest digest of one platform names another image in JAVV
    digest = repo_digest(target.get("repoDigests") or [])
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
    level = (env("JAVV_LOG_LEVEL", "info") or "info").upper()
    logging.basicConfig(
        level=level if level in LOG_LEVELS else "INFO",
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if level not in LOG_LEVELS:
        log.error(
            "setting not valid: JAVV_LOG_LEVEL=%r: use one of %s", level, LOG_LEVELS
        )
        return 2
    try:
        s = Settings()
    except SettingError as e:
        log.error("setting not valid: %s", e)
        return 2
    api = Javv(s)
    started = now()
    # The scope of the cluster in JAVV. Without it, the cycle does not scan (as the JAVV scanners).
    status, scope = api.call("GET", "/api/v1/scan-scope")
    if status != 200 or not isinstance(scope, dict) or "text" in scope:
        log.error(
            "no scan scope from JAVV (%s %s): no scan in this cycle", status, scope
        )
        return 1
    try:
        images, skipped = running_images(s, scope)
    except (DockerError, OSError) as e:
        log.error("the Docker API did not answer: %s", e)
        return 1
    log.info(
        "%d images to scan: %s",
        len(images),
        "; ".join(
            f"{min(e['refs'])} in {sorted(e['places'])} x{len(e['containers'])}"
            for e in images.values()
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
    for image_id, e in sorted(images.items()):
        ref = min(e["refs"])
        try:
            # by the image ID: the image that runs, also when its tag moved after the start
            digest, *result = (scan_trivy if s.scanner == "trivy" else scan_grype)(
                s, image_id
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
            log.error("skip %s: the scanner gave no repository digest", ref)
            failed += 1
            continue
        d = by_digest.setdefault(
            digest,
            {"ref": ref, "places": set(), "containers": set(), "result": result},
        )
        d["places"] |= e["places"]
        d["containers"] |= e["containers"]
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
            # a container is the Docker form of a pod: the JAVV scanners count pods
            "replicas": len(e["containers"]),
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
            failed += 1
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
