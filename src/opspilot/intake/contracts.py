"""Normalized incident-context contract (D-007) and request-shape interaction kind.

D-007 fixes the normalized incident-context contract to exactly five fields, deliberately excluding
the raw `IncidentRecord`'s answer-key content (`root_cause`, `resolution`) and ticket-workflow
fields, and excluding any evidence reference (evidence exists only through deterministic admission,
never through intake, see `system-design.md` §4.3's Evidence Investigator contract). This shape is
authored to its final accepted form now; a later free-text producer adds to it without reshaping it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from opspilot.tools.contracts import IncidentRecord

# Exactly five interaction kinds (system-design.md §4.1); only the type is introduced here. Later
# engineer input is classified into these by request shape or explicit interface action, never by
# a model call (D-002); the classifier itself is later work.
InteractionKind = Literal["question", "redirect", "supplied_evidence", "stop", "handoff_summary"]


class NormalizedIncidentContext(BaseModel):
    """The typed, frozen normalized-input contract (D-007). Shared by both intake paths."""

    model_config = ConfigDict(frozen=True)

    incident_id: str | None = None
    scope: str | None = None
    symptom: str
    time_anchor: datetime
    supplied_context: str | None = None


def from_predefined_incident(incident: IncidentRecord) -> NormalizedIncidentContext:
    """Build the normalized context for the predefined-intake path.

    `scope` stays `None`: `IncidentRecord` carries no affected-service or component field, only
    `category`, and D-007 forbids populating `scope` from `category` (a classification label is not
    a component identity, and doing so risks leaking the category as an answer hint). `symptom` and
    `time_anchor` come from the corpus record; `root_cause`/`resolution` and the ticket-workflow
    fields are never read here.
    """
    return NormalizedIncidentContext(
        incident_id=incident.incident_id,
        scope=None,
        symptom=incident.short_description,
        time_anchor=incident.opened_at,
        supplied_context=None,
    )
