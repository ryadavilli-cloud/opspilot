"""What the turn attempted, kept apart from what it observed.

The two answer different questions. The admitted evidence set reads as "what was observed" with
no filtering; refusals, timeouts, and unreachable sources stay visible here and in the limitations
a brief must disclose. Keeping them in one collection would force every reader to filter, and a
reader that forgot would treat an unreachable source as an observation.

An operation reference is opaque and turn-scoped. It names an attempt, not an observation, so it
deliberately carries no source semantics and does not parallel the evidence-reference grammar:
`evidence/references.py` owns that, and a reader must never be able to mistake one for the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opspilot.tools.contracts import Completeness, ExecutionOutcome

_OPERATION_PREFIX = "op-"


@dataclass(frozen=True)
class OperationRecord:
    """One attempted capability call. Preserved whether or not it answered."""

    operation_ref: str
    capability: str
    outcome: ExecutionOutcome
    completeness: Completeness
    duration_ms: float
    admitted: bool = False
    scope: str = ""


class OperationLedger:
    """The turn's operation history. Ephemeral while the turn runs, like everything else a turn
    holds before commit."""

    def __init__(self) -> None:
        self._counter = count(1)
        self._records: list[OperationRecord] = []

    def mint(self) -> str:
        """A fresh operation reference, unique within this turn and meaningful nowhere else."""
        return f"{_OPERATION_PREFIX}{next(self._counter):04d}"

    def record(self, record: OperationRecord) -> OperationRecord:
        self._records.append(record)
        return record

    @property
    def records(self) -> tuple[OperationRecord, ...]:
        return tuple(self._records)

    def __len__(self) -> int:
        return len(self._records)


def is_operation_ref(value: str) -> bool:
    """Whether a string is an operation reference. Used to keep the two identifier spaces from
    being confused at a boundary that accepts either."""
    return value.startswith(_OPERATION_PREFIX)


@dataclass
class TurnEvidence:
    """The turn's ephemeral evidence state: what was admitted, what could not be established, and
    the ledger of what was attempted."""

    investigation_id: str
    turn_id: str
    ledger: OperationLedger = field(default_factory=OperationLedger)
    observations: list = field(default_factory=list)
    limitations: list = field(default_factory=list)

    @property
    def admitted_refs(self) -> list[str]:
        return [obs.evidence_ref for obs in self.observations]
