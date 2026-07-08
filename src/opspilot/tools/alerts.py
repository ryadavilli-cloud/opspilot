"""get_correlated_alerts — the alert storm for an incident.

Returns every alert correlated to the incident (root_cause, symptoms, the trigger), optionally
filtered to a time window, sorted deterministically by fire time. Malformed rows are skipped, not
fatal. Alerts are not part of the evidence grammar, so `evidence_refs` is empty — this tool is
navigational: its results give the caller the affected services and timeframe to query next.
"""

from __future__ import annotations

from opspilot.data.repository import Repository
from opspilot.tools.contracts import AlertRecord, GetCorrelatedAlertsRequest, ToolResult, to_utc
from opspilot.tools.errors import run_tool


def get_correlated_alerts(repo: Repository, **kwargs) -> ToolResult[AlertRecord]:
    def logic(req: GetCorrelatedAlertsRequest) -> tuple[list[AlertRecord], list[str]]:
        start = to_utc(req.start_time) if req.start_time else None
        end = to_utc(req.end_time) if req.end_time else None
        recs: list[AlertRecord] = []
        for raw in repo.alerts_for_incident(req.incident_id):
            try:
                rec = AlertRecord(**raw)
            except Exception:  # noqa: BLE001 — skip malformed rows, don't fail the query
                continue
            fired = to_utc(rec.fired_at)
            if (start and fired < start) or (end and fired > end):
                continue
            recs.append(rec)
        recs.sort(key=lambda r: (to_utc(r.fired_at), r.alert_id))
        return recs, []

    return run_tool("get_correlated_alerts", GetCorrelatedAlertsRequest, logic, **kwargs)
