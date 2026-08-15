"""What the four grounding checks produce.

`data-and-evidence.md` §13 fixes the four checks; `workflow-design.md` §7 fixes when the gate runs
and how a failure routes. This module carries only the result shape those checks report against:
which check failed and why. It does not implement a check, run the gate, or decide the correction
routing that reads this result; that is `grounding/checks.py`.

The check set is fixed at four (`code-guidelines.md` §14: "adding, removing, or reconfiguring a
grounding check" is prohibited). `GroundingResult` enforces that at construction rather than
leaving it to a caller's discipline, so a gate that ran three checks or ran one twice cannot be
represented, let alone reported as a passing result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CheckName(StrEnum):
    """The four grounding checks. `data-and-evidence.md` §13 names and defines each; the names
    here are that section's own headings, so a reader can find a check's definition by its name."""

    REFERENCE_RESOLUTION = "reference_resolution"
    UNSUPPORTED_ELEMENT_REJECTION = "unsupported_element_rejection"
    RECOMMENDATION_PROVENANCE_PRESENCE = "recommendation_provenance_presence"
    REQUIRED_LIMITATION_DISCLOSURE = "required_limitation_disclosure"


@dataclass(frozen=True)
class CheckResult:
    """One check's verdict. `reason` names what failed, so a failure is diagnosable from the
    result alone rather than by re-running the check; it is empty when the check passed."""

    check: CheckName
    passed: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if self.passed and self.reason:
            raise ValueError("a passing check carries no failure reason")
        if not self.passed and not self.reason:
            raise ValueError("a failed check must name why")


@dataclass(frozen=True)
class GroundingResult:
    """All four checks' verdicts for one proposed brief.

    Passes only when every check passed. Naming which check failed, not just that the gate failed
    as a whole, is what diagnosability and the correction path both need: the gate routes
    differently depending on whether a structural failure or a grounding failure reached it.
    """

    checks: tuple[CheckResult, ...]

    def __post_init__(self) -> None:
        names = [result.check for result in self.checks]
        if set(names) != set(CheckName):
            raise ValueError("a grounding result must carry exactly the four fixed checks")
        if len(names) != len(set(names)):
            raise ValueError("a grounding result carries each check once")

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.checks)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self.checks if not result.passed)
