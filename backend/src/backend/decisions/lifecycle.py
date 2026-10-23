"""Decision immutable-write discipline (M5b, FR-8/D39-H5-r2/D40-G-r3). This module is the ONLY
write path to `system-decisions`; it exposes create / revoke / edit and nothing else — in-place
mutation has no API, and `revoked_at` is the single post-hoc stamp (a revocation is a forward
event, so past-T reconstruction never rewrites).

Edit = revoke + create-new under **one `effective_at`** (`revoked_at(old) = created_at(new)`),
the NEW doc carrying the pair's `operation_id`. Write order: **new first, then revoke old** — a
crash between the two leaves a moment of overlap (duplicate coverage, harmless) rather than a gap
where a risk-acceptance silently lapses; M5c's projection runs only once both are visible
(pair-detected via `operation_id` + the shared timestamp). Every lifecycle event is journaled
(D17). Precedence/expiry-refresh/projection itself is M5c."""

from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import uuid4

from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConflictError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.audit.writer import append_field_change
from backend.core.identifiers import ClusterId
from backend.triage.state_machine import CISA_JUSTIFICATIONS

DECISIONS_INDEX = "system-decisions"
DECISION_SCHEMA_VERSION = 1  # the decision DOC contract — this module owns bumps
_CAS_RETRIES = 8


def expiry_has_passed(expiry: str | None, now: datetime) -> bool:
    """True when a decision with this `expiry` is no longer active at `now`. A bare date stops at
    00:00 UTC on that day, because `is_active_at` compares it as text against UTC stamps, so a
    date of today has passed too (issue 984). A value the format check refuses is left to it."""
    if expiry is None:
        return False
    if len(expiry) == 10:  # bare date shape
        try:
            return date.fromisoformat(expiry) <= now.astimezone(UTC).date()
        except ValueError:
            return False
    try:
        parsed = datetime.fromisoformat(expiry)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= now


class DecisionScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    namespaces: list[str] = Field(default=[], max_length=1024)
    images: list[str] = Field(default=[], max_length=1024)  # both empty = cluster-wide


