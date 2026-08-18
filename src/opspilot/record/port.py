"""The record seam: save one completed investigation, read one back.

The record is passive. It stores a completed artifact and answers reads. It routes no workflow,
decides nothing, synthesizes nothing, validates no grounding, and is never a mid-run checkpoint.
Nothing is written while an investigation is still running, so an abandoned run leaves nothing
behind and no shell to clean up.

Saving precedes delivery, and a failed save is a failed execution rather than a brief delivered
without a record behind it. `save` raises instead of returning a status: an ordering rule expressed
as a return value is one a caller can ignore by forgetting to read it, and delivering a brief whose
record was never written is exactly the failure this seam exists to prevent.

A second save of the same identifier is refused. One investigation is one run and one record, so a
repeat is a defect somewhere upstream, and overwriting would destroy the first account of it.
"""

from __future__ import annotations

from typing import Protocol

from opspilot.record.completed import CompletedInvestigation


class RecordSaveError(RuntimeError):
    """A completed investigation could not be persisted. Carries a sanitized reason, so a
    persistence problem is never indistinguishable from a grounding or model one."""


class InvestigationRecord(Protocol):
    """Passive persistence. Every backend satisfies exactly this."""

    def save(self, record: CompletedInvestigation) -> None:
        """Persist one completed investigation, or raise `RecordSaveError`."""
        ...

    def get(self, investigation_id: str) -> CompletedInvestigation | None:
        """The completed investigation, or None where none was ever saved."""
        ...
