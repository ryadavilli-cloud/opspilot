"""The normalized incident context: what an investigation is allowed to know before it starts.

Four fields, and the omissions are the point. The raw incident record carries the answer the
investigation exists to find (`root_cause`, `resolution`) and ticket-workflow bookkeeping that says
nothing about the system; neither reaches an agent through here. Evidence does not either: it
enters only through admission, never through intake.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from opspilot.tools.contracts import IncidentRecord


class NormalizedIncidentContext(BaseModel):
    """The typed, frozen context one investigation is framed by."""

    model_config = ConfigDict(frozen=True)

    incident_id: str
    scope: str | None = None
    symptom: str
    time_anchor: datetime


def from_predefined_incident(incident: IncidentRecord) -> NormalizedIncidentContext:
    """Build the normalized context for the selected incident.

    `scope` stays `None` unless the incident names one. `IncidentRecord` carries no affected
    service or component, only `category`, and a classification label is not a component identity:
    populating `scope` from it would leak the category as an answer hint.
    """
    return NormalizedIncidentContext(
        incident_id=incident.incident_id,
        scope=None,
        symptom=incident.short_description,
        time_anchor=incident.opened_at,
    )
