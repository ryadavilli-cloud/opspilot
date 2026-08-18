"""The in-process record backend.

The local and test backend, and it stays that way. A durable backend replaces what sits behind the
seam, never the seam or the ordering rule that depends on it.

Strict about the one thing the design makes invariant rather than incidental: an investigation is
saved once, so a second save of the same identifier is refused rather than overwriting the first.
"""

from __future__ import annotations

from opspilot.record.completed import CompletedInvestigation
from opspilot.record.port import RecordSaveError


class InMemoryInvestigationRecord:
    """Completed investigations held in process, keyed by their identifier.

    Ephemeral by construction, which matches what it is for: nothing is stored until an
    investigation completes, and nothing survives the process.
    """

    def __init__(self) -> None:
        self._records: dict[str, CompletedInvestigation] = {}

    def save(self, record: CompletedInvestigation) -> None:
        if not record.investigation_id:
            raise RecordSaveError("a completed investigation needs an identifier")
        if record.investigation_id in self._records:
            raise RecordSaveError(f"{record.investigation_id} is already saved")
        self._records[record.investigation_id] = record

    def get(self, investigation_id: str) -> CompletedInvestigation | None:
        return self._records.get(investigation_id)
