"""The Investigation Record port, and the one ordering rule that depends on it.

The record is passive. It stores completed artifacts and answers reads. It routes no workflow,
decides nothing, synthesizes nothing, validates no grounding, and is never a mid-turn checkpoint.
Nothing is written while a turn is still running, so an interrupted turn leaves nothing behind.

**Persistence precedes delivery.** A successful result is never announced before it has been
persisted. Where the commit fails, no successful outcome is emitted, no completed turn exists, and
the attempt is a failed execution. `commit_then_deliver` is where that ordering lives, and it takes
delivery as a callable rather than performing it: the port supplies commit semantics and does not
own delivery.

The investigation is created by the first successful commit. Starting a turn persists nothing, so a
first execution that fails leaves no investigation shell and no orphan records.

What is committed is the completed-turn artifact, which this module deliberately does not define.
The port is structural over anything carrying an investigation and turn identity, so the artifact
can gain its remaining fields without reopening the port, its commit semantics, or this ordering.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class CommitOutcome(StrEnum):
    COMMITTED = "committed"
    FAILED = "failed"


@runtime_checkable
class CompletedTurn(Protocol):
    """The minimum a committed artifact carries. Structural on purpose: the completed-turn
    artifact is defined elsewhere and gains fields without this port changing."""

    @property
    def investigation_id(self) -> str: ...

    @property
    def turn_id(self) -> str: ...


@dataclass(frozen=True)
class CommitResult:
    """Whether the artifact was persisted. A failure carries a sanitized reason so a persistence
    problem is never indistinguishable from a grounding or model problem."""

    outcome: CommitOutcome
    investigation_id: str
    turn_id: str
    reason: str = ""

    @property
    def succeeded(self) -> bool:
        return self.outcome is CommitOutcome.COMMITTED

    @classmethod
    def committed(cls, investigation_id: str, turn_id: str) -> CommitResult:
        return cls(CommitOutcome.COMMITTED, investigation_id, turn_id)

    @classmethod
    def failed(cls, investigation_id: str, turn_id: str, reason: str) -> CommitResult:
        return cls(CommitOutcome.FAILED, investigation_id, turn_id, reason)


class InvestigationRecord(Protocol):
    """Passive persistence. Every backend satisfies exactly this, and adding a backend never
    changes the ordering rule below."""

    def commit(self, record: CompletedTurn) -> CommitResult:
        """Persist one completed turn. Never called mid-turn, and never by more than one writer."""
        ...

    def completed_turns(self, investigation_id: str) -> Sequence[CompletedTurn]:
        """Every committed turn for an investigation, in commit order."""
        ...

    def turn(self, investigation_id: str, turn_id: str) -> CompletedTurn | None: ...

    def has_investigation(self, investigation_id: str) -> bool:
        """Whether any turn has ever been committed for this investigation. False before the first
        successful commit, which is what "no investigation shell" means."""
        ...


@dataclass(frozen=True)
class DeliveryOutcome:
    """What the ordering produced: either the commit succeeded and delivery ran, or it did not and
    the attempt is a failed execution that left no completed turn behind."""

    commit: CommitResult
    delivered: bool

    @property
    def is_failed_execution(self) -> bool:
        return not self.commit.succeeded


def commit_then_deliver[T: CompletedTurn](
    record: T,
    *,
    into: InvestigationRecord,
    deliver: Callable[[T], None],
) -> DeliveryOutcome:
    """Commit, and deliver only if that commit succeeded.

    The single place this ordering is expressed. A caller cannot deliver first by accident, and a
    caller that ignores the returned result still cannot have delivered on a failed commit, because
    delivery is unreachable on that path rather than merely discouraged.
    """
    result = into.commit(record)
    if not result.succeeded:
        return DeliveryOutcome(commit=result, delivered=False)
    deliver(record)
    return DeliveryOutcome(commit=result, delivered=True)
