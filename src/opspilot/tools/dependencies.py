"""get_service_dependencies — the dependency graph, optionally filtered to one service/direction.

Evidence-bearing: each edge yields `deps:<from>-><to>`. Used to reason about blast radius —
which services a failure can propagate to (downstream) or arrive from (upstream).

An edge names its own relationship kind, and the container's first partition level is also called
`kind`. Preparation therefore carries the edge's kind as `dependency_kind`, and this is the one
place that maps it back onto the record. See `scripts/prepare_corpus.py`.
"""

from __future__ import annotations

from typing import Any, Literal

from opspilot.data.operational_records import OperationalRecords
from opspilot.tools.contracts import DependencyEdge
from opspilot.tools.errors import validated


def _matches(edge: DependencyEdge, service: str, direction: str) -> bool:
    if direction == "downstream":
        return edge.from_service == service
    if direction == "upstream":
        return edge.to_service == service
    return service in (edge.from_service, edge.to_service)


def _edge(raw: dict[str, Any]) -> DependencyEdge:
    return DependencyEdge(
        **{
            "from": raw.get("from"),
            "to": raw.get("to"),
            "kind": raw.get("dependency_kind"),
            "critical": raw.get("critical", False),
        }
    )


@validated
def get_service_dependencies(
    records: OperationalRecords,
    deadline_s: float,
    *,
    service: str | None = None,  # None -> the whole graph
    direction: Literal["upstream", "downstream", "both"] = "both",
) -> tuple[list[DependencyEdge], list[str]]:
    recs: list[DependencyEdge] = []
    for raw in records.edges(deadline_s=deadline_s):
        try:
            edge = _edge(raw)
        except Exception:  # noqa: BLE001 - skip malformed rows
            continue
        if service and not _matches(edge, service, direction):
            continue
        recs.append(edge)
    recs.sort(key=lambda e: (e.from_service, e.to_service))
    return recs, [f"deps:{e.from_service}->{e.to_service}" for e in recs]