class DecisionPayload(BaseModel):
    """What a human decides — identity/lifecycle stamps are minted here, never client-supplied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["risk_accepted", "ignore_rule", "not_affected"]
    cve_id: str = Field(min_length=1, max_length=256)
    scope: DecisionScope
    apply_both_scanners: bool  # semantics pinned (D22)
    # D22's scanner dimension needs a subject: which scanner a scanner-specific decision is FOR.
    # Required iff not apply-both; forbidden with apply-both (contradictory input = reject).
    scanner: Literal["trivy", "grype"] | None = None
    vex_justification: str | None = Field(default=None, max_length=128)
    justification: str = Field(min_length=1, max_length=10_000)
    expiry: str | None = None  # ISO date; IMMUTABLE after creation — change = revoke+create
    cluster_id: ClusterId  # the ONE shared shape (task E / audit M2)

    @field_validator("expiry")
    @classmethod
    def _expiry_is_iso_8601(cls, v: str | None) -> str | None:
        # A-m7: `expiry` maps to a `date` — free text either 500s the create or (epoch-millis)
        # compares lexicographically wrong against ISO stamps in is_active_at. Require a bare ISO
        # date (YYYY-MM-DD) or a tz-aware ISO-8601 datetime; reject naive/garbage at the door.
        if v is None:
            return v
        msg = "expiry must be an ISO-8601 date (YYYY-MM-DD) or a timezone-aware datetime"
        if len(v) == 10:  # bare date shape
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError(msg) from None
            return v
        try:
            parsed = datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(msg) from None
        if parsed.tzinfo is None:
            raise ValueError("expiry datetime must be timezone-aware")
        # stored in UTC: is_active_at compares it as text against UTC stamps (issue 706)
        return parsed.astimezone(UTC).isoformat()

    @model_validator(mode="after")
    def _scanner_iff_specific(self) -> "DecisionPayload":
        if self.apply_both_scanners and self.scanner is not None:
            raise ValueError("scanner must be unset when apply_both_scanners is true")
        if not self.apply_both_scanners and self.scanner is None:
            raise ValueError("a scanner-specific decision requires `scanner` (trivy|grype)")
        return self

    @model_validator(mode="after")
    def _vex_iff_not_affected(self) -> "DecisionPayload":
        # A-M2: mirror the triage state machine — a not_affected decision REQUIRES a CISA-five
        # justification (the projector copies it verbatim into findings → VEX export), and a
        # justification on any other type is a contradiction, rejected rather than dropped.
        if self.type == "not_affected":
            if self.vex_justification is None:
                raise ValueError("a not_affected decision requires a vex_justification (CISA five)")
            if self.vex_justification not in CISA_JUSTIFICATIONS:
                raise ValueError(
                    "vex_justification must be one of the CISA five, "
                    f"got {self.vex_justification!r}"
                )
        elif self.vex_justification is not None:
            raise ValueError("vex_justification is only valid on a not_affected decision")
        return self


async def create_decision(
    client: AsyncOpenSearch,
    *,
    actor: str,
    payload: DecisionPayload,
    effective_at: str | None = None,
    operation_id: str | None = None,
    reproject: bool = True,
    prefix: str = "",
) -> dict[str, Any]:
    """Mint an immutable decision doc; returns it. `effective_at`/`operation_id` are only passed
    by `edit_decision` (the revoke+create pair) — a plain create mints its own."""
    now = effective_at or datetime.now(UTC).isoformat()
    doc: dict[str, Any] = {
        **payload.model_dump(),
        "decision_id": uuid4().hex,
        "created_by": actor,
        "created_at": now,
        "effective_at": now,
        "operation_id": operation_id or uuid4().hex,
        "revoked_at": None,
        "schema_version": DECISION_SCHEMA_VERSION,
    }
    # journal-first (D17, audit #188): the row lands before the decision doc, so an audit failure
    # 500s WITHOUT a live-but-unjournaled decision — the client retry mints a fresh id and re-drives
    # (no orphan CHANGE; an orphan ROW for a doc that never landed is the tolerated direction).
    await append_field_change(
        client,
        actor=actor,
        action="decision_create",
        entity_type="decision",
        entity_id=doc["decision_id"],
        decision_id=doc["decision_id"],
        field="lifecycle",
        old_value=None,
        new_value="active",
        revision=1,
        cluster_id=payload.cluster_id,
        prefix=prefix,
    )
    await client.index(
        index=f"{prefix}{DECISIONS_INDEX}",
        id=doc["decision_id"],
        body=doc,
        params={"op_type": "create", "refresh": "true"},  # immutable — never an overwrite
    )
    if reproject:  # False only inside edit_decision — projection waits for the PAIR (D40/G-r3)
        from backend.decisions.reproject import reproject_cve

        await reproject_cve(client, payload.cluster_id, payload.cve_id, prefix=prefix)
    return doc


async def revoke_decision(
    client: AsyncOpenSearch,
    *,
    actor: str,
    decision_id: str,
    effective_at: str | None = None,
    reproject: bool = True,
    prefix: str = "",
) -> dict[str, Any]:
    """Stamp `revoked_at` — the ONLY legal post-hoc mutation. Refuses a second revocation.

    CAS'd on `if_seq_no`/`if_primary_term` (audit M-2, task A): the stamp is single-writer —
    a racing revoke loses the CAS, re-reads, and gets the same "already revoked" refusal a
    late sequential caller would. Check-then-act alone let the second racer overwrite the
    immutable stamp (corrupting past-T reconstruction)."""
    index = f"{prefix}{DECISIONS_INDEX}"
    for _ in range(_CAS_RETRIES):
        got = await client.get(index=index, id=decision_id)
        current = got["_source"]
        if current.get("revoked_at") is not None:
            raise ValueError(f"decision {decision_id} is already revoked")
        at = effective_at or datetime.now(UTC).isoformat()
        # journal-first with a DETERMINISTIC id (audit #188): the row lands before the CAS, so an
        # audit failure means the revoke never stamps and a retry re-drives it; and the id dedups
        # so concurrent revokes + retries yield EXACTLY ONE row (op_type=create), preserving the
        # single-writer invariant (`test_concurrent_revokes_cannot_double_stamp_revoked_at`).
        await append_field_change(
            client,
            actor=actor,
            action="decision_revoke",
            entity_type="decision",
            entity_id=decision_id,
            decision_id=decision_id,
            field="lifecycle",
            old_value="active",
            new_value="revoked",
            revision=2,
            cluster_id=current["cluster_id"],
            event_id=f"decision-revoke:{decision_id}",
            prefix=prefix,
        )
        try:
            await client.update(
                index=index,
                id=decision_id,
                body={"doc": {"revoked_at": at}},
                params={
                    "if_seq_no": got["_seq_no"],
                    "if_primary_term": got["_primary_term"],
                    "refresh": "true",
                },
            )
        except ConflictError:
            continue  # a racer stamped first — the re-read above raises "already revoked"
        if reproject:  # False only inside edit_decision (the pair reprojects once, at the end)
            from backend.decisions.reproject import reproject_cve

            await reproject_cve(client, current["cluster_id"], current["cve_id"], prefix=prefix)
        return {**current, "revoked_at": at}
    raise RuntimeError(f"decision revoke: CAS conflicts did not drain for {decision_id}")


async def edit_decision(
    client: AsyncOpenSearch,
    *,
    actor: str,
    decision_id: str,
    changes: dict[str, Any],
    prefix: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The ONLY way to change a decision: revoke + create-new under one `effective_at` and one
    `operation_id` (carried by the new doc). Returns (revoked_old, new). New lands FIRST —
    overlap over gap."""
    index = f"{prefix}{DECISIONS_INDEX}"
    old = (await client.get(index=index, id=decision_id))["_source"]
    if old.get("revoked_at") is not None:
        raise ValueError(f"decision {decision_id} is already revoked — edit the active one")

    effective_at = datetime.now(UTC).isoformat()
    payload_fields = set(DecisionPayload.model_fields)
    if unknown := set(changes) - payload_fields:
        raise ValueError(f"not editable: {sorted(unknown)}")
    payload = DecisionPayload.model_validate(
        {**{k: v for k, v in old.items() if k in payload_fields}, **changes}
    )
    new = await create_decision(
        client,
        actor=actor,
        payload=payload,
        effective_at=effective_at,
        operation_id=uuid4().hex,
        reproject=False,
        prefix=prefix,
    )
    try:
        revoked = await revoke_decision(
            client,
            actor=actor,
            decision_id=decision_id,
            effective_at=effective_at,
            reproject=False,
            prefix=prefix,
        )
    except ValueError:
        # A concurrent revoke/edit won the old doc (audit M-2, task A): withdraw our successor —
        # overlap is a crash allowance, never a licence for two active decisions. The
        # compensating revoke is journaled like any other, so the trail shows the lost race.
        await revoke_decision(
            client,
            actor=actor,
            decision_id=new["decision_id"],
            effective_at=effective_at,
            prefix=prefix,
        )
        raise
    # projection deferred until BOTH writes of the operation_id landed (D40/G-r3)
    from backend.decisions.reproject import reproject_cve

    await reproject_cve(client, payload.cluster_id, payload.cve_id, prefix=prefix)
    return revoked, new
