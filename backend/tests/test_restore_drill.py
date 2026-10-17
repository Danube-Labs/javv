"""M2 Slice 2 — the automated restore drill (the PLAN gate, NFR-6). Seed a known current-state
`findings` doc (+ a `system-config` snapshot-repo ref) → snapshot → drop the index → `_restore`
into a FRESH index prefix → assert the restored `_source` is byte-equal to the checked-in golden
seed. This is the anti-regression anchor for the durability contract: if a node dies, triage state
comes back exactly.

Needs a real OpenSearch with `path.repo` set (dev compose + CI service both point it at
`/usr/share/opensearch/data/snapshots`); skipped when unreachable."""

import contextlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.admin.snapshot import (
    DURABILITY_INDICES,
    SnapshotRepoRef,
    read_snapshot_repo_ref,
    register_repository,
    restore_snapshot,
    take_snapshot,
    write_snapshot_repo_ref,
)
from backend.core.bootstrap import bootstrap
from os_env import OS_URL, drop_prefix, requires_opensearch

# fs repo root configured via path.repo on the cluster; each drill uses a unique subdir under it
PATH_REPO = os.environ.get("JAVV_SNAPSHOT_PATH_REPO", "/usr/share/opensearch/data/snapshots")
GOLDEN = Path(__file__).parent / "fixtures" / "findings-seed-golden.json"


@pytest.fixture
async def drill():
    """A real client + isolated names (index prefix, repo, fs location). Tears down snapshots,
    the repo, and every index the drill created (source + restored)."""
    c = AsyncOpenSearch(hosts=[OS_URL])
    token = uuid4().hex[:8]
    prefix = f"pytest-{token}-"
    repo = f"pytest-repo-{token}"
    try:
        yield c, prefix, repo, token
    finally:
        with contextlib.suppress(NotFoundError):
            await c.snapshot.delete(repository=repo, snapshot="_all")
        with contextlib.suppress(NotFoundError):
            await c.snapshot.delete_repository(repository=repo)
        await drop_prefix(c, prefix)
        with contextlib.suppress(NotFoundError):  # restores bring indices back, never templates
            await c.indices.delete(index=f"restored-{prefix}*")
        await c.close()


async def _seed(client: AsyncOpenSearch, prefix: str) -> dict:
    await bootstrap(client, prefix=prefix)
    seed = json.loads(GOLDEN.read_text())
    await client.index(
        index=f"{prefix}findings", id=seed["finding_key"], body=seed, params={"refresh": "true"}
    )
    ref = SnapshotRepoRef(repository="prod-repo", type="fs", settings={"location": "/data/snap"})
    await write_snapshot_repo_ref(client, ref, updated_by="admin", prefix=prefix)
    return seed


@requires_opensearch
async def test_restore_drill_round_trips_current_state(drill) -> None:
    c, prefix, repo, token = drill
    seed = await _seed(c, prefix)

    # register the fs repo at a unique location, snapshot the whole prefixed set
    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    await register_repository(c, ref)
    await take_snapshot(c, repository=repo, snapshot="drill", indices=f"{prefix}*")

    # simulate loss, then restore into a FRESH prefix (rename) so nothing collides
    await c.indices.delete(index=f"{prefix}findings")
    await restore_snapshot(
        c,
        repository=repo,
        snapshot="drill",
        indices=f"{prefix}findings",
        rename_pattern="(.+)",
        rename_replacement="restored-$1",
    )
    await c.indices.refresh(index=f"restored-{prefix}findings")

    got = await c.get(index=f"restored-{prefix}findings", id=seed["finding_key"])
    assert got["_source"] == seed  # byte-equal, incl. triage fields + explicit nulls


