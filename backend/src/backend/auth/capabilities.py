"""Capability gate (M5a, D33/SEC-2/SEC-9) — `require_capability(cap)` is THE enforcement
point: every mutating/protected route declares it and receives a `Principal`. 401 answers
"who are you"; 403 answers "you may not". A `must_change` session never reaches this gate: the
principal it depends on refuses it first (principal.py, SEC-6). Admin holds all via the `"*"`
marker.

Role bundles live in `system-roles` (doc `_id` = role); the defaults below seed once
(`op_type=create`) so an operator's customized bundle is never overwritten. Destructive caps
(`can_manage_*`, `can_restore_snapshot`, `can_drop_index`, `can_rebuild_state`) are Admin-only by
default and stay journaled (D17)."""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from opensearchpy import AsyncOpenSearch, NotFoundError
from opensearchpy.exceptions import ConflictError

from backend.auth.principal import Principal, get_current_principal
from backend.core.metrics import AUTH_FAILURES

ROLES_INDEX = "system-roles"

# the D33 defaults — Admin's "*" means every capability, present and future
ROLE_BUNDLES: dict[str, list[str]] = {
    "viewer": [],
    "triager": ["can_triage"],
    "security_lead": ["can_triage", "can_accept_audit_final"],  # SEC-2: gates risk-accept
    "admin": ["*"],
}


@dataclass(frozen=True)
class Permission:
    id: str
    name: str
    description: str


# Every permission a route checks, in the order of the table in docs/API.md, with the words the
# Roles card shows (issue 990). test_capability_catalog.py fails when a check is missing here.
PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        "can_triage",
        "Triage findings",
        "Change the state, assignee and notes of a finding. Make, change and revoke "
        "not-affected decisions.",
    ),
    Permission(
        "can_accept_audit_final",
        "Accept a risk",
        "Accept a risk, and change or undo an acceptance. Change the state of a finding with "
        "an accepted risk. Read and export the Approval list.",
    ),
    Permission(
        "can_manage_tokens", "Manage scanner tokens", "Make, revoke and rotate scanner tokens."
    ),
    Permission(
        "can_manage_users",
        "Manage users",
        "Make users. Change their role, status and password. Read the account events in the "
        "Audit log.",
    ),
    Permission(
        "can_manage_settings",
        "Manage settings",
        "Change the SLA, staleness, retirement and scan scope settings, and the cluster names. "
        "Retire a cluster and bring it back. Start the staleness sweep. Change or delete the "
        "saved views of other users.",
    ),
    Permission(
        "can_manage_retention",
        "Manage data and retention",
        "Change the retention, rollover, export lifetime and findings cleanup settings. Read and "
        "take snapshots. Delete a retired cluster.",
    ),
    Permission("can_restore_snapshot", "Restore a snapshot", "Restore the data from a snapshot."),
    Permission(
        "can_inspect_store",
        "Use the data inspector",
        "Read the store with the data inspector. Read the status of the background jobs.",
    ),
    Permission(
        "can_rebuild_state",
        "Rebuild the current state",
        "Start the job that builds the current state again.",
    ),
    Permission(
        "can_drop_index",
        "Delete old indices",
        "Start the lifecycle sweep, which deletes old indices.",
    ),
)


def holds(principal: Principal, capability: str) -> bool:
    """The gate's test, for a route that varies its answer instead of refusing it."""
    return "*" in principal.capabilities or capability in principal.capabilities


def holds_accept_final(principal: Principal) -> bool:
    """SEC-2: may this principal make, change or undo a risk-accept (issue 892)?"""
    return holds(principal, "can_accept_audit_final")


def accept_final_refusal(title: str) -> HTTPException:
    """The 403 for a risk-accept the principal may not make or undo, counted like the gate's."""
    AUTH_FAILURES.labels("missing_capability").inc()
    return HTTPException(403, title)


def require_capability(capability: str):
    """Dependency factory: `Depends(require_capability("can_triage"))` → the Principal."""

    async def _gate(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if "*" not in principal.capabilities and capability not in principal.capabilities:
            AUTH_FAILURES.labels("missing_capability").inc()  # M-5 (#220)
            raise HTTPException(403, "missing capability")
        return principal

    return _gate


async def resolve_role_capabilities(
    client: AsyncOpenSearch, role: str, *, prefix: str = ""
) -> list[str]:
    """A role's bundle from `system-roles`; unknown role = no capabilities (fail closed)."""
    try:
        doc = (await client.get(index=f"{prefix}{ROLES_INDEX}", id=role))["_source"]
    except NotFoundError:
        return []
    return list(doc.get("capabilities", []))


async def seed_default_roles(client: Any, *, prefix: str = "") -> int:
    """Seed the D33 default bundles once; existing (possibly customized) roles are untouched.
    Returns how many were created."""
    created = 0
    for role, capabilities in ROLE_BUNDLES.items():
        try:
            await client.index(
                index=f"{prefix}{ROLES_INDEX}",
                id=role,
                body={"role": role, "capabilities": capabilities},
                params={"op_type": "create", "refresh": "true"},
            )
            created += 1
        except ConflictError:
            continue
    return created
