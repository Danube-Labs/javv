"""The MCP token sign-in (issue 1096 step 2): a Bearer token → the principal `mcp:<name>` (D3).

The check reads only `system-mcp-tokens`, so a scanner token never signs in here and an MCP token
never passes `core/auth.py::require_token`. The answer to every refusal is the same 401, as for
the scanner tokens: no answer tells a missing token from a revoked or an expired one.

A token holds the permissions of its level (D5) and nothing else. The read tools widen it for
their read only (`reader`)."""

import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import structlog

from backend.auth.principal import Principal
from backend.core.security import hash_token, token_expired, tokens_match
from backend.core.settings import get_settings
from backend.routers.mcp_tokens import MCP_TOKENS_INDEX

log = structlog.get_logger()

PRINCIPAL_PREFIX = "mcp:"

# D5: the permissions of each level; the write routes check these, as for a user
LEVEL_CAPABILITIES: dict[str, frozenset[str]] = {
    "read": frozenset(),
    "write": frozenset({"can_triage"}),
    "write_risk_accept": frozenset({"can_triage", "can_accept_audit_final"}),
}

# the two permissions that a read route checks inside its body: the audit log shows account rows
# with the first and dashboard rows with the second, and the dashboard list shows each dashboard
# with the second. D4 gives a token every read, so a read tool adds them for its read only.
READ_WIDENING = frozenset({"can_manage_users", "can_manage_settings"})

_LAST_USE_EVERY_S = 60.0
_last_use: dict[str, float] = {}  # per process, like the rate limiters
_MAX_KEYS = 100_000


async def resolve(client: Any, header: str) -> Principal | None:
    """The principal of a live MCP token in `Authorization: Bearer <token>`, else None. The scheme
    name can have any case (RFC 7235, section 2.1): a client sends it as its config writes it."""
    scheme, _, raw = header.partition(" ")
    if scheme.lower() != "bearer" or not raw or len(header) > 512:
        return None
    candidate = hash_token(raw, pepper=get_settings().secret_key)
    hits = await client.search(
        index=MCP_TOKENS_INDEX,
        body={"query": {"term": {"token_hash": candidate}}, "size": 1},
    )
    docs = hits["hits"]["hits"]
    token = docs[0]["_source"] if docs else None
    if (
        token is None
        or not tokens_match(candidate, token["token_hash"])
        or token.get("disabled")
        or token_expired(token)
    ):
        return None
    name = token["name"]
    await _note_use(client, name)
    return Principal(
        user_id=f"{PRINCIPAL_PREFIX}{name}",
        username=f"{PRINCIPAL_PREFIX}{name}",
        role=None,
        capabilities=LEVEL_CAPABILITIES[token["level"]],
    )


def reader(principal: Principal) -> Principal:
    """The principal a read tool passes to its route function."""
    return replace(principal, capabilities=principal.capabilities | READ_WIDENING)


async def _note_use(client: Any, name: str) -> None:
    """`last_used_at`, at most one write a minute for each token. A failed write costs the
    caller nothing: the field only tells an admin that the token is in use."""
    now = time.monotonic()
    if now - _last_use.get(name, float("-inf")) < _LAST_USE_EVERY_S:
        return
    if len(_last_use) >= _MAX_KEYS:
        _last_use.clear()
    _last_use[name] = now
    try:
        await client.update(
            index=MCP_TOKENS_INDEX,
            id=name,
            body={"doc": {"last_used_at": datetime.now(UTC).isoformat()}},
        )
    except Exception:  # noqa: BLE001
        log.warning("mcp token last use not saved", token=name)
