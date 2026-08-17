"""The investigation's evidence set: what was observed, what could not be, and what was attempted.

The three answer different questions and are kept apart. The admitted observations read as "what
was observed" with no filtering; refusals, timeouts, and unreachable sources stay visible in the
limitations a brief must disclose and in the operations list. Holding them in one collection would
force every reader to filter, and a reader that forgot would treat an unreachable source as an
observation.

An operation reference is opaque and scoped to the investigation. It names an attempt, not an
observation, so it deliberately carries no source semantics and does not parallel the evidence
reference grammar: `evidence/references.py` owns that, and a reader must never be able to mistake
one for the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opspilot.evidence.admission import AdmittedObservation, Limitation
    from opspilot.tools.contracts import ExecutionOutcome

_OPERATION_PREFIX = "op-"


@dataclass(frozen=True)
class Operation:
    """One attempted capability call: its identifier, what it called, and how it ended.

    Preserved whether or not it answered, and carrying nothing else. Its arguments and its raw
    result are not part of what an investigation records about itself.
    """

    operation_ref: str
    capability: str
    outcome: ExecutionOutcome


def is_operation_ref(value: str) -> bool:
    """Whether a string is an operation reference. Used to keep the two identifier spaces from
    being confused at a boundary that accepts either."""
    return value.startswith(_OPERATION_PREFIX)


@dataclass
class EvidenceSet:
    """The investigation's evidence while it runs: what was admitted, what could not be
    established, and every operation attempted. Ephemeral, like everything an investigation holds
    before it completes."""

    investigation_id: str
    observations: list[AdmittedObservation] = field(default_factory=list)
    limitations: list[Limitation] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)

    def next_operation_ref(self) -> str:
        """The reference the next operation will carry. Derived from the operations already
        recorded, so a minted reference and a recorded operation cannot drift apart."""
        return f"{_OPERATION_PREFIX}{len(self.operations) + 1:04d}"

    @property
    def admitted_refs(self) -> list[str]:
        return [obs.evidence_ref for obs in self.observations]
