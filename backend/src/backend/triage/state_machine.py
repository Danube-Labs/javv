"""The FR-7 triage state machine (M5b) — the two-field VEX model, pure and side-effect-free.

Constraints are TARGET-based (FR-7 defines no forbidden from→to pairs among human states — ruling
recorded here): `stale` is **system-only** (the M3 staleness sweep is its sole writer; a human
override FROM stale is fine and wins over the system flag), `resolved` is **manual-only** (a legal
human target; the scan pipeline expresses "gone" as `present=false`, never `state=resolved`), and
the CISA-five `vex_justification` is required **iff** the target is `not_affected` — on any other
target a justification is rejected rather than silently dropped. "False positive" is not a state:
it's `not_affected` + a component/code-not-present justification (a UI chip, FR-7)."""

STATES = frozenset({"open", "acknowledged", "not_affected", "risk_accepted", "resolved", "stale"})
HUMAN_TARGET_STATES = STATES - {"stale"}  # stale: staleness-sweep-only
CISA_JUSTIFICATIONS = frozenset(
    {
        "component_not_present",
        "vulnerable_code_not_present",
        "vulnerable_code_not_in_execute_path",
        "vulnerable_code_cannot_be_controlled_by_adversary",
        "inline_mitigations_already_exist",
    }
)


def holds_risk_accept(finding: dict) -> bool:
    """Does a state change on this finding undo a risk-accept? True for `risk_accepted`, and for
    a `stale` finding whose `pre_stale_status` the staleness sweep would restore to it (issue 892
    rulings 1 and 7)."""
    state = finding.get("state") or "open"
    return state == "risk_accepted" or (
        state == "stale" and finding.get("pre_stale_status") == "risk_accepted"
    )


class TransitionError(ValueError):
    """A rejected triage transition — the message is user-facing (422)."""


def validate_transition(current: str, target: str, *, vex_justification: str | None) -> None:
    """Raise TransitionError unless (current → target, justification) is a legal human action."""
    if current not in STATES:
        raise TransitionError(f"unknown current state {current!r}")
    if target not in STATES:
        raise TransitionError(f"unknown target state {target!r}")
    if target == "stale":
        raise TransitionError("stale is system-only — set by the staleness sweep, never by hand")
    if target == "not_affected":
        if vex_justification is None:
            raise TransitionError("not_affected requires a vex_justification (CISA five)")
        if vex_justification not in CISA_JUSTIFICATIONS:
            raise TransitionError(
                f"vex_justification must be one of the CISA five, got {vex_justification!r}"
            )
    elif vex_justification is not None:
        raise TransitionError("vex_justification is only valid with not_affected")
