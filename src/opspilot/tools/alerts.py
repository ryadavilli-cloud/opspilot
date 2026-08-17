"""get_correlated_alerts — the alert storm for an incident.

Returns every alert correlated to the incident (root_cause, symptoms, the trigger), optionally
filtered to a time window, sorted deterministically by fire time. Malformed rows are skipped, not
fatal.

Evidence-bearing: each alert yields `alert:<service>:<alert_id>`. An alert is an observation of the
running system at a moment, so it is citable like a log line or a deploy, and the services it names
are also what scopes the calls that follow it.
"""

from __future__ import annotations

from datetime import datetime

from opspilot.data.operational_records import OperationalRecords
from opspilot.tools.contracts import AlertRecord, NonEmptyText, check_window, to_utc
from opspilot.tools.errors import validated


@validated
def get_correlated_alerts(
    records: OperationalRecords,
    deadline_s: float,
    *,
    incident_id: NonEmptyText,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[list[AlertRecord], list[str]]:
    start = to_utc(start_time) if start_time else None
    end = to_utc(end_time) if end_time else None
    check_window(start, end)

    recs: list[AlertRecord] = []
    for raw in records.alerts_for(incident_id, deadline_s=deadline_s):
        try:
            rec = AlertRecord(**raw)
        except Exception:  # noqa: BLE001 - skip malformed rows, don't fail the query
            continue
        fired = to_utc(rec.fired_at)
        if (start and fired < start) or (end and fired > end):
            continue
        recs.append(rec)
    recs.sort(key=lambda r: (to_utc(r.fired_at), r.alert_id))
    return recs, [f"alert:{r.service}:{r.alert_id}" for r in recs]
