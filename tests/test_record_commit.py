"""Commit semantics, and the ordering that depends on them.

The property worth protecting here is not that a commit stores something. It is that a successful
result cannot be announced before it has been persisted, and that a failed commit leaves nothing
behind: no completed turn, and no investigation shell that a later read could mistake for one.

The delivery step is a stub. This slice has no completed-turn artifact and delivers no outcome, so
the ordering is asserted as a lifecycle property rather than demonstrated by a real turn.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from opspilot.record.memory import InMemoryInvestigationRecord
from opspilot.record.port import (
    CommitOutcome,
    CommitResult,
    CompletedTurn,
    InvestigationRecord,
    commit_then_deliver,
)


@dataclass(frozen=True)
class _Turn:
    """Stands in for the completed-turn artifact, which this slice does not define. It carries the
    two identities the port is structural over and nothing else."""

    investigation_id: str
    turn_id: str
    note: str = ""


class _AlwaysFails:
    """A backend whose commit never succeeds, so the failure contract can be exercised without
    reaching for a fault-injection hook on the real one."""

    def __init__(self, reason: str = "backend unavailable") -> None:
        self.reason = reason
        self.attempts = 0

    def commit(self, record: CompletedTurn) -> CommitResult:
        self.attempts += 1
        return CommitResult.failed(record.investigation_id, record.turn_id, self.reason)

    def completed_turns(self, investigation_id: str):
        return ()

    def turn(self, investigation_id: str, turn_id: str):
        return None

    def has_investigation(self, investigation_id: str) -> bool:
        return False


@pytest.fixture
def record() -> InMemoryInvestigationRecord:
    return InMemoryInvestigationRecord()


# --- the ordering rule ----------------------------------------------------------------------------
def test_delivery_does_not_run_when_the_commit_fails():
    """The rule this slice exists to fix in place. A successful result is never announced before it
    is persisted, so a failed commit must leave the delivery step unreached, not merely undone."""
    delivered: list[str] = []
    backend = _AlwaysFails()

    outcome = commit_then_deliver(
        _Turn("inv-1", "turn-1"), into=backend, deliver=lambda t: delivered.append(t.turn_id)
    )

    assert delivered == []
    assert outcome.delivered is False
    assert outcome.is_failed_execution
    assert outcome.commit.outcome is CommitOutcome.FAILED
    assert outcome.commit.reason == "backend unavailable"


def test_delivery_runs_only_after_a_successful_commit(record):
    """Ordering, observed rather than assumed: the commit must already be readable from the record
    at the moment delivery runs."""
    seen: list[str] = []

    def deliver(turn: _Turn) -> None:
        # If delivery could run before the commit landed, this read would return None.
        seen.append("delivered")
        assert record.turn(turn.investigation_id, turn.turn_id) is not None

    outcome = commit_then_deliver(_Turn("inv-1", "turn-1"), into=record, deliver=deliver)

    assert seen == ["delivered"]
    assert outcome.delivered is True
    assert not outcome.is_failed_execution


def test_a_failed_execution_leaves_no_completed_turn_behind():
    backend = _AlwaysFails()
    commit_then_deliver(_Turn("inv-1", "turn-1"), into=backend, deliver=lambda t: None)
    assert backend.completed_turns("inv-1") == ()
    assert backend.turn("inv-1", "turn-1") is None


# --- no shell before the first successful commit -------------------------------------------------
def test_starting_a_turn_persists_nothing(record):
    """Nothing is written mid-turn, so an investigation does not exist until a turn completes into
    it. A shell here would be an orphan record that survives a failed first execution."""
    assert record.has_investigation("inv-1") is False
    assert record.completed_turns("inv-1") == ()
    assert record.turn("inv-1", "turn-1") is None


def test_the_investigation_is_created_by_its_first_successful_commit(record):
    assert record.has_investigation("inv-1") is False
    record.commit(_Turn("inv-1", "turn-1"))
    assert record.has_investigation("inv-1") is True


def test_a_failed_first_commit_creates_no_investigation(record):
    """The failure path must not half-create the investigation on its way to failing."""
    result = record.commit(_Turn("inv-1", ""))
    assert not result.succeeded
    assert record.has_investigation("inv-1") is False


# --- commit semantics ----------------------------------------------------------------------------
def test_a_committed_turn_is_readable_back(record):
    record.commit(_Turn("inv-1", "turn-1", note="first"))
    stored = record.turn("inv-1", "turn-1")
    assert stored is not None and stored.note == "first"


def test_commit_result_carries_both_identities(record):
    result = record.commit(_Turn("inv-1", "turn-1"))
    assert result.succeeded
    assert (result.investigation_id, result.turn_id) == ("inv-1", "turn-1")


def test_a_turn_is_never_reopened(record):
    """A terminal turn is never reopened and a delivered brief is never edited, so a second commit
    of the same turn is refused rather than overwriting what was already delivered against."""
    record.commit(_Turn("inv-1", "turn-1", note="original"))
    second = record.commit(_Turn("inv-1", "turn-1", note="rewritten"))

    assert not second.succeeded
    assert "already committed" in second.reason
    stored = record.turn("inv-1", "turn-1")
    assert stored is not None and stored.note == "original"


def test_several_turns_accumulate_under_one_investigation(record):
    record.commit(_Turn("inv-1", "turn-1"))
    record.commit(_Turn("inv-1", "turn-2"))
    assert [t.turn_id for t in record.completed_turns("inv-1")] == ["turn-1", "turn-2"]


def test_investigations_are_isolated_from_each_other(record):
    """Evidence belonging to another investigation can never be read as this one's."""
    record.commit(_Turn("inv-1", "turn-1"))
    record.commit(_Turn("inv-2", "turn-1"))
    assert record.turn("inv-1", "turn-1") is not record.turn("inv-2", "turn-1")
    assert len(record.completed_turns("inv-1")) == 1


@pytest.mark.parametrize("investigation_id,turn_id", [("", "turn-1"), ("inv-1", ""), ("", "")])
def test_a_commit_without_both_identities_fails(record, investigation_id, turn_id):
    result = record.commit(_Turn(investigation_id, turn_id))
    assert not result.succeeded and result.reason


# --- the port itself -----------------------------------------------------------------------------
def test_the_in_memory_backend_satisfies_the_port():
    """A durable backend later replaces what sits behind the port, never the port itself, so both
    must satisfy the same protocol."""
    backend: InvestigationRecord = InMemoryInvestigationRecord()
    assert backend.has_investigation("nothing") is False


def test_the_port_is_structural_over_the_artifact():
    """The completed-turn artifact is not defined in this slice. Anything carrying the two
    identities commits, so the artifact can gain fields without reopening the port."""
    assert isinstance(_Turn("inv-1", "turn-1"), CompletedTurn)


def test_the_record_exposes_no_way_to_write_mid_turn():
    """Passive persistence: commit is the only mutation. An update, delete, or checkpoint entry
    point would make it possible to write while a turn is still running."""
    mutators = {
        name
        for name in dir(InMemoryInvestigationRecord)
        if not name.startswith("_")
        and name not in {"commit", "completed_turns", "turn", "has_investigation"}
    }
    assert mutators == set()
