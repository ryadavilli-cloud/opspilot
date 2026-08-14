"""get_incident — look up a single incident record by id.

Navigational: the entry point of an investigation. A known-error incident links to its postmortem
(`past_incident:<id>`); an unknown id is an empty (not error) result.
"""

from __future__ import annotations

from typing import Any

from opspilot.data.operational_records import OperationalRecords
from opspilot.tools.contracts import GetIncidentRequest, IncidentRecord, ToolResult
from opspilot.tools.errors import run_tool


def get_incident(
    records: OperationalRecords, *, deadline_s: float, **kwargs: Any
) -> ToolResult[IncidentRecord]:
    def logic(req: GetIncidentRequest) -> tuple[list[IncidentRecord], list[str]]:
        raw = records.incident(req.incident_id, deadline_s=deadline_s)
        if raw is None:
            return [], []
        rec = IncidentRecord(**raw)
        refs = [f"past_incident:{rec.incident_id}"] if rec.is_known_error else []
        return [rec], refs

    return run_tool("get_incident", GetIncidentRequest, logic, **kwargs)
