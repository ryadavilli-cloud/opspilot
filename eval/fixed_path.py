"""The control condition: the same tools, in a predetermined order, whatever the run observes.

This is what the adaptive path is compared against. Which step comes next is decided by how many
steps have already been taken and by nothing else: not by what an observation said, not by whether
a source held anything, not by whether the incident looks like a deployment regression or a
saturation. That is the whole point of the control, so the order is a list here rather than
anything that could branch.

Arguments are bound from what the run already admitted, which is not the same as choosing. A step
that needs a service name reads the one the alerts named, because a script that queried logs for a
hardcoded service would be testing the corpus rather than the path. The step it is on never moves.

It makes no model call. The proposal is the thing being replaced, so a run on this path spends
model calls only on synthesis and any correction, and its record says so rather than counting calls
that were never made.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from opspilot.investigation.agents import ProposedAction

# The order, fixed. An incident, what else fired with it, then the alerting service's logs and
# metrics, then whether anything shipped, then what it depends on.
ORDER = (
    "get_incident",
    "get_correlated_alerts",
    "query_logs",
    "get_metrics",
    "get_deployments",
    "get_service_dependencies",
)

WINDOW = timedelta(minutes=30)
DEPLOY_WINDOW = timedelta(hours=24)


def _alerting_service(evidence: Any, fallback: str) -> str:
    """The service the admitted alerts named, or the incident's own scope where none did.

    Binding a parameter, not choosing a step. The script asks for this service's logs whether or
    not any alert was admitted, and whether or not the logs turn out to hold anything.
    """
    for observation in evidence.observations:
        if observation.evidence_ref.startswith("alert:"):
            service = getattr(observation.observation, "service", None) or (
                observation.observation.get("service")
                if isinstance(observation.observation, dict)
                else None
            )
            if service:
                return str(service)
    return fallback


def fixed_path(
    model: Any,
    incident: Any,
    objective: str,
    evidence: Any,
    knowledge: Any,
    capabilities: tuple[str, ...],
    calls_left: int,
    open_question: str = "",
    deadline_s: float | None = None,
) -> tuple[ProposedAction, None]:
    """One step of the script, in the shape the investigator's own proposal has.

    Takes and returns exactly what `propose_action` does, minus the model call, so authorization,
    bounds, execution, and admission all treat this run exactly as they treat an adaptive one.
    """
    step = len(evidence.operations)
    if step >= len(ORDER):
        return ProposedAction(
            finished_because="the fixed path has issued every step it holds"
        ), None

    capability = ORDER[step]
    incident_id = str(getattr(incident, "incident_id", ""))
    anchor = getattr(incident, "time_anchor", None)
    scope = str(getattr(incident, "scope", "") or "")
    service = _alerting_service(evidence, scope)

    arguments: dict[str, Any] = {}
    if capability == "get_incident":
        arguments = {"incident_id": incident_id}
    elif capability == "get_correlated_alerts":
        arguments = {"incident_id": incident_id}
    elif capability in ("query_logs", "get_metrics"):
        arguments = {"service": service}
        if anchor is not None:
            arguments |= {"start_time": anchor - WINDOW, "end_time": anchor + WINDOW}
    elif capability == "get_deployments":
        arguments = {"services": [service] if service else []}
        if anchor is not None:
            arguments |= {"start_time": anchor - DEPLOY_WINDOW, "end_time": anchor + WINDOW}
    elif capability == "get_service_dependencies":
        arguments = {"service": service} if service else {}

    return ProposedAction(
        capability=capability,
        arguments=arguments,
        question=f"step {step + 1} of the fixed path: {capability}",
    ), None
