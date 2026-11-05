"""The write tools of the MCP endpoint (issue 1096 step 3, D5). Each one is a route function,
through `tools.build`, and `needs` the permission that a token level gives. The route runs all of
its own checks: risk accept needs `can_accept_audit_final`, a finding with an accepted risk keeps
its state (issue 892), an expiry must be in the future (issue 984), a bulk change has its limits.

The two decision tools take the same three routes. Each one makes, changes and revokes only its own
types of decision, so a `write` token never sees a tool that accepts a risk."""

import functools
import inspect
from collections.abc import Callable
from typing import Any, Literal, cast

from fastapi import HTTPException, Request
from opensearchpy import NotFoundError

from backend.auth.capabilities import holds_accept_final
from backend.decisions.lifecycle import DECISIONS_INDEX, DecisionPayload
from backend.mcp.tools import Tool
from backend.routers import decisions, triage
from backend.routers.decisions import DecisionEditRequest
from backend.triage import bulk_routes

_REQUIRED = inspect.Parameter.empty
RiskAcceptType = Literal["risk_accepted", "ignore_rule"]  # both project state=risk_accepted


class NotAffected(DecisionPayload):
    type: Literal["not_affected"]  # pyright: ignore[reportIncompatibleVariableOverride]


class NotAffectedEdit(DecisionEditRequest):
    type: Literal["not_affected"] | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class RiskAccept(DecisionPayload):
    type: RiskAcceptType  # pyright: ignore[reportIncompatibleVariableOverride]


class RiskAcceptEdit(DecisionEditRequest):
    type: RiskAcceptType | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


def _own_types(route: Callable[..., Any], types: frozenset[str]) -> Callable[..., Any]:
    """The route, for a decision of these types only. A change keeps the type it does not set,
    so the type of the old decision decides which tool can change or revoke it."""

    @functools.wraps(route)  # the tool builder reads the signature of the route
    async def checked(*, request: Request, decision_id: str, **rest: Any) -> dict[str, Any]:
        client = cast(Any, request.app.state.opensearch)
        try:
            old = (await client.get(index=DECISIONS_INDEX, id=decision_id))["_source"]
        except NotFoundError:
            old = None  # the route gives its 404
        # an undo of a risk accept without the permission keeps the 403 of the route (issue 892)
        undo_refused = old is not None and old["type"] in decisions.ACCEPT_TYPES
        undo_refused = undo_refused and not holds_accept_final(rest["principal"])
        if old is not None and old["type"] not in types and not undo_refused:
            raise HTTPException(422, f"this tool does not take a {old['type']} decision")
        return await route(request=request, decision_id=decision_id, **rest)

    return checked


def _decision_routes(types: frozenset[str]) -> dict[str, Callable[..., Any]]:
    return {
        "make": decisions.create,
        "change": _own_types(decisions.edit, types),
        "revoke": _own_types(decisions.revoke, types),
    }


WRITE_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="set_triage",
        description=(
            "Set the state, the assignee or the note of one finding (finding_key from "
            "search_findings). A finding with an accepted risk keeps its state."
        ),
        routes={"": triage.triage},
        needs="can_triage",
    ),
    Tool(
        name="bulk_triage",
        description=(
            "Set the same state, assignee or note on all the present findings of one cluster "
            "that the selector finds (cve_id, image_digest, severity, state, assignee: at least "
            "one). A selection that is too large is refused: narrow it."
        ),
        routes={"": bulk_routes.bulk_triage},
        needs="can_triage",
    ),
    Tool(
        name="not_affected_decision",
        description=(
            "A Not affected decision for a CVE: kind make (payload), change (decision_id and "
            "body; a change revokes the decision and makes a new one) or revoke (decision_id)."
        ),
        routes=_decision_routes(frozenset({"not_affected"})),
        params={"payload": (NotAffected, _REQUIRED), "body": (NotAffectedEdit, _REQUIRED)},
        needs="can_triage",
    ),
    Tool(
        name="risk_accept_decision",
        description=(
            "A risk accept decision (type risk_accepted or ignore_rule) for a CVE, with an "
            "expiry: kind make (payload), change (decision_id and body) or revoke (decision_id)."
        ),
        routes=_decision_routes(decisions.ACCEPT_TYPES),
        params={"payload": (RiskAccept, _REQUIRED), "body": (RiskAcceptEdit, _REQUIRED)},
        needs="can_accept_audit_final",
    ),
)
