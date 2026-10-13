"""The structured `system-audit-log` writer (M5b, D32/D17) — the ONE way audit rows are written.

One immutable row per field change (never prose); the row `_id` IS the `event_id` and every write
is `op_type=create`, so the log is **append-only by construction** — an overwrite is impossible in
code, and SEC-1's create-only OpenSearch role is the deploy-time backstop (Helm/M10). Replay
contract (D40/H-r3, D39/H6-r2): order rows by `(@timestamp, event_id)`; same-`(entity, field)`
edits order **by `revision`** (the finding's resulting CAS version) — no monotonic global counter.
Writes go through the `system-audit-log` write alias (M4 convention).

`append_field_change` RAISES on failure — a triage action without its journal row must fail (D17;
the caller's retry may produce a duplicate row for the same `revision`, which replay tolerates:
latest-per-field by revision is idempotent to duplicates).

`append_auth_event` has TWO policies (audit #188): **fire-and-forget for sign-in and sign-out**
(`strict=False`, default — an audit hiccup must never take down login/logout, an availability
tradeoff), and **strict for admin/token/config mutations and every password change**
(`strict=True` — those are correctness-critical audit trails; a mutation must never be left
applied-but-unjournaled, so the append raises and the caller journals BEFORE it mutates). A user's
own password change, the forced first one included, joined the strict side by operator ruling
(issue 833); #188 had left it with sign-in. Callers on the mutation paths append first, so an audit
failure means the mutation never happens and a retry re-drives it cleanly.

An optional explicit `event_id` makes an append **idempotent** (op_type=create → a duplicate id is
a replay, not a failure): a deterministic id lets a one-shot mutation (e.g. a decision revoke)
journal-first and still yield exactly one row under concurrent callers.

Versioning: `AUDIT_SCHEMA_VERSION` is the audit ROW contract, independent of the ingest
envelope's wire version. This module owns bumps."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConflictError

from backend.services.aliases import ensure_write_alias

log = structlog.get_logger()

ALIAS = "system-audit-log"
AUDIT_SCHEMA_VERSION = 1

_TEXT_FIELDS = frozenset({"notes"})  # everything else on findings is scalar


async def _append(
    client: AsyncOpenSearch, doc: dict[str, Any], *, prefix: str, event_id: str | None = None
) -> str:
    explicit = event_id is not None  # a deterministic id → op_type=create dedups a replay
    event_id = event_id or uuid4().hex
    alias = f"{prefix}{ALIAS}"
    await ensure_write_alias(client, alias)
    try:
        await client.index(
            index=alias,
            id=event_id,  # _id = event_id + op_type=create ⇒ append-only by construction
            body={
                "@timestamp": datetime.now(UTC).isoformat(),
                "event_id": event_id,
                "schema_version": AUDIT_SCHEMA_VERSION,
                **{k: v for k, v in doc.items() if v is not None},
            },
            # refresh=true → read-your-writes: the detail screen refetches its activity feed
            # right after the action returns (A-m2/#191: writes refresh, reads never force one).
            # All callers are human-rate (triage/decisions/auth) — never the ingest hot path.
            params={"op_type": "create", "refresh": "true"},
        )
    except ConflictError:
        if not explicit:
            raise  # a random-uuid collision is a real (astronomically rare) error, never swallow
        # an explicit id already present = this exact event is already journaled (idempotent replay)
    return event_id


async def append_field_change(
    client: AsyncOpenSearch,
    *,
    actor: str,
    action: str,  # assign|note|acknowledge|risk_accept|not_affected|resolve|reopen|…
    entity_type: str,  # finding|decision|…
    entity_id: str,
    field: str,
    old_value: str | None,
    new_value: str | None,
    revision: int,
    cluster_id: str | None,  # None = fleet-wide; the Audit screen shows those, a literal wouldn't
    finding_key: str | None = None,
    decision_id: str | None = None,
    old_value_json: dict[str, Any] | None = None,
    new_value_json: dict[str, Any] | None = None,  # non-scalar payload riding the row (D38/H8)
    event_id: str | None = None,  # deterministic id → journal-first stays idempotent (audit #188)
    prefix: str = "",
) -> str:
    """One structured row for one field change (D32). Raises on failure — no row, no action.
    Callers journal-first, so the raise leaves no applied-but-unjournaled change (D17/#188)."""
    try:
        return await _append(
            client,
            {
                "actor": actor,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "finding_key": finding_key,
                "decision_id": decision_id,
                "field": field,
                "field_type": "text" if field in _TEXT_FIELDS else "scalar",
                "old_value": old_value,
                "new_value": new_value,
                "old_value_json": old_value_json,
                "new_value_json": new_value_json,
                "revision": revision,
                "cluster_id": cluster_id,
            },
            prefix=prefix,
            event_id=event_id,
        )
    except Exception:  # structured signal for ops before the 5xx; values are never logged
        log.error(
            "audit append failed", action=action, entity_type=entity_type, entity_id=entity_id
        )
        raise


async def append_auth_event(
    client: AsyncOpenSearch,
    *,
    actor: str,
    action: str,  # login|logout|pwd_change|role_change|token_mint|token_revoke
    entity_type: str,  # user|token|session
    entity_id: str,
    cluster_id: str | None = None,
    strict: bool = False,
    event_id: str | None = None,
    prefix: str = "",
) -> None:
    """Auth/admin events. `strict=False` (login/logout) is fire-and-forget — an audit hiccup must
    never take down auth. `strict=True` (admin/token/config mutations, audit #188, and password
    changes, issue 833) RE-RAISES after logging, so the caller — which journals BEFORE it mutates —
    leaves no applied-but-unjournaled change (D17)."""
    try:
        await _append(
            client,
            {
                "actor": actor,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "cluster_id": cluster_id,
            },
            prefix=prefix,
            event_id=event_id,
        )
    except Exception:  # noqa: BLE001
        log.error("audit append failed", action=action, entity_type=entity_type)
        if strict:  # a correctness-critical mutation trail — surface the failure, don't swallow it
            raise
