"""The in-memory Investigation Record backend.

This is the local and CI backend, and it stays that way. A durable backend replaces what sits
behind the port, never the port, its commit semantics, or the ordering rule.

It is deliberately strict about the two things the design makes invariant rather than incidental: a
terminal turn is never reopened, so committing the same turn twice is refused rather than
overwriting; and the investigation exists only once a turn has been committed into it, so nothing
creates a shell in advance.
"""

from __future__ import annotations

from collections.abc import Sequence

from opspilot.record.port import CommitResult, CompletedTurn


class InMemoryInvestigationRecord:
    """One logical investigation record with subordinate completed turns, held in process.

    Ephemeral by construction, which matches what it is for: active-turn state is not durable, and
    only completed turns are stored at all.
    """

    def __init__(self) -> None:
        self._turns: dict[str, dict[str, CompletedTurn]] = {}

    def commit(self, record: CompletedTurn) -> CommitResult:
        investigation_id = record.investigation_id
        turn_id = record.turn_id

        if not investigation_id or not turn_id:
            return CommitResult.failed(
                investigation_id, turn_id, "a completed turn needs both identities"
            )

        turns = self._turns.get(investigation_id)
        if turns is not None and turn_id in turns:
            # A terminal turn is never reopened and a delivered brief is never edited, so a second
            # commit of the same turn is refused rather than silently replacing the first.
            return CommitResult.failed(investigation_id, turn_id, "turn already committed")

        # The investigation comes into existence here, on the first successful commit, and not
        # before: a failed first execution must leave no shell behind.
        self._turns.setdefault(investigation_id, {})[turn_id] = record
        return CommitResult.committed(investigation_id, turn_id)

    def completed_turns(self, investigation_id: str) -> Sequence[CompletedTurn]:
        return tuple(self._turns.get(investigation_id, {}).values())

    def turn(self, investigation_id: str, turn_id: str) -> CompletedTurn | None:
        return self._turns.get(investigation_id, {}).get(turn_id)

    def has_investigation(self, investigation_id: str) -> bool:
        return investigation_id in self._turns