@requires_opensearch
async def test_restore_brings_back_system_config_ref(drill) -> None:
    c, prefix, repo, token = drill
    await _seed(c, prefix)
    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    await register_repository(c, ref)
    await take_snapshot(c, repository=repo, snapshot="drill", indices=f"{prefix}*")

    await c.indices.delete(index=f"{prefix}system-config")
    await restore_snapshot(c, repository=repo, snapshot="drill", indices=f"{prefix}system-config")
    await c.indices.refresh(index=f"{prefix}system-config")

    # the repo ref persisted in system-config survives the round-trip
    restored = await read_snapshot_repo_ref(c, prefix=prefix)
    assert restored is not None
    assert restored.repository == "prod-repo"


@requires_opensearch
async def test_renamed_restore_never_steals_the_live_write_alias(drill) -> None:
    """The M9e panel bug: a snapshot of an ALIASED series index restored under a rename used to
    bring the original write alias along — two write indices on one alias, illegal_state, restore
    aborted. Renamed copies must come back alias-free with the live series untouched."""
    c, prefix, repo, token = drill
    alias = f"{prefix}javv-images-drill"
    index = f"{alias}-000001"
    await c.indices.create(index=index, body={"aliases": {alias: {"is_write_index": True}}})
    await c.index(index=alias, body={"image_digest": "sha256:d"}, params={"refresh": "true"})

    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    await register_repository(c, ref)
    await take_snapshot(c, repository=repo, snapshot="drill", indices=index)

    await restore_snapshot(
        c,
        repository=repo,
        snapshot="drill",
        indices=index,
        rename_pattern="(.+)",
        rename_replacement="restored-$1",
    )
    await c.indices.refresh(index=f"restored-{index}")

    restored_aliases = (await c.indices.get_alias(index=f"restored-{index}"))[f"restored-{index}"][
        "aliases"
    ]
    assert restored_aliases == {}  # the copy never carries the live alias
    live = await c.indices.get_alias(name=alias)
    assert list(live.keys()) == [index]  # the live series kept its single write index


@requires_opensearch
async def test_restore_is_repeatable_no_partial_state(drill) -> None:
    c, prefix, repo, token = drill
    seed = await _seed(c, prefix)
    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    await register_repository(c, ref)
    await take_snapshot(c, repository=repo, snapshot="drill", indices=f"{prefix}findings")

    async def restore_once() -> dict:
        with contextlib.suppress(NotFoundError):
            await c.indices.delete(index=f"restored-{prefix}findings")
        await restore_snapshot(
            c,
            repository=repo,
            snapshot="drill",
            indices=f"{prefix}findings",
            rename_pattern="(.+)",
            rename_replacement="restored-$1",
        )
        await c.indices.refresh(index=f"restored-{prefix}findings")
        return (await c.get(index=f"restored-{prefix}findings", id=seed["finding_key"]))["_source"]

    # a clean overwrite (delete → restore) is deterministic: same result twice, no partial state
    assert await restore_once() == seed
    assert await restore_once() == seed


def _prefixed(expr: str, prefix: str) -> str:
    """The durability expression for a prefixed index set; an exclusion keeps its leading `-`."""
    return ",".join(
        f"-{prefix}{part[1:]}" if part.startswith("-") else f"{prefix}{part}"
        for part in expr.split(",")
    )


async def test_durability_snapshot_holds_users_and_tokens_but_not_sessions(drill) -> None:
    # issue 892: a restored copy of system-sessions would bring back sessions that signed out
    # after the snapshot (sign-out only sets `revoked`), so the durability set leaves it out
    c, prefix, repo, token = drill
    await bootstrap(c, prefix=prefix)
    ref = SnapshotRepoRef(repository=repo, type="fs", settings={"location": f"{PATH_REPO}/{token}"})
    await register_repository(c, ref)
    await take_snapshot(
        c, repository=repo, snapshot="drill", indices=_prefixed(DURABILITY_INDICES, prefix)
    )
    info = await c.snapshot.get(repository=repo, snapshot="drill")
    taken = set(info["snapshots"][0]["indices"])
    assert {f"{prefix}system-users", f"{prefix}system-tokens", f"{prefix}findings"} <= taken
    assert f"{prefix}system-sessions" not in taken
