"""M2 snapshot/restore admin helpers (durability early, NFR-6). Register a snapshot repository,
persist only the repo *ref* in `system-config`, and trigger on-demand snapshots. Used by the
restore-drill harness and, later, the FR-19 "Data & OpenSearch" admin panel.

**Credentials never land in `system-config`** — they live in the OpenSearch keystore
(`s3.client.default.*`). `SnapshotRepoRef` enforces this structurally with a per-type settings
**allowlist**: a credential key (`secret_key`, `access_key`, …) isn't in the allowlist, so it's a
validation error at the boundary, never a silently-persisted secret (SEC / security-and-hardening).
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, field_validator

from backend.core.stored_settings import parse_stored_setting

SNAPSHOT_REPO_KEY = "snapshot_repo"  # the system-config doc _id holding the repo ref

# the durability set — current-state + config indices snapshotted on schedule (NFR-6). The bulky
# per-cluster append series (occurrences) are snapshotted less often / separately (DR RPO note).
# system-sessions stays out: sign-out only sets `revoked`, so a restored copy would revive
# sessions that ended after the snapshot, for the rest of their lifetime (issue 892).
DURABILITY_INDICES = "findings,javv-images-*,system-*,-system-sessions"

# Only these repo-settings keys may be persisted — non-secret location/addressing settings. Anything
# else (notably credentials) is refused. Allowlist, not denylist: safe by construction.
_ALLOWED_SETTINGS: dict[str, frozenset[str]] = {
    "fs": frozenset(
        {
            "location",
            "compress",
            "chunk_size",
            "readonly",
            "max_snapshot_bytes_per_sec",
            "max_restore_bytes_per_sec",
        }
    ),
    "s3": frozenset(
        {
            "bucket",
            "base_path",
            "endpoint",
            "region",
            "path_style_access",
            "compress",
            "readonly",
            "server_side_encryption",
            "storage_class",
        }
    ),
}


class SnapshotRepoRef(BaseModel):
    """The non-secret reference to a registered snapshot repository (stored in system-config)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str  # the repo name registered in OpenSearch
    type: Literal["fs", "s3"]
    settings: Mapping[str, str | int | bool]

    @field_validator("settings")
    @classmethod
    def _allowlist_settings(
        cls, v: Mapping[str, str | int | bool], info: Any
    ) -> Mapping[str, str | int | bool]:
        repo_type = info.data.get("type")
        if repo_type is None:  # `type` failed its own validation — let that error surface first
            return v
        allowed = _ALLOWED_SETTINGS[repo_type]
        rejected = set(v) - allowed
        if rejected:
            raise ValueError(
                f"disallowed {repo_type} repo settings {sorted(rejected)}; "
                f"credentials belong in the OpenSearch keystore, not system-config"
            )
        return v


def repository_body(ref: SnapshotRepoRef) -> dict[str, Any]:
    """The `_snapshot/<repo>` registration body (no credentials — those are keystore-supplied)."""
    return {"type": ref.type, "settings": dict(ref.settings)}


async def register_repository(client: AsyncOpenSearch, ref: SnapshotRepoRef) -> None:
    """Register (or update) the snapshot repository. Idempotent — the same body is a no-op."""
    await client.snapshot.create_repository(repository=ref.repository, body=repository_body(ref))


async def write_snapshot_repo_ref(
    client: AsyncOpenSearch,
    ref: SnapshotRepoRef,
    *,
    updated_by: str,
    prefix: str = "",
) -> None:
    """Persist the repo ref in system-config under a fixed id (single-doc config key)."""
    doc = {
        "key": SNAPSHOT_REPO_KEY,
        "value": ref.model_dump(),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": updated_by,
    }
    await client.index(
        index=f"{prefix}system-config",
        id=SNAPSHOT_REPO_KEY,
        body=doc,
        params={"refresh": "true"},
    )


