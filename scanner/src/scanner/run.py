"""One scan cycle: discover running images, drive the configured scanner against each, and push
the envelopes. A single ScanRun is shared across the whole cycle (one scan_run_id + scan_order),
so every image in this run sorts together (D40). The scan and push functions are injected so the
cycle is unit-testable; `main()` wires the real kube client, scanner binaries, and HTTP client.
"""

import os
import re
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import structlog

from scanner.config import GrypeConfig, TrivyConfig
from scanner.discovery import ImageTarget, discover
from scanner.envelope import EffectiveConfig, Envelope, Scanner, build_envelope, new_scan_run
from scanner.inventory import commit_inventory
from scanner.models import ScanResult
from scanner.orders import fetch_scan_order
from scanner.push import PushResult, push_envelope
from scanner.scope import fetch_scan_scope

ScanFn = Callable[[str], ScanResult]
PushFn = Callable[[Envelope], PushResult]
# cycle-end inventory certification (M8a slice 2): (scan_run_id, expected_count, started_at)
CommitFn = Callable[[str, int, datetime], object]

log = structlog.get_logger()

# Bounds one log line. The scanner prints its final error last; what precedes it is progress.
STDERR_TAIL_LINES = 5
STDERR_TAIL_CHARS = 1000


def failure_detail(exc: BaseException) -> dict[str, object]:
    """Why a scan failed, in the scanner's own words. The exception alone says "exit status 1";
    the reason (the registry refused the pull, the image is gone) is only on the scanner's
    stderr, which nothing else records (issue 633)."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return {"reason": "timeout", "timeout_s": exc.timeout}
    if isinstance(exc, subprocess.CalledProcessError):
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        tail = "\n".join(stderr.strip().splitlines()[-STDERR_TAIL_LINES:])
        return {
            "reason": "scanner_exit",
            "exit_code": exc.returncode,
            "scanner_stderr": tail[-STDERR_TAIL_CHARS:],
        }
    return {"reason": "error"}


def scan_all(
    targets: Iterable[ImageTarget],
    *,
    scanner: Scanner,
    cluster_id: str,
    scan_fn: ScanFn,
    push_fn: PushFn,
    scan_order: int,
    effective_config: EffectiveConfig | None = None,
    commit_fn: CommitFn | None = None,
) -> list[PushResult]:
    run = new_scan_run(scan_order)  # backend-allocated (D45) — the cycle's ordering key
    structlog.contextvars.bind_contextvars(scan_run_id=run.scan_run_id, scan_order=scan_order)
    cycle_started_at = datetime.now(UTC)
    targets = list(targets)
    results: list[PushResult] = []
    for i, t in enumerate(targets, start=1):
        # D30: scan everything every cycle. One un-pullable image, a scanner non-zero exit, or a
        # subprocess timeout must not abort the rest of the cycle — isolate it, log, and continue.
        # Per-image progress at INFO (#156): a big image can scan for minutes looking hung.
        log.info(
            "scanning image",
            image_ref=t.image_ref,
            pull_ref=t.pull_ref,
            image_digest=t.image_digest,
            position=f"{i}/{len(targets)}",
        )
        started = time.monotonic()
        try:
            scanned = scan_fn(t.pull_ref)
        except Exception as exc:
            log.warning(
                "scan failed, image skipped",
                image_ref=t.image_ref,
                pull_ref=t.pull_ref,
                image_digest=t.image_digest,
                **failure_detail(exc),
                exc_info=True,
            )
            continue
        log.info(
            "scan done",
            image_ref=t.image_ref,
            findings=len(scanned.findings),
            duration_s=round(time.monotonic() - started, 2),
        )
        envelope = build_envelope(
            run,
            cluster_id=cluster_id,
            scanner=scanner,
            image_digest=t.image_digest,
            image_ref=t.image_ref,
            namespaces=t.namespaces,
            replicas=t.pod_count,
            findings=scanned.findings,
            provenance=scanned.provenance,
            effective_config=effective_config,
        )
        results.append(push_fn(envelope))
    if commit_fn is not None:
        # cycle-end inventory certification (M8a slice 2, D39): expected = every image that was
        # SCANNED, one push result each. A dead-lettered push still counts, so lost data leaves
        # the run partial. A failed scan does not: an image its registry no longer serves would
        # otherwise make every run partial and freeze the running-images view for good (issue
        # 633). That image leaves the inventory and its findings go stale on the normal timer.
        # The exception is a cycle in which NOTHING scanned (no registry reachable, a broken
        # scanner): certifying it would publish an empty inventory, so it keeps the discovered
        # count, stays partial, and the last good inventory keeps answering.
        expected = len(results) if results else len(targets)
        commit_fn(run.scan_run_id, expected, cycle_started_at)
    return results


@dataclass(frozen=True)
class BackendTarget:
    url: str
    token: str | None
    cluster_id: str | None  # set = asserted against the cluster reached (see resolve_cluster_id)


def read_backend_env(environ: Mapping[str, str]) -> BackendTarget | None:
    """`JAVV_BACKEND_URL`, `JAVV_TOKEN` and `JAVV_CLUSTER_ID`, validated for a push. `None` = a
    value is garbage (logged with the variable's name); the caller exits 2 rather than push."""
    url = environ.get("JAVV_BACKEND_URL", "http://localhost:8000")
    if not url.startswith(("http://", "https://")):  # else httpx fails as a silent skip
        log.error("invalid JAVV_BACKEND_URL", value=url, want="http(s)://…")
        return None
    cluster_id = environ.get("JAVV_CLUSTER_ID")
    if cluster_id and not re.fullmatch(r"[a-z0-9-]{8,64}", cluster_id):
        # mirrors the backend's shape rule — garbage here would 422 on every push
        log.error("invalid JAVV_CLUSTER_ID", value=cluster_id, want="lowercase alnum/hyphen, 8-64")
        return None
    # bearer token — effectively required: without it the scope fetch 401s and every cycle skips
    return BackendTarget(url=url, token=environ.get("JAVV_TOKEN"), cluster_id=cluster_id or None)


def scan_wiring(scanner: Scanner) -> tuple[ScanFn, TrivyConfig | GrypeConfig]:
    """The scan function and tuning a cycle runs with: `JAVV_TRIVY_*`/`JAVV_GRYPE_*` (#91), whose
    defaults are the pinned command. The tuning is stamped into every envelope (D44)."""
    from scanner.adapters.grype import scan_grype
    from scanner.adapters.trivy import scan_trivy, trivy_db_info

    if scanner == "trivy":
        trivy_cfg = TrivyConfig.from_env()
        trivy_db = trivy_db_info()  # once per cycle, best-effort vuln-DB provenance (#96)
        return (lambda ref: scan_trivy(ref, config=trivy_cfg, db=trivy_db)), trivy_cfg
    grype_cfg = GrypeConfig.from_env()
    return (lambda ref: scan_grype(ref, config=grype_cfg)), grype_cfg


def resolve_cluster_id(live_uid: str, env_cluster_id: str | None) -> str | None:
    """`JAVV_CLUSTER_ID` asserts which cluster this cycle is for; it does not relabel one.

    Pushing a cluster's images under another tenant's id succeeds at every layer (the token's
    scope matches, ingest returns 202) and then reconcile-on-commit retires that tenant's real
    inventory, because the run omitted all of it. Only the live `kube-system` UID knows which
    cluster the kube client actually reached, so a disagreement is refused. `None` = refuse.
    """
    if env_cluster_id and env_cluster_id != live_uid:
        log.error(
            "JAVV_CLUSTER_ID is not the cluster the kube client reached — refusing the cycle",
            configured=env_cluster_id,
            reached=live_uid,
            want="point JAVV_KUBE_CONTEXT at the right context, or unset JAVV_CLUSTER_ID",
        )
        return None
    return env_cluster_id or live_uid


def main() -> int:
    import httpx
    from javv_common.logging import configure_logging
    from kubernetes import client, config

    configure_logging()  # JAVV_LOG_LEVEL, same pipeline as the backend (#156)

    scanner_env = os.environ.get("JAVV_SCANNER", "trivy")
    if scanner_env not in ("trivy", "grype"):  # a typo must not silently run grype (#97)
        log.error("unknown JAVV_SCANNER", value=scanner_env, want="trivy|grype")
        return 2
    scanner: Scanner = cast(Scanner, scanner_env)
    target = read_backend_env(os.environ)
    if target is None:
        return 2
    backend, token, env_cluster_id = target.url, target.token, target.cluster_id
    dead_letter = Path(os.environ.get("JAVV_DEAD_LETTER", f"{scanner}.dead-letter.jsonl"))

    # `or None` — an empty value (a blank Helm value, an exported-but-unset var) means "current
    # context", not a context literally named "", which kube_config raises on.
    kube_context = os.environ.get("JAVV_KUBE_CONTEXT") or None
    try:
        config.load_incluster_config()
    except config.ConfigException:
        # Out of cluster, the kubeconfig's current context silently decides which cluster gets
        # scanned. Name it, so a dev host holding several clusters does not pick by ambience.
        config.load_kube_config(context=kube_context)
        if kube_context is None:
            # name the one that was picked by ambience — list_kube_config_contexts reports the
            # kubeconfig's current-context, so it is only the truth when we did not override it
            _, active = config.list_kube_config_contexts()
            kube_context = cast(Any, active)["name"]
    api = client.CoreV1Api()

    # Tenant identity = the immutable kube-system namespace UID (never cluster_name).
    # kubernetes-client return types are untyped unions; cast for the attribute access.
    kube_system = cast(Any, api.read_namespace("kube-system"))
    resolved = resolve_cluster_id(str(kube_system.metadata.uid), env_cluster_id)
    if resolved is None:
        return 2
    cluster_id = resolved
    # every line of this cycle carries who/where (merged by the shared pipeline)
    structlog.contextvars.bind_contextvars(scanner=scanner, cluster_id=cluster_id)
    # which cluster this cycle actually reached — the counts below mean nothing without it
    log.info(
        "kube target",
        kube_context=kube_context or "in-cluster",
        api_server=cast(Any, api.api_client.configuration).host,
    )

    scan_fn, tuning = scan_wiring(scanner)

    with httpx.Client(base_url=backend, timeout=30.0) as http:
        # D43/FR-24: fetch the cluster's scan scope first. Fail-closed — if the backend is
        # unreachable we can't confirm what to scan (and couldn't push anyway), so skip the cycle.
        # A fetched *empty* scope means scan everything (handled by the discovery filter).
        scope = fetch_scan_scope(http, token=token)
        if scope is None:
            log.error("scan scope unavailable (backend unreachable) — skipping cycle")
            return 0
        # D45: the backend mints the cycle's ordering key — same fail-closed contract as scope
        scan_order = fetch_scan_order(http, token=token)
        if scan_order is None:
            log.error("scan_order allocation failed (backend) — skipping cycle")
            return 0
        targets = discover(api, scope)
        results = scan_all(
            targets,
            scanner=scanner,
            cluster_id=cluster_id,
            scan_fn=scan_fn,
            push_fn=lambda e: push_envelope(
                e, client=http, dead_letter_path=dead_letter, token=token
            ),
            scan_order=scan_order,
            # D44/FR-25: stamp what this cycle ran with (tuning flags + the applied scope)
            effective_config=EffectiveConfig(tuning=tuning, scope=scope),
            # M8a slice 2: certify the cycle's inventory at the end (best-effort — see inventory.py)
            commit_fn=lambda run_id, expected, started: commit_inventory(
                http,
                token=token,
                scan_run_id=run_id,
                expected_count=expected,
                started_at=started,
            ),
        )

    delivered = sum(1 for r in results if r.delivered)
    log.info(
        "cycle complete",
        discovered=len(targets),
        scanned=len(results),
        scan_failed=len(targets) - len(results),
        delivered=delivered,
        dead_lettered=len(results) - delivered,
    )
    return 0
