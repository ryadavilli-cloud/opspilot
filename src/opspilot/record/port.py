"""The Investigation Record seam: save one completed investigation, read it back by identifier,
and list what has been saved.

The record is passive. It stores the completed artifact and answers reads. It routes no workflow,
decides nothing, synthesizes nothing, validates no grounding, and never holds a partial run.

Three operations and no more. Nothing is written while an investigation is still running, so an
interrupted run leaves nothing behind, and the investigation comes into existence with its one
successful save rather than as a shell created in advance. Listing returns summaries rather than
records, because a listing is read to choose one, and each choice is then read in full.

A second save of the same identifier is refused rather than accepted. One completed record per
investigation is an invariant, not a convention: a delivered brief is never edited and a terminal
outcome is never reopened, so overwriting would quietly replace an account someone may already have
read. The refusal raises, because a caller that ignores a returned status would otherwise carry on
believing it had stored something.
"""

from __future__ import annotations

from typing import Protocol

from opspilot.record.completed import CompletedInvestigation, InvestigationSummary


class AlreadySaved(Exception):
    """A completed investigation was saved twice under one identifier.

    Raised by every backend, so the invariant reads the same whichever one is behind the seam.
    """

    def __init__(self, investigation_id: str) -> None:
        super().__init__(f"investigation {investigation_id!r} is already saved")
        self.investigation_id = investigation_id


class CompletedInvestigationRepository(Protocol):
    """Passive persistence. Every backend satisfies exactly this, and adding one changes nothing
    about when a record may be written."""

    def save(self, record: CompletedInvestigation) -> None:
        """Persist one completed investigation. Raises `AlreadySaved` if the identifier is taken."""
        ...

    def get(self, investigation_id: str) -> CompletedInvestigation | None:
        """The saved investigation, or None where nothing was ever saved under that identifier."""
        ...

    def list_investigations(self) -> list[InvestigationSummary]:
        """Every completed investigation as a summary, newest first."""
        ...
