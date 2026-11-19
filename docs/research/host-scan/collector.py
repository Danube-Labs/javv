"""Phase 0 of issue 1239: the collector of one node. A research script, not product code.

It reads the package database and the release files of its node from the read-only mounts under
/host, and serves two things on port 8080:
  GET /meta.json     the node name, the kernel that runs, the OS release, the hash of the package
                     database, and the files of the copy with their sizes
  GET /copy.tar.gz   the files, with their paths as on the node (etc/os-release, var/lib/dpkg/status)

It holds no scanner database and no JAVV token. Standard library only, so the scanner image runs it.
"""

import gzip
import hashlib
import io
import json
import os
import tarfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path("/host")
# the release files and the package database of each package system (research section 5.1)
FILES = [
    "etc/os-release",
    "usr/lib/os-release",
    "etc/lsb-release",
    "var/lib/dpkg/status",
    "lib/apk/db/installed",
    "var/lib/rpm/rpmdb.sqlite",
    "usr/lib/sysimage/rpm/rpmdb.sqlite",
]
PACKAGE_DBS = {
    "var/lib/dpkg/status",
    "lib/apk/db/installed",
    "var/lib/rpm/rpmdb.sqlite",
    "usr/lib/sysimage/rpm/rpmdb.sqlite",
}


def build() -> tuple[bytes, dict]:
    present = [f for f in FILES if (ROOT / f).is_file()]
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for f in present:
            tar.add(ROOT / f, arcname=f, recursive=False)
    digest = hashlib.sha256()
    for f in sorted(p for p in present if p in PACKAGE_DBS):
        digest.update((ROOT / f).read_bytes())
    release = {}
    for line in (
        (ROOT / "etc/os-release").read_text().splitlines()
        if (ROOT / "etc/os-release").is_file()
        else []
    ):
        key, _, value = line.partition("=")
        if key in ("ID", "VERSION_ID", "PRETTY_NAME"):
            release[key] = value.strip('"')
    copy = gzip.compress(raw.getvalue())
    meta = {
        "node": os.environ.get("NODE_NAME", ""),
        "kernel_running": Path("/proc/sys/kernel/osrelease").read_text().strip(),
        "os_release": release,
        "pkg_digest": "sha256:" + digest.hexdigest()
        if any(p in PACKAGE_DBS for p in present)
        else None,
        "files": {f: (ROOT / f).stat().st_size for f in present},
        "copy_bytes": len(copy),
    }
    return copy, meta


COPY, META = build()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/meta.json":
            body, kind = json.dumps(META).encode(), "application/json"
        elif self.path == "/copy.tar.gz":
            body, kind = COPY, "application/gzip"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(
            json.dumps({"event": "collector request", "line": fmt % args}), flush=True
        )


if __name__ == "__main__":
    print(json.dumps({"event": "collector ready", **META}), flush=True)
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
