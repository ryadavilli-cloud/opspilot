"""get_deployments — deploys for the given services within a time window ("what changed").

Evidence-bearing: each returned deploy yields a `deploys:<service>:<deploy_id>` ref in the frozen
grammar, so the result resolves against the answer key. Sorted deterministically by time; malformed
rows are skipped.

The service set narrows the read at the source, because service is a partition level. The window
narrows it here, because a time bound is value semantics rather than partitioning and this is the
one place the validated parameters are interpreted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from opspilot.data.operational_records import OperationalRecords
from opspilot.tools.contracts import (
    MAX_WINDOW_DAYS,
    DeploymentRecord,
    NonEmptyText,
    check_window,
    to_utc,
)
from opspilot.tools.errors import validated


@validated
def get_deployments(
    records: OperationalRecords,
    deadline_s: float,
    *,
    services: Annotated[list[NonEmptyText], Field(min_length=1)],
    start_time: datetime,
    end_time: datetime,
) -> tuple[list[DeploymentRecord], list[str]]:
    start, end = to_utc(start_time), to_utc(end_time)
    check_window(start, end, max_days=MAX_WINDOW_DAYS)

    recs: list[DeploymentRecord] = []
    for raw in records.deployments(services, deadline_s=deadline_s):
        try:
            rec = DeploymentRecord(**raw)
        except Exception:  # noqa: BLE001 - skip malformed rows
            continue
        if not (start <= to_utc(rec.ts) <= end):
            continue
        recs.append(rec)
    recs.sort(key=lambda r: (to_utc(r.ts), r.deploy_id))
    return recs, [f"deploys:{r.service}:{r.deploy_id}" for r in recs]
