"""query_logs — log search over a service and optional time window / level / substring.

Evidence-bearing: each returned row yields `logs:<service>:<event_id>`. The signal events are
returned alongside the noise floor for that service/window — separating them is the agent's job,
not the tool's.

The service narrows the read at the source; window, level, and substring narrow it here, where the
validated parameters are interpreted.
"""

from __future__ import annotations

from datetime import datetime

from opspilot.data.operational_records import OperationalRecords
from opspilot.tools.contracts import LogRecord, NonEmptyText, check_window, to_utc
from opspilot.tools.errors import validated


@validated
def query_logs(
    records: OperationalRecords,
    deadline_s: float,
    *,
    service: NonEmptyText,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    level: str | None = None,
    contains: str | None = None,
) -> tuple[list[LogRecord], list[str]]:
    """What a service logged: the errors and messages it emitted over a window you name."""
    start = to_utc(start_time) if start_time else None
    end = to_utc(end_time) if end_time else None
    check_window(start, end)

    want_level = level.lower() if level else None
    needle = contains.lower() if contains else None
    recs: list[LogRecord] = []
    for raw in records.logs(service, deadline_s=deadline_s):
        try:
            rec = LogRecord(**raw)
        except Exception:  # noqa: BLE001 - skip malformed rows
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
    return recs, [f"logs:{r.service}:{r.event_id}" for r in recs]
