"""Decision input validation (A-M2 / A-m7, issue 706): pure model and projector checks. They need
no store, so this module carries no store guard and they run in every environment."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.decisions.lifecycle import DecisionPayload, expiry_has_passed
from backend.decisions.projection import is_active_at

# --- A-M2 / A-m7: decision input validation (audit #185) -----------------------------


def _vex_base(**over) -> dict:
    return {
        "type": "not_affected",
        "cve_id": "CVE-1",
        "scope": {"namespaces": [], "images": []},
        "apply_both_scanners": True,
        "justification": "j",
        "cluster_id": "c-decisions",
        **over,
    }


def test_not_affected_decision_requires_a_cisa_justification() -> None:
    """A-M2: a not_affected decision without a CISA-five justification would project a null
    justification → invalid OpenVEX / a 500 on CycloneDX. Reject it at the model."""
    with pytest.raises(ValidationError, match="not_affected"):
        DecisionPayload.model_validate(_vex_base(vex_justification=None))
    with pytest.raises(ValidationError, match="CISA"):
        DecisionPayload.model_validate(_vex_base(vex_justification="because"))
    ok = DecisionPayload.model_validate(_vex_base(vex_justification="component_not_present"))
    assert ok.vex_justification == "component_not_present"


def test_justification_rejected_on_a_non_not_affected_decision() -> None:
    """A-M2: a justification only means something for not_affected — reject it elsewhere rather
    than silently drop it (mirrors the triage state machine)."""
    with pytest.raises(ValidationError, match="not_affected"):
        DecisionPayload.model_validate(
            _vex_base(type="risk_accepted", vex_justification="component_not_present")
        )


def test_expiry_must_be_iso_8601_date_or_aware_datetime() -> None:
    """A-m7: unvalidated expiry free-text either 500s the create (bad `date` mapping input) or,
    as epoch-millis, compares lexicographically wrong against ISO stamps in is_active_at."""
    base = _vex_base(type="risk_accepted", vex_justification=None)
    for bad in ("banana", "1800000000000", "2026-13-01", "2026-01-01T00:00:00"):  # last = naive
        with pytest.raises(ValidationError, match="expiry"):
            DecisionPayload.model_validate({**base, "expiry": bad})
    assert DecisionPayload.model_validate({**base, "expiry": "2026-12-31"}).expiry == "2026-12-31"
    aware = "2026-12-31T00:00:00+00:00"
    assert DecisionPayload.model_validate({**base, "expiry": aware}).expiry == aware
    assert DecisionPayload.model_validate({**base, "expiry": None}).expiry is None


def test_a_datetime_expiry_is_stored_in_utc() -> None:
    """Issue 706: `is_active_at` compares expiry as text against UTC stamps, so an offset kept
    as typed moved the expiry instant by the size of the offset (up to 14 hours)."""
    base = _vex_base(type="risk_accepted", vex_justification=None)
    stored = DecisionPayload.model_validate({**base, "expiry": "2026-10-02T23:00:00+02:00"}).expiry
    assert stored == "2026-10-02T21:00:00+00:00"
    zulu = DecisionPayload.model_validate({**base, "expiry": "2026-12-31T00:00:00Z"}).expiry
    assert zulu == "2026-12-31T00:00:00+00:00"
    decision = {"created_at": "2026-10-01T00:00:00+00:00", "revoked_at": None, "expiry": stored}
    assert not is_active_at(decision, "2026-10-02T22:00:00+00:00")  # an hour past the instant


# --- issue 984: an expiry that has passed --------------------------------------------------

NOON = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def test_a_date_passes_at_the_start_of_that_day_in_utc() -> None:
    """A bare date stops at 00:00 UTC on that day, so today has passed and tomorrow has not."""
    assert expiry_has_passed("2026-09-30", NOON)
    assert expiry_has_passed("2026-10-23", NOON)
    assert not expiry_has_passed("2026-10-24", NOON)


def test_the_utc_day_decides_not_the_day_of_the_given_clock() -> None:
    # 01:00 on 24 October at +03:00 is still 23 October in UTC: the 24th has not passed
    late = datetime.fromisoformat("2026-10-24T01:00:00+03:00")
    assert not expiry_has_passed("2026-10-24", late)
    assert expiry_has_passed("2026-10-23", late)


def test_a_date_and_time_passes_at_that_instant() -> None:
    assert expiry_has_passed("2026-10-23T12:00:00+00:00", NOON)  # dead AT the expiry
    assert expiry_has_passed("2026-10-23T13:59:00+02:00", NOON)  # 11:59 UTC
    assert not expiry_has_passed("2026-10-23T12:01:00+00:00", NOON)


def test_the_same_rule_as_is_active_at() -> None:
    """The route refuses what the projection would treat as dead at the moment of the write."""
    at = NOON.isoformat()
    for expiry in (
        "2026-10-22",
        "2026-10-23",
        "2026-10-24",
        "2026-10-23T12:00:00+00:00",
        "2026-10-23T12:00:01+00:00",
    ):
        decision = {"created_at": at, "revoked_at": None, "expiry": expiry}
        assert expiry_has_passed(expiry, NOON) is not is_active_at(decision, at), expiry


def test_no_expiry_and_an_unreadable_one_are_left_to_the_format_check() -> None:
    assert not expiry_has_passed(None, NOON)
    assert not expiry_has_passed("banana", NOON)
    assert not expiry_has_passed("2026-13-40", NOON)
    assert not expiry_has_passed("2026-10-01T00:00:00", NOON)  # no zone: the model refuses it
