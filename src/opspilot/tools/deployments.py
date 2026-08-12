"""get_deployments — deploys for the given services within a time window ("what changed").

Evidence-bearing: each returned deploy yields a `deploys:<service>:<deploy_id>` ref in the frozen
grammar, so the result resolves against the answer key. Sorted deterministically by time; malformed
rows are skipped.

The service set narrows the read at the source, because service is a partition level. The window
narrows it here, because a time bound is value semantics rather than partitioning and this is the
one place the request's validated parameters are interpreted.
"""

from __future__ import annotations

from opspilot.data.operational_records import OperationalRecords
from opspilot.tools.contracts import DeploymentRecord, GetDeploymentsRequest, ToolResult, to_utc
from opspilot.tools.errors import run_tool


def get_deployments(
    records: OperationalRecords, *, deadline_s: float, **kwargs
) -> ToolResult[DeploymentRecord]:
    def logic(req: GetDeploymentsRequest) -> tuple[list[DeploymentRecord], list[str]]:
        start, end = to_utc(req.start_time), to_utc(req.end_time)
        recs: list[DeploymentRecord] = []
        for raw in records.deployments(req.services, deadline_s=deadline_s):
            try:
                rec = DeploymentRecord(**raw)
            except Exception:  # noqa: BLE001 — skip malformed rows
                continue
            if not (start <= to_utc(rec.ts) <= end):
                continue
            recs.append(rec)
        recs.sort(key=lambda r: (to_utc(r.ts), r.deploy_id))
        refs = [f"deploys:{r.service}:{r.deploy_id}" for r in recs]
        return recs, refs

    return run_tool("get_deployments", GetDeploymentsRequest, logic, **kwargs)
