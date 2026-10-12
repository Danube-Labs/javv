"""Scanner compatibility gate (M0b, D41).

A candidate scanner version is publishable (compatible) only if its real output still satisfies
the JAVV adapter contracts. `contract_violations` is the pure checker; `run_compat` drives the
real binary and checks it; `main()` is the CI entry — `python -m scanner.compat --scanner trivy`
exits non-zero (blocking publish) when the format has drifted.

`--push` goes one step further (issue 631): the same image goes through the real cycle
(`scan_all` with the backend-allocated order, the real push client and the inventory commit) to
`JAVV_BACKEND_URL`, so CI can check what the backend stored against what was sent.
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import httpx
import structlog

from scanner.adapters.grype import scan_grype
from scanner.adapters.trivy import scan_trivy
from scanner.config import GrypeConfig, TrivyConfig
from scanner.discovery import ImageTarget, Location
from scanner.envelope import EffectiveConfig, Envelope, Scanner, build_envelope, new_scan_run
from scanner.inventory import commit_inventory
from scanner.models import ScanResult
from scanner.normalize import COUNT_COLUMN, SEVERITIES
from scanner.orders import fetch_scan_order
from scanner.push import push_envelope
from scanner.run import ScanFn, read_backend_env, scan_all, scan_wiring
from scanner.scope import fetch_scan_scope

_DRIVERS = {"trivy": scan_trivy, "grype": scan_grype}

# A deliberately old image with known vulnerabilities (python:3.9.16-slim). Pinned by digest so the
# gate scans the same bytes every run, and a push carries a real image_digest. Served from our own
# registry, copied there by digest (.github/workflows/compat-fixture.yml), so the gate doesn't
# depend on Docker Hub still serving it.
COMPAT_IMAGE = (
    "ghcr.io/danube-labs/javv-compat-fixture:python-3.9.16-slim"
    "@sha256:5cde4e147c4165ad8dbf8a4df9631863766eeb0b79b890fafe6885b3b127af74"
)

log = structlog.get_logger()


def contract_violations(
    result: ScanResult, *, scanner: Scanner, expect_findings: bool
) -> list[str]:
    """Return human-readable contract violations; empty list = the version is compatible."""
    violations: list[str] = []

    if not result.provenance.scanner_version:
        violations.append("scanner_version missing — provenance path drifted")
    if expect_findings and not result.findings:
        violations.append("no findings parsed on a known-vulnerable image — parse path drifted")

    non_canonical = [f.vuln_id for f in result.findings if f.severity_canonical not in SEVERITIES]
    if non_canonical:
        violations.append(f"{len(non_canonical)} findings with non-canonical severity")

    try:
        env = build_envelope(
            new_scan_run(1),  # local harness, no backend — any positive order works (D45)
            cluster_id="compat",
            scanner=scanner,
            image_digest="sha256:compat",
            findings=result.findings,
            provenance=result.provenance,
        )
        # count COLUMN names keep the short form (D46/COUNT_COLUMN) — map before getattr
        if env.counts.total != sum(getattr(env.counts, COUNT_COLUMN.get(s, s)) for s in SEVERITIES):
            violations.append("severity bucket invariant violated")
    except Exception as exc:  # noqa: BLE001 — any build failure means the contract broke
        violations.append(f"envelope build failed: {exc!r}")

    return violations


def run_compat(scanner: Scanner, image: str) -> tuple[ScanResult, list[str]]:
    result = _DRIVERS[scanner](image)
    return result, contract_violations(result, scanner=scanner, expect_findings=True)


@dataclass(frozen=True)
class PushSummary:
    """What was sent, for CI to compare with what the backend stored."""

    scanner: str
    scanner_version: str | None
    cluster_id: str
    scan_run_id: str
    image_digest: str
    counts: dict[str, int]
    delivered: bool
    inventory_committed: bool


def push_compat(
    scanner: Scanner,
    image: str,
    *,
    cluster_id: str,
    scan_fn: ScanFn,
    tuning: TrivyConfig | GrypeConfig,
    http: httpx.Client,
    token: str | None,
    dead_letter: Path,
) -> tuple[ScanResult | None, PushSummary | None, list[str]]:
    """One real cycle over the single compat image: the same scope fetch, `scan_all`, push client
    and inventory commit a CronJob runs, minus discovery. Returns the scan, what was pushed, and
    the violations."""
    _, _, digest = image.partition("@")
    if not digest.startswith("sha256:"):
        return None, None, [f"--push needs a digest-pinned image (name@sha256:…), got {image!r}"]
    scope = fetch_scan_scope(http, token=token)
    if scope is None:
        return None, None, ["scan scope unavailable — backend unreachable or token refused"]
    scan_order = fetch_scan_order(http, token=token)
    if scan_order is None:
        return None, None, ["scan_order allocation failed — backend unreachable or token refused"]

    scanned: list[ScanResult] = []
    pushed: list[Envelope] = []
    committed: list[bool] = []

    def scan_and_keep(ref: str) -> ScanResult:
        scanned.append(scan_fn(ref))
        return scanned[-1]

    target = ImageTarget(
        image_digest=digest,
        image_ref=image,
        pull_ref=image,
        locations=(Location(namespace="javv-compat", pod="compat", container=scanner),),
    )
    results = scan_all(
        [target],
        scanner=scanner,
        cluster_id=cluster_id,
        scan_fn=scan_and_keep,
        push_fn=lambda e: (
            pushed.append(e),
            push_envelope(e, client=http, dead_letter_path=dead_letter, token=token),
        )[1],
        scan_order=scan_order,
        effective_config=EffectiveConfig(tuning=tuning, scope=scope),
        commit_fn=lambda run_id, expected, started: committed.append(
            commit_inventory(
                http,
                token=token,
                scan_run_id=run_id,
                expected_count=expected,
                started_at=started,
            )
        ),
    )
    if not scanned or not pushed:
        return None, None, ["the scan failed before anything was pushed (see the warning above)"]
    result, envelope = scanned[0], pushed[0]
    violations = contract_violations(result, scanner=scanner, expect_findings=True)
    summary = PushSummary(
        scanner=scanner,
        scanner_version=result.provenance.scanner_version,
        cluster_id=cluster_id,
        scan_run_id=envelope.scan_run_id,
        image_digest=digest,
        counts=envelope.counts.model_dump(),
        delivered=results[0].delivered,
        inventory_committed=bool(committed and committed[0]),
    )
    if not summary.delivered:
        violations.append("the backend did not accept the envelope (dead-lettered)")
    if not summary.inventory_committed:
        violations.append("the inventory run was not committed")
    return result, summary, violations


def _push_main(scanner: Scanner, image: str, summary_path: Path | None) -> int:
    from javv_common.logging import configure_logging

    configure_logging()  # the cycle's lines go through the same pipeline as a CronJob's
    target = read_backend_env(os.environ)
    if target is None:
        return 2
    if target.cluster_id is None:
        log.error("--push needs JAVV_CLUSTER_ID", want="the cluster id the token was minted for")
        return 2
    structlog.contextvars.bind_contextvars(scanner=scanner, cluster_id=target.cluster_id)
    scan_fn, tuning = scan_wiring(scanner)
    with httpx.Client(base_url=target.url, timeout=30.0) as http:
        result, summary, violations = push_compat(
            scanner,
            image,
            cluster_id=target.cluster_id,
            scan_fn=scan_fn,
            tuning=tuning,
            http=http,
            token=target.token,
            dead_letter=Path(os.environ.get("JAVV_DEAD_LETTER", f"{scanner}.dead-letter.jsonl")),
        )
    if summary is not None and summary_path is not None:
        summary_path.write_text(json.dumps(asdict(summary), indent=2) + "\n")
    version = result.provenance.scanner_version if result else None
    if violations:
        log.error("compat push failed", scanner_version=version, violations=violations)
        return 1
    assert summary is not None  # no violations means the push path completed
    log.info(
        "compat push ok",
        scanner_version=version,
        scan_run_id=summary.scan_run_id,
        total=summary.counts.get("total"),
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="JAVV scanner compatibility gate")
    ap.add_argument("--scanner", required=True, choices=["trivy", "grype"])
    ap.add_argument("--image", default=COMPAT_IMAGE)
    ap.add_argument(
        "--push",
        action="store_true",
        help="also run the real cycle for this image into JAVV_BACKEND_URL as JAVV_CLUSTER_ID",
    )
    ap.add_argument("--summary", type=Path, help="with --push: write what was sent here (JSON)")
    args = ap.parse_args()

    if args.push:
        return _push_main(cast(Scanner, args.scanner), args.image, args.summary)
    result, violations = run_compat(cast(Scanner, args.scanner), args.image)
    version = result.provenance.scanner_version
    if violations:
        print(
            f"FAIL {args.scanner} {version}: {len(violations)} contract violation(s):",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print(f"OK {args.scanner} {version}: contract holds, {len(result.findings)} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