async def read_snapshot_repo_ref(
    client: AsyncOpenSearch, *, prefix: str = ""
) -> SnapshotRepoRef | None:
    """Read the repo ref from system-config, or None if it hasn't been configured yet."""
    try:
        got = await client.get(index=f"{prefix}system-config", id=SNAPSHOT_REPO_KEY)
    except NotFoundError:
        return None
    return parse_stored_setting(SnapshotRepoRef, got["_source"]["value"], key=SNAPSHOT_REPO_KEY)


async def take_snapshot(
    client: AsyncOpenSearch,
    *,
    repository: str,
    snapshot: str,
    indices: str,
    wait: bool = True,
) -> dict[str, Any]:
    """Trigger an on-demand snapshot of `indices` into `repository`. `include_global_state=False`
    keeps it index-scoped (cluster settings/templates aren't part of the durability contract)."""
    return await client.snapshot.create(
        repository=repository,
        snapshot=snapshot,
        body={"indices": indices, "include_global_state": False},
        params={"wait_for_completion": "true" if wait else "false"},
    )


async def restore_snapshot(
    client: AsyncOpenSearch,
    *,
    repository: str,
    snapshot: str,
    indices: str,
    rename_pattern: str | None = None,
    rename_replacement: str | None = None,
    wait: bool = True,
) -> dict[str, Any]:
    """Restore `indices` from a snapshot. Optional rename (`rename_pattern`/`rename_replacement`)
    restores into a fresh index name — used by the restore drill to avoid colliding with the live
    index. OpenSearch refuses to restore over an open index, so the target must not exist yet.

    A renamed restore drops the snapshotted aliases: the copy would otherwise carry the ORIGINAL
    write alias and collide with the live write index (`illegal_state_exception`, two write
    indices on one alias) — a renamed copy must never steal the live series' aliases."""
    body: dict[str, Any] = {"indices": indices, "include_global_state": False}
    if rename_pattern is not None:
        body["rename_pattern"] = rename_pattern
        body["rename_replacement"] = rename_replacement
        body["include_aliases"] = False
    return await client.snapshot.restore(
        repository=repository,
        snapshot=snapshot,
        body=body,
        params={"wait_for_completion": "true" if wait else "false"},
    )


# --- scheduled snapshots (OpenSearch Snapshot Management) --------------------
# Native SM policy (`_plugins/_sm/policies`) — OpenSearch schedules + takes the snapshot itself, so
# no CronJob/broker is needed for the *taking* (coordination stays in OpenSearch). The retention/
# schedule settings are D26-configurable; these defaults are the starting policy. The k8s deploy
# manifests (repo registration + the restore-drill verify CronJob) are M10's, where the chart lives.


def snapshot_policy_body(
    *,
    repository: str,
    indices: str = DURABILITY_INDICES,
    creation_cron: str = "0 2 * * *",  # daily 02:00
    deletion_cron: str = "0 3 * * *",  # daily 03:00
    timezone: str = "UTC",
    retention_max_age: str = "30d",
    retention_min_count: int = 14,
    retention_max_count: int = 50,
    time_limit: str = "1h",
) -> dict[str, Any]:
    """Build an SM policy body: take a scheduled snapshot of `indices` into `repository`, and prune
    old snapshots by age/count (retention floor keeps at least `retention_min_count`).
    D26 settings."""
    return {
        "description": "JAVV automated durability snapshots (current-state + config indices)",
        "creation": {
            "schedule": {"cron": {"expression": creation_cron, "timezone": timezone}},
            "time_limit": time_limit,
        },
        "deletion": {
            "schedule": {"cron": {"expression": deletion_cron, "timezone": timezone}},
            "condition": {
                "max_age": retention_max_age,
                "min_count": retention_min_count,
                "max_count": retention_max_count,
            },
            "time_limit": time_limit,
        },
        "snapshot_config": {
            "repository": repository,
            "indices": indices,
            "include_global_state": False,
            "ignore_unavailable": True,
            "partial": False,
        },
    }


async def create_snapshot_policy(
    client: AsyncOpenSearch, name: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Register an SM policy. OpenSearch then takes + prunes snapshots on the policy's schedule."""
    return await client.transport.perform_request(
        "POST", f"/_plugins/_sm/policies/{name}", body=body
    )
