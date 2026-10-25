"""Session-wide test setup (#221, major-audit 01 §2 S-1).

The suite's dominant cost was ~0.85 s of per-test *setup*: every integration fixture re-ran
`bootstrap(client)` (+ `seed_default_roles`) against the shared dev/CI OpenSearch — idempotent,
but a dozen round-trips × ~450 tests. Both are versioned/seed-once, so ONE run per session is
equivalent: this autouse fixture does it up front and the per-test fixtures just connect.

Event-loop edge case (01 §2): the suite runs per-test event loops (`asyncio_mode = "auto"`), so
this is a session-scoped **sync** fixture driving its own short-lived loop via `asyncio.run` —
an AsyncOpenSearch client is never shared across loops.

Deliberately NOT converted: the restore-drill / rollover / bootstrap tests keep their private
prefixes (they delete indices — sharing would poison the session), and anything prefix-isolated
stays as is."""

import asyncio
import contextlib
import os
from uuid import uuid4

import httpx
import pytest

from os_env import OS_URL, drop_prefix, opensearch_up

# The suite starts the app many times against a shared store. With the job scheduler running
# (issue 691) a sweep could land in the middle of another test's data, so it is off for every
# test; `test_scheduler.py` builds its own schedulers on a private prefix with a fixed clock.
os.environ.setdefault("JAVV_SCHEDULER_ENABLED", "false")


async def _bootstrap_once() -> None:
    from opensearchpy import AsyncOpenSearch

    from backend.auth.capabilities import seed_default_roles
    from backend.core.bootstrap import bootstrap

    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        await bootstrap(client)
        await seed_default_roles(client)
    finally:
        await client.close()


@pytest.fixture(scope="session", autouse=True)
def shared_bootstrap() -> None:
    """Bootstrap the real (unprefixed) indices + role seed ONCE per session. No-op (fast fail on
    the reachability probe) when OpenSearch is down — the integration tests skip themselves."""
    if opensearch_up():
        asyncio.run(_bootstrap_once())


@pytest.fixture
async def real_os():
    """A prefix-isolated store: private `t-*` indices and templates bootstrapped for this test
    alone, both dropped on teardown. The suite-wide convention for anything that mutates
    index-level state (#368 dedup — this was copy-pasted into 23 files)."""
    from opensearchpy import AsyncOpenSearch

    from backend.core.bootstrap import bootstrap

    prefix = f"t-{uuid4().hex[:8]}-"
    client = AsyncOpenSearch(hosts=[OS_URL])
    await bootstrap(client, prefix=prefix)
    yield client, prefix
    with contextlib.suppress(Exception):
        await drop_prefix(client, prefix)
    await client.close()


# The test-residue sweep (2026-07-10): integration fixtures seed `c-*` clusters and `u-*` users
# into the SHARED dev/CI OpenSearch and never cleaned up — the dev UI then shows phantom test
# clusters and the switcher can default to an empty one (bit the M9b slice-4 verification twice
# in one day). Best-effort, prefix-scoped, session-end: real tenants are UUIDs and `admin`-like
# usernames, so the `c-`/`u-` prefixes (the suite-wide fixture convention) can never touch them.
_RESIDUE_CLUSTER_PREFIX = "c-"
_RESIDUE_USER_PREFIX = "u-"
_RESIDUE_FIXTURE_UUIDS = ("0f0e6c4e-93f1-4b52-9f20-1234567890ab",)  # golden-envelope cluster
_RESIDUE_INDICES_BY_CLUSTER = (
    "findings",
    "system-tokens",
    "system-audit-log",
    "system-decisions",
    "system-reports",
    "system-views",
    "javv-scan-watermarks",
)


def _sweep_residue() -> None:
    with httpx.Client(base_url=OS_URL, timeout=60.0) as c:
        cluster_q = {
            "query": {
                "bool": {
                    "should": [
                        {"prefix": {"cluster_id": _RESIDUE_CLUSTER_PREFIX}},
                        *({"term": {"cluster_id": u}} for u in _RESIDUE_FIXTURE_UUIDS),
                    ],
                    "minimum_should_match": 1,
                }
            }
        }
        for index in _RESIDUE_INDICES_BY_CLUSTER:
            c.post(
                f"/{index}/_delete_by_query",
                params={"refresh": "true", "conflicts": "proceed", "ignore_unavailable": "true"},
                json=cluster_q,
            )
        c.post(
            "/system-users/_delete_by_query",
            params={"refresh": "true", "conflicts": "proceed", "ignore_unavailable": "true"},
            json={"query": {"prefix": {"username": _RESIDUE_USER_PREFIX}}},
        )
        c.post(  # a dashboard holds no cluster, so its test owner marks it (issue 440)
            "/system-dashboards/_delete_by_query",
            params={"refresh": "true", "conflicts": "proceed", "ignore_unavailable": "true"},
            json={"query": {"prefix": {"owner": _RESIDUE_USER_PREFIX}}},
        )
        # per-cluster test indices (occurrences / images / scan-events / inventory-runs …)
        for pattern in (
            f"javv-*-{_RESIDUE_CLUSTER_PREFIX}*",
            *(f"javv-*-{u}-*" for u in _RESIDUE_FIXTURE_UUIDS),
        ):
            c.delete(f"/{pattern}", params={"ignore_unavailable": "true"})
        # cluster registry: drop test entries, keep real tenants
        reg = c.get("/system-config/_doc/cluster-registry")
        if reg.status_code == 200:
            doc = reg.json()["_source"]
            kept = {
                k: v
                for k, v in doc.get("value", {}).items()
                if not k.startswith(_RESIDUE_CLUSTER_PREFIX) and k not in _RESIDUE_FIXTURE_UUIDS
            }
            if kept != doc.get("value"):
                doc["value"] = kept
                c.put("/system-config/_doc/cluster-registry", params={"refresh": "true"}, json=doc)


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Sweep everything the integration fixtures seeded, once, after the last test. Under xdist each
    worker is a session of its own, and a worker that finished first swept the users of tests the
    other one was still running (issue 844): only the controller, or a run without xdist, sweeps.
    Best-effort: a failed sweep must never fail the suite (it reruns next session)."""
    if hasattr(session.config, "workerinput") or not opensearch_up():
        return
    with contextlib.suppress(Exception):
        _sweep_residue()
