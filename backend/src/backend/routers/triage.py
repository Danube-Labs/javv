"""Triage route (M5b, FR-7) — `PATCH /api/v1/findings/{finding_key}/triage`, capability-gated
(`can_triage`; **risk-accept, and a state change away from one, additionally requires
`can_accept_audit_final`**, SEC-2/D33 and issue 892) and
registered in the standing RBAC/IDOR suite. The service does the CAS + journaling; this layer
only translates auth + errors (404 unknown finding, 422 illegal transition/patch, 403 caps)."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.auth.capabilities import accept_final_refusal, holds_accept_final, require_capability
from backend.auth.principal import Principal
from backend.triage.service import FindingNotFound, RiskAcceptLocked, TriagePatch, apply_triage
from backend.triage.state_machine import TransitionError

router = APIRouter(prefix="/api/v1/findings", tags=["triage"])

CanTriage = Annotated[Principal, Depends(require_capability("can_triage"))]


@router.patch("/{finding_key}/triage")
async def triage(
    request: Request, finding_key: str, patch: TriagePatch, principal: CanTriage
) -> dict[str, Any]:
    accept_final = holds_accept_final(principal)
    if patch.state == "risk_accepted" and not accept_final:
        raise accept_final_refusal("risk-accept requires can_accept_audit_final")
    client = cast(Any, request.app.state.opensearch)
    try:
        finding = await apply_triage(
            client,
            actor=principal.user_id,
            finding_key=finding_key,
            patch=patch,
            may_undo_risk_accept=accept_final,
        )
    except FindingNotFound:
        raise HTTPException(404, "finding not found") from None
    except RiskAcceptLocked:
        raise accept_final_refusal(
            "changing the state of a risk-accepted finding requires can_accept_audit_final"
        ) from None
    except TransitionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"finding": finding}
