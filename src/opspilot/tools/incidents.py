"""get_incident — look up a single incident record by id.

Navigational: the entry point of an investigation. An unknown id is an empty (not error) result,
because the source answered authoritatively.

What it returns is narrower than what it read. The stored row carries the corpus's own answers, so
this admits the incident only in the fields the approved structured-query surface exposes: the same
record read two ways yields the same fields, and `root_cause`, `resolution`, `close_code`, and the
free-text description never leave this adapter. The row is parsed through `IncidentRecord` first so
the projected values are typed rather than whatever the container happened to store.
"""

from __future__ import annotations

from typing import Any

from opspilot.data.operational_records import OperationalRecords
from opspilot.data.structured_query import APPROVED_SURFACE
from opspilot.tools.contracts import IncidentRecord, NonEmptyText
from opspilot.tools.errors import validated

_ADMITTED_FIELDS = tuple(APPROVED_SURFACE["incident"])


@validated
def get_incident(
    records: OperationalRecords,
    deadline_s: float,
    *,
    incident_id: NonEmptyText,
) -> tuple[list[dict[str, Any]], list[str]]:
    raw = records.incident(incident_id, deadline_s=deadline_s)
    if raw is None:
        return [], []
    record = IncidentRecord(**raw)
    row = {name: getattr(record, name) for name in _ADMITTED_FIELDS}
    return [row], [f"incident:{record.incident_id}"]
