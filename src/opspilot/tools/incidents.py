"""get_incident — look up a single incident record by id.

Navigational: the entry point of an investigation. A known-error incident links to its postmortem
(`past_incident:<id>`); an unknown id is an empty (not error) result.
"""

from __future__ import annotations

from opspilot.data.repository import Repository
from opspilot.tools.contracts import GetIncidentRequest, IncidentRecord, ToolResult
from opspilot.tools.errors import run_tool


def get_incident(repo: Repository, **kwargs) -> ToolResult[IncidentRecord]:
    def logic(req: GetIncidentRequest) -> tuple[list[IncidentRecord], list[str]]:
        raw = repo.incident(req.incident_id)
        if raw is None:
            return [], []
        rec = IncidentRecord(**raw)
        refs = [f"past_incident:{rec.incident_id}"] if rec.is_known_error else []
        return [rec], refs

    return run_tool("get_incident", GetIncidentRequest, logic, **kwargs)
