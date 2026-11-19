"""Phase 0 of issue 1239: the central scan of each node copy. A research script, not product code.

It finds each collector pod through the headless Service, gets its copy, and runs one scanner on it
(the image decides: JAVV_SCANNER is trivy or grype). Then it reads the report twice: raw, and with
the adapters of the scanner package. It prints one JSON line per node with the measurements:
  - the time of the scan, and the memory peak of the container (cgroup v2 memory.peak, the
    kernel's own record; the database download runs in an init container, so it is not in it)
  - the findings: raw rows of the report, the adapters' count, the different IDs, the packages
  - the kernel split: packages of the kernel that runs, other kernel packages, all others
  - the size of a host envelope built with the scanner's own build_envelope, plain and gzipped
"""

import gzip
import io
import json
import os
import re
import socket
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

from scanner.adapters.grype import parse_grype, parse_grype_provenance
from scanner.adapters.trivy import parse_trivy, parse_trivy_provenance
from scanner.envelope import build_envelope, new_scan_run

SCANNER = os.environ["JAVV_SCANNER"]
SERVICE = os.environ.get("COLLECTORS", "host-collector.javv-hostscan.svc.cluster.local")
WORK = Path("/work")


def fetch(ip: str, path: str) -> bytes:
    with urllib.request.urlopen(f"http://{ip}:8080{path}", timeout=60) as r:
        return r.read()


def scan(root: Path, report: Path) -> float:
    if SCANNER == "trivy":
        cmd = [
            "trivy",
            "rootfs",
            "--pkg-types",
            "os",
            "--scanners",
            "vuln",
            "--skip-db-update",
            "--format",
            "json",
            "--output",
            str(report),
            str(root),
        ]
    else:
        cmd = ["grype", f"dir:{root}", "-o", "json", "--file", str(report)]
    t0 = time.monotonic()
    subprocess.run(cmd, check=True, capture_output=True)
    return time.monotonic() - t0


def raw_rows(data: dict) -> int:
    if SCANNER == "trivy":
        return sum(
            len(r.get("Vulnerabilities") or []) for r in data.get("Results") or []
        )
    return len(data.get("matches") or [])


def kernel_split(findings: list, running: str) -> dict:
    # `7.0.0-42-generic` runs; its packages are linux-image-7.0.0-42-generic but also
    # linux-headers-7.0.0-42, so match the version without the flavour, up to a `-` or the end
    version = re.sub(r"-[a-z][a-z0-9]*$", "", running) if running else None
    of_running = re.compile(re.escape(version or "") + r"(-|$)")
    groups = {"running_kernel": 0, "other_kernel": 0, "not_kernel": 0}
    ids = {k: set() for k in groups}
    pkgs = {k: set() for k in groups}
    for f in findings:
        if f.package_name.startswith("linux-"):
            key = (
                "running_kernel"
                if version and of_running.search(f.package_name)
                else "other_kernel"
            )
        else:
            key = "not_kernel"
        groups[key] += 1
        ids[key].add(f.vuln_id)
        pkgs[key].add(f.package_name)
    return {
        k: {"findings": groups[k], "ids": len(ids[k]), "packages": len(pkgs[k])}
        for k in groups
    }


def memory_peak() -> int | None:
    p = Path("/sys/fs/cgroup/memory.peak")
    return int(p.read_text()) if p.exists() else None


def local_meta(root: Path) -> dict:
    """The meta of a local root (slice 0.5): its files, and its release, as the collector reads them."""
    files = {
        str(p.relative_to(root)): p.stat().st_size
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
    release = {}
    os_release = root / "etc/os-release"
    for line in os_release.read_text().splitlines() if os_release.is_file() else []:
        key, _, value = line.partition("=")
        if key in ("ID", "VERSION_ID", "PRETTY_NAME"):
            release[key] = value.strip('"')
    return {
        "node": root.name,
        "kernel_running": "",
        "os_release": release,
        "pkg_digest": None,
        "files": files,
        "copy_bytes": sum(files.values()),
    }


def main() -> None:
    # ROOTS=dir,dir scans local roots (slice 0.5); else the copies of the collectors (slice 0.3)
    if os.environ.get("ROOTS"):
        for root in (Path(r) for r in os.environ["ROOTS"].split(",")):
            WORK.mkdir(parents=True, exist_ok=True)
            try:
                measure(root, local_meta(root), WORK / f"{root.name}.{SCANNER}.json")
            except subprocess.CalledProcessError as e:
                # a root the scanner refuses is a result too: keep its own words, go on
                print(
                    json.dumps(
                        {
                            "event": "host scan refused",
                            "scanner": SCANNER,
                            "node": root.name,
                            "exit": e.returncode,
                            "stderr": e.stderr.decode()[-600:],
                        }
                    ),
                    flush=True,
                )
        return
    _, _, ips = socket.gethostbyname_ex(SERVICE)
    for ip in sorted(ips):
        meta = json.loads(fetch(ip, "/meta.json"))
        copy = fetch(ip, "/copy.tar.gz")
        root = WORK / meta["node"]
        root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(copy), mode="r:gz") as tar:
            tar.extractall(root, filter="data")
        measure(root, meta, WORK / f"{meta['node']}.{SCANNER}.json")


def measure(root: Path, meta: dict, report: Path) -> None:
    seconds = scan(root, report)
    data = json.loads(report.read_text())
    parse, prov = (
        (parse_trivy, parse_trivy_provenance)
        if SCANNER == "trivy"
        else (parse_grype, parse_grype_provenance)
    )
    findings = parse(data)
    env = build_envelope(
        new_scan_run(1),
        cluster_id="hostscan-phase0",
        scanner=SCANNER,
        image_digest=meta["pkg_digest"] or "sha256:0",
        findings=findings,
        provenance=prov(data),
    )
    body = env.model_dump_json().encode()
    print(
        json.dumps(
            {
                "event": "host scan measured",
                "scanner": SCANNER,
                "node": meta["node"],
                "kernel_running": meta["kernel_running"],
                "os": meta["os_release"],
                "copy_bytes": meta["copy_bytes"],
                "files": meta["files"],
                "scan_seconds": round(seconds, 1),
                "memory_peak_bytes": memory_peak(),
                "report_bytes": report.stat().st_size,
                "report_rows": raw_rows(data),
                "adapter_findings": len(findings),
                "different_ids": len({f.vuln_id for f in findings}),
                "packages": len({f.package_name for f in findings}),
                "kev": sum(f.kev for f in findings),
                "fixable": sum(f.fixable for f in findings),
                "kernel": kernel_split(findings, meta["kernel_running"]),
                "envelope_bytes": len(body),
                "envelope_gzip_bytes": len(gzip.compress(body)),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
