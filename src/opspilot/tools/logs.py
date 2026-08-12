"""query_logs — log search over a service and optional time window / level / substring.

Evidence-bearing: each returned row yields `logs:<service>:<event_id>`. The signal events are
returned alongside the noise floor for that service/window — separating them is the agent's job,
not the tool's.

The service narrows the read at the source; window, level, and substring narrow it here, where the
request's validated parameters are interpreted.
"""

from __future__ import annotations

from opspilot.data.operational_records import OperationalRecords
from opspilot.tools.contracts import GetLogsRequest, LogRecord, ToolResult, to_utc
from opspilot.tools.errors import run_tool


def query_logs(
    records: OperationalRecords, *, deadline_s: float, **kwargs
) -> ToolResult[LogRecord]:
    def logic(req: GetLogsRequest) -> tuple[list[LogRecord], list[str]]:
        start = to_utc(req.start_time) if req.start_time else None
        end = to_utc(req.end_time) if req.end_time else None
        want_level = req.level.lower() if req.level else None
        needle = req.contains.lower() if req.contains else None
        recs: list[LogRecord] = []
        for raw in records.logs(req.service, deadline_s=deadline_s):
            try:
                rec = LogRecord(**raw)
            except Exception:  # noqa: BLE001 — skip malformed rows
                continue
            t = to_utc(rec.ts)
            if (start and t < start) or (end and t > end):
                continue
            if want_level and rec.level.lower() != want_level:
                continue
            if needle and needle not in rec.message.lower():
                continue
            recs.append(rec)
        recs.sort(key=lambda r: (to_utc(r.ts), r.event_id))
        refs = [f"logs:{r.service}:{r.event_id}" for r in recs]
        return recs, refs

    return run_tool("query_logs", GetLogsRequest, logic, **kwargs)
