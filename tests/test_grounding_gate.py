"""The grounding gate.

This module grows as the gate does: today it protects only the result contracts the four checks
report against, since the checks and the gate that runs them do not exist yet. The property worth
protecting here is that the fixed set of four cannot be misrepresented: a `GroundingResult` cannot
be built with a missing check, a duplicate check, or a verdict that omits the reason a reader would
need to diagnose it.
"""

from __future__ import annotations

import pytest

from opspilot.grounding.contracts import CheckName, CheckResult, GroundingResult

_ALL_PASSING = tuple(CheckResult(check=name, passed=True) for name in CheckName)


def _failing(
    passing: tuple[CheckResult, ...], check: CheckName, reason: str
) -> tuple[CheckResult, ...]:
    """`passing` with one check's verdict replaced by a named failure."""
    return tuple(
        CheckResult(check=check, passed=False, reason=reason) if result.check is check else result
        for result in passing
    )


# --- CheckResult -----------------------------------------------------------------------------
def test_a_passing_check_carries_no_reason():
    with pytest.raises(ValueError, match="no failure reason"):
        CheckResult(check=CheckName.REFERENCE_RESOLUTION, passed=True, reason="unused")


def test_a_failed_check_must_name_why():
    with pytest.raises(ValueError, match="must name why"):
        CheckResult(check=CheckName.REFERENCE_RESOLUTION, passed=False)


def test_a_failed_check_carries_its_reason():
    result = CheckResult(
        check=CheckName.UNSUPPORTED_ELEMENT_REJECTION, passed=False, reason="no current support"
    )
    assert result.reason == "no current support"


# --- GroundingResult: the fixed set of four ---------------------------------------------------
def test_exactly_four_checks_are_required():
    with pytest.raises(ValueError, match="exactly the four fixed checks"):
        GroundingResult(checks=_ALL_PASSING[:3])


def test_a_duplicate_check_is_rejected():
    duplicated = (_ALL_PASSING[0],) + _ALL_PASSING
    with pytest.raises(ValueError, match="each check once"):
        GroundingResult(checks=duplicated)


def test_an_unknown_check_cannot_stand_in_for_a_fixed_one():
    # Four results, but one repeated in place of a required check: still not the fixed set.
    substituted = _ALL_PASSING[:3] + (_ALL_PASSING[0],)
    with pytest.raises(ValueError, match="exactly the four fixed checks"):
        GroundingResult(checks=substituted)


def test_all_four_passing_is_a_passing_result():
    result = GroundingResult(checks=_ALL_PASSING)
    assert result.passed is True
    assert result.failures == ()


def test_one_failure_fails_the_whole_result():
    checks = _failing(
        _ALL_PASSING, CheckName.RECOMMENDATION_PROVENANCE_PRESENCE, "no provenance category"
    )
    result = GroundingResult(checks=checks)

    assert result.passed is False
    assert [f.check for f in result.failures] == [CheckName.RECOMMENDATION_PROVENANCE_PRESENCE]


def test_failures_names_every_check_that_failed_not_just_the_first():
    checks = _failing(_ALL_PASSING, CheckName.REFERENCE_RESOLUTION, "unresolved")
    checks = _failing(checks, CheckName.REQUIRED_LIMITATION_DISCLOSURE, "limitation omitted")
    result = GroundingResult(checks=checks)

    assert {f.check for f in result.failures} == {
        CheckName.REFERENCE_RESOLUTION,
        CheckName.REQUIRED_LIMITATION_DISCLOSURE,
    }
