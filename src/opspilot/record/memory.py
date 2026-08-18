"""The in-memory Investigation Record backend: the local and CI store.

It holds each record as the document it would be written as, and revalidates on read, rather than
handing back the object it was given. That is deliberate. A store that returns the caller's own
object proves nothing about whether the record survives being stored, so a field that cannot make
the round trip would pass here and fail against Cosmos. Normalizing the same way both backends do
makes the two behave identically, which is what lets one set of tests speak for both.
"""

from __future__ import annotations

from typing import Any

from opspilot.record.completed import CompletedInvestigation
from opspilot.record.port import AlreadySaved


class InMemoryCompletedInvestigations:
    """Completed investigations held in process, keyed by investigation identity.

    Ephemeral by construction, which matches what it is for: only completed investigations are
    stored at all, and nothing here is expected to outlive the process.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def save(self, record: CompletedInvestigation) -> None:
        if record.investigation_id in self._records:
            raise AlreadySaved(record.investigation_id)
        self._records[record.investigation_id] = record.model_dump(mode="json")

    def get(self, investigation_id: str) -> CompletedInvestigation | None:
        document = self._records.get(investigation_id)
        if document is None:
            return None
        return CompletedInvestigation.model_validate(document)
