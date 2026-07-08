"""get_deployments — deploys for the given services within a time window ("what changed").

Evidence-bearing: each returned deploy yields a `deploys:<service>:<deploy_id>` ref in the frozen
grammar, so the result resolves against the answer key. Sorted deterministically by time; malformed
rows are skipped.
"""

from __future__ import annotations

from opspilot.data.repository import Repository
from opspilot.tools.contracts import DeploymentRecord, GetDeploymentsRequest, ToolResult, to_utc
from opspilot.tools.errors import run_tool


def get_deployments(repo: Repository, **kwargs) -> ToolResult[DeploymentRecord]:
    def logic(req: GetDeploymentsRequest) -> tuple[list[DeploymentRecord], list[str]]:
        services = set(req.services)
        start, end = to_utc(req.start_time), to_utc(req.end_time)
        recs: list[DeploymentRecord] = []
        for raw in repo.deployments():
            try:
                rec = DeploymentRecord(**raw)
            except Exception:  # noqa: BLE001 — skip malformed rows
                continue
            if rec.service not in services:
                continue
            if not (start <= to_utc(rec.ts) <= end):
                continue
            recs.append(rec)
        recs.sort(key=lambda r: (to_utc(r.ts), r.deploy_id))
        refs = [f"deploys:{r.service}:{r.deploy_id}" for r in recs]
        return recs, refs

    return run_tool("get_deployments", GetDeploymentsRequest, logic, **kwargs)
