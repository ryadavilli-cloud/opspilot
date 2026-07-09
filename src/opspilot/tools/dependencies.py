"""get_service_dependencies — the dependency graph, optionally filtered to one service/direction.

Evidence-bearing: each edge yields `deps:<from>-><to>`. Used to reason about blast radius —
which services a failure can propagate to (downstream) or arrive from (upstream).
"""

from __future__ import annotations

from opspilot.data.repository import Repository
from opspilot.tools.contracts import DependencyEdge, GetServiceDependenciesRequest, ToolResult
from opspilot.tools.errors import run_tool


def _matches(edge: DependencyEdge, service: str, direction: str) -> bool:
    if direction == "downstream":
        return edge.from_service == service
    if direction == "upstream":
        return edge.to_service == service
    return service in (edge.from_service, edge.to_service)


def get_service_dependencies(repo: Repository, **kwargs) -> ToolResult[DependencyEdge]:
    def logic(req: GetServiceDependenciesRequest) -> tuple[list[DependencyEdge], list[str]]:
        recs: list[DependencyEdge] = []
        for raw in repo.edges():
            try:
                edge = DependencyEdge(**raw)
            except Exception:  # noqa: BLE001 — skip malformed rows
                continue
            if req.service and not _matches(edge, req.service, req.direction):
                continue
            recs.append(edge)
        recs.sort(key=lambda e: (e.from_service, e.to_service))
        refs = [f"deps:{e.from_service}->{e.to_service}" for e in recs]
        return recs, refs

    return run_tool("get_service_dependencies", GetServiceDependenciesRequest, logic, **kwargs)
